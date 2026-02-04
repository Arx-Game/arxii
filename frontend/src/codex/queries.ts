/**
 * Codex React Query hooks
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCodexTree,
  getEntry,
  getEntries,
  searchEntries,
  getCategory,
  getSubject,
  getSubjectChildren,
} from './api';

export const codexKeys = {
  all: ['codex'] as const,
  tree: () => [...codexKeys.all, 'tree'] as const,
  category: (id: number) => [...codexKeys.all, 'category', id] as const,
  subject: (id: number) => [...codexKeys.all, 'subject', id] as const,
  subjectChildren: (id: number) => [...codexKeys.all, 'subject', id, 'children'] as const,
  entries: (subjectId?: number) => [...codexKeys.all, 'entries', subjectId] as const,
  entry: (id: number) => [...codexKeys.all, 'entry', id] as const,
  search: (query: string) => [...codexKeys.all, 'search', query] as const,
};

export function useCodexTree() {
  return useQuery({
    queryKey: codexKeys.tree(),
    queryFn: getCodexTree,
    staleTime: 5 * 60 * 1000, // 5 minutes - codex structure changes rarely
    throwOnError: true,
  });
}

export function useCodexEntries(subjectId?: number) {
  return useQuery({
    queryKey: codexKeys.entries(subjectId),
    queryFn: () => getEntries(subjectId),
    throwOnError: true,
  });
}

export function useCodexEntry(id: number) {
  return useQuery({
    queryKey: codexKeys.entry(id),
    queryFn: () => getEntry(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

export function useCodexSearch(query: string) {
  return useQuery({
    queryKey: codexKeys.search(query),
    queryFn: () => searchEntries(query),
    enabled: query.length >= 2,
    staleTime: 30 * 1000, // 30 seconds
    throwOnError: true,
  });
}

export function useCodexCategory(id: number) {
  return useQuery({
    queryKey: codexKeys.category(id),
    queryFn: () => getCategory(id),
    enabled: id > 0,
    staleTime: 5 * 60 * 1000,
    throwOnError: true,
  });
}

export function useCodexSubject(id: number) {
  return useQuery({
    queryKey: codexKeys.subject(id),
    queryFn: () => getSubject(id),
    enabled: id > 0,
    staleTime: 5 * 60 * 1000,
    throwOnError: true,
  });
}

export function useCodexSubjectChildren(id: number) {
  return useQuery({
    queryKey: codexKeys.subjectChildren(id),
    queryFn: () => getSubjectChildren(id),
    enabled: id > 0,
    staleTime: 5 * 60 * 1000,
    throwOnError: true,
  });
}
