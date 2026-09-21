import { describe, expect, it } from 'vitest';
import { NarrativeBodyCache } from './narrativeRetention';

describe('NarrativeBodyCache', () => {
  it('accounts UTF-8 bytes and evicts least recently used bodies', () => {
    const cache = new NarrativeBodyCache({
      maxTemporaryPoses: 2_000,
      maxBodyBytes: 8,
      warningRatio: 0.8,
      maxMountedBodies: 150,
      maxCachedBodies: 2,
    });
    cache.put({ id: 1, timestamp: 'a', content: 'é' });
    cache.put({ id: 2, timestamp: 'b', content: 'two' });
    expect(cache.get(1, 'a')?.content).toBe('é');
    cache.put({ id: 3, timestamp: 'c', content: 'three' });
    expect(cache.get(1, 'a')).toBeDefined();
    expect(cache.get(2, 'b')).toBeUndefined();
    expect(cache.stats().entries).toBe(2);
  });

  it('clears account-scoped text and warning state', () => {
    const cache = new NarrativeBodyCache();
    cache.put({ id: 1, timestamp: 'a', content: 'pose' });
    expect(cache.stats().entries).toBe(1);
    cache.clear();
    expect(cache.stats()).toMatchObject({ entries: 0, bytes: 0, evictions: 0, warning: false });
  });
});
