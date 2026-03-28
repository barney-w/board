import { describe, it, expect } from 'vitest';
import { getErrorInfo, isHostKeyChanged } from '../src/errors';

describe('getErrorInfo', () => {
  it('vm-stopped returns message containing "stopped" and action with board.start', () => {
    const info = getErrorInfo('vm-stopped');
    expect(info.message.toLowerCase()).toContain('stopped');
    expect(info.actions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ command: 'board.start' }),
      ]),
    );
  });

  it('remote-ssh-missing returns message about Remote-SSH', () => {
    const info = getErrorInfo('remote-ssh-missing');
    expect(info.message).toContain('Remote-SSH');
  });

  it('ssh-key-missing returns action to import bundle', () => {
    const info = getErrorInfo('ssh-key-missing');
    expect(info.actions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ command: 'board.importPass' }),
      ]),
    );
  });

  it('host-key-changed provides a non-empty message and action', () => {
    const info = getErrorInfo('host-key-changed');
    expect(info.message.length).toBeGreaterThan(0);
    expect(info.actions.length).toBeGreaterThan(0);
  });
});

describe('isHostKeyChanged', () => {
  it('returns true for REMOTE HOST IDENTIFICATION HAS CHANGED', () => {
    const output =
      '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n' +
      '@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @\n' +
      '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@';
    expect(isHostKeyChanged(output)).toBe(true);
  });

  it('returns true for Host key verification failed', () => {
    expect(isHostKeyChanged('Host key verification failed.')).toBe(true);
  });

  it('returns false for normal SSH output', () => {
    expect(isHostKeyChanged('Welcome to Ubuntu 24.04 LTS')).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isHostKeyChanged('')).toBe(false);
  });
});
