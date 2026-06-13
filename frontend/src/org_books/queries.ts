/**
 * Org books React Query hooks (#930).
 */

import { useQuery } from '@tanstack/react-query';
import * as api from './api';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const orgBooksKeys = {
  all: ['org-books'] as const,
  shelf: () => [...orgBooksKeys.all, 'shelf'] as const,
  books: (orgId: number) => [...orgBooksKeys.all, 'books', orgId] as const,
};

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useMyBooksShelf() {
  return useQuery({
    queryKey: orgBooksKeys.shelf(),
    queryFn: () => api.getMyBooksShelf(),
    throwOnError: true,
  });
}

export function useOrgBooks(orgId: number) {
  return useQuery({
    queryKey: orgBooksKeys.books(orgId),
    queryFn: () => api.getOrgBooks(orgId),
    enabled: orgId > 0,
    throwOnError: true,
  });
}
