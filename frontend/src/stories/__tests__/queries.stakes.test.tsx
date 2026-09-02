/**
 * Stakes query hooks tests (#3561) - key factory shapes plus the
 * create-stake mutation's cascading invalidation (stakes list, beat
 * readiness, and the player-safe stakes summary all key off the beat).
 *
 * Mirrors the mock/wrapper pattern in stories/__tests__/queries.test.tsx.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  storiesKeys,
  useCreateStake,
  useCreateStakeResolution,
  useCreateStakeRewardLine,
  useStakeResolutions,
  useStakeRewardLines,
  useStakes,
  useStakesSummary,
  useStakeTemplates,
} from '../queries';
import type { Stake, StakeResolution, StakeRewardLine } from '../types';

vi.mock('../api', () => ({
  listStakes: vi.fn(),
  createStake: vi.fn(),
  updateStake: vi.fn(),
  deleteStake: vi.fn(),
  listStakeResolutions: vi.fn(),
  createStakeResolution: vi.fn(),
  updateStakeResolution: vi.fn(),
  deleteStakeResolution: vi.fn(),
  listStakeRewardLines: vi.fn(),
  createStakeRewardLine: vi.fn(),
  updateStakeRewardLine: vi.fn(),
  deleteStakeRewardLine: vi.fn(),
  listStakeTemplates: vi.fn(),
  getStakesSummary: vi.fn(),
}));

import * as api from '../api';

beforeEach(() => {
  vi.clearAllMocks();
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const mockStake: Stake = {
  id: 7,
  beat: 15,
  template: null,
  subject_kind: 'asset',
  severity: 3,
  subject_sheet: null,
  subject_item: null,
  subject_society: null,
  subject_organization: null,
  subject_asset: 42,
  subject_label: '',
  player_summary: 'The safehouse could burn.',
  outcomes: [],
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
};

const mockResolution: StakeResolution = {
  id: 3,
  stake: 7,
  column: 'loss',
  outcome_key: '',
  consequence_pool: null,
  escalates_to_risk: '',
  narrative_summary: '',
  forfeits_subject_item: false,
  subject_standing_delta: 0,
  npc_regard_delta: 0,
  sets_subject_lifecycle: '',
  machine_match_lifecycle_state: '',
  transitions_subject_asset: 'compromised',
  reward_lines: [],
};

const mockRewardLine: StakeRewardLine = {
  id: 5,
  resolution: 3,
  sink: 'money',
  amount: 10,
  resonance: null,
};

describe('storiesKeys - stakes', () => {
  it('scopes stakes list keys by beat id', () => {
    expect(storiesKeys.stakes(15)).toEqual([...storiesKeys.all, 'stakes', 15]);
  });

  it('scopes stake resolution list keys by stake id', () => {
    expect(storiesKeys.stakeResolutions(7)).toEqual([...storiesKeys.all, 'stake-resolutions', 7]);
  });

  it('scopes stake reward line list keys by resolution id', () => {
    expect(storiesKeys.stakeRewardLines(3)).toEqual([...storiesKeys.all, 'stake-reward-lines', 3]);
  });

  it('elides the params slot for a no-arg stake templates key', () => {
    expect(storiesKeys.stakeTemplates()).toEqual([...storiesKeys.all, 'stake-templates']);
    expect(storiesKeys.stakeTemplates({ subject_kind: 'asset' })).toEqual([
      ...storiesKeys.all,
      'stake-templates',
      { subject_kind: 'asset' },
    ]);
  });

  it('scopes the stakes summary key by beat id, alongside beatReadiness', () => {
    expect(storiesKeys.stakesSummary(15)).toEqual([
      ...storiesKeys.all,
      'beat',
      15,
      'stakes-summary',
    ]);
    expect(storiesKeys.beatReadiness(15)).toEqual([...storiesKeys.all, 'beat', 15, 'readiness']);
  });
});

describe('useStakes', () => {
  it('lists stakes filtered by beat', async () => {
    vi.mocked(api.listStakes).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [mockStake],
    });

    const { result } = renderHook(() => useStakes(15, true), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listStakes).toHaveBeenCalledWith({ beat: 15 });
    expect(result.current.data?.results).toEqual([mockStake]);
  });

  it('stays disabled when the caller has not opted in', () => {
    renderHook(() => useStakes(15, false), { wrapper: createWrapper() });
    expect(api.listStakes).not.toHaveBeenCalled();
  });
});

describe('useStakeResolutions / useStakeRewardLines / useStakeTemplates / useStakesSummary', () => {
  it('lists resolutions filtered by stake', async () => {
    vi.mocked(api.listStakeResolutions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [mockResolution],
    });
    const { result } = renderHook(() => useStakeResolutions(7, true), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listStakeResolutions).toHaveBeenCalledWith({ stake: 7 });
  });

  it('lists reward lines filtered by resolution', async () => {
    vi.mocked(api.listStakeRewardLines).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [mockRewardLine],
    });
    const { result } = renderHook(() => useStakeRewardLines(3, true), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listStakeRewardLines).toHaveBeenCalledWith({ resolution: 3 });
  });

  it('lists templates with the given filters', async () => {
    vi.mocked(api.listStakeTemplates).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    const { result } = renderHook(() => useStakeTemplates({ subject_kind: 'asset' }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listStakeTemplates).toHaveBeenCalledWith({ subject_kind: 'asset' });
  });

  it('loads the beat stakes summary', async () => {
    vi.mocked(api.getStakesSummary).mockResolvedValue({
      declared_risk: 'moderate',
      effective_risk: 'moderate',
      is_ready: true,
      stakes: [],
    });
    const { result } = renderHook(() => useStakesSummary(15, true), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getStakesSummary).toHaveBeenCalledWith(15);
  });
});

describe('useCreateStake', () => {
  it('creates a stake and invalidates the stakes list, readiness, and summary for its beat', async () => {
    vi.mocked(api.createStake).mockResolvedValue(mockStake);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCreateStake(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        beatId: 15,
        beat: 15,
        subject_kind: 'asset',
        subject_asset: 42,
        player_summary: 'The safehouse could burn.',
      });
    });

    expect(api.createStake).toHaveBeenCalledWith({
      beat: 15,
      subject_kind: 'asset',
      subject_asset: 42,
      player_summary: 'The safehouse could burn.',
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakes(15) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.beatReadiness(15) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakesSummary(15) })
    );
  });
});

describe('useCreateStakeResolution', () => {
  it('creates a resolution and invalidates its stake list plus the beat readiness/summary', async () => {
    vi.mocked(api.createStakeResolution).mockResolvedValue(mockResolution);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCreateStakeResolution(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        beatId: 15,
        stake: 7,
        column: 'loss',
        outcome_key: '',
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakeResolutions(7) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.beatReadiness(15) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakesSummary(15) })
    );
  });
});

describe('useCreateStakeRewardLine', () => {
  it('creates a reward line and invalidates its resolution list plus the beat readiness/summary', async () => {
    vi.mocked(api.createStakeRewardLine).mockResolvedValue(mockRewardLine);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCreateStakeRewardLine(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        beatId: 15,
        resolution: 3,
        sink: 'money',
        amount: 10,
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakeRewardLines(3) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.beatReadiness(15) })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: storiesKeys.stakesSummary(15) })
    );
  });
});
