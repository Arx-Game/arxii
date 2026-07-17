/**
 * usePersonaSearch / useOrganizationSearch tests (2026-07 audit).
 *
 * These hooks replaced 6+ hand-rolled debounce+setState search blocks, several
 * of which had no stale-response guard. React Query provides the debounce (via
 * useDebouncedValue), request dedup, and response ordering; these tests lock in
 * the two behaviors callers depend on: no fetch below the min length, and a
 * fetch (with limit slicing) once the debounced term qualifies.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';

import { usePersonaSearch, useOrganizationSearch } from '../usePersonaSearch';
import * as eventsQueries from '@/events/queries';

vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(),
  searchOrganizations: vi.fn(),
}));

// Collapse the 300ms debounce so tests don't wait on real time.
vi.mock('@/hooks/useDebouncedValue', () => ({
  useDebouncedValue: (value: unknown) => value,
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const personaRow = (id: number) => ({ id, name: `P${id}`, character_sheet: id });

describe('usePersonaSearch', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does not fetch until the trimmed term reaches minLength', () => {
    renderHook(() => usePersonaSearch('a'), { wrapper: createWrapper() });
    expect(eventsQueries.searchPersonas).not.toHaveBeenCalled();
  });

  it('does not fetch for a whitespace-only term', () => {
    renderHook(() => usePersonaSearch('   '), { wrapper: createWrapper() });
    expect(eventsQueries.searchPersonas).not.toHaveBeenCalled();
  });

  it('fetches once the term qualifies and slices to the limit', async () => {
    vi.mocked(eventsQueries.searchPersonas).mockResolvedValue(
      [1, 2, 3, 4, 5, 6, 7].map(personaRow)
    );

    const { result } = renderHook(() => usePersonaSearch('abc', { limit: 3 }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.results).toHaveLength(3));
    expect(eventsQueries.searchPersonas).toHaveBeenCalledWith('abc');
    expect(result.current.results.map((p) => p.id)).toEqual([1, 2, 3]);
  });

  it('degrades to an empty list on fetch error instead of throwing', async () => {
    vi.mocked(eventsQueries.searchPersonas).mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => usePersonaSearch('abc'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(result.current.results).toEqual([]);
  });
});

describe('useOrganizationSearch', () => {
  beforeEach(() => vi.clearAllMocks());

  it('respects the enabled flag (no fetch when disabled)', () => {
    renderHook(() => useOrganizationSearch('abc', { enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(eventsQueries.searchOrganizations).not.toHaveBeenCalled();
  });

  it('fetches organizations once the term qualifies', async () => {
    vi.mocked(eventsQueries.searchOrganizations).mockResolvedValue([{ id: 9, name: 'House' }]);

    const { result } = renderHook(() => useOrganizationSearch('hou'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.results).toHaveLength(1));
    expect(eventsQueries.searchOrganizations).toHaveBeenCalledWith('hou');
  });
});
