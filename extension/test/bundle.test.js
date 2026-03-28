"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const vitest_1 = require("vitest");
const crypto = __importStar(require("crypto"));
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
const bundle_1 = require("../src/bundle");
/** Encrypt a payload to match the format produced by export-bundle.sh */
function encryptBundle(payload, passphrase) {
    const salt = crypto.randomBytes(16);
    const iv = crypto.randomBytes(12);
    const key = crypto.pbkdf2Sync(passphrase, salt, 100_000, 32, 'sha256');
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    let encrypted = cipher.update(JSON.stringify(payload), 'utf8');
    encrypted = Buffer.concat([encrypted, cipher.final()]);
    const tag = cipher.getAuthTag();
    return JSON.stringify({
        version: 1,
        format: 'devvm-bundle',
        salt: salt.toString('base64'),
        iv: iv.toString('base64'),
        ciphertext: encrypted.toString('base64'),
        tag: tag.toString('base64'),
    });
}
/** Sample bundle payload */
const samplePayload = {
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
const passphrase = 'test-passphrase-12345';
// Temp directory for bundle files
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'devvm-bundle-test-'));
(0, vitest_1.afterAll)(() => {
    // Clean up temp files
    fs.rmSync(tmpDir, { recursive: true, force: true });
});
function writeTempBundle(content, name) {
    const filePath = path.join(tmpDir, name);
    fs.writeFileSync(filePath, content, 'utf-8');
    return filePath;
}
(0, vitest_1.describe)('bundle encrypt/decrypt round-trip', () => {
    (0, vitest_1.it)('round-trip: encrypt then decrypt recovers original payload', async () => {
        const encrypted = encryptBundle(samplePayload, passphrase);
        const bundlePath = writeTempBundle(encrypted, 'roundtrip.devvm-bundle');
        const result = await (0, bundle_1.decryptBundle)(bundlePath, passphrase);
        (0, vitest_1.expect)(result.developerName).toBe('testuser');
        (0, vitest_1.expect)(result.environment).toBe('personal');
        (0, vitest_1.expect)(result.region).toBe('australiaeast');
        (0, vitest_1.expect)(result.sshPrivateKey).toContain('BEGIN OPENSSH PRIVATE KEY');
        (0, vitest_1.expect)(result.vmName).toBe('vm-personal-aue-devvm-testuser');
    });
    (0, vitest_1.it)('decrypt with wrong passphrase throws an error', async () => {
        const encrypted = encryptBundle(samplePayload, passphrase);
        const bundlePath = writeTempBundle(encrypted, 'wrong-pass.devvm-bundle');
        await (0, vitest_1.expect)((0, bundle_1.decryptBundle)(bundlePath, 'wrong-passphrase')).rejects.toThrow();
    });
    (0, vitest_1.it)('encrypted bundle JSON has all required fields', () => {
        const encrypted = encryptBundle(samplePayload, passphrase);
        const envelope = JSON.parse(encrypted);
        (0, vitest_1.expect)(envelope).toHaveProperty('version', 1);
        (0, vitest_1.expect)(envelope).toHaveProperty('format', 'devvm-bundle');
        (0, vitest_1.expect)(envelope).toHaveProperty('salt');
        (0, vitest_1.expect)(envelope).toHaveProperty('iv');
        (0, vitest_1.expect)(envelope).toHaveProperty('ciphertext');
        (0, vitest_1.expect)(envelope).toHaveProperty('tag');
    });
    (0, vitest_1.it)('decrypted payload has expected fields matching input', async () => {
        const encrypted = encryptBundle(samplePayload, passphrase);
        const bundlePath = writeTempBundle(encrypted, 'fields.devvm-bundle');
        const result = await (0, bundle_1.decryptBundle)(bundlePath, passphrase);
        (0, vitest_1.expect)(result).toEqual(samplePayload);
    });
});
//# sourceMappingURL=bundle.test.js.map