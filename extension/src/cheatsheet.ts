import * as vscode from 'vscode';

let currentPanel: vscode.WebviewPanel | undefined;

export function showCheatsheet(context: vscode.ExtensionContext): void {
  if (currentPanel) {
    currentPanel.reveal(vscode.ViewColumn.One);
    return;
  }

  currentPanel = vscode.window.createWebviewPanel(
    'boardCheatsheet',
    'Board Cheatsheet',
    vscode.ViewColumn.One,
    { enableScripts: true },
  );

  currentPanel.webview.html = getCheatsheetHtml();

  currentPanel.webview.onDidReceiveMessage(
    (message) => {
      if (message.command) {
        vscode.commands.executeCommand(message.command);
      }
    },
    undefined,
    context.subscriptions,
  );

  currentPanel.onDidDispose(() => {
    currentPanel = undefined;
  });
}

function getCheatsheetHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Board Cheatsheet</title>
  <style>
    body {
      font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif);
      color: var(--vscode-foreground, #ccc);
      background: var(--vscode-editor-background, #1e1e1e);
      padding: 24px 32px;
      margin: 0;
      line-height: 1.6;
    }
    .container { max-width: 720px; margin: 0 auto; }
    h1 {
      font-size: 1.6em;
      font-weight: 600;
      margin: 0 0 4px;
    }
    .subtitle {
      color: var(--vscode-descriptionForeground, #999);
      margin: 0 0 24px;
      font-size: 0.9em;
    }
    h2 {
      font-size: 1.1em;
      font-weight: 600;
      margin: 24px 0 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--vscode-panel-border, #333);
    }
    table { width: 100%; border-collapse: collapse; margin: 0 0 8px; }
    td {
      padding: 4px 8px;
      vertical-align: top;
      border-bottom: 1px solid var(--vscode-panel-border, #222);
    }
    td:first-child {
      white-space: nowrap;
      font-family: var(--vscode-editor-font-family, 'Cascadia Code', Consolas, monospace);
      font-size: 0.9em;
      color: var(--vscode-textLink-foreground, #3794ff);
      width: 40%;
    }
    td:last-child {
      color: var(--vscode-descriptionForeground, #999);
      font-size: 0.9em;
    }
    .tag {
      display: inline-block;
      font-size: 0.7em;
      padding: 1px 6px;
      border-radius: 3px;
      margin-left: 6px;
      vertical-align: middle;
    }
    .tag-ext {
      background: var(--vscode-badge-background, #0e639c);
      color: var(--vscode-badge-foreground, #fff);
    }
    .tag-term {
      background: var(--vscode-terminal-ansiGreen, #3c8527);
      color: #fff;
    }
    .note {
      font-size: 0.85em;
      color: var(--vscode-descriptionForeground, #999);
      margin: 12px 0;
      padding: 8px 12px;
      background: var(--vscode-textBlockQuote-background, #222);
      border-left: 3px solid var(--vscode-textLink-foreground, #3794ff);
    }
    code {
      font-family: var(--vscode-editor-font-family, 'Cascadia Code', Consolas, monospace);
      font-size: 0.9em;
      background: var(--vscode-textCodeBlock-background, #2a2a2a);
      padding: 1px 4px;
      border-radius: 3px;
    }
    .footer {
      margin-top: 32px;
      padding-top: 12px;
      border-top: 1px solid var(--vscode-panel-border, #333);
      font-size: 0.8em;
      color: var(--vscode-descriptionForeground, #666);
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Board Cheatsheet</h1>
    <p class="subtitle">Quick reference for your cloud dev environment</p>

    <h2>VS Code Commands <span class="tag tag-ext">Cmd+Shift+P</span></h2>
    <table>
      <tr><td>Board: Import Pass</td><td>Decrypt and install a <code>.board-pass</code> file</td></tr>
      <tr><td>Board: Connect</td><td>Open a remote VS Code window on your VM</td></tr>
      <tr><td>Board: Start</td><td>Start your VM (requires Azure CLI)</td></tr>
      <tr><td>Board: Stop</td><td>Deallocate your VM (saves costs)</td></tr>
      <tr><td>Board: Run First-Time Setup</td><td>Configure Git identity + SSH keys on the VM</td></tr>
      <tr><td>Board: Open code-server</td><td>Open code-server in your browser</td></tr>
      <tr><td>Board: Open Cockpit</td><td>System monitoring, logs, file browser (localhost:9091)</td></tr>
      <tr><td>Board: Open Portainer</td><td>Docker container management and logs (localhost:9444)</td></tr>
      <tr><td>Board: Open Terminal</td><td>SSH terminal to your VM</td></tr>
      <tr><td>Board: Open Workspace Terminals</td><td>Open the standard terminal + Copilot split layout</td></tr>
      <tr><td>Board: Open in Azure Portal</td><td>Jump to the VM in the Azure portal</td></tr>
      <tr><td>Board: Cheatsheet</td><td>This page</td></tr>
    </table>

    <h2>On the VM — Health &amp; Status <span class="tag tag-term">Terminal</span></h2>
    <table>
      <tr><td>check</td><td>Run all health checks (Docker, services, ports)</td></tr>
      <tr><td>board-help</td><td>Show the on-VM quick reference</td></tr>
    </table>

    <h2>On the VM — Git Aliases <span class="tag tag-term">Terminal</span></h2>
    <table>
      <tr><td>gs</td><td><code>git status</code></td></tr>
      <tr><td>gd</td><td><code>git diff</code></td></tr>
      <tr><td>gl</td><td><code>git log --oneline -20</code></td></tr>
    </table>

    <h2>On the VM — Docker Aliases <span class="tag tag-term">Terminal</span></h2>
    <table>
      <tr><td>dc up</td><td><code>docker compose up</code></td></tr>
      <tr><td>dc down</td><td><code>docker compose down</code></td></tr>
      <tr><td>dc logs -f</td><td>Follow container logs</td></tr>
      <tr><td>dc ps</td><td>List running containers</td></tr>
    </table>

    <h2>On the VM — Services <span class="tag tag-term">Terminal</span></h2>
    <table>
      <tr><td>systemctl --user restart &lt;svc&gt;</td><td>Restart a project service</td></tr>
      <tr><td>journalctl --user -u &lt;svc&gt; -f</td><td>Stream service logs</td></tr>
    </table>
    <div class="note">
      <strong>Tip:</strong> Use <strong>Ctrl+Shift+P &gt; Run Task</strong> in VS Code to see project-specific tasks
      (start, stop, logs) without memorising service names.
    </div>

    <h2>On the VM — Paths</h2>
    <table>
      <tr><td>~/projects/</td><td>Your project workspace (you start here)</td></tr>
      <tr><td>~/.board/</td><td>Board config, health scripts</td></tr>
    </table>

    <h2>Access Methods</h2>
    <table>
      <tr><td>VS Code Desktop + SSH</td><td>Full Marketplace, Copilot, SSH key auth</td></tr>
      <tr><td>code-server</td><td>Browser-based, Open VSX, password auth</td></tr>
      <tr><td>Cockpit</td><td>System monitoring, logs, file browser — localhost:9091</td></tr>
      <tr><td>Portainer</td><td>Docker container management — localhost:9444 (self-signed cert, pwd in <code>~/.portainer-password</code>)</td></tr>
    </table>

    <h2>Port Forwarding</h2>
    <div class="note">
      <strong>VS Code auto-forwards every port.</strong> When a service starts on the VM (API, database, Langfuse, etc.),
      VS Code detects it and forwards the port to your localhost automatically. Check the <strong>Ports</strong> panel
      (<code>Ctrl+Shift+P</code> &rarr; <em>Ports: Focus on Ports View</em>) to see all forwarded ports, open them in your
      browser, or change visibility.<br><br>
      <strong>Not using VS Code?</strong> Run <code>forward-ports</code> on the VM to get an SSH command that tunnels all
      listening ports at once.
    </div>

    <h2>Daily Workflow</h2>
    <div class="note">
      <strong>Morning:</strong> Click <strong>Board: Connect</strong> (or click the status bar).
      If your VM is stopped, it starts automatically.<br>
      <strong>During the day:</strong> Code normally. Run <code>check</code> if something feels off.<br>
      <strong>Evening:</strong> VMs auto-shutdown at 7 PM. Your files, Docker volumes, and git state all persist — just reconnect tomorrow.
    </div>

    <h2>Troubleshooting</h2>
    <table>
      <tr><td>Can't connect</td><td>Check the status bar — is the VM running? Try <strong>Board: Start</strong></td></tr>
      <tr><td>Services unhealthy</td><td>Run <code>check</code>, then <code>systemctl --user restart &lt;svc&gt;</code></td></tr>
      <tr><td>Docker issues</td><td><code>dc down &amp;&amp; dc up</code> to restart all containers</td></tr>
      <tr><td>Git auth issues</td><td>Run <strong>Board: Run First-Time Setup</strong> again</td></tr>
      <tr><td>Need a fresh start</td><td>Ask your admin to reprovision</td></tr>
    </table>

    <p class="footer">Board v0.1.0 — need help? Message your admin or check the docs.</p>
  </div>
</body>
</html>`;
}
