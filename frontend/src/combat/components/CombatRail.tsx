/**
 * CombatRail — the combat right rail, rendered in-scene on /scenes/:id (#2197).
 *
 * Extracted verbatim from the now-deleted CombatScenePage (the former
 * /scenes/:id/combat route's C-frame right column): a tab strip (Your Turn |
 * Map) switching between CombatTurnPanel and CombatTacticalMap (#2006), plus
 * the deep-link modal host (#551). SceneDetailPage mounts this only once it
 * has resolved an active encounter for the scene — the no-encounter /
 * loading states, and the incoming-duel-challenge prompt (now covered
 * site-wide by DuelChallengeNotifier, #2157), stay the caller's concern.
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
import { DeepLinkModalHost } from '@/combat/modals/DeepLinkModalHost';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { CastPosition, PositionTargetShape } from '@/actions/types';

export interface CombatRailProps {
  /** The scene this encounter belongs to — reserved for rail-level scene-scoped affordances. */
  sceneId: number;
  encounterId: number;
}

export function CombatRail({ encounterId }: CombatRailProps) {
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

  // Right-rail tab — "Your Turn" (CombatTurnPanel) vs "Map" (CombatTacticalMap, #2006).
  // Defaults to 'turn' so existing behavior is unchanged for anyone not opting into the map.
  const [rightRailTab, setRightRailTab] = useState<'turn' | 'map'>('turn');

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
        onValueChange={(value) => setRightRailTab(value as 'turn' | 'map')}
        className="flex h-full flex-col"
      >
        <TabsList className="grid w-full shrink-0 grid-cols-2">
          <TabsTrigger value="turn" data-testid="rail-tab-turn" className="text-xs">
            Your Turn
          </TabsTrigger>
          <TabsTrigger value="map" data-testid="rail-tab-map" className="text-xs">
            Map
          </TabsTrigger>
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
            encounterId={encounterId}
            characterId={characterId}
            positionShape={focusedPositionShape}
            onPickPosition={handlePickPosition}
          />
        </TabsContent>
      </Tabs>

      {/* Deep-link modal host — single Redux-driven modal for condition / clash /
       * opponent / participant / combo deep links (#551). Mounted once; reads
       * the open-modal target from the deepLinkModal slice. */}
      <DeepLinkModalHost encounterId={encounterId} />
    </div>
  );
}
