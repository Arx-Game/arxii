/**
 * React Query hooks for the distinctions system.
 *
 * Provides hooks for fetching distinction categories, distinctions,
 * and managing distinctions on character creation drafts.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type {
  AddDistinctionRequest,
  Distinction,
  DistinctionCategory,
  DistinctionDetail,
  DraftDistinctionEntry,
  SwapDistinctionRequest,
  SwapDistinctionResponse,
  SyncDistinctionsResponse,
} from '@/types/distinctions';

const BASE_URL = '/api/distinctions';

// =============================================================================
// Query Keys
// =============================================================================

export const distinctionKeys = {
  all: ['distinctions'] as const,
  categories: () => [...distinctionKeys.all, 'categories'] as const,
  lists: () => [...distinctionKeys.all, 'list'] as const,
  list: (filters: { category?: string; search?: string; draftId?: number }) =>
    [...distinctionKeys.lists(), filters] as const,
  details: () => [...distinctionKeys.all, 'detail'] as const,
  detail: (slug: string) => [...distinctionKeys.details(), slug] as const,
  draftDistinctions: (draftId: number) => [...distinctionKeys.all, 'draft', draftId] as const,
};

// =============================================================================
// API Functions
// =============================================================================

async function fetchCategories(): Promise<DistinctionCategory[]> {
  const res = await apiFetch(`${BASE_URL}/categories/`);
  if (!res.ok) {
    throw new Error('Failed to load distinction categories');
  }
  return res.json();
}

interface FetchDistinctionsParams {
  category?: string;
  search?: string;
  draftId?: number;
}

async function fetchDistinctions(params: FetchDistinctionsParams = {}): Promise<Distinction[]> {
  const searchParams = new URLSearchParams();

  if (params.category) {
    searchParams.append('category', params.category);
  }
  if (params.search) {
    searchParams.append('search', params.search);
  }
  if (params.draftId) {
    searchParams.append('draft_id', params.draftId.toString());
  }
  // By default, exclude variant children from the list view
  searchParams.append('exclude_variants', 'true');

  const queryString = searchParams.toString();
  const url = queryString
    ? `${BASE_URL}/distinctions/?${queryString}`
    : `${BASE_URL}/distinctions/`;

  const res = await apiFetch(url);
  if (!res.ok) {
    throw new Error('Failed to load distinctions');
  }
  return res.json();
}

async function fetchDistinctionDetail(slug: string): Promise<DistinctionDetail> {
  const res = await apiFetch(`${BASE_URL}/distinctions/${slug}/`);
  if (!res.ok) {
    throw new Error('Failed to load distinction details');
  }
  return res.json();
}

async function fetchDraftDistinctions(draftId: number): Promise<DraftDistinctionEntry[]> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/distinctions/`);
  if (!res.ok) {
    throw new Error('Failed to load draft distinctions');
  }
  return res.json();
}

async function addDistinctionToDraft(
  draftId: number,
  data: AddDistinctionRequest
): Promise<DraftDistinctionEntry> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/distinctions/`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to add distinction');
  }
  return res.json();
}

async function removeDistinctionFromDraft(draftId: number, distinctionId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/distinctions/${distinctionId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to remove distinction');
  }
}

async function swapDistinctionsOnDraft(
  draftId: number,
  data: SwapDistinctionRequest
): Promise<SwapDistinctionResponse> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/distinctions/swap/`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to swap distinctions');
  }
  return res.json();
}

async function syncDistinctionsOnDraft(
  draftId: number,
  distinctionIds: number[]
): Promise<SyncDistinctionsResponse> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/distinctions/sync/`, {
    method: 'PUT',
    body: JSON.stringify({ distinction_ids: distinctionIds }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to sync distinctions');
  }
  return res.json();
}

// =============================================================================
// Query Hooks
// =============================================================================

/**
 * Fetch all distinction categories.
 */
export function useDistinctionCategories() {
  return useQuery({
    queryKey: distinctionKeys.categories(),
    queryFn: fetchCategories,
  });
}

/**
 * Fetch distinctions with optional filtering.
 *
 * @param params.category - Filter by category slug
 * @param params.search - Search in name, description, tags, effects
 * @param params.draftId - Include lock status based on draft's existing distinctions
 */
export function useDistinctions(
  params: FetchDistinctionsParams = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: distinctionKeys.list(params),
    queryFn: () => fetchDistinctions(params),
    enabled: options?.enabled ?? true,
  });
}

/**
 * Fetch detailed information for a single distinction.
 *
 * @param slug - The distinction's slug identifier
 */
export function useDistinctionDetail(slug: string | undefined) {
  return useQuery({
    queryKey: distinctionKeys.detail(slug!),
    queryFn: () => fetchDistinctionDetail(slug!),
    enabled: !!slug,
  });
}

/**
 * Fetch distinctions currently on a character creation draft.
 *
 * @param draftId - The draft ID to fetch distinctions for
 */
export function useDraftDistinctions(draftId: number | undefined) {
  return useQuery({
    queryKey: distinctionKeys.draftDistinctions(draftId!),
    queryFn: () => fetchDraftDistinctions(draftId!),
    enabled: !!draftId,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Add a distinction to a character creation draft.
 *
 * Invalidates the draft distinctions query on success.
 */
export function useAddDistinction(draftId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: AddDistinctionRequest) => addDistinctionToDraft(draftId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.draftDistinctions(draftId),
      });
      // Also invalidate the distinctions list to refresh lock status
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.lists(),
      });
    },
  });
}

/**
 * Remove a distinction from a character creation draft.
 *
 * Invalidates the draft distinctions query on success.
 */
export function useRemoveDistinction(draftId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (distinctionId: number) => removeDistinctionFromDraft(draftId, distinctionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.draftDistinctions(draftId),
      });
      // Also invalidate the distinctions list to refresh lock status
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.lists(),
      });
    },
  });
}

/**
 * Swap mutually exclusive distinctions on a draft.
 *
 * This atomically removes one distinction and adds another.
 * Invalidates the draft distinctions query on success.
 */
export function useSwapDistinction(draftId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SwapDistinctionRequest) => swapDistinctionsOnDraft(draftId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.draftDistinctions(draftId),
      });
      // Also invalidate the distinctions list to refresh lock status
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.lists(),
      });
    },
  });
}

/**
 * Sync all distinctions on a draft at once.
 *
 * This replaces all distinctions with the provided list in a single API call.
 * Use this for bulk updates instead of individual add/remove calls.
 */
export function useSyncDistinctions(draftId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (distinctionIds: number[]) => syncDistinctionsOnDraft(draftId, distinctionIds),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.draftDistinctions(draftId),
      });
      // Also invalidate the distinctions list to refresh lock status
      queryClient.invalidateQueries({
        queryKey: distinctionKeys.lists(),
      });
      // Invalidate draft to refresh stat_bonuses after cap enforcement
      queryClient.invalidateQueries({
        queryKey: ['character-creation', 'draft'],
      });
    },
  });
}
