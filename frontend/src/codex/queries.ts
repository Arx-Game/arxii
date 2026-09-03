/**
 * Codex React Query hooks
 *
 * `characterId` scopes knowledge to one of the viewer's characters (see
 * api.ts); it is part of every query key so switching scope refetches.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCodexTree,
  getEntry,
  getEntries,
  getFeaturedEntries,
  searchEntries,
  getSubject,
  getSubjectChildren,
} from './api';

export const codexKeys = {
  all: ['codex'] as const,
  tree: (characterId?: number) => [...codexKeys.all, 'tree', characterId ?? null] as const,
  subject: (id: number, characterId?: number) =>
    [...codexKeys.all, 'subject', id, characterId ?? null] as const,
  subjectChildren: (id: number, characterId?: number) =>
    [...codexKeys.all, 'subject', id, 'children', characterId ?? null] as const,
  entries: (subjectId?: number, characterId?: number) =>
    [...codexKeys.all, 'entries', subjectId, characterId ?? null] as const,
  featured: () => [...codexKeys.all, 'featured'] as const,
  entry: (id: number, characterId?: number) =>
    [...codexKeys.all, 'entry', id, characterId ?? null] as const,
  search: (query: string, characterId?: number) =>
    [...codexKeys.all, 'search', query, characterId ?? null] as const,
};

export function useCodexTree(characterId?: number) {
  return useQuery({
    queryKey: codexKeys.tree(characterId),
    queryFn: () => getCodexTree(characterId),
    staleTime: 5 * 60 * 1000, // 5 minutes - codex structure changes rarely
    throwOnError: true,
  });
}

export function useCodexEntries(subjectId?: number, characterId?: number) {
  return useQuery({
    queryKey: codexKeys.entries(subjectId, characterId),
    queryFn: () => getEntries(subjectId, characterId),
    throwOnError: true,
  });
}

export function useFeaturedCodexEntries() {
  return useQuery({
    queryKey: codexKeys.featured(),
    queryFn: getFeaturedEntries,
    staleTime: 5 * 60 * 1000, // 5 minutes — codex content changes rarely
    throwOnError: true,
  });
}

/**
 * `throwOnError` defaults to the app-wide convention (route error boundary).
 * An overlay such as `CodexModal` passes `false` so a missing or hidden entry
 * is reported inside the dialog instead of replacing the page behind it.
 */
export function useCodexEntry(
  id: number,
  characterId?: number,
  options: { throwOnError?: boolean } = {}
) {
  return useQuery({
    queryKey: codexKeys.entry(id, characterId),
    queryFn: () => getEntry(id, characterId),
    enabled: id > 0,
    throwOnError: options.throwOnError ?? true,
  });
}

export function useCodexSearch(query: string, characterId?: number) {
  return useQuery({
    queryKey: codexKeys.search(query, characterId),
    queryFn: () => searchEntries(query, characterId),
    enabled: query.length >= 2,
    staleTime: 30 * 1000, // 30 seconds
    throwOnError: true,
  });
}

export function useCodexSubject(id: number, characterId?: number) {
  return useQuery({
    queryKey: codexKeys.subject(id, characterId),
    queryFn: () => getSubject(id, characterId),
    enabled: id > 0,
    staleTime: 5 * 60 * 1000,
    throwOnError: true,
  });
}

export function useCodexSubjectChildren(id: number, characterId?: number) {
  return useQuery({
    queryKey: codexKeys.subjectChildren(id, characterId),
    queryFn: () => getSubjectChildren(id, characterId),
    enabled: id > 0,
    staleTime: 5 * 60 * 1000,
    throwOnError: true,
  });
}
