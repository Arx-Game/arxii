import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, matchQuery, type InfiniteData } from '@tanstack/react-query';

const { fetchInteractionMock } = vi.hoisted(() => ({ fetchInteractionMock: vi.fn() }));

vi.mock('@/scenes/queries', () => ({ fetchInteraction: fetchInteractionMock }));

import { refreshSceneFeedRow, sceneFeedQueryKey, sceneFeedSceneKey } from '@/scenes/sceneFeedCache';
import { ApiError } from '@/lib/errors';
import type { Interaction } from '@/scenes/types';

type Pages = InfiniteData<{ results: Interaction[]; next?: string }>;

// Ids rise with time, so the timestamp follows the id.
const row = (id: number, endorsers: unknown[] = []) =>
  ({
    id,
    pose_endorsers: endorsers,
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, id)).toISOString(),
  }) as unknown as Interaction;

describe('sceneFeedCache keys', () => {
  it('puts the scene second so a scene prefix matches the feed', () => {
    const key = sceneFeedQueryKey({ sceneId: 7, accountId: 3, viewerKey: 'Ann' });
    expect(key[1]).toBe('7');
    expect(matchQuery({ queryKey: sceneFeedSceneKey('7') }, { queryKey: key } as never)).toBe(true);
    expect(matchQuery({ queryKey: sceneFeedSceneKey('8') }, { queryKey: key } as never)).toBe(
      false
    );
  });

  it('gives two accounts different keys', () => {
    const a = sceneFeedQueryKey({ sceneId: 7, accountId: 3, viewerKey: 'Ann' });
    const b = sceneFeedQueryKey({ sceneId: 7, accountId: 4, viewerKey: 'Ann' });
    expect(a).not.toEqual(b);
  });
});

function deferred() {
  let resolve!: (value: Interaction) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Interaction>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('refreshSceneFeedRow', () => {
  let client: QueryClient;
  const key = sceneFeedQueryKey({ sceneId: 7, accountId: 3, viewerKey: 'Ann' });
  const seed = () =>
    client.setQueryData<Pages>(key, {
      pages: [{ results: [row(6), row(5)], next: 'x' }, { results: [row(4)] }],
      pageParams: [undefined, 'x'],
    });

  beforeEach(() => {
    vi.clearAllMocks();
    client = new QueryClient();
  });

  it('replaces a row in place', async () => {
    seed();
    fetchInteractionMock.mockResolvedValue(row(5, [{ sheet_id: 1 }]));
    await refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 });
    const data = client.getQueryData<Pages>(key)!;
    expect(data.pages[0].results.map((r) => r.id)).toEqual([6, 5]);
    expect(data.pages[0].results[1].pose_endorsers).toHaveLength(1);
  });

  it('adds a row that only the live store had to the newest end of the newest page', async () => {
    seed();
    fetchInteractionMock.mockResolvedValue(row(9));
    await refreshSceneFeedRow(client, { interactionId: 9, sceneId: 7 });
    const data = client.getQueryData<Pages>(key)!;
    expect(data.pages[0].results.map((r) => r.id)).toEqual([9, 6, 5]);
    expect(data.pages[1].results.map((r) => r.id)).toEqual([4]);
  });

  it('does not add a row older than everything loaded, since paging will bring it', async () => {
    seed();
    const before = client.getQueryData<Pages>(key);
    fetchInteractionMock.mockResolvedValue(row(2));
    await refreshSceneFeedRow(client, { interactionId: 2, sceneId: 7 });
    expect(client.getQueryData<Pages>(key)!.pages.map((p) => p.results.map((r) => r.id))).toEqual(
      before!.pages.map((p) => p.results.map((r) => r.id))
    );
  });

  it('does not add a row tied with the oldest loaded row', async () => {
    seed();
    fetchInteractionMock.mockResolvedValue({ ...row(99), timestamp: row(4).timestamp });
    await refreshSceneFeedRow(client, { interactionId: 99, sceneId: 7 });
    const ids = client.getQueryData<Pages>(key)!.pages.flatMap((p) => p.results.map((r) => r.id));
    expect(ids).toEqual([6, 5, 4]);
  });

  it('does not fetch when no feed for the scene is cached', async () => {
    await refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 });
    expect(fetchInteractionMock).not.toHaveBeenCalled();
  });

  it('coalesces frames that arrive during a fetch into one follow-up fetch', async () => {
    seed();
    const first = deferred();
    fetchInteractionMock.mockReturnValueOnce(first.promise).mockResolvedValue(row(5, [{}]));
    const calls = [1, 2, 3].map(() =>
      refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 })
    );
    expect(fetchInteractionMock).toHaveBeenCalledTimes(1);
    first.resolve(row(5));
    await Promise.all(calls);
    expect(fetchInteractionMock).toHaveBeenCalledTimes(2);
    expect(client.getQueryData<Pages>(key)!.pages[0].results[1].pose_endorsers).toHaveLength(1);
  });

  it('still runs the follow-up fetch when the in-flight one fails', async () => {
    seed();
    const first = deferred();
    fetchInteractionMock.mockReturnValueOnce(first.promise).mockResolvedValue(row(5, [{}]));
    const calls = [1, 2].map(() => refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 }));
    first.reject(new ApiError('boom', { status: 500 }));
    await Promise.all(calls);
    expect(fetchInteractionMock).toHaveBeenCalledTimes(2);
    expect(client.getQueryData<Pages>(key)!.pages[0].results[1].pose_endorsers).toHaveLength(1);
  });

  it('fetches again for a pose once its earlier fetch has finished', async () => {
    seed();
    fetchInteractionMock.mockResolvedValue(row(5));
    await refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 });
    await refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 });
    expect(fetchInteractionMock).toHaveBeenCalledTimes(2);
  });

  it.each([403, 404])('ignores a %i and leaves the cache unchanged', async (status) => {
    seed();
    const before = client.getQueryData<Pages>(key);
    fetchInteractionMock.mockRejectedValue(new ApiError('nope', { status }));
    await expect(
      refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 })
    ).resolves.toBeUndefined();
    expect(client.getQueryData<Pages>(key)).toBe(before);
  });

  it('surfaces a 500 and a network failure', async () => {
    seed();
    const before = client.getQueryData<Pages>(key);
    fetchInteractionMock.mockRejectedValueOnce(new ApiError('boom', { status: 500 }));
    await expect(refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 })).rejects.toThrow(
      'boom'
    );
    fetchInteractionMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 })).rejects.toThrow(
      'Failed to fetch'
    );
    expect(client.getQueryData<Pages>(key)).toBe(before);
  });
});
