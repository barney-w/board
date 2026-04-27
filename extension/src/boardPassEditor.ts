import * as vscode from 'vscode';
import { getConfig, getHostname, getResourceGroup, getVmName } from './config';
import { importBundle, BundlePayload } from './bundle';
import { getBoardPassHtml } from './boardPassCard';

/**
 * Custom read-only editor for `.board-pass` files.
 *
 * Instead of showing encrypted JSON as raw text, this editor renders the
 * board pass card webview directly in the editor tab.
 */
export class BoardPassEditorProvider implements vscode.CustomReadonlyEditorProvider {
  public static readonly viewType = 'board.boardPassEditor';

  constructor(private readonly context: vscode.ExtensionContext) {}

  openCustomDocument(uri: vscode.Uri): vscode.CustomDocument {
    return { uri, dispose: () => {} };
  }

  async resolveCustomEditor(
    document: vscode.CustomDocument,
    webviewPanel: vscode.WebviewPanel,
  ): Promise<void> {
    webviewPanel.webview.options = { enableScripts: true };

    // Always import the actual file — it may be for a different developer
    // than the currently configured one, or a refreshed pass.
    webviewPanel.webview.html = getLoadingHtml();
    await this.importAndShowCard(webviewPanel, document.uri);
  }

  private showCard(
    panel: vscode.WebviewPanel,
    fileUri: vscode.Uri,
    payload?: BundlePayload,
  ): void {
    if (!payload) {
      const cfg = getConfig();
      payload = {
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
        browserIde: cfg.tunnelUrl
          ? { vscodeTunnel: { url: cfg.tunnelUrl, auth: '' } }
          : undefined,
      };
    }

    panel.webview.html = getBoardPassHtml(payload);
    panel.webview.onDidReceiveMessage(
      async (message) => {
        if (message.command === 'connect') {
          await vscode.commands.executeCommand('board.connect');
        }
      },
      undefined,
      this.context.subscriptions,
    );
  }

  private async importAndShowCard(
    panel: vscode.WebviewPanel,
    fileUri: vscode.Uri,
  ): Promise<void> {
    let payload: BundlePayload | undefined;
    try {
      payload = await importBundle(this.context, fileUri, {
        showCard: false,
      });
    } catch (err) {
      console.error('[Board] Import failed in custom editor:', err);
    }

    if (payload) {
      this.showCard(panel, fileUri, payload);
    } else {
      // Import was cancelled or failed — offer retry
      panel.webview.html = getCancelledHtml();
      panel.webview.onDidReceiveMessage(
        async (message) => {
          if (message.command === 'retry') {
            panel.webview.html = getLoadingHtml();
            await this.importAndShowCard(panel, fileUri);
          }
        },
        undefined,
        this.context.subscriptions,
      );
    }
  }
}

function getLoadingHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body {
      font-family: var(--vscode-font-family, sans-serif);
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 80vh;
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
    }
    .msg { text-align: center; }
    .msg p { color: var(--vscode-descriptionForeground); }
    .spinner {
      width: 32px; height: 32px; margin: 0 auto 16px;
      border: 3px solid var(--vscode-descriptionForeground, #666);
      border-top-color: #0ea5e9;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="msg">
    <div class="spinner"></div>
    <p>Importing your board pass...</p>
  </div>
</body>
</html>`;
}

function getCancelledHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body {
      font-family: var(--vscode-font-family, sans-serif);
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 80vh;
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
    }
    .msg { text-align: center; }
    .msg p { margin-bottom: 16px; color: var(--vscode-descriptionForeground); }
    button {
      padding: 10px 24px;
      background: #0ea5e9;
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    button:hover { background: #0284c7; }
  </style>
</head>
<body>
  <div class="msg">
    <p>Import cancelled. Click below to try again.</p>
    <button id="retryBtn">Import Board Pass</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    document.getElementById('retryBtn').addEventListener('click', () => {
      vscode.postMessage({ command: 'retry' });
    });
  </script>
</body>
</html>`;
}
