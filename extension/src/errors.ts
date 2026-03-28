import * as vscode from 'vscode';

export type ErrorScenario =
  | 'vm-stopped'
  | 'vm-starting'
  | 'ssh-refused'
  | 'host-key-changed'
  | 'ssh-key-missing'
  | 'no-az-cli'
  | 'cloud-init-running'
  | 'remote-ssh-missing';

export interface ErrorAction {
  label: string;
  command: string;
  args?: unknown[];
}

export interface ErrorInfo {
  message: string;
  detail?: string;
  actions: ErrorAction[];
}

/** Map an error scenario to user-friendly message and recovery actions */
export function getErrorInfo(scenario: ErrorScenario): ErrorInfo {
  switch (scenario) {
    case 'vm-stopped':
      return {
        message: 'Your VM is stopped.',
        actions: [{ label: 'Start VM', command: 'board.start' }],
      };
    case 'vm-starting':
      return {
        message: 'Starting up (~30s)...',
        detail: 'The VM is starting. It will be ready in about 30 seconds.',
        actions: [],
      };
    case 'ssh-refused':
      return {
        message: 'Cannot connect. VM may still be starting.',
        actions: [
          { label: 'Retry', command: 'board.connect' },
        ],
      };
    case 'host-key-changed':
      return {
        message: 'VM identity changed (normal after redeploy).',
        detail: 'The SSH host key has changed. This is expected after a VM redeploy.',
        actions: [{ label: 'Accept New Key', command: 'board.connect' }],
      };
    case 'ssh-key-missing':
      return {
        message: 'SSH key not found.',
        actions: [{ label: 'Import Pass', command: 'board.importPass' }],
      };
    case 'no-az-cli':
      return {
        message: 'Cannot manage VM without Azure CLI. Connection still works.',
        detail: 'Install from https://aka.ms/installazurecli',
        actions: [],
      };
    case 'cloud-init-running':
      return {
        message: 'VM still being configured (5-8 min).',
        actions: [],
      };
    case 'remote-ssh-missing':
      return {
        message: 'Remote-SSH extension is required.',
        actions: [{ label: 'Install', command: 'workbench.extensions.installExtension', args: ['ms-vscode-remote.remote-ssh'] }],
      };
  }
}

/** Show an error notification with action buttons */
export async function showError(scenario: ErrorScenario): Promise<void> {
  const info = getErrorInfo(scenario);
  const buttons = info.actions.map(a => a.label);

  const choice = await vscode.window.showErrorMessage(
    info.message,
    ...buttons,
  );

  if (choice) {
    const action = info.actions.find(a => a.label === choice);
    if (action) {
      await vscode.commands.executeCommand(action.command, ...(action.args || []));
    }
  }
}

/** Detect host key change from SSH error output */
export function isHostKeyChanged(errorOutput: string): boolean {
  return (
    errorOutput.includes('REMOTE HOST IDENTIFICATION HAS CHANGED') ||
    errorOutput.includes('Host key verification failed')
  );
}

/** Handle host key change: remove old key and add new one */
export async function handleHostKeyChange(config: import('./config').BoardConfig): Promise<void> {
  const { execFile } = await import('child_process');
  const { promisify } = await import('util');
  const execFileAsync = promisify(execFile);
  const { getHostname } = await import('./config');

  const hostname = getHostname(config);
  try {
    await execFileAsync('ssh-keygen', ['-R', hostname], { timeout: 5000 });
    vscode.window.showInformationMessage('Old host key removed. Reconnecting...');
    await vscode.commands.executeCommand('board.connect');
  } catch {
    vscode.window.showErrorMessage('Failed to remove old host key.');
  }
}
