import * as vscode from 'vscode';

export interface BoardConfig {
  developerName: string;
  resourceGroup: string;
  region: string;
  authMethod: 'ssh-key' | 'entra-id';
  autoStartVm: boolean;
  autoOpenTerminals: boolean;
  pollIntervalSeconds: number;
  tunnelUrl: string;
}

/** Read current settings from VS Code workspace configuration */
export function getConfig(): BoardConfig {
  const cfg = vscode.workspace.getConfiguration('board');
  return {
    developerName: cfg.get<string>('developerName', ''),
    resourceGroup: cfg.get<string>('resourceGroup', ''),
    region: cfg.get<string>('region', 'australiaeast'),
    authMethod: cfg.get<'ssh-key' | 'entra-id'>('authMethod', 'entra-id'),
    autoStartVm: cfg.get<boolean>('autoStartVm', true),
    autoOpenTerminals: cfg.get<boolean>('autoOpenTerminals', true),
    pollIntervalSeconds: cfg.get<number>('pollIntervalSeconds', 60),
    tunnelUrl: cfg.get<string>('tunnelUrl', ''),
  };
}

/** Check whether minimum required settings (developerName, resourceGroup) are configured */
export function isConfigured(): boolean {
  const cfg = getConfig();
  return cfg.developerName.length > 0 && cfg.resourceGroup.length > 0;
}

/** Derive the SSH host alias: `devvm-<name>` */
export function getSshHostAlias(config: BoardConfig): string {
  return `devvm-${config.developerName}`;
}

/** Derive the VM FQDN: `devvm-<name>.<region>.cloudapp.azure.com` */
export function getHostname(config: BoardConfig): string {
  return `devvm-${config.developerName}.${config.region}.cloudapp.azure.com`;
}

/** Return the configured resource group name (must already exist in Azure) */
export function getResourceGroup(config: BoardConfig): string {
  return config.resourceGroup;
}

/** Derive the VM name: `vm-<rg-suffix>-<name>`, where rg-suffix strips a leading `rg-`. */
export function getVmName(config: BoardConfig): string {
  const suffix = config.resourceGroup.startsWith('rg-')
    ? config.resourceGroup.slice(3)
    : config.resourceGroup;
  return `vm-${suffix}-${config.developerName}`;
}

/** Derive the SSH key path: `~/.ssh/devvm-<name>` */
export function getSshKeyPath(config: BoardConfig): string {
  return `~/.ssh/devvm-${config.developerName}`;
}

/** Get the tunnel URL for the current board */
export function getTunnelUrl(config: BoardConfig): string {
  if (config.tunnelUrl) {
    return config.tunnelUrl;
  }
  // Derive from developer name if not explicitly set
  if (config.developerName) {
    return `https://vscode.dev/tunnel/devvm-${config.developerName}`;
  }
  return '';
}

/** Azure Portal URL for this VM */
export function getPortalUrl(_config: BoardConfig): string {
  return 'https://portal.azure.com';
}
