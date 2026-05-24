import { useQuery } from '@tanstack/react-query';
import { fetchPendingUnlinkedActions } from '../queries';
import type { PendingUnlinkedActionRow } from '../queries';

export type { PendingUnlinkedActionRow };

export function usePendingUnlinkedActions(
  sceneId: string,
  personaId: number | null
): { data: PendingUnlinkedActionRow[]; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['scenes', 'pending-unlinked-actions', sceneId, personaId],
    queryFn: () => fetchPendingUnlinkedActions(sceneId, personaId!),
    enabled: personaId !== null,
    staleTime: 5_000,
  });

  return {
    data: query.data ?? [],
    isLoading: query.isLoading,
  };
}
