/**
 * React Query hooks for the journals module (#2160).
 *
 * Follows the key-factory + hook shape used by `frontend/src/relationships/queries.ts`.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type {
  CreateJournalEntryRequest,
  JournalEntryListFilters,
  RespondToJournalRequest,
} from './api';

export const journalsKeys = {
  all: ['journals'] as const,
  lists: () => [...journalsKeys.all, 'list'] as const,
  list: (filters: JournalEntryListFilters = {}) => [...journalsKeys.lists(), filters] as const,
  mine: (page = 1) => [...journalsKeys.all, 'mine', page] as const,
  detail: (id: number) => [...journalsKeys.all, 'detail', id] as const,
};

/** GET /api/journals/entries/ — public feed, optionally filtered by author/tag. */
export function useJournalEntries(filters: JournalEntryListFilters = {}) {
  return useQuery({
    queryKey: journalsKeys.list(filters),
    queryFn: () => api.listJournalEntries(filters),
  });
}

/** GET /api/journals/entries/mine/ — the viewer's own entries, including private. */
export function useMyJournalEntries(page = 1) {
  return useQuery({
    queryKey: journalsKeys.mine(page),
    queryFn: () => api.listMyJournalEntries({ page }),
  });
}

/** GET /api/journals/entries/{id}/ — a single entry with its responses. */
export function useJournalEntry(id: number | null, enabled = true) {
  return useQuery({
    queryKey: journalsKeys.detail(id ?? -1),
    queryFn: () => api.getJournalEntry(id as number),
    enabled: enabled && id != null,
  });
}

/**
 * POST /api/journals/entries/ — write a new entry. Invalidates the public
 * feed and "mine" lists so the new entry (and its weekly-XP-driven counters)
 * show up without a manual refetch.
 */
export function useCreateJournalEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateJournalEntryRequest) => api.createJournalEntry(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.all }).catch(() => {});
    },
  });
}

/**
 * POST /api/journals/entries/{id}/respond/ — praise or retort a parent entry.
 * Invalidates the parent's detail (its `responses` list grows) plus the
 * public/mine feeds (`response_count` changes).
 */
export function useRespondToJournal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, body }: { entryId: number; body: RespondToJournalRequest }) =>
      api.respondToJournal(entryId, body),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.detail(entryId) }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.mine() }).catch(() => {});
    },
  });
}
