/**
 * React Query hooks for the journals module (#2160).
 *
 * Follows the key-factory + hook shape used by `frontend/src/relationships/queries.ts`.
 */

import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useActiveCharacterId } from '@/gm-adjudication/useActiveCharacterId';
import { magicKeys } from '@/magic/queries';

import * as api from './api';
import type {
  CreateJournalEntryRequest,
  EditJournalEntryRequest,
  JournalEntryListFilters,
  PatchJournalSettingsRequest,
  RespondToJournalRequest,
} from './api';

/**
 * Every read is the acting character's (the viewer's own entries, retort rights and settings
 * differ per character), so the keys that read as someone carry `characterId` last. The bare
 * forms (no id) are the prefixes the mutations invalidate.
 */
export const journalsKeys = {
  all: ['journals'] as const,
  lists: () => [...journalsKeys.all, 'list'] as const,
  list: (filters: JournalEntryListFilters = {}, characterId?: number | null) =>
    [
      ...journalsKeys.lists(),
      filters,
      ...(characterId === undefined ? [] : [characterId]),
    ] as const,
  mine: (page = 1, characterId?: number | null) =>
    [
      ...journalsKeys.all,
      'mine',
      page,
      ...(characterId === undefined ? [] : [characterId]),
    ] as const,
  detail: (id: number, characterId?: number | null) =>
    [
      ...journalsKeys.all,
      'detail',
      id,
      ...(characterId === undefined ? [] : [characterId]),
    ] as const,
  settings: (characterId?: number | null) =>
    [...journalsKeys.all, 'settings', ...(characterId === undefined ? [] : [characterId])] as const,
};

/**
 * GET /api/journals/entries/ — the feed, optionally filtered (see
 * `JournalEntryListFilters`).
 *
 * `markVisitOnce` stamps the reader's visit mark on the FIRST fetch this hook
 * performs and on no other. It is deliberately not part of `filters`: in the
 * query key it would make "the stream" and "the stream, marked" two different
 * queries — so the first thing to re-render the page would swap the key and
 * refetch — and baked into the queryFn it would re-stamp on every background
 * refetch, quietly moving the mark to now and emptying "since your last visit".
 * The ref is read at fetch time, which is the only moment that can tell a first
 * fetch from a refetch.
 */
export function useJournalEntries(filters: JournalEntryListFilters = {}, markVisitOnce = false) {
  const stamped = useRef(false);
  const characterId = useActiveCharacterId();
  return useQuery({
    queryKey: journalsKeys.list(filters, characterId),
    queryFn: () => {
      const stamp = markVisitOnce && !stamped.current;
      stamped.current = true;
      return api.listJournalEntries(characterId, stamp ? { ...filters, mark_visit: 1 } : filters);
    },
  });
}

/** GET /api/journals/entries/mine/ — the viewer's own entries, including private. */
export function useMyJournalEntries(page = 1) {
  const characterId = useActiveCharacterId();
  return useQuery({
    queryKey: journalsKeys.mine(page, characterId),
    queryFn: () => api.listMyJournalEntries(characterId, { page }),
    enabled: characterId !== null,
  });
}

/** GET /api/journals/entries/{id}/ — a single entry with its responses. */
export function useJournalEntry(id: number | null, enabled = true) {
  const characterId = useActiveCharacterId();
  return useQuery({
    queryKey: journalsKeys.detail(id ?? -1, characterId),
    queryFn: () => api.getJournalEntry(characterId, id as number),
    enabled: enabled && id != null,
  });
}

/**
 * POST /api/journals/entries/ — write a new entry. Invalidates the public
 * feed and "mine" lists so the new entry (and its weekly-XP-driven counters)
 * show up without a manual refetch, plus settings (`posts_this_week` changes, #3941).
 */
export function useCreateJournalEntry() {
  const queryClient = useQueryClient();
  const characterId = useActiveCharacterId();
  return useMutation({
    mutationFn: (body: CreateJournalEntryRequest) => api.createJournalEntry(characterId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.all }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.settings() }).catch(() => {});
      // A reflection the entry carried used up a deed, or replaced a waiting one (#5124).
      queryClient.invalidateQueries({ queryKey: magicKeys.reflectionOptionsAll() }).catch(() => {});
    },
  });
}

/**
 * POST /api/journals/entries/{id}/respond/ — praise, retort, or condemn a parent entry.
 * Invalidates the parent's detail (its `responses` list grows) plus the
 * public/mine feeds (`response_count` changes) and settings (`posts_this_week`, #3941).
 */
export function useRespondToJournal() {
  const queryClient = useQueryClient();
  const characterId = useActiveCharacterId();
  return useMutation({
    mutationFn: ({ entryId, body }: { entryId: number; body: RespondToJournalRequest }) =>
      api.respondToJournal(characterId, entryId, body),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.detail(entryId) }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.mine() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.settings() }).catch(() => {});
    },
  });
}

/**
 * PATCH /api/journals/entries/{id}/ — edit title/body, the per-entry posthumous
 * override (#3287), and/or the relationship-journal `about` subject (#3941). Invalidates
 * the entry's detail plus "mine" (own-entries tab shows the updated override/about), the
 * public feed (title/body edits should refresh there too), and settings.
 */
export function useEditJournalEntry() {
  const queryClient = useQueryClient();
  const characterId = useActiveCharacterId();
  return useMutation({
    mutationFn: ({ entryId, body }: { entryId: number; body: EditJournalEntryRequest }) =>
      api.editJournalEntry(characterId, entryId, body),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.detail(entryId) }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.lists() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.mine() }).catch(() => {});
      queryClient.invalidateQueries({ queryKey: journalsKeys.settings() }).catch(() => {});
    },
  });
}

/**
 * GET /api/journals/entries/disposition/ — the caller's journal settings (#3941, was
 * #3287): sheet-level posthumous default, retort consent, and weekly posting-XP tracker.
 */
export function useJournalSettings() {
  const characterId = useActiveCharacterId();
  return useQuery({
    queryKey: journalsKeys.settings(characterId),
    queryFn: () => api.getJournalSettings(characterId),
    enabled: characterId !== null,
  });
}

/**
 * PATCH /api/journals/entries/disposition/ — update the caller's journal settings
 * (#3941, was #3287); pass only the keys being changed.
 */
export function usePatchJournalSettings() {
  const queryClient = useQueryClient();
  const characterId = useActiveCharacterId();
  return useMutation({
    mutationFn: (body: PatchJournalSettingsRequest) => api.patchJournalSettings(characterId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: journalsKeys.settings() }).catch(() => {});
    },
  });
}
