"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const vitest_1 = require("vitest");
const ssh_1 = require("../src/ssh");
function makeConfig(overrides = {}) {
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
(0, vitest_1.describe)('buildSshKeyConfigBlock', () => {
    (0, vitest_1.it)('produces config with IdentityFile, ForwardAgent, StrictHostKeyChecking', () => {
        const block = (0, ssh_1.buildSshKeyConfigBlock)(makeConfig());
        (0, vitest_1.expect)(block).toContain('IdentityFile ~/.ssh/devvm-jbloggs');
        (0, vitest_1.expect)(block).toContain('ForwardAgent yes');
        (0, vitest_1.expect)(block).toContain('StrictHostKeyChecking accept-new');
    });
    (0, vitest_1.it)('contains the correct hostname', () => {
        const block = (0, ssh_1.buildSshKeyConfigBlock)(makeConfig());
        (0, vitest_1.expect)(block).toContain('HostName devvm-jbloggs.australiaeast.cloudapp.azure.com');
    });
    (0, vitest_1.it)('contains the correct Host alias', () => {
        const block = (0, ssh_1.buildSshKeyConfigBlock)(makeConfig());
        (0, vitest_1.expect)(block).toMatch(/^Host devvm-jbloggs$/m);
    });
});
(0, vitest_1.describe)('buildEntraIdConfigBlock', () => {
    (0, vitest_1.it)('produces config with ProxyCommand and no IdentityFile', () => {
        const block = (0, ssh_1.buildEntraIdConfigBlock)(makeConfig({ authMethod: 'entra-id' }));
        (0, vitest_1.expect)(block).toContain('ProxyCommand az ssh proxy');
        (0, vitest_1.expect)(block).not.toContain('IdentityFile');
    });
    (0, vitest_1.it)('includes resource group and vm name in ProxyCommand', () => {
        const block = (0, ssh_1.buildEntraIdConfigBlock)(makeConfig());
        (0, vitest_1.expect)(block).toContain('--resource-group rg-personal-aue-devvm');
        (0, vitest_1.expect)(block).toContain('--vm-name vm-personal-aue-devvm-jbloggs');
    });
});
(0, vitest_1.describe)('updateManagedBlock', () => {
    const alias = 'devvm-jbloggs';
    const newBlock = 'Host devvm-jbloggs\n    HostName example.com';
    (0, vitest_1.it)('appends new block to empty content', () => {
        const result = (0, ssh_1.updateManagedBlock)('', alias, newBlock);
        (0, vitest_1.expect)(result).toContain('# BEGIN devvm-connect: devvm-jbloggs');
        (0, vitest_1.expect)(result).toContain('# END devvm-connect: devvm-jbloggs');
        (0, vitest_1.expect)(result).toContain('Host devvm-jbloggs');
    });
    (0, vitest_1.it)('replaces existing block for same alias', () => {
        const existing = [
            '# BEGIN devvm-connect: devvm-jbloggs',
            'Host devvm-jbloggs',
            '    HostName old.example.com',
            '# END devvm-connect: devvm-jbloggs',
        ].join('\n');
        const result = (0, ssh_1.updateManagedBlock)(existing, alias, newBlock);
        (0, vitest_1.expect)(result).toContain('HostName example.com');
        (0, vitest_1.expect)(result).not.toContain('HostName old.example.com');
        // Should still have exactly one begin/end pair
        (0, vitest_1.expect)(result.match(/# BEGIN devvm-connect/g)?.length).toBe(1);
        (0, vitest_1.expect)(result.match(/# END devvm-connect/g)?.length).toBe(1);
    });
    (0, vitest_1.it)('preserves other content when appending', () => {
        const existing = 'Host other-server\n    HostName other.com\n';
        const result = (0, ssh_1.updateManagedBlock)(existing, alias, newBlock);
        (0, vitest_1.expect)(result).toContain('Host other-server');
        (0, vitest_1.expect)(result).toContain('Host devvm-jbloggs');
    });
});
//# sourceMappingURL=ssh.test.js.map