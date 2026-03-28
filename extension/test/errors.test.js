"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const vitest_1 = require("vitest");
const errors_1 = require("../src/errors");
(0, vitest_1.describe)('getErrorInfo', () => {
    (0, vitest_1.it)('vm-stopped returns message containing "stopped" and action with devvm.start', () => {
        const info = (0, errors_1.getErrorInfo)('vm-stopped');
        (0, vitest_1.expect)(info.message.toLowerCase()).toContain('stopped');
        (0, vitest_1.expect)(info.actions).toEqual(vitest_1.expect.arrayContaining([
            vitest_1.expect.objectContaining({ command: 'devvm.start' }),
        ]));
    });
    (0, vitest_1.it)('remote-ssh-missing returns message about Remote-SSH', () => {
        const info = (0, errors_1.getErrorInfo)('remote-ssh-missing');
        (0, vitest_1.expect)(info.message).toContain('Remote-SSH');
    });
    (0, vitest_1.it)('ssh-key-missing returns action to import bundle', () => {
        const info = (0, errors_1.getErrorInfo)('ssh-key-missing');
        (0, vitest_1.expect)(info.actions).toEqual(vitest_1.expect.arrayContaining([
            vitest_1.expect.objectContaining({ command: 'devvm.importBundle' }),
        ]));
    });
    (0, vitest_1.it)('host-key-changed provides a non-empty message and action', () => {
        const info = (0, errors_1.getErrorInfo)('host-key-changed');
        (0, vitest_1.expect)(info.message.length).toBeGreaterThan(0);
        (0, vitest_1.expect)(info.actions.length).toBeGreaterThan(0);
    });
});
(0, vitest_1.describe)('isHostKeyChanged', () => {
    (0, vitest_1.it)('returns true for REMOTE HOST IDENTIFICATION HAS CHANGED', () => {
        const output = '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n' +
            '@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @\n' +
            '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@';
        (0, vitest_1.expect)((0, errors_1.isHostKeyChanged)(output)).toBe(true);
    });
    (0, vitest_1.it)('returns true for Host key verification failed', () => {
        (0, vitest_1.expect)((0, errors_1.isHostKeyChanged)('Host key verification failed.')).toBe(true);
    });
    (0, vitest_1.it)('returns false for normal SSH output', () => {
        (0, vitest_1.expect)((0, errors_1.isHostKeyChanged)('Welcome to Ubuntu 24.04 LTS')).toBe(false);
    });
    (0, vitest_1.it)('returns false for empty string', () => {
        (0, vitest_1.expect)((0, errors_1.isHostKeyChanged)('')).toBe(false);
    });
});
//# sourceMappingURL=errors.test.js.map