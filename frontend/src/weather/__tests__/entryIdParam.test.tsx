/**
 * #3479 Task 5: the weather conditions read carries the tab's browsing
 * identity as an `entry_id` query param, but ONLY on the no-room path: the
 * server ignores `entry_id` when `room_id` is supplied, and the in-game
 * WeatherWidget stays keyed to its live session room, sending no entry at
 * all.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

import { fetchWeatherConditions } from '../api';
import { useWeatherConditions } from '../queries';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
});

describe('fetchWeatherConditions (#3479)', () => {
  it('sends entry_id on the no-room path', async () => {
    await fetchWeatherConditions(null, 5);
    expect(apiFetch).toHaveBeenCalledWith('/api/weather/conditions/?entry_id=5');
  });

  it('sends only room_id when a room is known (server ignores entry_id there)', async () => {
    await fetchWeatherConditions(31, 5);
    expect(apiFetch).toHaveBeenCalledWith('/api/weather/conditions/?room_id=31');
  });

  it('sends neither when no room and no identity', async () => {
    await fetchWeatherConditions(null, null);
    expect(apiFetch).toHaveBeenCalledWith('/api/weather/conditions/');
  });
});

describe('useWeatherConditions (#3479)', () => {
  it('threads entryId into the fetch on the fallback path', async () => {
    renderHook(() => useWeatherConditions(null, { fallbackToSelection: true, entryId: 5 }), {
      wrapper: wrapper(),
    });
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/weather/conditions/?entry_id=5')
    );
  });

  it('stays disabled with no room and no fallback', () => {
    renderHook(() => useWeatherConditions(null), { wrapper: wrapper() });
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
