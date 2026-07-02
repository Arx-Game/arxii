/**
 * Justice React Query hooks (#1765).
 */

import { useQuery } from '@tanstack/react-query';

import { fetchPersonaHeat } from './api';

/** The viewer's own warrant rows — where their active persona is wanted. */
export function usePersonaHeat(viewerEntryId: number | null) {
  return useQuery({
    queryKey: ['justice', 'heat', viewerEntryId],
    queryFn: () => fetchPersonaHeat(viewerEntryId as number),
    enabled: viewerEntryId !== null,
  });
}
