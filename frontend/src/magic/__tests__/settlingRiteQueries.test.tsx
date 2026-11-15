/**
 * Tests for the rite of settling hooks and the open chance to atone (#4733, #5124):
 * vi.fn() mocks of the api, no msw.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  magicKeys,
  usePendingDriftConversionOffers,
  usePerformSettlingRite,
  useSettlingRite,
} from '../queries';
import { auraKeys } from '../auraQueries';
import type { SettlingRiteReading, SettlingRiteResult } from '../types';

vi.mock('../api', () => ({
  getPendingDriftConversionOffers: vi.fn(),
  getSettlingRite: vi.fn(),
  performSettlingRite: vi.fn(),
}));

import * as api from '../api';

const READING: SettlingRiteReading = {
  reflections: [],
  offerings: [],
  rite_ready: true,
  not_ready_message: '',
  check_name: 'Composure',
};

const RESULT: SettlingRiteResult = {
  outcome_name: 'Success',
  success_level: 1,
  focus_bonus: 0,
  lines: ['You become more abyssal.'],
};

function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { wrapper, client };
}

describe('useSettlingRite', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reads the rite for the named character', async () => {
    vi.mocked(api.getSettlingRite).mockResolvedValue(READING);
    const { wrapper } = createWrapperWithClient();

    const { result } = renderHook(() => useSettlingRite(55), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(api.getSettlingRite).toHaveBeenCalledWith(55);
    expect(result.current.data).toEqual(READING);
  });

  it('does not fetch while disabled, so a viewer of another sheet never asks', () => {
    const { wrapper } = createWrapperWithClient();

    renderHook(() => useSettlingRite(55, false), { wrapper });

    expect(api.getSettlingRite).not.toHaveBeenCalled();
  });
});

describe('usePendingDriftConversionOffers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is read once, not polled: the chance stays open until the rite spends it', async () => {
    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    const { wrapper, client } = createWrapperWithClient();

    const { result } = renderHook(() => usePendingDriftConversionOffers(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const query = client.getQueryCache().find({ queryKey: magicKeys.driftConversionPending() });
    expect(query?.observers[0]?.options.refetchInterval).toBeUndefined();
  });
});

describe('usePerformSettlingRite', () => {
  beforeEach(() => vi.clearAllMocks());

  it('passes the body through and refetches what the rite changes', async () => {
    vi.mocked(api.performSettlingRite).mockResolvedValue(RESULT);
    const { wrapper, client } = createWrapperWithClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const body = { character_sheet_id: 55, component_ids: [502] };

    const { result } = renderHook(() => usePerformSettlingRite(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(body);
    });

    expect(api.performSettlingRite).toHaveBeenCalledWith(body);
    await waitFor(() => {
      for (const queryKey of [
        magicKeys.settlingRiteAll(),
        magicKeys.driftConversionPending(),
        magicKeys.reflectionOptionsAll(),
        magicKeys.characterResonanceList(),
        auraKeys.all,
        ['character-sheets'],
      ]) {
        expect(invalidate).toHaveBeenCalledWith({ queryKey });
      }
    });
  });

  it('surfaces a refusal as the thrown error', async () => {
    vi.mocked(api.performSettlingRite).mockRejectedValue(new Error('You have no reflections.'));
    const { wrapper } = createWrapperWithClient();

    const { result } = renderHook(() => usePerformSettlingRite(), { wrapper });
    await act(async () => {
      await result.current
        .mutateAsync({ character_sheet_id: 55, component_ids: [] })
        .catch(() => {});
    });

    await waitFor(() => expect(result.current.error?.message).toBe('You have no reflections.'));
  });
});
