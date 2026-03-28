import * as vscode from 'vscode';
import { getConfig, isConfigured, getSshHostAlias, getPortalUrl } from './config';
import { writeSshConfig } from './ssh';
import { connect } from './connection';
import { importBundle } from './bundle';
import { StatusBar } from './statusBar';
import { isAzCliAvailable, startVm, stopVm } from './azure';
import { PollingService } from './polling';
import { VmStatusProvider, QuickActionsProvider } from './sidebar';
import { runSetupScript, handleFirstRun } from './firstRun';
import { showWelcomePanel } from './welcome';

/* ------------------------------------------------------------------ */
/*  Developer name validation                                          */
/* ------------------------------------------------------------------ */

/** Validate developer name: lowercase, alphanumeric, 1-12 chars, starts with letter */
function validateDeveloperName(value: string): string | undefined {
  if (!value) {
    return 'Developer name is required';
  }
  if (!/^[a-z]/.test(value)) {
    return 'Must start with a lowercase letter';
  }
  if (!/^[a-z][a-z0-9]*$/.test(value)) {
    return 'Only lowercase letters and numbers are allowed';
  }
  if (value.length > 12) {
    return 'Maximum 12 characters';
  }
  return undefined;
}

/* ------------------------------------------------------------------ */
/*  Activation                                                         */
/* ------------------------------------------------------------------ */

