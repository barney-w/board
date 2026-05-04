import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { getConfig, isConfigured, getSshHostAlias, getSshKeyPath } from './config';
import { writeSshConfig, sshKeyExists, writeSshKey, refreshEntraCerts } from './ssh';
import { isAzCliAvailable, getVmStatus, startVm, VmStatus } from './azure';

const execFileAsync = promisify(execFile);

/** Poll VM status until it is running or the timeout elapses. */
async function waitForRunning(
  token: vscode.CancellationToken,
  timeoutMs: number = 120_000,
  pollMs: number = 5_000,
): Promise<boolean> {
  const config = getConfig();
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (token.isCancellationRequested) {
      return false;
    }
    const status = await getVmStatus(config);
    if (status.powerState === 'running') {
      return true;
    }
    await new Promise((r) => setTimeout(r, pollMs));
  }
  return false;
}

/** Check whether the Azure CLI `ssh` extension is installed */
async function checkAzSshExtension(): Promise<boolean> {
  try {
    await execFileAsync('az', ['extension', 'show', '--name', 'ssh', '--output', 'json'], {
      timeout: 10_000,
    });
    return true;
  } catch {
    return false;
  }
}

/** Orchestrate the full connect flow */
export async function connect(context: vscode.ExtensionContext): Promise<void> {
  // 1. Check configuration
  const config = getConfig();
  if (!isConfigured()) {
    const choice = await vscode.window.showWarningMessage(
      'Board is not configured yet.',
      'Configure Now',
    );
    if (choice === 'Configure Now') {
      await vscode.commands.executeCommand('board.configure');
    }
    return;
  }

  // 2. Ensure SSH config exists (idempotent)
  await writeSshConfig(config);

  // 3. If ssh-key auth, verify the key exists
  if (config.authMethod === 'ssh-key') {
    let keyFound = await sshKeyExists(config);

    if (!keyFound) {
      // Try to restore from VS Code secret storage
      const storedKey = await context.secrets.get(
        `board.sshKey.${config.developerName}`,
      );
      if (storedKey) {
        await writeSshKey(getSshKeyPath(config), storedKey);
        keyFound = true;
      }
    }

    if (!keyFound) {
      const choice = await vscode.window.showErrorMessage(
        `SSH key not found at ~/.ssh/devvm-${config.developerName}.`,
        'Import Pass',
        'Dismiss',
      );
      if (choice === 'Import Pass') {
        await vscode.commands.executeCommand('board.importPass');
      }
      return;
    }
  }

  // 3b. If entra-id auth, verify Azure CLI + ssh extension are available
  if (config.authMethod === 'entra-id') {
    const azReady = await isAzCliAvailable();
    if (!azReady) {
      const choice = await vscode.window.showErrorMessage(
        'Azure CLI is required for Entra ID authentication.',
        'Learn More',
      );
      if (choice === 'Learn More') {
        vscode.env.openExternal(vscode.Uri.parse('https://aka.ms/installazurecli'));
      }
      return;
    }

    // Check for az ssh extension
    const sshExtInstalled = await checkAzSshExtension();
    if (!sshExtInstalled) {
      const choice = await vscode.window.showErrorMessage(
        'Azure CLI "ssh" extension is required for Entra ID auth.',
        'Install',
        'Cancel',
      );
      if (choice === 'Install') {
        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: 'Installing az ssh extension...',
          },
          async () => {
            try {
              await execFileAsync('az', ['extension', 'add', '--name', 'ssh'], {
                timeout: 60_000,
              });
            } catch {
              vscode.window.showErrorMessage('Failed to install az ssh extension.');
            }
          },
        );
      } else {
        return;
      }
    }

    // Refresh short-lived Entra ID certificates before connecting
    const certResult = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: 'Refreshing Entra ID certificates...',
      },
      async () => refreshEntraCerts(config),
    );
    if (!certResult.success) {
      const detail = (certResult.stderr || certResult.errorMessage || '').trim();
      const az = certResult.azPath || 'az';
      // Show the real az error so the user can act on it. Common causes:
      //   - "az login" required
      //   - az ssh extension missing (`az extension add --name ssh`)
      //   - VS Code launched without Homebrew on PATH so az isn't found
      //   - Wrong subscription / no RBAC on the VM
      const message = detail
        ? `Failed to refresh Entra ID certificates (${az}):\n${detail}`
        : `Failed to refresh Entra ID certificates. Ensure you are signed in with "az login" and the az ssh extension is installed.`;
      vscode.window.showErrorMessage(message, { modal: false });
      console.error('[Board] cert refresh failed', certResult);
      return;
    }

    // Re-write SSH config with the Entra user from the cert
    await writeSshConfig(config, certResult.entraUser);
  }

  // 4. Check VM state (only if az CLI is available — degrade gracefully)
  const azAvailable = await isAzCliAvailable();
  if (azAvailable) {
    const vmReady = await checkVmStateBeforeConnect(config);
    if (!vmReady) {
      return; // User cancelled or VM is unavailable
    }
  }

  // 5. Check Remote-SSH extension is installed
  const remoteSsh = vscode.extensions.getExtension(
    'ms-vscode-remote.remote-ssh',
  );
  if (!remoteSsh) {
    const choice = await vscode.window.showErrorMessage(
      'Remote-SSH extension is required to connect to the Board VM.',
      'Install',
    );
    if (choice === 'Install') {
      await vscode.commands.executeCommand(
        'workbench.extensions.installExtension',
        'ms-vscode-remote.remote-ssh',
      );
    }
    return;
  }

  // 6. Open the remote folder via Remote-SSH (replaces current window)
  const hostAlias = getSshHostAlias(config);
  await vscode.commands.executeCommand(
    'vscode.openFolder',
    vscode.Uri.parse(
      `vscode-remote://ssh-remote+${hostAlias}/home/devuser/projects`,
    ),
  );
}

