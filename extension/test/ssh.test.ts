import { describe, it, expect } from 'vitest';
import type { BoardConfig } from '../src/config';
import {
  buildSshKeyConfigBlock,
  buildEntraIdConfigBlock,
  updateManagedBlock,
} from '../src/ssh';

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

describe('buildSshKeyConfigBlock', () => {
  it('produces config with IdentityFile, ForwardAgent, StrictHostKeyChecking', () => {
    const block = buildSshKeyConfigBlock(makeConfig());
    expect(block).toContain('IdentityFile ~/.ssh/devvm-jbloggs');
    expect(block).toContain('ForwardAgent yes');
    expect(block).toContain('StrictHostKeyChecking accept-new');
  });

  it('contains the correct hostname', () => {
    const block = buildSshKeyConfigBlock(makeConfig());
    expect(block).toContain(
      'HostName devvm-jbloggs.australiaeast.cloudapp.azure.com',
    );
  });

  it('contains the correct Host alias', () => {
    const block = buildSshKeyConfigBlock(makeConfig());
    expect(block).toMatch(/^Host devvm-jbloggs$/m);
  });
});

describe('buildEntraIdConfigBlock', () => {
  it('produces config with CertificateFile and IdentityFile', () => {
    const block = buildEntraIdConfigBlock(makeConfig({ authMethod: 'entra-id' }));
    expect(block).toContain('CertificateFile ~/.ssh/board-entra/devvm-jbloggs/id_rsa.pub-aadcert.pub');
    expect(block).toContain('IdentityFile ~/.ssh/board-entra/devvm-jbloggs/id_rsa');
    expect(block).not.toContain('ProxyCommand');
  });

  it('includes User when entraUser is provided', () => {
    const block = buildEntraIdConfigBlock(makeConfig(), 'user@tenant.onmicrosoft.com');
    expect(block).toContain('User user@tenant.onmicrosoft.com');
  });

  it('omits User when entraUser is not provided', () => {
    const block = buildEntraIdConfigBlock(makeConfig());
    expect(block).not.toContain('User ');
  });
});

describe('updateManagedBlock', () => {
  const alias = 'devvm-jbloggs';
  const newBlock = 'Host devvm-jbloggs\n    HostName example.com';

  it('appends new block to empty content', () => {
    const result = updateManagedBlock('', alias, newBlock);
    expect(result).toContain('# BEGIN board: devvm-jbloggs');
    expect(result).toContain('# END board: devvm-jbloggs');
    expect(result).toContain('Host devvm-jbloggs');
  });

  it('replaces existing block for same alias', () => {
    const existing = [
      '# BEGIN board: devvm-jbloggs',
      'Host devvm-jbloggs',
      '    HostName old.example.com',
      '# END board: devvm-jbloggs',
    ].join('\n');

    const result = updateManagedBlock(existing, alias, newBlock);
    expect(result).toContain('HostName example.com');
    expect(result).not.toContain('HostName old.example.com');
    // Should still have exactly one begin/end pair
    expect(result.match(/# BEGIN board/g)?.length).toBe(1);
    expect(result.match(/# END board/g)?.length).toBe(1);
  });

  it('preserves other content when appending', () => {
    const existing = 'Host other-server\n    HostName other.com\n';
    const result = updateManagedBlock(existing, alias, newBlock);
    expect(result).toContain('Host other-server');
    expect(result).toContain('Host devvm-jbloggs');
  });
});
