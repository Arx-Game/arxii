/**
 * Tests for the per-tab browsing identity store (#3479).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readTabIdentity, writeTabIdentity, clearTabIdentity } from '../browsingIdentity';

describe('tab identity store', () => {
  beforeEach(() => sessionStorage.clear());

  it('is empty in a fresh context', () => {
    expect(readTabIdentity()).toBeNull();
  });

  it('round-trips an entry id and keeps one tab id across writes', () => {
    writeTabIdentity(7);
    const a = readTabIdentity();
    writeTabIdentity(9);
    const b = readTabIdentity();
    expect(a?.entryId).toBe(7);
    expect(b?.entryId).toBe(9);
    expect(b?.tabId).toBe(a?.tabId);
  });

  it('survives a storage failure without throwing', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    expect(() => writeTabIdentity(1)).not.toThrow();
    spy.mockRestore();
  });

  it('clears a stored identity', () => {
    writeTabIdentity(3);
    expect(readTabIdentity()).not.toBeNull();
    clearTabIdentity();
    expect(readTabIdentity()).toBeNull();
  });

  it('survives a clear failure without throwing', () => {
    const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('unavailable');
    });
    expect(() => clearTabIdentity()).not.toThrow();
    spy.mockRestore();
  });

  it('treats unparsable stored JSON as empty', () => {
    sessionStorage.setItem('arx.tabIdentity', 'not json');
    expect(readTabIdentity()).toBeNull();
  });
});
