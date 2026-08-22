/**
 * React Query hooks for the journals module (#2160).
 *
 * Follows the key-factory + hook shape used by `frontend/src/relationships/queries.ts`.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type {
  CreateJournalEntryRequest,
  EditJournalEntryRequest,
  JournalEntryListFilters,
  PosthumousJournalDisposition,
  RespondToJournalRequest,
} from './api';

export const journalsKeys = {
  all: ['journals'] as const,
  lists: () => [...journalsKeys.all, 'list'] as const,
  list: (filters: JournalEntryListFilters = {}) => [...journalsKeys.lists(), filters] as const,
  mine: (page = 1) => [...journalsKeys.all, 'mine', page] as const,
  detail: (id: number) => [...journalsKeys.all, 'detail', id] as const,
  disposition: () => [...journalsKeys.all, 'disposition'] as const,
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

/**
 * PATCH /api/journals/entries/{id}/ — edit title/body and/or the per-entry posthumous
 * override (#3287). Invalidates the entry's detail plus "mine" (own-entries tab shows the
 * updated override) and the public feed (title/body edits should refresh there too).
 */
export function useEditJournalEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, body }: { entryId: number; body: EditJournalEntryRequest }) =>
      api.editJournalEntry(entryId, body),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.detail(entryId) }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.mine() }).catch(() => {});
    },
  });
}

/** GET /api/journals/entries/disposition/ — the caller's sheet-level default (#3287). */
export function useJournalDisposition() {
  return useQuery({
    queryKey: journalsKeys.disposition(),
    queryFn: () => api.getJournalDisposition(),
  });
}

/**
 * PATCH /api/journals/entries/disposition/ — set the caller's sheet-level default (#3287).
 */
export function useSetJournalDisposition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (disposition: PosthumousJournalDisposition) =>
      api.setJournalDisposition(disposition),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.disposition() }).catch(() => {});
    },
  });
}

