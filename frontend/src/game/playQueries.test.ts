import { describe, it, expect, vi, afterEach } from 'vitest';
import { fetchPlayContext } from './playQueries';

describe('getJson error shape', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('attaches the response status to the thrown error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 404 })));

    await expect(
      fetchPlayContext({ id: '1', timestamp: '2026-01-01T00:00:00.000Z' })
    ).rejects.toMatchObject({ status: 404 });

    vi.unstubAllGlobals();
  });
});
