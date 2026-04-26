/**
 * Narrative React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { acknowledgeDelivery, getMyMessages } from './api';
import type { MyMessagesQueryParams } from './types';

export const narrativeKeys = {
  all: ['narrative'] as const,
  myMessages: (filters?: MyMessagesQueryParams) =>
    [...narrativeKeys.all, 'my-messages', filters] as const,
};

export function useMyMessages(filters?: MyMessagesQueryParams) {
  return useQuery({
    queryKey: narrativeKeys.myMessages(filters),
    queryFn: () => getMyMessages(filters),
    throwOnError: true,
  });
}

export function useAcknowledgeDelivery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acknowledgeDelivery,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: narrativeKeys.all });
    },
  });
}

export function useUnreadNarrativeCount() {
  const { data } = useMyMessages({ acknowledged: false });
  return data?.count ?? 0;
}