/**
 * Check the VM power state and handle stopped / starting / deallocating VMs.
 * Returns true if connection should proceed, false to abort.
 */
async function checkVmStateBeforeConnect(
  config: import('./config').BoardConfig,
): Promise<boolean> {
  let status: VmStatus;
  try {
    status = await getVmStatus(config);
  } catch {
    // If we can't determine status, warn but allow connection attempt
    vscode.window.showWarningMessage(
      'Cannot determine VM status. Attempting connection anyway.',
    );
    return true;
  }

  switch (status.powerState) {
    case 'running':
      return true;

    case 'stopped':
    case 'deallocated': {
      if (config.autoStartVm) {
        const action = await vscode.window.showInformationMessage(
          'Your VM is stopped. Start it?',
          'Start',
          'Cancel',
        );
        if (action !== 'Start') {
          return false;
        }
        try {
          await startVm(config);
        } catch (err) {
          vscode.window.showErrorMessage(
            `Failed to start VM: ${err instanceof Error ? err.message : String(err)}`,
          );
          return false;
        }
        // Wait for VM to reach running state
        const started = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: 'Waiting for VM to start...',
            cancellable: true,
          },
          async (_progress, token) => waitForRunning(token),
        );
        if (!started) {
          vscode.window.showWarningMessage(
            'Timed out waiting for VM to start. Please try again later.',
          );
          return false;
        }
        return true;
      }
      // autoStartVm is false
      vscode.window.showInformationMessage(
        'Your VM is stopped. Start it with "Board: Start" before connecting.',
      );
      return false;
    }

    case 'starting': {
      const started = await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'VM is starting, please wait...',
          cancellable: true,
        },
        async (_progress, token) => waitForRunning(token),
      );
      if (!started) {
        vscode.window.showWarningMessage(
          'Timed out waiting for VM to start. Please try again later.',
        );
        return false;
      }
      return true;
    }

    case 'deallocating':
      vscode.window.showInformationMessage(
        'VM is stopping. Please try again later.',
      );
      return false;

    case 'unknown':
    default:
      vscode.window.showWarningMessage(
        'Cannot determine VM status. Attempting connection anyway.',
      );
      return true;
  }
}
