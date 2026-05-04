import * as vscode from 'vscode';
import { BundlePayload } from './bundle';

/**
 * Show a beautifully designed access-pass card in a VS Code webview
 * after a successful board pass import.
 */
export function showBoardPassCard(
  context: vscode.ExtensionContext,
  payload: BundlePayload,
  bundleUri?: vscode.Uri,
): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    'boardPassCard',
    'Board Pass',
    vscode.ViewColumn.One,
    { enableScripts: true },
  );

  panel.webview.html = getBoardPassHtml(payload);

  panel.webview.onDidReceiveMessage(
    async (message) => {
      if (message.command === 'connect') {
        panel.dispose();
        await vscode.commands.executeCommand('board.connect');
      }
    },
    undefined,
    context.subscriptions,
  );

  return panel;
}

function formatDate(iso: string | undefined): string {
  if (!iso) { return '---'; }
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function isExpired(iso: string | undefined): boolean {
  if (!iso) { return false; }
  return new Date(iso) < new Date();
}

function daysRemaining(iso: string | undefined): string {
  if (!iso) { return ''; }
  const diff = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (diff < 0) { return 'EXPIRED'; }
  if (diff === 0) { return 'TODAY'; }
  if (diff === 1) { return '1 day'; }
  return `${diff} days`;
}

function generateBarcode(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
  }
  const bars: string[] = [];
  let x = 0;
  for (let i = 0; i < 60; i++) {
    const seed = Math.abs((hash * (i + 1) * 2654435761) | 0);
    const w = (seed % 3) + 1;
    const gap = (seed % 2) + 1;
    const opacity = 0.5 + (seed % 50) / 100;
    bars.push(`<rect x="${x}" y="0" width="${w}" height="40" rx="0.5" fill="currentColor" opacity="${opacity.toFixed(2)}" />`);
    x += w + gap;
  }
  return `<svg viewBox="0 0 ${x} 40" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:40px;color:var(--bar-color)">${bars.join('')}</svg>`;
}

/** Generate initials avatar SVG (like an ID badge photo placeholder) */
function generateAvatar(name: string): string {
  const initials = name.slice(0, 2).toUpperCase();
  return `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" width="64" height="64">
    <rect width="64" height="64" rx="8" fill="var(--sky-glow)" stroke="var(--sky)" stroke-width="1.5"/>
    <text x="32" y="38" text-anchor="middle" font-size="22" font-weight="700" font-family="inherit" fill="var(--sky-light)">${initials}</text>
  </svg>`;
}

