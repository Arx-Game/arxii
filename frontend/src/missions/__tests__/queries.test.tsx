/**
 * Mission Studio query hook tests.
 *
 * Mocks the api module; verifies hook shape, query-key wiring, and the
 * enabled-on-arg guards (template detail hooks shouldn't fire when slug
 * is undefined; nested filters require a parent id).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import {
  missionKeys,
  useCreateMissionNode,
  useDeleteMissionNode,
  useGraphCheck,
  useOutcomeTiers,
  useMissionTemplate,
  useMissionTemplates,
  useMissionOptions,
  usePredicateLeaves,
} from '../queries';

vi.mock('../api', () => ({
  listMissionTemplates: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionNodes: vi.fn(),
  listMissionOptions: vi.fn(),
  listMissionRoutes: vi.fn(),
  listRouteCandidates: vi.fn(),
  listRouteRewards: vi.fn(),
  listPredicateLeaves: vi.fn(),
  patchMissionTemplate: vi.fn(),
  patchMissionNode: vi.fn(),
  copyTemplate: vi.fn(),
  copyNode: vi.fn(),
  copySubtree: vi.fn(),
  assignMission: vi.fn(),
  deleteMissionInstance: vi.fn(),
  createMissionTemplate: vi.fn(),
  listMissionCategories: vi.fn(),
  getGraphCheck: vi.fn(),
  listOutcomeTiers: vi.fn(),
  createMissionNode: vi.fn(),
  deleteMissionNode: vi.fn(),
  createMissionOption: vi.fn(),
  deleteMissionOption: vi.fn(),
  createMissionRoute: vi.fn(),
  patchMissionRoute: vi.fn(),
  deleteMissionRoute: vi.fn(),
}));

import * as api from '../api';

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('missionKeys', () => {
  it('namespaces under "missions"', () => {
    expect(missionKeys.all[0]).toBe('missions');
    expect(missionKeys.templates()).toEqual(['missions', 'templates']);
    expect(missionKeys.templateDetail(42)).toEqual(['missions', 'templates', 'detail', 42]);
    expect(missionKeys.predicateLeaves()).toEqual(['missions', 'predicate-leaves']);
  });

  it('encodes filter state into the list key', () => {
    const key = missionKeys.templateList({ name: 'heist', risk_tier: 5 });
    expect(key).toContain('missions');
    expect(key).toContainEqual({ name: 'heist', risk_tier: 5 });
  });
});

describe('useMissionTemplates', () => {
  beforeEach(() => {
    vi.mocked(api.listMissionTemplates).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 1,
          name: 'Test',
          summary: 's',
          level_band_min: 1,
          level_band_max: 5,
          risk_tier: 1,
          arc_scope: 'global',
          cooldown: 'P1D',
          categories: [],
          visibility: 'open',
        } as never,
      ],
    });
  });

  it('returns the paginated list', async () => {
    const { result } = renderHook(() => useMissionTemplates(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.count).toBe(1);
    expect(result.current.data?.results[0].name).toBe('Test');
  });

  it('forwards filter args to the API', async () => {
    renderHook(() => useMissionTemplates({ name: 'heist', risk_tier: 5 }), {
      wrapper: wrapper(),
    });
    await waitFor(() =>
      expect(api.listMissionTemplates).toHaveBeenCalledWith({
        name: 'heist',
        risk_tier: 5,
      })
    );
  });
});

describe('useMissionTemplate (detail)', () => {
  it('is disabled when id is undefined', () => {
    const { result } = renderHook(() => useMissionTemplate(undefined), {
      wrapper: wrapper(),
    });
    // Fetching never starts; queryFn never invoked.
    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getMissionTemplate).not.toHaveBeenCalled();
  });

  it('fetches when id is provided', async () => {
    vi.mocked(api.getMissionTemplate).mockResolvedValue({
      id: 1,
      name: 'X',
      summary: 's',
      level_band_min: 1,
      level_band_max: 5,
      risk_tier: 1,
      arc_scope: 'global',
      cooldown: 'P1D',
      categories: [],
      lifetime_completions: 0,
      active_instances: [],
    } as never);
    const { result } = renderHook(() => useMissionTemplate(1), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getMissionTemplate).toHaveBeenCalledWith(1);
  });
});

describe('useMissionOptions (parent-FK guard)', () => {
  it('is disabled when neither node nor template is provided', () => {
    renderHook(() => useMissionOptions({}), { wrapper: wrapper() });
    expect(api.listMissionOptions).not.toHaveBeenCalled();
  });

  it('fires when node is provided', async () => {
    vi.mocked(api.listMissionOptions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderHook(() => useMissionOptions({ node: 7 }), { wrapper: wrapper() });
    await waitFor(() => expect(api.listMissionOptions).toHaveBeenCalledWith({ node: 7 }));
  });
});

describe('usePredicateLeaves', () => {
  it('fetches the leaf catalog with typed params', async () => {
    // D5 now emits {name, type} per param so the FE can coerce strings
    // to int / bool / float before save.
    vi.mocked(api.listPredicateLeaves).mockResolvedValue([
      { name: 'has_distinction', params: [{ name: 'slug', type: 'str' }] },
    ]);
    const { result } = renderHook(() => usePredicateLeaves(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([
      { name: 'has_distinction', params: [{ name: 'slug', type: 'str' }] },
    ]);
  });
});

describe('graph authoring hooks (#4558)', () => {
  it('fetches the graph check for a template', async () => {
    vi.mocked(api.getGraphCheck).mockResolvedValue([
      {
        kind: 'no_entry',
        message: 'No entry node',
        node: null,
        option: null,
        route: null,
        missing_tiers: [],
      },
    ]);
    const { result } = renderHook(() => useGraphCheck(3), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getGraphCheck).toHaveBeenCalledWith(3);
    expect(result.current.data?.[0].kind).toBe('no_entry');
  });

  it('loads outcome tiers', async () => {
    vi.mocked(api.listOutcomeTiers).mockResolvedValue([
      { id: 1, name: 'Success', success_level: 1, rolled_by_checks: true },
    ]);
    const { result } = renderHook(() => useOutcomeTiers(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].name).toBe('Success');
  });

  it('creating a node invalidates nodes and the graph check', async () => {
    vi.mocked(api.createMissionNode).mockResolvedValue({ id: 9 } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const w = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCreateMissionNode(), { wrapper: w });
    await act(async () => {
      await result.current.mutateAsync({ template: 3, key: 'start', is_entry: true });
    });
    const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(missionKeys.nodes());
    expect(keys).toContainEqual(missionKeys.graphChecks());
  });

  it('a delete refused with 409 surfaces the server message', async () => {
    vi.mocked(api.deleteMissionNode).mockRejectedValue(
      new Error('A mission run has recorded this node.')
    );
    const { result } = renderHook(() => useDeleteMissionNode(), { wrapper: wrapper() });
    await act(async () => {
      await result.current.mutateAsync(4).catch(() => undefined);
    });
    await waitFor(() =>
      expect(result.current.error?.message).toBe('A mission run has recorded this node.')
    );
  });
});