export function activate(context: vscode.ExtensionContext): void {
  // Output channel
  const outputChannel = vscode.window.createOutputChannel('Board');
  context.subscriptions.push(outputChannel);

  // Status bar
  const statusBar = new StatusBar();
  context.subscriptions.push(statusBar);

  // Polling service
  const pollingService = new PollingService(
    getConfig().pollIntervalSeconds * 1000,
  );
  context.subscriptions.push(pollingService);

  // ---- Tree-view providers ----
  const vmStatusProvider = new VmStatusProvider();
  const quickActionsProvider = new QuickActionsProvider();
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('board.vmStatus', vmStatusProvider),
  );
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      'board.quickActions',
      quickActionsProvider,
    ),
  );

  // Refresh tree views with initial (no-data) state
  vmStatusProvider.refresh(undefined);
  quickActionsProvider.refresh(undefined);

  // Update status bar and tree views whenever VM status changes
  context.subscriptions.push(
    pollingService.onDidChangeStatus((status) => {
      statusBar.update(status.powerState);
      vmStatusProvider.refresh(status);
      quickActionsProvider.refresh(status);
    }),
  );

  // Update status bar tooltip when health data changes
  context.subscriptions.push(
    pollingService.onDidChangeHealth((healthLines) => {
      statusBar.updateHealth(healthLines);
    }),
  );

  // Initial status: if configured + az available, do an initial poll;
  // otherwise fall back to simple configured/not-configured
  if (isConfigured()) {
    isAzCliAvailable().then((available) => {
      if (available) {
        pollingService.start();
        pollingService.pollNow().catch((err) => {
          console.error('[Board] Initial poll failed:', err);
        });
      } else {
        // No az CLI — show a generic "running" icon (configured but can't poll)
        statusBar.update('running');
      }
    });
  } else {
    statusBar.update('not-configured');
  }

  // Restart polling when pollIntervalSeconds setting changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('board.pollIntervalSeconds')) {
        const newInterval = getConfig().pollIntervalSeconds * 1000;
        pollingService.setInterval(newInterval);
      }
    }),
  );

  // ---- board.configure ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.configure', async () => {
      // 1. Prompt for developer name
      const developerName = await vscode.window.showInputBox({
        title: 'Developer Name',
        prompt:
          'Enter your developer name (lowercase, alphanumeric, 1-12 chars)',
        placeHolder: 'e.g. jbloggs',
        value: getConfig().developerName || undefined,
        validateInput: validateDeveloperName,
      });
      if (developerName === undefined) {
        return; // User cancelled
      }

      // 2. Prompt for environment
      const environment = await vscode.window.showQuickPick(
        ['personal', 'sandbox'],
        {
          title: 'Environment',
          placeHolder: 'Select Azure environment',
        },
      );
      if (environment === undefined) {
        return; // User cancelled
      }

      // 3. Prompt for auth method
      const authMethod = await vscode.window.showQuickPick(
        ['ssh-key', 'entra-id'],
        {
          title: 'Authentication Method',
          placeHolder: 'Select SSH authentication method',
        },
      );
      if (authMethod === undefined) {
        return; // User cancelled
      }

      // 4. Save to global settings
      const cfg = vscode.workspace.getConfiguration('board');
      await cfg.update(
        'developerName',
        developerName,
        vscode.ConfigurationTarget.Global,
      );
      await cfg.update(
        'environment',
        environment,
        vscode.ConfigurationTarget.Global,
      );
      await cfg.update(
        'authMethod',
        authMethod,
        vscode.ConfigurationTarget.Global,
      );

      // 5. Auto-write SSH config
      const config = getConfig();
      await writeSshConfig(config);

      // 6. Update status bar, start polling, and show completion
      outputChannel.appendLine(
        `Configured: ${developerName} / ${environment} / ${authMethod}`,
      );
      vscode.window.showInformationMessage(
        `Board configured for "${developerName}". SSH config written.`,
      );

      // Refresh tree views now that configuration has changed
      vmStatusProvider.refresh(undefined);
      quickActionsProvider.refresh(undefined);

      // Start polling now that we're configured
      isAzCliAvailable().then((available) => {
        if (available) {
          pollingService.start();
          pollingService.pollNow().catch((err) => {
            console.error('[Board] Post-configure poll failed:', err);
          });
        } else {
          statusBar.update('running');
        }
      });
    }),
  );

  // ---- board.connect ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.connect', async () => {
      await connect(context);
      // Post-connect sentinel check (async, non-blocking)
      if (isConfigured()) {
        setTimeout(() => {
          handleFirstRun(getConfig(), context).catch(err => {
            console.error('[Board] First-run check failed:', err);
          });
        }, 5000);
      }
    }),
  );

  // ---- board.openTerminal ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.openTerminal', () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage(
          'Board is not configured. Run "Board: Configure Connection" first.',
        );
        return;
      }
      const config = getConfig();
      const terminal = vscode.window.createTerminal({
        name: 'Board',
        shellPath: 'ssh',
        shellArgs: [getSshHostAlias(config)],
        iconPath: new vscode.ThemeIcon('vm-running'),
      });
      terminal.show();
    }),
  );

  // ---- Azure CLI availability check (async, non-blocking) ----
  const azCliInstallUrl = 'https://aka.ms/installazurecli';

  /** Show a helpful error when az CLI is missing and return true if unavailable */
  async function ensureAzCli(): Promise<boolean> {
    const available = await isAzCliAvailable();
    if (!available) {
      const action = await vscode.window.showErrorMessage(
        'Azure CLI is not installed. Install it from https://aka.ms/installazurecli',
        'Learn More',
      );
      if (action === 'Learn More') {
        vscode.env.openExternal(vscode.Uri.parse(azCliInstallUrl));
      }
      return false;
    }
    return true;
  }

  // Fire-and-forget: log a warning if az is not on PATH
  isAzCliAvailable().then((available) => {
    if (!available) {
      outputChannel.appendLine(
        'WARNING: Azure CLI (az) not found on PATH. VM lifecycle commands will not work.',
      );
    }
  });


  // ---- board.start ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.start', async () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage(
          'Board is not configured. Run "Board: Configure Connection" first.',
        );
        return;
      }
      if (!(await ensureAzCli())) {
        return;
      }
      const config = getConfig();
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Starting Board VM...',
        },
        async () => {
          await startVm(config);
        },
      );
      vscode.window.showInformationMessage('Board VM start initiated.');
      pollingService.pollNow().catch((err) => {
        console.error('[Board] Poll after start failed:', err);
      });
    }),
  );

  // ---- board.stop ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.stop', async () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage(
          'Board is not configured. Run "Board: Configure Connection" first.',
        );
        return;
      }
      if (!(await ensureAzCli())) {
        return;
      }
      const answer = await vscode.window.showWarningMessage(
        'Stop your Board VM? This will deallocate it (no compute charges).',
        { modal: true },
        'Stop',
      );
      if (answer !== 'Stop') {
        return;
      }
      const config = getConfig();
      await stopVm(config);
      vscode.window.showInformationMessage('Board VM stop initiated.');
      pollingService.pollNow().catch((err) => {
        console.error('[Board] Poll after stop failed:', err);
      });
    }),
  );

  // ---- board.importPass ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.importPass', async (uri?: vscode.Uri) => {
      await importBundle(context, uri);
    }),
  );

  // ---- File open handler for .board-pass files ----
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.uri.fsPath.endsWith('.board-pass') || doc.uri.fsPath.endsWith('.devvm-bundle')) {
        vscode.commands.executeCommand('board.importPass', doc.uri);
      }
    }),
  );

  // ---- board.runSetup ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.runSetup', () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage('Board is not configured.');
        return;
      }
      runSetupScript(getConfig());
    }),
  );

  // ---- board.openPortal ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.openPortal', () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage('Configure Board first.');
        return;
      }
      const config = getConfig();
      vscode.env.openExternal(vscode.Uri.parse(getPortalUrl(config)));
    }),
  );

  // ---- Show welcome panel for first-time users ----
  const config = getConfig();
  if (!config.developerName) {
    showWelcomePanel(context);
  }

  outputChannel.appendLine('Board extension activated');
}

export function deactivate(): void {
  // Nothing to clean up
}
