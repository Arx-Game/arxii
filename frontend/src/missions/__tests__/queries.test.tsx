/**
 * Mission Studio query hook tests.
 *
 * Mocks the api module; verifies hook shape, query-key wiring, and the
 * enabled-on-arg guards (template/giver detail hooks shouldn't fire
 * when slug is undefined; nested filters require a parent id).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import {
  missionKeys,
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
  listMissionGivers: vi.fn(),
  getMissionGiver: vi.fn(),
  listGiverOfferings: vi.fn(),
  listGiverStandings: vi.fn(),
  listPredicateLeaves: vi.fn(),
  patchMissionTemplate: vi.fn(),
  patchMissionNode: vi.fn(),
  copyTemplate: vi.fn(),
  copyNode: vi.fn(),
  copySubtree: vi.fn(),
  assignMission: vi.fn(),
  deleteMissionInstance: vi.fn(),
  createMissionGiver: vi.fn(),
  patchMissionGiver: vi.fn(),
  deleteMissionGiver: vi.fn(),
  createGiverOffering: vi.fn(),
  patchGiverOffering: vi.fn(),
  deleteGiverOffering: vi.fn(),
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
    expect(missionKeys.templateDetail('foo')).toEqual(['missions', 'templates', 'detail', 'foo']);
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
          slug: 'test',
          summary: 's',
          level_band_min: 1,
          level_band_max: 5,
          risk_tier: 1,
          arc_scope: 'global',
          cooldown: 'P1D',
          categories: [],
          access_tier: 'open',
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
    expect(result.current.data?.results[0].slug).toBe('test');
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
  it('is disabled when slug is undefined', () => {
    const { result } = renderHook(() => useMissionTemplate(undefined), {
      wrapper: wrapper(),
    });
    // Fetching never starts; queryFn never invoked.
    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getMissionTemplate).not.toHaveBeenCalled();
  });

  it('fetches when slug is provided', async () => {
    vi.mocked(api.getMissionTemplate).mockResolvedValue({
      id: 1,
      name: 'X',
      slug: 'x',
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
    const { result } = renderHook(() => useMissionTemplate('x'), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getMissionTemplate).toHaveBeenCalledWith('x');
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
  it('fetches the leaf catalog', async () => {
    vi.mocked(api.listPredicateLeaves).mockResolvedValue([
      { name: 'has_distinction', params: ['slug'] },
    ]);
    const { result } = renderHook(() => usePredicateLeaves(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ name: 'has_distinction', params: ['slug'] }]);
  });
});
