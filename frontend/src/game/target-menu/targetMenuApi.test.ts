import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiFetch } = vi.hoisted(() => ({ mockApiFetch: vi.fn() }));

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: mockApiFetch }));

import {
  fetchTargetMenu,
  markTargetMenusStale,
  targetMenuKey,
  targetMenuPrefix,
  targetMenuQueryPolicy,
} from './targetMenuApi';

const target = { kind: 'items' as const, target_id: 5 };

describe('target menu API cache contract', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('keys by login partition, actor, typed target, and context assertions', () => {
    const base = targetMenuKey('account-1:login-1', 10, target);
    expect(base).toEqual(['target-menu', 'account-1:login-1', 10, 'items', 5, null, null]);
    expect(targetMenuKey('account-2:login-1', 10, target)).not.toEqual(base);
    expect(targetMenuKey('account-1:login-1', 11, target)).not.toEqual(base);
    expect(
      targetMenuKey('account-1:login-1', 10, {
        ...target,
        owner_persona_id: 22,
      })
    ).not.toEqual(base);
    expect(
      targetMenuKey('account-1:login-1', 10, {
        ...target,
        container_item_id: 31,
      })
    ).not.toEqual(base);
  });

  it('builds the typed endpoint and sends context only when asserted', async () => {
    const body = { actor_id: 10, target, label: 'Coat', groups: [], entries: [] };
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => body });

    await expect(fetchTargetMenu(10, target)).resolves.toEqual(body);
    expect(mockApiFetch).toHaveBeenLastCalledWith('/api/actions/characters/10/items/5/menu/', {
      signal: undefined,
    });

    await fetchTargetMenu(10, { ...target, owner_persona_id: 22 });
    expect(mockApiFetch).toHaveBeenLastCalledWith(
      '/api/actions/characters/10/items/5/menu/?owner_persona_id=22',
      { signal: undefined }
    );

    await fetchTargetMenu(10, { ...target, container_item_id: 31 });
    expect(mockApiFetch).toHaveBeenLastCalledWith(
      '/api/actions/characters/10/items/5/menu/?container_item_id=31',
      { signal: undefined }
    );
  });

  it('rejects conflicting context assertions before making a request', async () => {
    const invalidTarget = {
      ...target,
      owner_persona_id: 22,
      container_item_id: 31,
    } as unknown as Parameters<typeof fetchTargetMenu>[1];

    await expect(fetchTargetMenu(10, invalidTarget)).rejects.toThrow(
      'owner_persona_id and container_item_id are mutually exclusive.'
    );
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('encodes a typed candidate cursor for deliberate chooser paging', async () => {
    const body = { actor_id: 10, target, label: 'Coat', groups: [], entries: [] };
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => body });

    await fetchTargetMenu(10, target, undefined, 'put_in', 'cursor/2');

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/actions/characters/10/items/5/menu/?inputs_for=put_in&candidate_cursor=cursor%2F2',
      { signal: undefined }
    );
  });

  it('preserves a throttling response and its deliberate retry delay', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ 'Retry-After': '17' }),
    });
    await expect(fetchTargetMenu(10, target)).rejects.toMatchObject({
      name: 'TargetMenuFetchError',
      status: 429,
      retryAfterSeconds: 17,
    });
  });

  it('does not retry or refresh an open menu from focus, reconnect, or mount', () => {
    expect(targetMenuQueryPolicy).toEqual({
      staleTime: 30_000,
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
    });
  });

  it('marks only one actor partition stale without fetching', async () => {
    const client = new QueryClient();
    const own = targetMenuKey('account-1:login-1', 10, target);
    const otherActor = targetMenuKey('account-1:login-1', 11, target);
    const otherPartition = targetMenuKey('account-2:login-1', 10, target);
    client.setQueryData(own, { entries: [] });
    client.setQueryData(otherActor, { entries: [] });
    client.setQueryData(otherPartition, { entries: [] });

    await markTargetMenusStale(client, 'account-1:login-1', 10);

    expect(client.getQueryState(own)?.isInvalidated).toBe(true);
    expect(client.getQueryState(otherActor)?.isInvalidated).toBe(false);
    expect(client.getQueryState(otherPartition)?.isInvalidated).toBe(false);
    expect(client.isFetching()).toBe(0);
    expect(targetMenuPrefix('account-1:login-1', 10)).toEqual([
      'target-menu',
      'account-1:login-1',
      10,
    ]);
    client.clear();
  });

  it('coalesces simultaneous reads for the same query key', async () => {
    const client = new QueryClient();
    let resolve!: (value: { entries: never[] }) => void;
    const queryFn = vi.fn(() => new Promise<{ entries: never[] }>((done) => (resolve = done)));
    const queryKey = targetMenuKey('account-1:login-1', 10, target);
    const first = client.fetchQuery({ queryKey, queryFn, ...targetMenuQueryPolicy });
    const second = client.fetchQuery({ queryKey, queryFn, ...targetMenuQueryPolicy });

    resolve({ entries: [] });
    await expect(Promise.all([first, second])).resolves.toEqual([{ entries: [] }, { entries: [] }]);
    expect(queryFn).toHaveBeenCalledTimes(1);
    client.clear();
  });
});
