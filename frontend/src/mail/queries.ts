import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchMail, sendMail, searchTenures, markMailRead, fetchUnreadMailCount } from './api';
import type { PlayerMail, MailFormData, RosterTenureOption } from './types';
import type { PaginatedResponse } from '@/shared/types';
import { useAccount } from '@/store/hooks';

export const mailKeys = {
  all: ['mail'] as const,
  list: (page: number) => [...mailKeys.all, page] as const,
  unreadCount: () => [...mailKeys.all, 'unread-count'] as const,
};

export function useMailQuery(page: number) {
  return useQuery<PaginatedResponse<PlayerMail>>({
    queryKey: mailKeys.list(page),
    queryFn: () => fetchMail(page),
    throwOnError: true,
  });
}

export function useSendMail() {
  return useMutation({
    mutationFn: (data: MailFormData) => sendMail(data),
  });
}

export function useTenureSearch(term: string) {
  return useQuery<PaginatedResponse<RosterTenureOption>>({
    queryKey: ['tenure-search', term],
    queryFn: () => searchTenures(term),
    enabled: term.length > 1,
    throwOnError: true,
  });
}

/** Marks a single received letter read; invalidates the mail list + unread count on success. */
export function useMarkMailRead(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markMailRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mailKeys.all }).catch(() => {});
    },
  });
}

/**
 * Unread-letter count for the "Letters" header badge — mirrors
 * `useUnreadNarrativeCount` (REST count query, guarded on auth so the query
 * doesn't fire on unauthenticated page loads like the login page).
 */
export function useUnreadMailCount() {
  const account = useAccount();
  const { data } = useQuery({
    queryKey: mailKeys.unreadCount(),
    queryFn: fetchUnreadMailCount,
    enabled: !!account,
    // No throwOnError: a nav badge must fail silent (0 → hidden), never
    // detonate the Header tree. Mirrors UnreadNarrativeBadge.
  });
  return data ?? 0;
}
