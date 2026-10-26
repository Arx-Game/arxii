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
 * - `GMFeatureControls` (#4675): add a feature to a place, or remove one.
 *
 * The tab itself is shown only when `scene.viewer_can_gm` (CombatRail).
 */

import { useCombatEncounter, useOpenStandoff } from '@/combat/queries';
import { GMStandoffPanel } from '@/combat/standoff/GMStandoffPanel';
import { Button } from '@/components/ui/button';
import { GMEncounterControls } from '@/combat/sections/GMEncounterControls';
import { GMFeatureControls } from '@/combat/components/GMFeatureControls';
import { COMBAT_GM_TOOL_TABS, GMAdjudicationPanel } from '@/scenes/components/GMAdjudicationPanel';
import type { SceneDetail } from '@/scenes/types';

export interface CombatGMTabProps {
  sceneId: number;
  encounterId: number;
  scene: SceneDetail | undefined;
  viewerCanGm: boolean;
  /** The GM's active character: its available actions gate the Add feature control. */
  characterId: number;
}

function OpenStandoffButton({ encounterId }: { encounterId: number }) {
  const open = useOpenStandoff(encounterId);
  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={open.isPending}
        onClick={() => open.mutate()}
      >
        Open a standoff
      </Button>
      {open.error && (
        <p role="alert" className="text-xs text-destructive">
          {open.error.message}
        </p>
      )}
    </div>
  );
}

export function CombatGMTab({
  sceneId,
  encounterId,
  scene,
  viewerCanGm,
  characterId,
}: CombatGMTabProps) {
  const { data: encounter } = useCombatEncounter(encounterId);
  return (
    <div className="space-y-3" data-testid="combat-gm-tab">
      {encounter?.gm_standoff && (
        <GMStandoffPanel encounterId={encounterId} standoff={encounter.gm_standoff} />
      )}
      {encounter && !encounter.gm_standoff && (encounter.round_number ?? 0) === 0 && (
        <OpenStandoffButton encounterId={encounterId} />
      )}
      {encounter && (
        <GMEncounterControls sceneId={sceneId} encounter={encounter} viewerCanGm={viewerCanGm} />
      )}
      <GMFeatureControls sceneId={sceneId} encounterId={encounterId} characterId={characterId} />
      <GMAdjudicationPanel scene={scene} tabs={COMBAT_GM_TOOL_TABS} title="Fight Tools" />
    </div>
  );
}
