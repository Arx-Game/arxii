/**
 * Tables React Query hooks
 *
 * Wraps every api.ts function with React Query hooks.
 * tablesKeys factory provides consistent query keys for cache invalidation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import type { ListMembershipsParams, ListTablesParams } from './api';
import type {
  GMTableCreateBody,
  GMTableMembershipCreateBody,
  GMTableTransferBody,
  GMTableUpdateBody,
} from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const tablesKeys = {
  all: ['tables'] as const,
  list: (filters?: ListTablesParams) => [...tablesKeys.all, 'list', filters] as const,
  detail: (id: number) => [...tablesKeys.all, 'detail', id] as const,
  members: (tableId: number, filters?: ListMembershipsParams) =>
    [...tablesKeys.all, 'members', tableId, filters] as const,
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
      void qc.invalidateQueries({ queryKey: tablesKeys.list() });
    },
  });
}

export function useUpdateTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: GMTableUpdateBody }) =>
      api.updateTable(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: tablesKeys.list() });
    },
  });
}

export function useArchiveTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.archiveTable(id),
    onSuccess: (_, id) => {
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: tablesKeys.list() });
    },
  });
}

export function useTransferOwnership() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: GMTableTransferBody }) =>
      api.transferOwnership(id, data),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: tablesKeys.list() });
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
      void qc.invalidateQueries({ queryKey: tablesKeys.members(membership.table) });
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(membership.table) });
    },
  });
}

export function useRemoveMembership() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ membershipId, tableId: _tableId }: { membershipId: number; tableId: number }) =>
      api.removeMembership(membershipId),
    onSuccess: (_, { tableId }) => {
      void qc.invalidateQueries({ queryKey: tablesKeys.members(tableId) });
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(tableId) });
    },
  });
}

export function useLeaveTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ membershipId, tableId: _tableId }: { membershipId: number; tableId: number }) =>
      api.leaveTable(membershipId),
    onSuccess: (_, { tableId }) => {
      void qc.invalidateQueries({ queryKey: tablesKeys.members(tableId) });
      void qc.invalidateQueries({ queryKey: tablesKeys.detail(tableId) });
      void qc.invalidateQueries({ queryKey: tablesKeys.list() });
    },
  });
}
