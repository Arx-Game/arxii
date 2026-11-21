import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { hallKeys } from '@/home/hall/queries';
import { ApiError } from '@/lib/errors';
import {
  fetchClock,
  fetchClockHistory,
  fetchJumpPreview,
  pauseClock,
  resumeClock,
  setClockDate,
  setClockSpeed,
} from './api';

export const clockKeys = {
  // The Hall and the game's top bar read the clock under this key, so a change made on
  // the staff page reaches them when it is invalidated.
  state: hallKeys.clock,
  history: (page: number) => ['staff', 'clock', 'history', page] as const,
  historyAll: ['staff', 'clock', 'history'] as const,
  preview: (icDatetime: string) => ['staff', 'clock', 'preview', icDatetime] as const,
};

const TEN_SECONDS = 10 * 1000;

/** The clock, re-read every ten seconds so a running date moves on the page. */
export function useStaffClock() {
  return useQuery({
    queryKey: clockKeys.state,
    queryFn: fetchClock,
    refetchInterval: TEN_SECONDS,
    // An answer from the server is not retried: "no clock yet" is a 503 and is the truth.
    retry: (count, error) => !(error instanceof ApiError) && count < 2,
  });
}

export function useClockHistory(page: number) {
  return useQuery({
    queryKey: clockKeys.history(page),
    queryFn: () => fetchClockHistory(page),
  });
}

/** What setting the clock to `icDatetime` would do. Idle while `icDatetime` is null. */
export function useJumpPreview(icDatetime: string | null) {
  return useQuery({
    queryKey: clockKeys.preview(icDatetime ?? ''),
    queryFn: () => fetchJumpPreview(icDatetime ?? ''),
    enabled: icDatetime !== null,
    staleTime: 0,
  });
}

function useClockMutation<TInput>(mutationFn: (input: TInput) => Promise<void>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    // Settled, not success: a refusal ("already paused") means the page is stale too.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clockKeys.state });
      queryClient.invalidateQueries({ queryKey: clockKeys.historyAll });
    },
  });
}

export function usePauseClock() {
  return useClockMutation<void>(pauseClock);
}

export function useResumeClock() {
  return useClockMutation<void>(resumeClock);
}

export function useSetClockDate() {
  return useClockMutation(setClockDate);
}

export function useSetClockSpeed() {
  return useClockMutation(setClockSpeed);
}
