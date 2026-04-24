import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs/promises';
import { execFile } from 'child_process';
import { promisify } from 'util';
import {
  BoardConfig,
  getSshHostAlias,
  getHostname,
  getResourceGroup,
  getVmName,
  getSshKeyPath,
} from './config';

const execFileAsync = promisify(execFile);

const MARKER_PREFIX = '# BEGIN board:';
const MARKER_SUFFIX = '# END board:';

/** The SSH config block to write for SSH key auth */
export function buildSshKeyConfigBlock(config: BoardConfig): string {
  const alias = getSshHostAlias(config);
  const hostname = getHostname(config);
  const keyPath = getSshKeyPath(config);

  return [
    `Host ${alias}`,
    `    HostName ${hostname}`,
    '    User devuser',
    `    IdentityFile ${keyPath}`,
    '    ForwardAgent yes',
    '    ServerAliveInterval 60',
    '    ServerAliveCountMax 3',
    '    StrictHostKeyChecking accept-new',
  ].join('\n');
}

/** The SSH config block to write for Entra ID auth */
export function buildEntraIdConfigBlock(config: BoardConfig): string {
  const alias = getSshHostAlias(config);
  const hostname = getHostname(config);
  const rg = getResourceGroup(config);
  const vm = getVmName(config);

  return [
    `Host ${alias}`,
    `    HostName ${hostname}`,
    `    ProxyCommand az ssh proxy --resource-group ${rg} --vm-name ${vm} --port %p`,
    '    ForwardAgent yes',
    '    ServerAliveInterval 60',
    '    ServerAliveCountMax 3',
    '    LocalForward 8080 127.0.0.1:8080',
    '    LocalForward 9091 127.0.0.1:9190',
    '    LocalForward 9444 127.0.0.1:9443',
  ].join('\n');
}

/** Get the path to the user's SSH config file. Cross-platform. */
export function getSshConfigPath(): string {
  return path.join(os.homedir(), '.ssh', 'config');
}

/** Read the SSH config file, returns empty string if not found */
export async function readSshConfig(): Promise<string> {
  try {
    return await fs.readFile(getSshConfigPath(), 'utf-8');
  } catch {
    return '';
  }
}

/**
 * Pure function: update managed block within SSH config content string.
 * If a block for this host alias already exists, replace it.
 * If not, append it.
 */
export function updateManagedBlock(
  existingContent: string,
  hostAlias: string,
  newBlock: string,
): string {
  const beginMarker = `${MARKER_PREFIX} ${hostAlias}`;
  const endMarker = `${MARKER_SUFFIX} ${hostAlias}`;
  const managedBlock = `${beginMarker}\n${newBlock}\n${endMarker}`;

  const beginIdx = existingContent.indexOf(beginMarker);
  const endIdx = existingContent.indexOf(endMarker);

  if (beginIdx !== -1 && endIdx !== -1) {
    // Replace existing block
    const before = existingContent.substring(0, beginIdx);
    const after = existingContent.substring(endIdx + endMarker.length);
    return before + managedBlock + after;
  }

  // Append new block
  if (existingContent.length === 0) {
    return managedBlock + '\n';
  }

  // Ensure there's a blank line before the new block
  const separator = existingContent.endsWith('\n') ? '\n' : '\n\n';
  return existingContent + separator + managedBlock + '\n';
}

/**
 * Write/update the managed host block in SSH config.
 * Preserves other entries. If a block for this host alias already exists,
 * replace it. If not, append it. Creates the file + .ssh directory if
 * they don't exist.
 */
export async function writeSshConfig(config: BoardConfig): Promise<void> {
  const sshDir = path.join(os.homedir(), '.ssh');
  const configPath = getSshConfigPath();
  const hostAlias = getSshHostAlias(config);

  // Ensure ~/.ssh directory exists
  await fs.mkdir(sshDir, { recursive: true, mode: 0o700 });

  // Build the appropriate config block
  const block =
    config.authMethod === 'entra-id'
      ? buildEntraIdConfigBlock(config)
      : buildSshKeyConfigBlock(config);

  // Read existing content, update, and write back
  const existing = await readSshConfig();
  const updated = updateManagedBlock(existing, hostAlias, block);

  await fs.writeFile(configPath, updated, { encoding: 'utf-8', mode: 0o600 });
}

/** Remove the managed host block from SSH config */
export async function removeSshConfig(hostAlias: string): Promise<void> {
  const configPath = getSshConfigPath();
  let content: string;

  try {
    content = await fs.readFile(configPath, 'utf-8');
  } catch {
    return; // File doesn't exist, nothing to remove
  }

  const beginMarker = `${MARKER_PREFIX} ${hostAlias}`;
  const endMarker = `${MARKER_SUFFIX} ${hostAlias}`;

  const beginIdx = content.indexOf(beginMarker);
  const endIdx = content.indexOf(endMarker);

  if (beginIdx === -1 || endIdx === -1) {
    return; // Block not found, nothing to remove
  }

  const before = content.substring(0, beginIdx);
  const after = content.substring(endIdx + endMarker.length);

  // Clean up extra blank lines at the junction
  const cleaned = (before + after).replace(/\n{3,}/g, '\n\n').trim();
  const result = cleaned.length > 0 ? cleaned + '\n' : '';

  await fs.writeFile(configPath, result, { encoding: 'utf-8', mode: 0o600 });
}

/** Check if the SSH key file exists at the expected path */
export async function sshKeyExists(config: BoardConfig): Promise<boolean> {
  const keyPath = getSshKeyPath(config);
  // Expand ~ to homedir
  const resolved = keyPath.replace(/^~/, os.homedir());
  try {
    await fs.access(resolved);
    return true;
  } catch {
    return false;
  }
}

/** Write an SSH private key to disk with correct permissions (0600 on Unix) */
export async function writeSshKey(
  keyPath: string,
  content: string,
): Promise<void> {
  // Expand ~ to homedir
  const resolved = keyPath.replace(/^~/, os.homedir());
  const dir = path.dirname(resolved);

  // Ensure directory exists
  await fs.mkdir(dir, { recursive: true, mode: 0o700 });

  // Write the key file
  await fs.writeFile(resolved, content, { encoding: 'utf-8', mode: 0o600 });

  // On Windows, use icacls to restrict permissions since mode is ignored
  if (process.platform === 'win32') {
    const username = os.userInfo().username;
    await execFileAsync('icacls', [
      resolved,
      '/inheritance:r',
      '/grant:r',
      `${username}:(F)`,
    ]);
  }
}
