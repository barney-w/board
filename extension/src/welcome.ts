import * as vscode from 'vscode';

export function showWelcomePanel(context: vscode.ExtensionContext): vscode.WebviewPanel {
    const panel = vscode.window.createWebviewPanel(
        'boardWelcome',
        'Board - Get Started',
        vscode.ViewColumn.One,
        { enableScripts: true }
    );

    panel.webview.html = getWelcomeHtml();

    panel.webview.onDidReceiveMessage(
        (message) => {
            switch (message.command) {
                case 'importBundle':
                    vscode.commands.executeCommand('board.importPass');
                    break;
                case 'configure':
                    vscode.commands.executeCommand('board.configure');
                    break;
            }
        },
        undefined,
        context.subscriptions
    );

    return panel;
}

function getWelcomeHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Board</title>
    <style>
        body {
            font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif);
            color: var(--vscode-foreground, #cccccc);
            background-color: var(--vscode-editor-background, #1e1e1e);
            padding: 32px;
            margin: 0;
            line-height: 1.6;
        }

        .container {
            max-width: 560px;
            margin: 0 auto;
        }

        h1 {
            font-size: 1.8em;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--vscode-foreground, #cccccc);
        }

        .subtitle {
            font-size: 1em;
            color: var(--vscode-descriptionForeground, #999999);
            margin-bottom: 32px;
        }

        .steps {
            list-style: none;
            padding: 0;
            margin: 0 0 32px 0;
        }

        .steps li {
            display: flex;
            align-items: flex-start;
            margin-bottom: 20px;
        }

        .step-number {
            flex-shrink: 0;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background-color: var(--vscode-button-background, #0e639c);
            color: var(--vscode-button-foreground, #ffffff);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85em;
            font-weight: 600;
            margin-right: 14px;
            margin-top: 2px;
        }

        .step-text {
            font-size: 0.95em;
        }

        .step-text strong {
            color: var(--vscode-foreground, #cccccc);
        }

        .actions {
            display: flex;
            flex-direction: column;
            gap: 12px;
            align-items: flex-start;
        }

        .btn-primary {
            display: inline-block;
            padding: 10px 28px;
            font-size: 1em;
            font-weight: 600;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            background-color: var(--vscode-button-background, #0e639c);
            color: var(--vscode-button-foreground, #ffffff);
        }

        .btn-primary:hover {
            background-color: var(--vscode-button-hoverBackground, #1177bb);
        }

        .link-secondary {
            background: none;
            border: none;
            color: var(--vscode-textLink-foreground, #3794ff);
            cursor: pointer;
            font-size: 0.9em;
            padding: 0;
            text-decoration: none;
        }

        .link-secondary:hover {
            text-decoration: underline;
            color: var(--vscode-textLink-activeForeground, #3794ff);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Board</h1>
        <p class="subtitle">Your admin created a cloud dev environment for you. Import your board pass to get connected.</p>

        <ol class="steps">
            <li>
                <span class="step-number">1</span>
                <span class="step-text"><strong>Get your board pass</strong> — a <code>.board-pass</code> file and a passphrase from your admin.</span>
            </li>
            <li>
                <span class="step-number">2</span>
                <span class="step-text"><strong>Click Import Pass</strong> below, select the file, and enter the passphrase.</span>
            </li>
            <li>
                <span class="step-number">3</span>
                <span class="step-text"><strong>Click Connect</strong> — that's it. You're coding in the cloud.</span>
            </li>
        </ol>

        <div class="actions">
            <button class="btn-primary" id="importBtn">Import Pass</button>
            <button class="link-secondary" id="configureBtn">I'm an admin setting up manually</button>
        </div>

        <p style="margin-top: 24px; font-size: 0.85em; color: var(--vscode-descriptionForeground, #999);">
            Don't have a board pass? Ask your admin — they'll create one for you.
        </p>
    </div>

    <script>
        const vscode = acquireVsCodeApi();

        document.getElementById('importBtn').addEventListener('click', () => {
            vscode.postMessage({ command: 'importBundle' });
        });

        document.getElementById('configureBtn').addEventListener('click', () => {
            vscode.postMessage({ command: 'configure' });
        });
    </script>
</body>
</html>`;
}
