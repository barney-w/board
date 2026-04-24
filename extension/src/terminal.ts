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
 * Open workspace terminals: a general-purpose Terminal and a Copilot tab.
 *
 * When running inside a Remote-SSH session, createTerminal() opens shells
 * on the remote VM — no SSH wrapping needed.
 */
export async function openWorkspaceTerminals(): Promise<void> {
  // Create the Copilot terminal first (so it appears as the second tab)
  const copilot = vscode.window.createTerminal({
    name: 'Copilot',
    iconPath: new vscode.ThemeIcon('sparkle'),
  });
  copilot.sendText(
    'if gh extension list 2>/dev/null | grep -q gh-copilot; then gh copilot; else echo "Run: gh auth login && gh extension install github/gh-copilot && gh copilot"; fi',
  );

  // Create the main terminal and focus it
  const terminal = vscode.window.createTerminal({
    name: 'Terminal',
    iconPath: new vscode.ThemeIcon('terminal'),
  });
  terminal.show();
}
