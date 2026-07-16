import { useQuery } from '@tanstack/react-query';

import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { searchOrganizations, searchPersonas, type PersonaSearchResult } from '@/events/queries';

interface EntitySearchOptions {
  minLength?: number;
  limit?: number;
  delay?: number;
  /** Skip fetching entirely (e.g. a toggle points at a different entity type). */
  enabled?: boolean;
}

/**
 * Debounced, race-safe persona type-ahead (2026-07 audit).
 *
 * Consolidates the 6+ hand-rolled `searchPersonas` + setState blocks scattered
 * across the app — several of which had no debounce and no stale-response
 * guard, so a slow response for "ab" could overwrite a newer one for "abc".
 * React Query handles debounced fetching, request dedup, response ordering,
 * and caching; callers just render `data`.
 *
 * Returns an empty list (no fetch) until the trimmed term reaches `minLength`.
 */
export function usePersonaSearch(
  term: string,
  { minLength = 2, limit = 5, delay = 300, enabled: enabledOpt = true }: EntitySearchOptions = {}
) {
  const debounced = useDebouncedValue(term.trim(), delay);
  const enabled = enabledOpt && debounced.length >= minLength;

  const query = useQuery({
    queryKey: ['persona-search', debounced, limit],
    queryFn: () => searchPersonas(debounced),
    enabled,
    // Type-ahead: a transient failure should clear the list, never crash a form.
    throwOnError: false,
    staleTime: 30_000,
  });

  const results: PersonaSearchResult[] = enabled ? (query.data ?? []).slice(0, limit) : [];
  return { results, isFetching: enabled && query.isFetching };
}

/** Organization type-ahead — the same debounced, race-safe pattern as {@link usePersonaSearch}. */
export function useOrganizationSearch(
  term: string,
  { minLength = 2, limit = 5, delay = 300, enabled: enabledOpt = true }: EntitySearchOptions = {}
) {
  const debounced = useDebouncedValue(term.trim(), delay);
  const enabled = enabledOpt && debounced.length >= minLength;

  const query = useQuery({
    queryKey: ['organization-search', debounced, limit],
    queryFn: () => searchOrganizations(debounced),
    enabled,
    throwOnError: false,
    staleTime: 30_000,
  });

  const results = enabled ? (query.data ?? []).slice(0, limit) : [];
  return { results, isFetching: enabled && query.isFetching };
}
