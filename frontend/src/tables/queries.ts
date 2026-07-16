/**
 * Tables React Query hooks
 *
 * Wraps every api.ts function with React Query hooks.
 * tablesKeys factory provides consistent query keys for cache invalidation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type {
  ListBulletinPostsParams,
  ListBulletinRepliesParams,
  ListMembershipsParams,
  ListTablesParams,
} from './api';
import type {
  BulletinPostCreateBody,
  BulletinPostUpdateBody,
  BulletinReplyCreateBody,
  BulletinReplyUpdateBody,
  GMTableCreateBody,
  GMTableMembershipCreateBody,
  GMTableTransferBody,
  GMTableUpdateBody,
} from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

const TABLES_ROOT = ['tables'] as const;

/**
 * Trailing params are ELIDED when absent (2026-07 audit fix): the old shape
 * appended the filters slot unconditionally, so `tablesKeys.members(id)` was
 * `['tables','members',id,undefined]` — which React Query v5 does NOT treat
 * as a prefix of `['tables','members',id,{table,active:true}]`. Every
 * invite/remove/leave/bulletin invalidation therefore matched nothing and the
 * roster/post list stayed stale until a hard refresh. The `*All` bare-prefix
 * keys give invalidations a params-agnostic root to target.
 */
export const tablesKeys = {
  all: TABLES_ROOT,
  list: (filters?: ListTablesParams) =>
    filters === undefined
      ? ([...TABLES_ROOT, 'list'] as const)
      : ([...TABLES_ROOT, 'list', filters] as const),
  detail: (id: number) => [...TABLES_ROOT, 'detail', id] as const,
  members: (tableId: number, filters?: ListMembershipsParams) =>
    filters === undefined
      ? ([...TABLES_ROOT, 'members', tableId] as const)
      : ([...TABLES_ROOT, 'members', tableId, filters] as const),
  bulletinPostsAll: [...TABLES_ROOT, 'bulletin-posts'] as const,
  bulletinPosts: (params?: ListBulletinPostsParams) =>
    params === undefined
      ? ([...TABLES_ROOT, 'bulletin-posts'] as const)
      : ([...TABLES_ROOT, 'bulletin-posts', params] as const),
  bulletinRepliesAll: [...TABLES_ROOT, 'bulletin-replies'] as const,
  bulletinReplies: (params?: ListBulletinRepliesParams) =>
    params === undefined
      ? ([...TABLES_ROOT, 'bulletin-replies'] as const)
      : ([...TABLES_ROOT, 'bulletin-replies', params] as const),
};

// ---------------------------------------------------------------------------
// Table read hooks
// ---------------------------------------------------------------------------

export function useTables(filters?: ListTablesParams) {
  return useQuery({
    queryKey: tablesKeys.list(filters),
    queryFn: () => api.getTables(filters),
    throwOnError: true,
  });
}

export function useTable(id: number) {
  return useQuery({
    queryKey: tablesKeys.detail(id),
    queryFn: () => api.getTable(id),
    enabled: id > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Membership read hooks
// ---------------------------------------------------------------------------

export function useTableMembers(tableId: number, filters?: Omit<ListMembershipsParams, 'table'>) {
  const params: ListMembershipsParams = { table: tableId, ...filters };
  return useQuery({
    queryKey: tablesKeys.members(tableId, params),
    queryFn: () => api.getTableMemberships(params),
    enabled: tableId > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Table mutation hooks
// ---------------------------------------------------------------------------

export function useCreateTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: GMTableCreateBody) => api.createTable(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tablesKeys.list() }).catch(() => {});
    },
  });
}

export function useUpdateTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: GMTableUpdateBody }) =>
      api.updateTable(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: tablesKeys.detail(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.list() }).catch(() => {});
    },
  });
}

export function useArchiveTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.archiveTable(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: tablesKeys.detail(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.list() }).catch(() => {});
    },
  });
}

export function useTransferOwnership() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: GMTableTransferBody }) =>
      api.transferOwnership(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: tablesKeys.detail(id) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.list() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Membership mutation hooks
// ---------------------------------------------------------------------------

export function useInviteToTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: GMTableMembershipCreateBody) => api.inviteToTable(data),
    onSuccess: (membership) => {
      qc.invalidateQueries({ queryKey: tablesKeys.members(membership.table) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.detail(membership.table) }).catch(() => {});
    },
  });
}

export function useRemoveMembership() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ membershipId, tableId: _tableId }: { membershipId: number; tableId: number }) =>
      api.removeMembership(membershipId),
    onSuccess: (_, { tableId }) => {
      qc.invalidateQueries({ queryKey: tablesKeys.members(tableId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.detail(tableId) }).catch(() => {});
    },
  });
}

export function useLeaveTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ membershipId, tableId: _tableId }: { membershipId: number; tableId: number }) =>
      api.leaveTable(membershipId),
    onSuccess: (_, { tableId }) => {
      qc.invalidateQueries({ queryKey: tablesKeys.members(tableId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.detail(tableId) }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.list() }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Bulletin Post read hooks
// ---------------------------------------------------------------------------

/**
 * Fetch bulletin posts for a given table (and optionally story).
 * The queryset is already permission-filtered by the backend.
 */
export function useBulletinPosts(params: ListBulletinPostsParams) {
  return useQuery({
    queryKey: tablesKeys.bulletinPosts(params),
    queryFn: () => api.getBulletinPosts(params),
    enabled: (params.table ?? 0) > 0,
    throwOnError: true,
  });
}

/**
 * Fetch replies for a single bulletin post.
 * Replies are also embedded in the post's `replies` field but this
 * hook is provided for manual refresh scenarios.
 */
export function useBulletinReplies(postId: number) {
  const params: ListBulletinRepliesParams = { post: postId };
  return useQuery({
    queryKey: tablesKeys.bulletinReplies(params),
    queryFn: () => api.getBulletinReplies(params),
    enabled: postId > 0,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Bulletin Post mutation hooks
// ---------------------------------------------------------------------------

export function useCreateBulletinPost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BulletinPostCreateBody) => api.createBulletinPost(data),
    onSuccess: () => {
      // Bare prefix (2026-07 audit): a specific { table } params object never
      // partial-matched the list query's { table, story } key, so a new/edited
      // post never appeared until a hard refresh.
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
    },
  });
}

export function useUpdateBulletinPost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: BulletinPostUpdateBody; tableId: number }) =>
      api.updateBulletinPost(id, data),
    onSuccess: () => {
      // Bare prefix (2026-07 audit): a specific { table } params object never
      // partial-matched the list query's { table, story } key, so a new/edited
      // post never appeared until a hard refresh.
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
    },
  });
}

export function useDeleteBulletinPost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tableId: _tableId }: { id: number; tableId: number }) =>
      api.deleteBulletinPost(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
    },
  });
}

// ---------------------------------------------------------------------------
// Bulletin Reply mutation hooks
// ---------------------------------------------------------------------------

export function useCreateBulletinReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BulletinReplyCreateBody) => api.createBulletinReply(data),
    onSuccess: () => {
      // Invalidate the post list so the embedded replies_cached refreshes.
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinRepliesAll }).catch(() => {});
    },
  });
}

export function useUpdateBulletinReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
      postId: _postId,
    }: {
      id: number;
      data: BulletinReplyUpdateBody;
      postId: number;
    }) => api.updateBulletinReply(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
    },
  });
}

export function useDeleteBulletinReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, postId: _postId }: { id: number; postId: number }) =>
      api.deleteBulletinReply(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tablesKeys.bulletinPostsAll }).catch(() => {});
    },
  });
}
