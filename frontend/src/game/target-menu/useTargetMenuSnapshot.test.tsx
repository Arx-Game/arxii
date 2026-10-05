import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiFetch } = vi.hoisted(() => ({ mockApiFetch: vi.fn() }));
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: mockApiFetch }));

import { useTargetMenuSnapshot } from './useTargetMenuSnapshot';
import { targetMenuKey, type TargetMenuData } from './targetMenuApi';

const target = { kind: 'items' as const, target_id: 5 };
const payload = (label: string): TargetMenuData => ({
  actor_id: 10,
  target,
  label,
  groups: [],
  entries: [],
});

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    ({ open, actorId = 10 }: { open: boolean; actorId?: number | null }) =>
      useTargetMenuSnapshot('account-1', actorId, target, open),
    { initialProps: { open: true, actorId: 10 as number | null }, wrapper }
  );
  return { ...hook, client };
}

describe('useTargetMenuSnapshot', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('keeps the successful opening snapshot despite later cache changes', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => payload('First view') });
    const { result, client, rerender } = setup();
    await waitFor(() => expect(result.current.data?.label).toBe('First view'));

    client.setQueryData(targetMenuKey('account-1', 10, target), payload('Later cache data'));
    expect(result.current.data?.label).toBe('First view');

    rerender({ open: false, actorId: 10 });
    expect(result.current.data).toBeNull();
    client.clear();
  });

  it('does not refetch when a parent recreates an unchanged target assertion', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => payload('Stable view') });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result, rerender } = renderHook(
      ({ currentTarget }: { currentTarget: typeof target }) =>
        useTargetMenuSnapshot('account-1', 10, currentTarget, true),
      { initialProps: { currentTarget: { ...target } }, wrapper }
    );
    await waitFor(() => expect(result.current.data?.label).toBe('Stable view'));

    rerender({ currentTarget: { ...target } });
    expect(result.current.data?.label).toBe('Stable view');
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    client.clear();
  });

  it('uses a fresh cached response on a new opening without another request', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => payload('Cached view') });
    const { result, rerender, client } = setup();
    await waitFor(() => expect(result.current.data?.label).toBe('Cached view'));
    rerender({ open: false, actorId: 10 });
    rerender({ open: true, actorId: 10 });
    await waitFor(() => expect(result.current.data?.label).toBe('Cached view'));
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    client.clear();
  });

  it('ignores a response from an opening that has already closed', async () => {
    let resolve!: (response: { ok: boolean; json: () => Promise<TargetMenuData> }) => void;
    mockApiFetch.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      })
    );
    const { result, rerender, client } = setup();
    rerender({ open: false, actorId: 10 });
    await act(async () => {
      resolve({ ok: true, json: async () => payload('Late response') });
      await Promise.resolve();
    });
    expect(result.current.data).toBeNull();
    expect(result.current.isLoading).toBe(false);
    client.clear();
  });

  it('clears displayed data when actor identity changes', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => payload('First view') });
    const { result, rerender, client } = setup();
    await waitFor(() => expect(result.current.data?.label).toBe('First view'));
    mockApiFetch.mockResolvedValue({ ok: true, json: async () => payload('Other actor') });
    rerender({ open: true, actorId: 11 });
    expect(result.current.data).toBeNull();
    await waitFor(() => expect(result.current.data?.label).toBe('Other actor'));
    client.clear();
  });
});
