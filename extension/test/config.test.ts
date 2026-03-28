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
    environment: 'personal',
    region: 'australiaeast',
    regionShort: 'aue',
    authMethod: 'ssh-key',
    autoStartVm: true,
    pollIntervalSeconds: 60,
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

  it('getResourceGroup returns rg-<env>-<regionShort>-devvm', () => {
    expect(getResourceGroup(makeConfig())).toBe('rg-personal-aue-devvm');
  });

  it('getVmName returns vm-<env>-<regionShort>-devvm-<name>', () => {
    expect(getVmName(makeConfig())).toBe('vm-personal-aue-devvm-jbloggs');
  });

  it('getSshKeyPath returns path ending in .ssh/devvm-<name>', () => {
    const result = getSshKeyPath(makeConfig());
    expect(result).toMatch(/\.ssh\/devvm-jbloggs$/);
  });

  it('getResourceGroup uses environment field — sandbox', () => {
    expect(getResourceGroup(makeConfig({ environment: 'sandbox' }))).toBe(
      'rg-sandbox-aue-devvm',
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
