import { describe, it, expect } from 'vitest';
import type { BoardConfig } from '../src/config';
import {
  getSshHostAlias,
  getHostname,
  getResourceGroup,
  getVmName,
  getSshKeyPath,
  getPortalUrl,
} from '../src/config';

/** Reusable default config for the majority of tests */
function makeConfig(overrides: Partial<BoardConfig> = {}): BoardConfig {
  return {
    developerName: 'jbloggs',
    resourceGroup: 'rg-personal-aue-devvm',
    region: 'australiaeast',
    authMethod: 'ssh-key',
    autoStartVm: true,
    autoOpenTerminals: true,
    pollIntervalSeconds: 60,
    tunnelUrl: '',
    ...overrides,
  };
}

describe('config — pure derivation functions', () => {
  it('getSshHostAlias returns devvm-<name>', () => {
    expect(getSshHostAlias(makeConfig())).toBe('devvm-jbloggs');
  });

  it('getHostname returns FQDN with region', () => {
    expect(getHostname(makeConfig())).toBe(
      'devvm-jbloggs.australiaeast.cloudapp.azure.com',
    );
  });

  it('getResourceGroup returns the configured resourceGroup', () => {
    expect(getResourceGroup(makeConfig())).toBe('rg-personal-aue-devvm');
  });

  it('getVmName strips leading rg- and appends developer name', () => {
    expect(getVmName(makeConfig())).toBe('vm-personal-aue-devvm-jbloggs');
  });

  it('getSshKeyPath returns path ending in .ssh/devvm-<name>', () => {
    const result = getSshKeyPath(makeConfig());
    expect(result).toMatch(/\.ssh\/devvm-jbloggs$/);
  });

  it('getResourceGroup returns a different configured group', () => {
    expect(
      getResourceGroup(makeConfig({ resourceGroup: 'rg-sandbox-aue-devvm' })),
    ).toBe('rg-sandbox-aue-devvm');
  });

  it('getVmName falls back to raw resourceGroup when no rg- prefix', () => {
    expect(getVmName(makeConfig({ resourceGroup: 'team-platform' }))).toBe(
      'vm-team-platform-jbloggs',
    );
  });

  it('getHostname uses a different region', () => {
    expect(
      getHostname(makeConfig({ region: 'westus2' })),
    ).toBe('devvm-jbloggs.westus2.cloudapp.azure.com');
  });

  it('getPortalUrl returns Azure portal URL', () => {
    expect(getPortalUrl(makeConfig())).toBe('https://portal.azure.com');
  });
});
