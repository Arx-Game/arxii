/**
 * CombatGMTab (#3557): the combat rail's GM tab body. One home for every
 * lever a GM reaches for mid-fight:
 *
 * - `GMEncounterControls` (lifecycle, stakes/risk/pace/timer, add/remove
 *   combatants, manual round control), moved here from SceneDetailPage's rail
 *   column. Rendered only once `useCombatEncounter` has data, exactly as the
 *   page gated it, so the no-encounter "Start Encounter" branch can never
 *   flash inside a tab whose premise is a live encounter. The component keeps
 *   its own narrower `encounter.is_gm` gate.
 * - `GMAdjudicationPanel` narrowed to COMBAT_GM_TOOL_TABS (Condition,
 *   Dramatic Beat, Traps). The header panel renders the other tabs while an
 *   encounter is active, so no lever has two homes.
 *
 * The tab itself is shown only when `scene.viewer_can_gm` (CombatRail).
 */

import { useCombatEncounter } from '@/combat/queries';
import { GMEncounterControls } from '@/combat/sections/GMEncounterControls';
import { COMBAT_GM_TOOL_TABS, GMAdjudicationPanel } from '@/scenes/components/GMAdjudicationPanel';
import type { SceneDetail } from '@/scenes/types';

export interface CombatGMTabProps {
  sceneId: number;
  encounterId: number;
  scene: SceneDetail | undefined;
  viewerCanGm: boolean;
}

export function CombatGMTab({ sceneId, encounterId, scene, viewerCanGm }: CombatGMTabProps) {
  const { data: encounter } = useCombatEncounter(encounterId);
  return (
    <div className="space-y-3" data-testid="combat-gm-tab">
      {encounter && (
        <GMEncounterControls sceneId={sceneId} encounter={encounter} viewerCanGm={viewerCanGm} />
      )}
      <GMAdjudicationPanel scene={scene} tabs={COMBAT_GM_TOOL_TABS} title="Fight Tools" />
    </div>
  );
}
