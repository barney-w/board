import * as vscode from 'vscode';
import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import { writeSshConfig, writeSshKey } from './ssh';
import { getConfig, isConfigured, getSshKeyPath } from './config';
import { showBoardPassCard } from './boardPassCard';

export interface BrowserIdeConfig {
  codeServer?: {
    password: string;
    localUrl: string;
    sshTunnelCommand: string;
  };
  vscodeTunnel?: {
    url: string;
    auth: string;
  };
}

export interface BundlePayload {
  developerName: string;
  region: string;
  hostname: string;
  username: string;
  authMethod: 'ssh-key' | 'entra-id';
  sshPrivateKey: string;
  sshPublicKey: string;
  resourceGroup: string;
  vmName: string;
  issuedAt?: string;            // ISO 8601 timestamp
  validUntil?: string;          // ISO 8601 timestamp (expiry)
  browserIde?: BrowserIdeConfig;  // v2 only
}

interface BundleEnvelope {
  version: number;
  format: string;
  // Encrypted envelope fields (ssh-key auth)
  salt?: string;
  iv?: string;
  ciphertext?: string;
  tag?: string;
  // Plaintext envelope fields (entra-id auth)
  authMethod?: 'ssh-key' | 'entra-id';
  payload?: BundlePayload;
}

/**
 * Check whether an envelope is plaintext (Entra ID, no encryption).
 */
function isPlaintextEnvelope(envelope: BundleEnvelope): boolean {
  return envelope.authMethod === 'entra-id' && envelope.payload != null;
}

/**
 * Read a bundle file. Returns the payload directly for plaintext (Entra ID)
 * envelopes, or decrypts with the given passphrase for encrypted (SSH-key) ones.
 */
export async function decryptBundle(
  bundlePath: string,
  passphrase?: string,
): Promise<BundlePayload> {
  const raw = await fs.readFile(bundlePath, 'utf-8');
  const envelope: BundleEnvelope = JSON.parse(raw);

  // Validate envelope
  if (envelope.version !== 1 && envelope.version !== 2) {
    throw new Error(`Unsupported bundle version: ${envelope.version}`);
  }
  if (envelope.format !== 'board-pass' && envelope.format !== 'devvm-bundle') {
    throw new Error(`Unsupported bundle format: ${envelope.format}`);
  }

  // Plaintext Entra ID envelope — no decryption needed
  if (isPlaintextEnvelope(envelope)) {
    return envelope.payload!;
  }

  // Encrypted SSH-key envelope — passphrase required
  if (!passphrase) {
    throw new Error('Passphrase required for SSH-key bundles');
  }

  // Decode fields
  const salt = Buffer.from(envelope.salt!, 'base64');
  const iv = Buffer.from(envelope.iv!, 'base64');
  const ciphertext = Buffer.from(envelope.ciphertext!, 'base64');
  const tag = Buffer.from(envelope.tag!, 'base64');

  // Derive key via PBKDF2
  const key = crypto.pbkdf2Sync(passphrase, salt, 100_000, 32, 'sha256');

  // Decrypt with AES-256-GCM
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAuthTag(tag);

  const decrypted = Buffer.concat([
    decipher.update(ciphertext),
    decipher.final(),
  ]);

  return JSON.parse(decrypted.toString('utf-8')) as BundlePayload;
}

/**
 * Check whether a bundle file is a plaintext (Entra ID) envelope.
 * Used by importBundle to skip the passphrase prompt.
 */
export async function isBundlePlaintext(bundlePath: string): Promise<boolean> {
  const raw = await fs.readFile(bundlePath, 'utf-8');
  const envelope: BundleEnvelope = JSON.parse(raw);
  return isPlaintextEnvelope(envelope);
}

/**
 * Import a bundle: decrypt, write SSH key, write SSH config,
 * save settings, and back up key to SecretStorage.
 */