export function getBoardPassHtml(payload: BundlePayload): string {
  const expired = isExpired(payload.validUntil);
  const remaining = daysRemaining(payload.validUntil);
  const barcode = generateBarcode(payload.developerName + payload.hostname);
  const avatar = generateAvatar(payload.developerName);
  const hasBrowserIde = !!payload.browserIde?.codeServer;

  // Shield SVG icon for the header
  const shieldIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Board Pass</title>
  <style>
    :root {
      --sky: #0ea5e9;
      --sky-light: #38bdf8;
      --sky-dark: #0284c7;
      --sky-glow: rgba(14, 165, 233, 0.12);
      --bar-color: rgba(14, 165, 233, 0.6);
      --card-bg: var(--vscode-editor-background, #1e1e1e);
      --card-surface: color-mix(in srgb, var(--vscode-editor-background, #1e1e1e) 85%, white);
      --text-primary: var(--vscode-foreground, #cccccc);
      --text-secondary: var(--vscode-descriptionForeground, #999999);
      --text-label: var(--vscode-descriptionForeground, #888888);
      --border: color-mix(in srgb, var(--vscode-foreground, #cccccc) 12%, transparent);
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif);
      background: var(--card-bg);
      color: var(--text-primary);
      display: flex;
      justify-content: center;
      padding: 40px 20px;
      min-height: 100vh;
    }

    .pass-wrapper {
      width: 100%;
      max-width: 520px;
      animation: fadeIn 0.6s ease-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes stampIn {
      0% { opacity: 0; transform: scale(2.5) rotate(-20deg); }
      50% { opacity: 1; transform: scale(0.9) rotate(-12deg); }
      100% { opacity: 1; transform: scale(1) rotate(-12deg); }
    }

    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }

    /* ---- The card ---- */
    .pass {
      background: var(--card-surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 24px rgba(0,0,0,0.25), 0 0 0 1px var(--border);
      position: relative;
    }

    /* Subtle holographic sheen across the whole card */
    .pass::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(
        105deg,
        transparent 40%,
        rgba(14,165,233,0.03) 45%,
        rgba(14,165,233,0.06) 50%,
        rgba(14,165,233,0.03) 55%,
        transparent 60%
      );
      background-size: 200% 100%;
      animation: shimmer 6s ease-in-out infinite;
      pointer-events: none;
      z-index: 1;
    }

    /* ---- Header strip ---- */
    .pass-header {
      background: linear-gradient(135deg, var(--sky-dark), var(--sky), var(--sky-light));
      padding: 18px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: relative;
    }

    /* Subtle grid pattern overlay on header */
    .pass-header::after {
      content: '';
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
      background-size: 20px 20px;
      pointer-events: none;
    }

    .pass-header-left {
      display: flex;
      align-items: center;
      gap: 10px;
      position: relative;
      z-index: 1;
    }

    .pass-logo {
      display: flex;
      align-items: center;
    }

    .pass-title {
      font-size: 1.05em;
      font-weight: 700;
      color: white;
      letter-spacing: 3px;
      text-transform: uppercase;
    }

    .pass-type {
      font-size: 0.7em;
      font-weight: 600;
      color: rgba(255,255,255,0.65);
      letter-spacing: 1px;
      text-transform: uppercase;
      position: relative;
      z-index: 1;
    }

    /* ---- Identity section ---- */
    .identity {
      display: flex;
      align-items: center;
      gap: 20px;
      padding: 24px 28px 4px;
      position: relative;
      z-index: 2;
    }

    .avatar {
      flex-shrink: 0;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    .identity-info {
      min-width: 0;
    }

    .identity-name {
      font-size: 1.8em;
      font-weight: 700;
      letter-spacing: 0.5px;
      line-height: 1.2;
    }

    .identity-role {
      font-size: 0.8em;
      color: var(--text-secondary);
      margin-top: 2px;
    }

    /* ---- Perforated tear line ---- */
    .perforation {
      position: relative;
      height: 20px;
      margin: 0;
      z-index: 2;
    }

    .perforation::before {
      content: '';
      position: absolute;
      top: 50%;
      left: 20px;
      right: 20px;
      border-top: 2px dashed var(--border);
    }

    /* Circle cutouts at perforation edges */
    .perforation::after {
      content: '';
      position: absolute;
      top: 50%;
      left: -8px;
      width: 16px;
      height: 16px;
      transform: translateY(-50%);
      border-radius: 50%;
      background: var(--card-bg);
      box-shadow: calc(520px - 0px) 0 0 0 var(--card-bg);
    }

    /* ---- Body ---- */
    .pass-body {
      padding: 16px 28px 24px;
      position: relative;
      z-index: 2;
    }

    /* Authorised / Revoked stamp overlay */
    .stamp {
      position: absolute;
      top: 0px;
      right: 20px;
      border: 3px solid var(--success);
      color: var(--success);
      padding: 4px 14px;
      font-weight: 800;
      font-size: 0.7em;
      letter-spacing: 3px;
      text-transform: uppercase;
      border-radius: 6px;
      opacity: 0;
      animation: stampIn 0.4s ease-out 0.5s forwards;
      pointer-events: none;
    }

    .stamp.expired {
      border-color: var(--danger);
      color: var(--danger);
    }

    /* ---- Field grid ---- */
    .field-row {
      display: flex;
      gap: 20px;
      margin-bottom: 18px;
    }

    .field {
      flex: 1;
      min-width: 0;
    }

    .field-label {
      font-size: 0.6em;
      font-weight: 600;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--text-label);
      margin-bottom: 3px;
    }

    .field-value {
      font-size: 1em;
      font-weight: 600;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .field-value.large {
      font-size: 1.5em;
      font-weight: 700;
      letter-spacing: 1px;
    }

    .field-value.mono {
      font-family: var(--vscode-editor-font-family, 'SF Mono', 'Fira Code', monospace);
      font-size: 0.8em;
      color: var(--text-secondary);
    }

    .field-value .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75em;
      font-weight: 600;
      letter-spacing: 0.5px;
    }

    .badge-ok { background: rgba(34,197,94,0.15); color: var(--success); }
    .badge-warn { background: rgba(245,158,11,0.15); color: var(--warning); }
    .badge-danger { background: rgba(239,68,68,0.15); color: var(--danger); }
    .badge-info { background: var(--sky-glow); color: var(--sky-light); }

    /* ---- Clearance row ---- */
    .clearance {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }

    .clearance-chip {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 6px;
      background: var(--sky-glow);
      border: 1px solid color-mix(in srgb, var(--sky) 20%, transparent);
      font-size: 0.72em;
      font-weight: 600;
      color: var(--sky-light);
      letter-spacing: 0.3px;
    }

    .clearance-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 4px var(--success);
    }

    /* ---- Barcode area ---- */
    .barcode-section {
      padding: 12px 28px 16px;
      text-align: center;
      position: relative;
      z-index: 2;
    }

    .barcode {
      opacity: 0.7;
      margin-bottom: 4px;
    }

    .barcode-label {
      font-family: var(--vscode-editor-font-family, 'SF Mono', monospace);
      font-size: 0.65em;
      letter-spacing: 2px;
      color: var(--text-label);
    }

    /* ---- Divider ---- */
    .divider {
      height: 1px;
      background: var(--border);
      margin: 0 28px;
      position: relative;
      z-index: 2;
    }

    /* ---- Stub (tear-off bottom) ---- */
    .pass-stub {
      padding: 16px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: color-mix(in srgb, var(--card-surface) 50%, var(--card-bg));
      position: relative;
      z-index: 2;
    }

    .stub-info {
      font-size: 0.72em;
      color: var(--text-label);
      line-height: 1.6;
    }

    .stub-zone {
      text-align: right;
    }

    .stub-zone-label {
      font-size: 0.55em;
      font-weight: 600;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--text-label);
    }

    .stub-zone-code {
      font-size: 2em;
      font-weight: 800;
      color: var(--sky);
      letter-spacing: 2px;
      line-height: 1;
    }

    /* ---- Actions ---- */
    .actions {
      display: flex;
      gap: 12px;
      margin-top: 24px;
      justify-content: center;
    }

    .btn {
      padding: 12px 32px;
      font-size: 0.95em;
      font-weight: 600;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .btn-connect {
      background: linear-gradient(135deg, var(--sky-dark), var(--sky));
      color: white;
      box-shadow: 0 2px 12px rgba(14,165,233,0.3);
    }

    .btn-connect:hover {
      box-shadow: 0 4px 20px rgba(14,165,233,0.5);
      transform: translateY(-1px);
    }

    /* ---- Responsive ---- */
    @media (max-width: 460px) {
      .field-row { flex-direction: column; gap: 12px; }
      .pass-header { padding: 14px 20px; }
      .pass-body { padding: 16px 20px; }
      .identity { padding: 20px; }
    }
  </style>
</head>
<body>
  <div class="pass-wrapper">
    <div class="pass">
      <!-- Header -->
      <div class="pass-header">
        <div class="pass-header-left">
          <span class="pass-logo">${shieldIcon}</span>
          <span class="pass-title">Board Pass</span>
        </div>
        <span class="pass-type">Access Credential</span>
      </div>

      <!-- Identity -->
      <div class="identity">
        <div class="avatar">${avatar}</div>
        <div class="identity-info">
          <div class="identity-name">${escHtml(payload.developerName)}</div>
          <div class="identity-role">${escHtml(payload.resourceGroup)} &middot; ${escHtml(payload.region)}</div>
        </div>
      </div>

      <!-- Body -->
      <div class="pass-body">
        <div class="stamp ${expired ? 'expired' : ''}">${expired ? 'Revoked' : 'Authorised'}</div>

        <div class="field-row">
          <div class="field" style="flex:2">
            <div class="field-label">Host</div>
            <div class="field-value mono">${escHtml(payload.hostname)}</div>
          </div>
          <div class="field">
            <div class="field-label">Zone</div>
            <div class="field-value large" style="color:var(--sky)">${escHtml(payload.region.slice(0, 3).toUpperCase())}</div>
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <div class="field-label">Auth Method</div>
            <div class="field-value"><span class="badge badge-info">${escHtml(payload.authMethod)}</span></div>
          </div>
          <div class="field">
            <div class="field-label">Issued</div>
            <div class="field-value">${formatDate(payload.issuedAt)}</div>
          </div>
          <div class="field">
            <div class="field-label">Expires</div>
            <div class="field-value">${formatDate(payload.validUntil)} <span class="badge ${expired ? 'badge-danger' : 'badge-ok'}">${remaining}</span></div>
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <div class="field-label">Clearance</div>
            <div class="clearance">
              <span class="clearance-chip"><span class="clearance-dot"></span>SSH Terminal</span>
              ${hasBrowserIde && payload.browserIde?.codeServer ? '<span class="clearance-chip"><span class="clearance-dot"></span>code-server</span>' : ''}
              <span class="clearance-chip"><span class="clearance-dot"></span>Cockpit</span>
              <span class="clearance-chip"><span class="clearance-dot"></span>Portainer</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Perforation -->
      <div class="perforation"></div>

      <!-- Barcode -->
      <div class="barcode-section">
        <div class="barcode">${barcode}</div>
        <div class="barcode-label">${escHtml(payload.vmName)}</div>
      </div>

      <!-- Stub -->
      <div class="divider"></div>
      <div class="pass-stub">
        <div class="stub-info">
          <div><strong>${escHtml(payload.developerName)}</strong></div>
          <div>${escHtml(payload.region)} &middot; ${escHtml(payload.resourceGroup)}</div>
          <div>Expires: ${formatDate(payload.validUntil)}</div>
        </div>
        <div class="stub-zone">
          <div class="stub-zone-label">Zone</div>
          <div class="stub-zone-code">${escHtml(payload.region.slice(0, 3).toUpperCase())}</div>
        </div>
      </div>
    </div>

    ${payload.authMethod === 'entra-id' ? `
    <!-- Entra ID prerequisite notice -->
    <div style="
      margin-top: 20px;
      padding: 14px 20px;
      border-radius: 10px;
      border: 1px solid color-mix(in srgb, var(--sky) 25%, transparent);
      background: var(--sky-glow);
      font-size: 0.82em;
      color: var(--text-secondary);
      line-height: 1.6;
    ">
      <div style="font-weight:600;color:var(--sky-light);margin-bottom:4px;">Entra ID Authentication</div>
      Before connecting, ensure you have:
      <ul style="margin:6px 0 0 16px;padding:0;">
        <li><a href="https://aka.ms/installazurecli" style="color:var(--sky-light)">Azure CLI</a> installed</li>
        <li>Signed in with <code style="background:var(--border);padding:1px 5px;border-radius:3px;font-size:0.9em;">az login</code></li>
      </ul>
    </div>
    ` : ''}

    <!-- Actions below card -->
    <div class="actions">
      <button class="btn btn-connect" id="connectBtn">Connect Now</button>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    document.getElementById('connectBtn').addEventListener('click', () => {
      vscode.postMessage({ command: 'connect' });
    });

  </script>
</body>
</html>`;
}

function escHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
