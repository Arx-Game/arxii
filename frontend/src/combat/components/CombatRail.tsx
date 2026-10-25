/**
 * CombatRail — the combat right rail, rendered in-scene on /scenes/:id (#2197).
 *
 * Extracted verbatim from the now-deleted CombatScenePage (the former
 * /scenes/:id/combat route's C-frame right column): a tab strip (Your Turn |
 * GM, the last only for a scene GM, #3557) switching between
 * CombatTurnPanel and CombatGMTab, plus the
 * deep-link modal host (#551). SceneDetailPage mounts this only once it
 * has resolved an active encounter for the scene — the no-encounter /
 * loading states, and the incoming-duel-challenge prompt (now covered
 * site-wide by DuelChallengeNotifier, #2157), stay the caller's concern.
 *
 * The GM tab (`CombatGMTab`) hosts the encounter controls and the combat GM
 * tools so a GM never leaves the rail mid-fight. The battle map is the page's
 * main view (CombatMainMap, #4670); cast-time position selection (#2206) lives
 * in CombatPickProvider so Your Turn here and the map there share it.
 */

import { useState, useMemo, useEffect } from 'react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { CombatTurnPanel } from '@/combat/CombatTurnPanel';
import { useCombatPick } from '@/combat/combatPick';
import { CombatGMTab } from '@/combat/components/CombatGMTab';
import { DeepLinkModalHost } from '@/combat/modals/DeepLinkModalHost';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { SceneDetail } from '@/scenes/types';

export interface CombatRailProps {
  /** The scene this encounter belongs to; feeds the GM tab (#3557). */
  sceneId: number;
  encounterId: number;
  /** `scene.viewer_can_gm`: shows the GM tab (#3557). Defaults to false. */
  viewerCanGm?: boolean;
  /** The scene detail the GM tools need (participants for the target picker). */
  scene?: SceneDetail;
  /** Forwarded to CombatTurnPanel's outcome banner Dismiss button (#3551). */
  onDismissOutcome?: () => void;
}

export function CombatRail({
  sceneId,
  encounterId,
  viewerCanGm = false,
  scene,
  onDismissOutcome,
}: CombatRailProps) {
  // Active character from Redux global state
  const activeCharacter = useAppSelector((state) => state.game.active);

  // Resolve the active character's character_id (== character_sheet_id).
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const characterId = activeEntry?.character_id ?? 0;
  const characterSheetId = activeEntry?.character_id ?? 0; // same pk — see MyRosterEntry type

  // Right-rail tab: "Your Turn" (CombatTurnPanel) and "GM" (CombatGMTab, #3557,
  // shown only when viewerCanGm). The map is the page's main view (#4670).
  const [rightRailTab, setRightRailTab] = useState<'turn' | 'gm'>('turn');
  const { castPosition, setCastPosition, setPositionShape } = useCombatPick();

  // Your Turn unmounts on the GM tab; with it gone nothing can clear the shape,
  // and the map would keep consuming place clicks.
  useEffect(() => {
    if (rightRailTab === 'gm') setPositionShape('none');
  }, [rightRailTab, setPositionShape]);

  return (
    <div className="min-h-0 overflow-y-auto" data-testid="combat-rail">
      <Tabs
        value={rightRailTab}
        onValueChange={(value) => setRightRailTab(value as 'turn' | 'gm')}
        className="flex h-full flex-col"
      >
        {viewerCanGm && (
          <TabsList className="grid w-full shrink-0 grid-cols-2">
            <TabsTrigger value="turn" data-testid="rail-tab-turn" className="text-xs">
              Your Turn
            </TabsTrigger>
            <TabsTrigger value="gm" data-testid="rail-tab-gm" className="text-xs">
              GM
            </TabsTrigger>
          </TabsList>
        )}
        <TabsContent value="turn" className="mt-2 min-h-0 flex-1 overflow-y-auto">
          <CombatTurnPanel
            encounterId={encounterId}
            characterId={characterId}
            characterSheetId={characterSheetId}
            castPosition={castPosition}
            onCastPositionChange={setCastPosition}
            onPositionShapeChange={setPositionShape}
            onDismissOutcome={onDismissOutcome}
          />
        </TabsContent>
        {viewerCanGm && (
          <TabsContent value="gm" className="mt-2 min-h-0 flex-1 overflow-y-auto">
            <CombatGMTab
              sceneId={sceneId}
              encounterId={encounterId}
              scene={scene}
              viewerCanGm={viewerCanGm}
            />
          </TabsContent>
        )}
      </Tabs>

      {/* Deep-link modal host — single Redux-driven modal for condition / clash /
       * opponent / participant / combo deep links (#551). Mounted once; reads
       * the open-modal target from the deepLinkModal slice. */}
      <DeepLinkModalHost encounterId={encounterId} />
    </div>
  );
}
