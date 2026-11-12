import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dispatchMissiveAction, fetchMissives, fetchMissiveUnreadCount } from './api';
import type { MissiveActionKey } from './types';
import { inventoryKeys } from '@/inventory/hooks/useInventory';

/** Prefix of `useCharacterPurse`'s key (`@/status/queries`). */
const PURSE_KEY = ['status', 'purse'] as const;

export const missiveKeys = {
  all: ['missives'] as const,
  list: (entryId: number, page: number) => [...missiveKeys.all, 'list', entryId, page] as const,
  unreadCount: (entryId: number) => [...missiveKeys.all, 'unread-count', entryId] as const,
};

export function useMissivesQuery(entryId: number | null, page: number, enabled = true) {
  return useQuery({
    queryKey: missiveKeys.list(entryId ?? -1, page),
    queryFn: () => fetchMissives(entryId as number, page),
    enabled: enabled && entryId != null,
  });
}

/** Unread count for the top-bar badge; fails silent (a badge never breaks the bar). */
export function useMissiveUnreadCount(entryId: number | null) {
  const { data } = useQuery({
    queryKey: missiveKeys.unreadCount(entryId ?? -1),
    queryFn: () => fetchMissiveUnreadCount(entryId as number),
    enabled: entryId != null,
  });
  return data ?? 0;
}

export interface MissiveActionVars {
  key: MissiveActionKey;
  kwargs: Record<string, unknown>;
}

export function useMissiveAction(characterId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, kwargs }: MissiveActionVars) => {
      if (characterId == null) throw new Error('No active character.');
      return dispatchMissiveAction(characterId, key, kwargs);
    },
    onSettled: (_result, _error, { key }) => {
      queryClient.invalidateQueries({ queryKey: missiveKeys.all }).catch(() => {});
      if (key === 'read_missive') return;
      // Sending carries items and coin away; accepting brings them in; refusing sends
      // them home (the purse prefix covers every character this account plays).
      queryClient.invalidateQueries({ queryKey: PURSE_KEY }).catch(() => {});
      if (key !== 'refuse_missive') {
        queryClient.invalidateQueries({ queryKey: inventoryKeys.all }).catch(() => {});
      }
    },
  });
}
