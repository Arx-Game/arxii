import { useQuery } from '@tanstack/react-query';

import { getPresence } from './api';

export const presenceKeys = {
  all: ['presence'] as const,
};

/** Online presence (who + where). Refetches periodically — presence changes often. */
export function usePresence() {
  return useQuery({
    queryKey: presenceKeys.all,
    queryFn: getPresence,
    staleTime: 20 * 1000,
    refetchInterval: 30 * 1000,
  });
}
