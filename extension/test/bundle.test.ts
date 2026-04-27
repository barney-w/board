import { describe, it, expect, afterAll } from 'vitest';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { decryptBundle, isBundlePlaintext, type BundlePayload } from '../src/bundle';

/** Encrypt a payload to match the format produced by export-bundle.sh */
function encryptBundle(payload: object, passphrase: string): string {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const key = crypto.pbkdf2Sync(passphrase, salt, 100_000, 32, 'sha256');
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  let encrypted = cipher.update(JSON.stringify(payload), 'utf8');
  encrypted = Buffer.concat([encrypted, cipher.final()]);
  const tag = cipher.getAuthTag();
  return JSON.stringify({
    version: 1,
    format: 'board-pass',
    salt: salt.toString('base64'),
    iv: iv.toString('base64'),
    ciphertext: encrypted.toString('base64'),
    tag: tag.toString('base64'),
  });
}

/** Create a plaintext Entra ID envelope */
function plaintextBundle(payload: object): string {
  return JSON.stringify({
    version: 2,
    format: 'board-pass',
    authMethod: 'entra-id',
    payload,
  });
}

/** Sample SSH-key bundle payload */
const samplePayload: BundlePayload = {
  developerName: 'testuser',
  environment: 'personal',
  region: 'australiaeast',
  regionShort: 'aue',
  hostname: 'devvm-testuser.australiaeast.cloudapp.azure.com',
  username: 'devuser',
  authMethod: 'ssh-key',
  sshPrivateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key-content\n-----END OPENSSH PRIVATE KEY-----',
  sshPublicKey: 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5 test@devvm',
  resourceGroup: 'rg-personal-aue-devvm',
  vmName: 'vm-personal-aue-devvm-testuser',
};

/** Sample Entra ID bundle payload */
const entraPayload: BundlePayload = {
  developerName: 'testuser',
  environment: 'personal',
  region: 'australiaeast',
  regionShort: 'aue',
  hostname: 'devvm-testuser.australiaeast.cloudapp.azure.com',
  username: 'devuser',
  authMethod: 'entra-id',
  sshPrivateKey: '',
  sshPublicKey: '',
  resourceGroup: 'rg-personal-aue-devvm',
  vmName: 'vm-personal-aue-devvm-testuser',
};

const passphrase = 'test-passphrase-12345';

// Temp directory for bundle files
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'devvm-bundle-test-'));

afterAll(() => {
  // Clean up temp files
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

function writeTempBundle(content: string, name: string): string {
  const filePath = path.join(tmpDir, name);
  fs.writeFileSync(filePath, content, 'utf-8');
  return filePath;
}

describe('bundle encrypt/decrypt round-trip', () => {
  it('round-trip: encrypt then decrypt recovers original payload', async () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const bundlePath = writeTempBundle(encrypted, 'roundtrip.devvm-bundle');

    const result = await decryptBundle(bundlePath, passphrase);

    expect(result.developerName).toBe('testuser');
    expect(result.environment).toBe('personal');
    expect(result.region).toBe('australiaeast');
    expect(result.sshPrivateKey).toContain('BEGIN OPENSSH PRIVATE KEY');
    expect(result.vmName).toBe('vm-personal-aue-devvm-testuser');
  });

  it('decrypt with wrong passphrase throws an error', async () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const bundlePath = writeTempBundle(encrypted, 'wrong-pass.devvm-bundle');

    await expect(decryptBundle(bundlePath, 'wrong-passphrase')).rejects.toThrow();
  });

  it('encrypted bundle JSON has all required fields', () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const envelope = JSON.parse(encrypted);

    expect(envelope).toHaveProperty('version', 1);
    expect(envelope).toHaveProperty('format', 'board-pass');
    expect(envelope).toHaveProperty('salt');
    expect(envelope).toHaveProperty('iv');
    expect(envelope).toHaveProperty('ciphertext');
    expect(envelope).toHaveProperty('tag');
  });

  it('decrypted payload has expected fields matching input', async () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const bundlePath = writeTempBundle(encrypted, 'fields.devvm-bundle');

    const result = await decryptBundle(bundlePath, passphrase);

    expect(result).toEqual(samplePayload);
  });
});

describe('Entra ID plaintext bundle', () => {
  it('imports without passphrase', async () => {
    const bundle = plaintextBundle(entraPayload);
    const bundlePath = writeTempBundle(bundle, 'entra.board-pass');

    const result = await decryptBundle(bundlePath);

    expect(result.developerName).toBe('testuser');
    expect(result.authMethod).toBe('entra-id');
    expect(result.sshPrivateKey).toBe('');
  });

  it('isBundlePlaintext returns true for Entra ID bundles', async () => {
    const bundle = plaintextBundle(entraPayload);
    const bundlePath = writeTempBundle(bundle, 'entra-check.board-pass');

    expect(await isBundlePlaintext(bundlePath)).toBe(true);
  });

  it('isBundlePlaintext returns false for encrypted bundles', async () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const bundlePath = writeTempBundle(encrypted, 'encrypted-check.board-pass');

    expect(await isBundlePlaintext(bundlePath)).toBe(false);
  });

  it('payload fields match input exactly', async () => {
    const bundle = plaintextBundle(entraPayload);
    const bundlePath = writeTempBundle(bundle, 'entra-fields.board-pass');

    const result = await decryptBundle(bundlePath);

    expect(result).toEqual(entraPayload);
  });

  it('throws for encrypted bundle without passphrase', async () => {
    const encrypted = encryptBundle(samplePayload, passphrase);
    const bundlePath = writeTempBundle(encrypted, 'no-pass.board-pass');

    await expect(decryptBundle(bundlePath)).rejects.toThrow('Passphrase required');
  });
});
