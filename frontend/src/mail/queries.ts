import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchMail, sendMail, searchTenures } from './api';
import type { PlayerMail, MailFormData, RosterTenureOption } from './types';
import type { PaginatedResponse } from '@/shared/types';

export function useMailQuery(page: number) {
  return useQuery<PaginatedResponse<PlayerMail>>({
    queryKey: ['mail', page],
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
