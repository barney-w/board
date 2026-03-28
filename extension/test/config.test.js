"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const vitest_1 = require("vitest");
const config_1 = require("../src/config");
/** Reusable default config for the majority of tests */
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
(0, vitest_1.describe)('config — pure derivation functions', () => {
    (0, vitest_1.it)('getSshHostAlias returns devvm-<name>', () => {
        (0, vitest_1.expect)((0, config_1.getSshHostAlias)(makeConfig())).toBe('devvm-jbloggs');
    });
    (0, vitest_1.it)('getHostname returns FQDN with region', () => {
        (0, vitest_1.expect)((0, config_1.getHostname)(makeConfig())).toBe('devvm-jbloggs.australiaeast.cloudapp.azure.com');
    });
    (0, vitest_1.it)('getResourceGroup returns rg-<env>-<regionShort>-devvm', () => {
        (0, vitest_1.expect)((0, config_1.getResourceGroup)(makeConfig())).toBe('rg-personal-aue-devvm');
    });
    (0, vitest_1.it)('getVmName returns vm-<env>-<regionShort>-devvm-<name>', () => {
        (0, vitest_1.expect)((0, config_1.getVmName)(makeConfig())).toBe('vm-personal-aue-devvm-jbloggs');
    });
    (0, vitest_1.it)('getSshKeyPath returns path ending in .ssh/devvm-<name>', () => {
        const result = (0, config_1.getSshKeyPath)(makeConfig());
        (0, vitest_1.expect)(result).toMatch(/\.ssh\/devvm-jbloggs$/);
    });
    (0, vitest_1.it)('getResourceGroup uses environment field — sandbox', () => {
        (0, vitest_1.expect)((0, config_1.getResourceGroup)(makeConfig({ environment: 'sandbox' }))).toBe('rg-sandbox-aue-devvm');
    });
    (0, vitest_1.it)('getHostname uses a different region', () => {
        (0, vitest_1.expect)((0, config_1.getHostname)(makeConfig({ region: 'westus2' }))).toBe('devvm-jbloggs.westus2.cloudapp.azure.com');
    });
    (0, vitest_1.it)('getPortalUrl returns Azure portal URL', () => {
        (0, vitest_1.expect)((0, config_1.getPortalUrl)(makeConfig())).toBe('https://portal.azure.com');
    });
});
//# sourceMappingURL=config.test.js.map