export async function importBundle(
  context: vscode.ExtensionContext,
  fileUri?: vscode.Uri,
  options?: { showCard?: boolean },
): Promise<BundlePayload | undefined> {
  // Check if current auth method is entra-id — bundle import is for SSH key auth only
  const currentConfig = getConfig();
  if (currentConfig.authMethod === 'entra-id' && isConfigured()) {
    vscode.window.showInformationMessage(
      'Bundle import is for SSH key authentication. Your current auth method is Entra ID.',
    );
    // Still allow import — the user may be switching auth methods
  }

  let bundleUri: vscode.Uri;

  if (fileUri) {
    // URI provided directly (e.g. from file open handler)
    bundleUri = fileUri;
  } else {
    // 1. Show file picker
    const uris = await vscode.window.showOpenDialog({
      filters: { 'Board Pass': ['board-pass', 'devvm-bundle'] },
      canSelectMany: false,
      openLabel: 'Import Bundle',
    });

    if (!uris || uris.length === 0) {
      return; // User cancelled
    }

    bundleUri = uris[0];
  }

  const bundlePath = bundleUri.fsPath;

  // 2-3. Read and validate (done inside decryptBundle)

  // 4-6. Decrypt: plaintext (Entra ID) skips passphrase, encrypted (SSH-key) prompts
  let payload: BundlePayload | undefined;

  const plaintext = await isBundlePlaintext(bundlePath);
  if (plaintext) {
    // Entra ID bundle — no passphrase needed
    payload = await decryptBundle(bundlePath);
  } else {
    // SSH-key bundle — prompt for passphrase with retry loop
    while (!payload) {
      const passphrase = await vscode.window.showInputBox({
        prompt: 'Enter the passphrase for this bundle',
        password: true,
        ignoreFocusOut: true,
      });

      if (passphrase === undefined) {
        return; // User cancelled
      }

      try {
        payload = await decryptBundle(bundlePath, passphrase);
      } catch (err) {
        // GCM auth failure or other crypto error -> treat as bad passphrase
        const retry = await vscode.window.showErrorMessage(
          'Invalid passphrase. Please try again.',
          'Retry',
          'Cancel',
        );
        if (retry !== 'Retry') {
          return;
        }
      }
    }
  }

  // 6b. Check expiration
  if (payload.validUntil) {
    const expiry = new Date(payload.validUntil);
    if (expiry < new Date()) {
      const action = await vscode.window.showWarningMessage(
        `This board pass expired on ${expiry.toLocaleDateString()}. Ask your admin for a new one.`,
        'Import Anyway',
        'Cancel',
      );
      if (action !== 'Import Anyway') {
        return;
      }
    }
  }

  // 7. Write SSH private key to ~/.ssh/devvm-<name> (ssh-key auth only)
  if (payload.authMethod !== 'entra-id') {
    const keyPath = getSshKeyPath({
      ...getConfig(),
      developerName: payload.developerName,
    });
    await writeSshKey(keyPath, payload.sshPrivateKey);

    // 8. Backup private key to SecretStorage
    await context.secrets.store(
      `board.sshKey.${payload.developerName}`,
      payload.sshPrivateKey,
    );
  }

  // 9. Save all settings to VS Code global config
  const cfg = vscode.workspace.getConfiguration('board');
  await cfg.update(
    'developerName',
    payload.developerName,
    vscode.ConfigurationTarget.Global,
  );
  await cfg.update('region', payload.region, vscode.ConfigurationTarget.Global);
  await cfg.update(
    'resourceGroup',
    payload.resourceGroup,
    vscode.ConfigurationTarget.Global,
  );
  await cfg.update(
    'authMethod',
    payload.authMethod,
    vscode.ConfigurationTarget.Global,
  );

  // 10. Write SSH config
  const updatedConfig = getConfig();
  await writeSshConfig(updatedConfig);

  // 10b. Store browser IDE config (v2 bundles only)
  if (payload.browserIde) {
    if (payload.browserIde.codeServer?.password) {
      await context.secrets.store(
        `board.codeServerPassword.${payload.developerName}`,
        payload.browserIde.codeServer.password,
      );
    }
    if (payload.browserIde.vscodeTunnel?.url) {
      await cfg.update(
        'tunnelUrl',
        payload.browserIde.vscodeTunnel.url,
        vscode.ConfigurationTarget.Global,
      );
    }
  }

  // 11-12. Show the boarding pass card (handles delete + connect)
  if (options?.showCard !== false) {
    showBoardPassCard(context, payload, bundleUri);

    // 13. Open the Get Started walkthrough so users see next steps
    vscode.commands.executeCommand(
      'workbench.action.openWalkthrough',
      'barney-w.board#board.getStarted',
      false,
    );
  }

  return payload;
}
