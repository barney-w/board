import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { BoardConfig, getSshHostAlias } from './config';

const execFileAsync = promisify(execFile);

/** Check sentinel files on the remote VM via SSH command.
 *  Returns { cloudInitComplete: boolean, setupComplete: boolean } */
export async function checkRemoteSentinels(config: BoardConfig): Promise<{
  cloudInitComplete: boolean;
  setupComplete: boolean;
}> {
  const hostAlias = getSshHostAlias(config);
  try {
    const { stdout } = await execFileAsync('ssh', [
      '-o', 'ConnectTimeout=5',
      '-o', 'StrictHostKeyChecking=accept-new',
      hostAlias,
      'test -f ~/.cloud-init-complete && echo CLOUD_INIT_OK; test -f ~/.setup-me-complete && echo SETUP_OK',
    ], { timeout: 10000 });
    return {
      cloudInitComplete: stdout.includes('CLOUD_INIT_OK'),
      setupComplete: stdout.includes('SETUP_OK'),
    };
  } catch {
    return { cloudInitComplete: false, setupComplete: false };
  }
}

/** Show appropriate notification based on sentinel state */
export async function handleFirstRun(config: BoardConfig, context: vscode.ExtensionContext): Promise<void> {
  // Check one-time flag
  const key = `board.firstRunPromptShown.${config.developerName}`;
  if (context.globalState.get<boolean>(key)) {
    return;
  }

  const sentinels = await checkRemoteSentinels(config);

  if (!sentinels.cloudInitComplete) {
    const choice = await vscode.window.showInformationMessage(
      'Your VM is still being configured by cloud-init. Some tools may not be ready yet. This usually takes 5-8 minutes.',
      'Check Again',
    );
    if (choice === 'Check Again') {
      await handleFirstRun(config, context); // Recursive retry
    }
    return;
  }

  if (!sentinels.setupComplete) {
    const choice = await vscode.window.showInformationMessage(
      'This looks like your first time on this VM. Run first-time setup?',
      'Run Setup',
      'Skip',
    );
    if (choice === 'Run Setup') {
      runSetupScript(config);
    }
    // Mark as shown regardless of choice
    await context.globalState.update(key, true);
  }
}

/** Run setup-me.sh on the VM via an integrated terminal */
export function runSetupScript(config: BoardConfig): void {
  const terminal = vscode.window.createTerminal({
    name: 'Board Setup',
    shellPath: 'ssh',
    shellArgs: [getSshHostAlias(config), 'bash ~/setup-me.sh'],
    iconPath: new vscode.ThemeIcon('gear'),
  });
  terminal.show();
}
