import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, matchQuery, type InfiniteData } from '@tanstack/react-query';

const { fetchInteractionMock } = vi.hoisted(() => ({ fetchInteractionMock: vi.fn() }));

vi.mock('@/scenes/queries', () => ({ fetchInteraction: fetchInteractionMock }));

import { refreshSceneFeedRow, sceneFeedQueryKey, sceneFeedSceneKey } from '@/scenes/sceneFeedCache';
import type { Interaction } from '@/scenes/types';

type Pages = InfiniteData<{ results: Interaction[]; next?: string }>;

const row = (id: number, endorsers: unknown[] = []) =>
  ({ id, pose_endorsers: endorsers }) as unknown as Interaction;

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

  it('ignores a failed fetch such as a 404', async () => {
    seed();
    const before = client.getQueryData<Pages>(key);
    fetchInteractionMock.mockRejectedValue(new Error('Failed to load interaction'));
    await expect(
      refreshSceneFeedRow(client, { interactionId: 5, sceneId: 7 })
    ).resolves.toBeUndefined();
    expect(client.getQueryData<Pages>(key)).toBe(before);
  });
});
