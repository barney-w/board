import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';
import { VmStatus, VmPowerState, getVmStatus, isAzCliAvailable } from './azure';
import { getConfig, isConfigured, getSshHostAlias, getSshKeyPath } from './config';

const execAsync = promisify(exec);

/**
 * Run the project health-check script on the VM via SSH.
 * Returns parsed status lines (those containing check/cross marks).
 */
export async function checkProjectHealth(hostAlias: string, keyPath: string): Promise<string[]> {
  try {
    const { stdout } = await execAsync(
      `ssh -i "${keyPath}" -o ConnectTimeout=5 -o BatchMode=yes -o LogLevel=ERROR devuser@${hostAlias} "bash ~/projects/.board/check.sh 2>/dev/null"`,
      { timeout: 15000 },
    );
    // Parse check output into summary lines
    return stdout
      .split('\n')
      .filter(line => line.includes('\u2713') || line.includes('\u2717'))
      .map(line => line.trim());
  } catch {
    return [];
  }
}

export class PollingService implements vscode.Disposable {
  private timer: ReturnType<typeof setInterval> | undefined;
  private readonly _onStatusChange = new vscode.EventEmitter<VmStatus>();
  readonly onDidChangeStatus: vscode.Event<VmStatus> = this._onStatusChange.event;
  private lastState: VmPowerState | undefined;
  private paused = false;
  private windowStateDisposable: vscode.Disposable | undefined;

  /* Health-check caching */
  private lastHealthCheck: string[] = [];
  private lastHealthCheckTime = 0;
  private static readonly HEALTH_CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutes

  private readonly _onHealthChange = new vscode.EventEmitter<string[]>();
  readonly onDidChangeHealth: vscode.Event<string[]> = this._onHealthChange.event;

  constructor(private intervalMs: number) {
    // Pause when the VS Code window loses focus, resume on regain
    this.windowStateDisposable = vscode.window.onDidChangeWindowState((e) => {
      if (e.focused) {
        this.resume();
      } else {
        this.pause();
      }
    });
  }

  /** Start polling. No-op if already polling. */
  start(): void {
    if (this.timer) {
      return;
    }
    this.scheduleTimer();
  }

  /** Stop polling. */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  /** Force an immediate poll (resets the timer). */
  async pollNow(): Promise<VmStatus> {
    // Reset the timer so the next tick starts fresh from now
    this.stop();
    const status = await this.doPoll();
    // Restart the timer only if we haven't been explicitly stopped elsewhere
    // (i.e., we were polling before or the caller expects us to keep going)
    this.scheduleTimer();
    return status;
  }

  /** Pause polling (e.g., when window loses focus). */
  pause(): void {
    if (this.paused) {
      return;
    }
    this.paused = true;
    this.stop();
  }

  /** Resume polling. */
  resume(): void {
    if (!this.paused) {
      return;
    }
    this.paused = false;
    // Immediately poll on resume, then restart the interval
    this.pollNow().catch((err) => {
      console.error('[Board] Error on resume poll:', err);
    });
  }

  /** Update the polling interval (restarts timer if currently running). */
  setInterval(ms: number): void {
    this.intervalMs = ms;
    if (this.timer) {
      this.stop();
      this.scheduleTimer();
    }
  }

  dispose(): void {
    this.stop();
    this.windowStateDisposable?.dispose();
    this._onStatusChange.dispose();
    this._onHealthChange.dispose();
  }

  /* ------------------------------------------------------------------ */
  /*  Internals                                                          */
  /* ------------------------------------------------------------------ */

  private scheduleTimer(): void {
    this.timer = setInterval(() => {
      this.doPoll().catch((err) => {
        console.error('[Board] Poll error:', err);
      });
    }, this.intervalMs);
  }

  private async doPoll(): Promise<VmStatus> {
    if (!isConfigured()) {
      return { powerState: 'unknown' };
    }

    const azAvailable = await isAzCliAvailable();
    if (!azAvailable) {
      return { powerState: 'unknown' };
    }

    try {
      const config = getConfig();
      const status = await getVmStatus(config);

      if (status.powerState !== this.lastState) {
        this.lastState = status.powerState;
        this._onStatusChange.fire(status);
      }

      // Run health check when VM is running (cached, every 5 min)
      if (status.powerState === 'running') {
        const now = Date.now();
        if (now - this.lastHealthCheckTime >= PollingService.HEALTH_CHECK_INTERVAL) {
          this.lastHealthCheckTime = now;
          const hostAlias = getSshHostAlias(config);
          const keyPath = getSshKeyPath(config);
          // Fire-and-forget — don't block the poll cycle
          checkProjectHealth(hostAlias, keyPath)
            .then((lines) => {
              this.lastHealthCheck = lines;
              this._onHealthChange.fire(lines);
            })
            .catch((err) => {
              console.error('[Board] Health check failed:', err);
            });
        }
      } else {
        // VM not running — clear cached health data
        if (this.lastHealthCheck.length > 0) {
          this.lastHealthCheck = [];
          this.lastHealthCheckTime = 0;
          this._onHealthChange.fire([]);
        }
      }

      return status;
    } catch (err) {
      console.error('[Board] getVmStatus failed:', err);
      return { powerState: 'unknown' };
    }
  }
}
