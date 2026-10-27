/**
 * Tests for drift conversion offer query hooks (#4733).
 * Mirrors entryFlourishQueries.test.tsx: vi.fn() mocks, no msw.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  usePendingDriftConversionOffers,
  useConvertDrift,
  useDeclineDriftConversion,
  magicKeys,
} from '../queries';
import type { DriftCorrectionResult, PaginatedDriftConversionOfferList } from '../types';

vi.mock('../api', () => ({
  getPendingDriftConversionOffers: vi.fn(),
  convertDrift: vi.fn(),
  declineDriftConversion: vi.fn(),
}));

import * as api from '../api';

const PENDING_FIXTURE: PaginatedDriftConversionOfferList = {
  count: 1,
  next: null,
  previous: null,
  results: [{ id: 12, scene_id: 101, caps: [], rite_ready: true, rite_not_ready_message: '' }],
};

const RESULT_FIXTURE: DriftCorrectionResult = {
  source_resonance_id: 30,
  target_resonance_id: 20,
  attempted_amount: 12,
  converted_amount: 8,
  granted_amount: 4,
  outcome_name: 'Partial Success',
  success_level: 1,
  conversion_type: 'REDEMPTION',
  focus_bonus: 0,
};

const CONVERT_BODY = {
  offer_id: 12,
  source_resonance_id: 30,
  target_resonance_id: 20,
  amount: 12,
  component_ids: [502],
};

function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { wrapper: Wrapper, client };
}

describe('usePendingDriftConversionOffers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the pending offer list when enabled (default)', async () => {
    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(PENDING_FIXTURE);
    const { wrapper } = createWrapperWithClient();

    const { result } = renderHook(() => usePendingDriftConversionOffers(), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.results?.[0]?.id).toBe(12);
    expect(api.getPendingDriftConversionOffers).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when enabled=false', () => {
    const { wrapper } = createWrapperWithClient();
    const { result } = renderHook(() => usePendingDriftConversionOffers(false), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getPendingDriftConversionOffers).not.toHaveBeenCalled();
  });

  it('polls every 5 seconds', async () => {
    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(PENDING_FIXTURE);
    const { wrapper, client } = createWrapperWithClient();

    const { result } = renderHook(() => usePendingDriftConversionOffers(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const query = client.getQueryCache().find({ queryKey: magicKeys.driftConversionPending() });
    expect(query?.observers[0]?.options.refetchInterval).toBe(5_000);
  });
});

describe('useConvertDrift', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the body through to api.convertDrift', async () => {
    vi.mocked(api.convertDrift).mockResolvedValue(RESULT_FIXTURE);
    const { wrapper } = createWrapperWithClient();

    const { result } = renderHook(() => useConvertDrift(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(CONVERT_BODY);
    });

    expect(api.convertDrift).toHaveBeenCalledWith(CONVERT_BODY);
  });

  it('invalidates the pending inbox and the character resonance list on success', async () => {
    vi.mocked(api.convertDrift).mockResolvedValue(RESULT_FIXTURE);
    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useConvertDrift(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(CONVERT_BODY);
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'drift-correction', 'pending'],
      });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: magicKeys.characterResonanceList(),
      });
    });
  });

  it('invalidates nothing when the rite is refused', async () => {
    vi.mocked(api.convertDrift).mockRejectedValue(new Error('refused'));
    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useConvertDrift(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(CONVERT_BODY).catch(() => {});
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

describe('useDeclineDriftConversion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts { offer_id } and invalidates the pending inbox', async () => {
    vi.mocked(api.declineDriftConversion).mockResolvedValue({ detail: 'ok' });
    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useDeclineDriftConversion(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ offer_id: 12 });
    });

    expect(api.declineDriftConversion).toHaveBeenCalledWith({ offer_id: 12 });
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'drift-correction', 'pending'],
      });
    });
  });
});

describe('magicKeys - drift-correction key', () => {
  it('driftConversionPending() equals [magic, drift-correction, pending]', () => {
    expect(magicKeys.driftConversionPending()).toEqual(['magic', 'drift-correction', 'pending']);
  });
});
