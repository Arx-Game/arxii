/**
 * The roster character the viewer is acting as, or null (#3564).
 *
 * Moved out of `GMAdjudicationPanel` so the beat form can dispatch GM
 * actions too (see `GMAdjudicationPanel.tsx`, which now calls this hook
 * instead of duplicating the resolution).
 */

import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';

export function useActiveCharacterId(): number | null {
  const { entry } = useBrowsingIdentity();
  return entry?.character_id ?? null;
}
