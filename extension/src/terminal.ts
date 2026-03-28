import * as vscode from 'vscode';
import { getConfig, isConfigured, getSshHostAlias } from './config';

export class BoardTerminalProfileProvider
  implements vscode.TerminalProfileProvider
{
  provideTerminalProfile(
    _token: vscode.CancellationToken,
  ): vscode.ProviderResult<vscode.TerminalProfile> {
    if (!isConfigured()) {
      return undefined;
    }

    const config = getConfig();
    return new vscode.TerminalProfile({
      name: 'Board',
      shellPath: 'ssh',
      shellArgs: [getSshHostAlias(config)],
      iconPath: new vscode.ThemeIcon('vm-running'),
    });
  }
}

/**
 * Open a 2-pane workspace terminal layout: Terminal (left) | Copilot (right).
 *
 * When running inside a Remote-SSH session, createTerminal() opens shells
 * on the remote VM — no SSH wrapping needed.
 */
export async function openWorkspaceTerminals(): Promise<void> {
  // Create the free terminal (left pane)
  const terminal = vscode.window.createTerminal({
    name: 'Terminal',
    iconPath: new vscode.ThemeIcon('terminal'),
  });
  terminal.show();

  // Small delay to let the terminal initialise before splitting
  await new Promise((r) => setTimeout(r, 500));

  // Split to create Copilot pane (right pane)
  await vscode.commands.executeCommand('workbench.action.terminal.split');

  // Rename the new split pane
  await vscode.commands.executeCommand(
    'workbench.action.terminal.renameWithArg',
    { name: 'Copilot' },
  );

  // Send the copilot command to the active (right) pane
  const copilotTerminal = vscode.window.activeTerminal;
  if (copilotTerminal) {
    copilotTerminal.sendText('gh copilot');
  }

  // Focus back on the left terminal
  await vscode.commands.executeCommand(
    'workbench.action.terminal.focusPreviousPane',
  );
}
