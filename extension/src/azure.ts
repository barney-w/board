import { execFile } from 'child_process';
import { BoardConfig, getResourceGroup, getVmName } from './config';

export type VmPowerState =
  | 'running'
  | 'starting'
  | 'stopped'
  | 'deallocated'
  | 'deallocating'
  | 'unknown';

export interface VmStatus {
  powerState: VmPowerState;
  ipAddress?: string;
  fqdn?: string;
  vmSize?: string;
}

/* ------------------------------------------------------------------ */
/*  Internals                                                          */
/* ------------------------------------------------------------------ */

/** Cached result of `isAzCliAvailable()` — checked once per session */
let azCliAvailableCache: boolean | undefined;

/** Default timeout for az commands (ms) */
const AZ_TIMEOUT_MS = 30_000;

interface AzResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * Run an Azure CLI command and capture the output.
 * Never throws — returns exitCode 1 + stderr on failure.
 */
async function runAzCommand(args: string[]): Promise<AzResult> {
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: `${process.env.PATH || ''}:/opt/homebrew/bin:/usr/local/bin` };
    execFile('az', args, { timeout: AZ_TIMEOUT_MS, env }, (error, stdout, stderr) => {
      if (error) {
        // `error.code` may be the exit code (number) or a Node error string
        const rawCode = (error as NodeJS.ErrnoException).code;
        const exitCode = typeof rawCode === 'string' ? 1 : (rawCode as unknown as number) ?? 1;
        resolve({
          stdout: stdout ?? '',
          stderr: stderr ?? error.message,
          exitCode,
        });
        return;
      }
      resolve({ stdout: stdout ?? '', stderr: stderr ?? '', exitCode: 0 });
    });
  });
}

/** Map the display string from Azure to our enum */
function parsePowerState(display: string | undefined | null): VmPowerState {
  switch (display) {
    case 'VM running':
      return 'running';
    case 'VM starting':
      return 'starting';
    case 'VM stopped':
      return 'stopped';
    case 'VM deallocated':
      return 'deallocated';
    case 'VM deallocating':
      return 'deallocating';
    default:
      return 'unknown';
  }
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * Check whether the Azure CLI (`az`) is installed and available on PATH.
 * The result is cached for the lifetime of the extension host process.
 */
export async function isAzCliAvailable(): Promise<boolean> {
  if (azCliAvailableCache !== undefined) {
    return azCliAvailableCache;
  }

  const { exitCode } = await runAzCommand(['version', '--output', 'json']);
  azCliAvailableCache = exitCode === 0;
  return azCliAvailableCache;
}

/**
 * Fetch the current VM power state, public IP, FQDN, and size.
 * Returns `{ powerState: 'unknown' }` on any failure — never throws.
 */
export async function getVmStatus(config: BoardConfig): Promise<VmStatus> {
  const rg = getResourceGroup(config);
  const vmName = getVmName(config);

  const jmesQuery = [
    '{',
    "powerState:instanceView.statuses[?starts_with(code, `PowerState/`)].displayStatus | [0],",
    'ip:publicIps,',
    'fqdn:fqdns,',
    'vmSize:hardwareProfile.vmSize',
    '}',
  ].join('');

  const { stdout, exitCode } = await runAzCommand([
    'vm',
    'get-instance-view',
    '--resource-group',
    rg,
    '--name',
    vmName,
    '--query',
    jmesQuery,
    '--output',
    'json',
  ]);

  if (exitCode !== 0) {
    return { powerState: 'unknown' };
  }

  try {
    const data = JSON.parse(stdout) as {
      powerState?: string;
      ip?: string;
      fqdn?: string;
      vmSize?: string;
    };

    return {
      powerState: parsePowerState(data.powerState),
      ipAddress: data.ip || undefined,
      fqdn: data.fqdn || undefined,
      vmSize: data.vmSize || undefined,
    };
  } catch {
    return { powerState: 'unknown' };
  }
}

/**
 * Start the VM. Uses `--no-wait` so it returns immediately while Azure
 * boots the machine in the background.
 */
export async function startVm(config: BoardConfig): Promise<void> {
  const rg = getResourceGroup(config);
  const vmName = getVmName(config);

  const { exitCode, stderr } = await runAzCommand([
    'vm',
    'start',
    '--resource-group',
    rg,
    '--name',
    vmName,
    '--no-wait',
  ]);

  if (exitCode !== 0) {
    throw new Error(`Failed to start VM: ${stderr}`);
  }
}

/**
 * Deallocate (stop + release compute) the VM. Uses `--no-wait` so it
 * returns immediately.
 */
export async function stopVm(config: BoardConfig): Promise<void> {
  const rg = getResourceGroup(config);
  const vmName = getVmName(config);

  const { exitCode, stderr } = await runAzCommand([
    'vm',
    'deallocate',
    '--resource-group',
    rg,
    '--name',
    vmName,
    '--no-wait',
  ]);

  if (exitCode !== 0) {
    throw new Error(`Failed to stop VM: ${stderr}`);
  }
}
