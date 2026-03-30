import * as vscode from 'vscode';
import { getConfig, isConfigured, getSshHostAlias, getHostname, getResourceGroup, getVmName, getPortalUrl } from './config';
import { writeSshConfig } from './ssh';
import { connect } from './connection';
import { importBundle, BundlePayload } from './bundle';
import { showBoardPassCard } from './boardPassCard';
import { BoardPassEditorProvider } from './boardPassEditor';
import { StatusBar } from './statusBar';
import { BoardTerminalProfileProvider, openWorkspaceTerminals } from './terminal';
import { isAzCliAvailable, startVm, stopVm } from './azure';
import { PollingService } from './polling';
import { VmStatusProvider, QuickActionsProvider, CheatsheetProvider } from './sidebar';
import { runSetupScript, handleFirstRun } from './firstRun';
import { showWelcomePanel } from './welcome';
import { showCheatsheet } from './cheatsheet';

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
  const cheatsheetProvider = new CheatsheetProvider();
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('board.vmStatus', vmStatusProvider),
  );
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      'board.quickActions',
      quickActionsProvider,
    ),
  );
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('board.cheatsheet', cheatsheetProvider),
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

  // ---- board.openWorkspace ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.openWorkspace', async () => {
      await openWorkspaceTerminals();
    }),
  );

  // ---- board.cheatsheet ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.cheatsheet', () => {
      showCheatsheet(context);
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

  // ---- Custom editor for .board-pass files ----
  // Renders the board pass card directly in the editor tab instead of raw JSON.
  context.subscriptions.push(
    vscode.window.registerCustomEditorProvider(
      BoardPassEditorProvider.viewType,
      new BoardPassEditorProvider(context),
      { supportsMultipleEditorsPerDocument: false },
    ),
  );

  // ---- Fallback: text-document handler for .board-pass files ----
  // If the custom editor doesn't activate (e.g. fresh install, extension host
  // hasn't reloaded, user chose "Open With > Text"), this catches the file
  // opened as raw text and shows the card / triggers import anyway.
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (!doc.uri.fsPath.endsWith('.board-pass') && !doc.uri.fsPath.endsWith('.devvm-bundle')) {
        return;
      }
      const uri = doc.uri;

      // Close the raw text editor tab (encrypted JSON is meaningless)
      setTimeout(() => {
        for (const group of vscode.window.tabGroups.all) {
          for (const tab of group.tabs) {
            if (tab.input instanceof vscode.TabInputText &&
                tab.input.uri.toString() === uri.toString()) {
              vscode.window.tabGroups.close(tab);
            }
          }
        }
      }, 200);

      if (isConfigured()) {
        const cfg = getConfig();
        const payload: BundlePayload = {
          developerName: cfg.developerName,
          environment: cfg.environment,
          region: cfg.region,
          regionShort: cfg.regionShort,
          hostname: getHostname(cfg),
          username: 'devuser',
          authMethod: cfg.authMethod,
          sshPrivateKey: '',
          sshPublicKey: '',
          resourceGroup: getResourceGroup(cfg),
          vmName: getVmName(cfg),
        };
        showBoardPassCard(context, payload);
      } else {
        vscode.commands.executeCommand('board.importPass', uri);
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

  // ---- board.openCodeServer ----
  context.subscriptions.push(
    vscode.commands.registerCommand('board.openCodeServer', async () => {
      if (!isConfigured()) {
        vscode.window.showWarningMessage('Configure Board first.');
        return;
      }
      const config = getConfig();
      const hostAlias = getSshHostAlias(config);

      // Open SSH tunnel in a terminal
      const terminal = vscode.window.createTerminal({
        name: 'code-server tunnel',
        shellPath: 'ssh',
        shellArgs: ['-L', '8080:localhost:8080', '-N', hostAlias],
        iconPath: new vscode.ThemeIcon('globe'),
      });
      terminal.show();

      // Wait briefly for tunnel to establish, then open browser
      setTimeout(() => {
        vscode.env.openExternal(vscode.Uri.parse('http://localhost:8080'));
      }, 2000);

      // No password needed — code-server uses auth:none (SSH tunnel is the auth)
    }),
  );

  // ---- Terminal profile provider ----
  const terminalProvider = new BoardTerminalProfileProvider();
  context.subscriptions.push(
    vscode.window.registerTerminalProfileProvider(
      'board.terminalProfile',
      terminalProvider,
    ),
  );

  // ---- Show welcome panel for first-time users ----
  const config = getConfig();
  if (!config.developerName) {
    showWelcomePanel(context);
  }

  // ---- Remote SSH session: show board pass card + auto-open terminals ----
  if (vscode.env.remoteName === 'ssh-remote' && isConfigured()) {
    // Show the board pass card so the user sees their credentials on the remote side
    const cfg = getConfig();
    const remotePayload: BundlePayload = {
      developerName: cfg.developerName,
      environment: cfg.environment,
      region: cfg.region,
      regionShort: cfg.regionShort,
      hostname: getHostname(cfg),
      username: 'devuser',
      authMethod: cfg.authMethod,
      sshPrivateKey: '',
      sshPublicKey: '',
      resourceGroup: getResourceGroup(cfg),
      vmName: getVmName(cfg),
    };
    showBoardPassCard(context, remotePayload);

    if (config.autoOpenTerminals) {
      outputChannel.appendLine(
        `Remote SSH session detected — opening workspace terminals (existing: ${vscode.window.terminals.length})`,
      );
      // Delay to let the remote window settle before opening terminals
      setTimeout(() => {
        openWorkspaceTerminals().catch((err) => {
          outputChannel.appendLine(`Failed to open workspace terminals: ${err}`);
        });
      }, 3000);
    }
  } else {
    outputChannel.appendLine(
      `Terminal auto-open skipped: remoteName=${vscode.env.remoteName}, configured=${isConfigured()}, autoOpen=${config.autoOpenTerminals}`,
    );
  }

  outputChannel.appendLine('Board extension activated');
}

export function deactivate(): void {
  // Nothing to clean up
}
