/**
 * CombatRail — the combat right rail, rendered in-scene on /scenes/:id (#2197).
 *
 * Extracted verbatim from the now-deleted CombatScenePage (the former
 * /scenes/:id/combat route's C-frame right column): a tab strip (Your Turn |
 * Map | GM, the last only for a scene GM, #3557) switching between
 * CombatTurnPanel, CombatTacticalMap (#2006), and CombatGMTab, plus the
 * deep-link modal host (#551). SceneDetailPage mounts this only once it
 * has resolved an active encounter for the scene — the no-encounter /
 * loading states, and the incoming-duel-challenge prompt (now covered
 * site-wide by DuelChallengeNotifier, #2157), stay the caller's concern.
 *
 * The GM tab (`CombatGMTab`) hosts the encounter controls and the combat GM
 * tools so a GM never leaves the rail mid-fight; the map tab draws
 * bystanders from the scene, which is why `sceneId` is consumed here.
 *
 * Cast-time position selection (#2206) is lifted here (above the tab switch)
 * so both CombatTurnPanel's YourTurn section and the CombatTacticalMap tab
 * share the same state; each tab's TabsContent unmounts when inactive, so
 * this can't live inside either tab's own component.
 */

import { useState, useCallback, useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { CombatTurnPanel } from '@/combat/CombatTurnPanel';
import { CombatTacticalMap } from '@/combat/components/CombatTacticalMap';
import { CombatGMTab } from '@/combat/components/CombatGMTab';
import { DeepLinkModalHost } from '@/combat/modals/DeepLinkModalHost';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { CastPosition, PositionTargetShape } from '@/actions/types';
import type { SceneDetail } from '@/scenes/types';

export interface CombatRailProps {
  /** The scene this encounter belongs to; feeds the map's bystanders and the GM tab (#3557). */
  sceneId: number;
  encounterId: number;
  /** `scene.viewer_can_gm`: shows the GM tab (#3557). Defaults to false. */
  viewerCanGm?: boolean;
  /** The scene detail the GM tools need (participants for the target picker). */
  scene?: SceneDetail;
}

export function CombatRail({ sceneId, encounterId, viewerCanGm = false, scene }: CombatRailProps) {
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

  // Right-rail tab — "Your Turn" (CombatTurnPanel), "Map" (CombatTacticalMap,
  // #2006), and "GM" (CombatGMTab, #3557, shown only when viewerCanGm).
  // Defaults to 'turn' so existing behavior is unchanged for anyone not opting into the map.
  const [rightRailTab, setRightRailTab] = useState<'turn' | 'map' | 'gm'>('turn');

  // Cast-time position selection + the selected technique's position shape
  // (#2206) — lifted here (above the tab switch) so both CombatTurnPanel's
  // YourTurn section and the CombatTacticalMap tab share the same state; each
  // rail tab's TabsContent unmounts when inactive, so this can't live inside
  // either tab's own component. YourTurn reports `focusedPositionShape` via
  // onPositionShapeChange whenever the focused technique/its shape changes;
  // castPosition is the shared single-destination / pair A-B selection.
  const [castPosition, setCastPosition] = useState<CastPosition>({});
  const [focusedPositionShape, setFocusedPositionShape] = useState<PositionTargetShape>('none');

  // Map-click handler for the tactical-map tab (#2206). Single-click UI needs
  // its own fill/clear rules, distinct from ActionDeclarationCard's
  // PositionPicker (which renders explicit, separately-clickable A/B slot
  // pickers): single shape toggles the one destination on/off per click; pair
  // shape fills whichever of A/B is still empty, and clicking a position
  // already occupying a slot clears just that slot. Returns false (consumes
  // nothing) unless a position-shaped technique is selected, so TacticalMap's
  // move-dispatch logic runs unchanged otherwise.
  const handlePickPosition = useCallback(
    (positionId: number): boolean => {
      if (focusedPositionShape === 'none') return false;
      if (focusedPositionShape === 'single') {
        setCastPosition((prev) =>
          prev.destinationId === positionId
            ? { ...prev, destinationId: undefined }
            : { ...prev, destinationId: positionId }
        );
        return true;
      }
      // pair
      setCastPosition((prev) => {
        if (prev.pairA === positionId) return { ...prev, pairA: undefined };
        if (prev.pairB === positionId) return { ...prev, pairB: undefined };
        if (prev.pairA === undefined) return { ...prev, pairA: positionId };
        return { ...prev, pairB: positionId };
      });
      return true;
    },
    [focusedPositionShape]
  );

  return (
    <div className="min-h-0 overflow-y-auto" data-testid="combat-rail">
      <Tabs
        value={rightRailTab}
        onValueChange={(value) => setRightRailTab(value as 'turn' | 'map' | 'gm')}
        className="flex h-full flex-col"
      >
        <TabsList className={`grid w-full shrink-0 ${viewerCanGm ? 'grid-cols-3' : 'grid-cols-2'}`}>
          <TabsTrigger value="turn" data-testid="rail-tab-turn" className="text-xs">
            Your Turn
          </TabsTrigger>
          <TabsTrigger value="map" data-testid="rail-tab-map" className="text-xs">
            Map
          </TabsTrigger>
          {viewerCanGm && (
            <TabsTrigger value="gm" data-testid="rail-tab-gm" className="text-xs">
              GM
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="turn" className="mt-2 min-h-0 flex-1 overflow-y-auto">
          <CombatTurnPanel
            encounterId={encounterId}
            characterId={characterId}
            characterSheetId={characterSheetId}
            castPosition={castPosition}
            onCastPositionChange={setCastPosition}
            onPositionShapeChange={setFocusedPositionShape}
          />
        </TabsContent>
        <TabsContent value="map" className="mt-2 min-h-0 flex-1 overflow-y-auto">
          <CombatTacticalMap
            sceneId={sceneId}
            encounterId={encounterId}
            characterId={characterId}
            positionShape={focusedPositionShape}
            onPickPosition={handlePickPosition}
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
