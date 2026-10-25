/**
 * CombatMainMap - the battle map as the main view of a fight (#4670).
 *
 * Mounted in the wide column of the scene page and the game page while an
 * encounter is on; the turn panel and log sit beside it in the rail. Reads
 * the shared cast-position pick state so a place click fills the cast.
 */

import { useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useCombatPick } from '@/combat/combatPick';
import { CombatTacticalMap } from '@/combat/components/CombatTacticalMap';

export function CombatMainMap({ sceneId, encounterId }: { sceneId: number; encounterId: number }) {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter)?.character_id ?? 0,
    [myRosterEntries, activeCharacter]
  );
  const { positionShape, pickPosition } = useCombatPick();
  return (
    <div
      className="h-[clamp(320px,55vh,640px)] shrink-0 max-md:h-[40vh]"
      data-testid="combat-main-map"
    >
      <CombatTacticalMap
        sceneId={sceneId}
        encounterId={encounterId}
        characterId={characterId}
        positionShape={positionShape}
        onPickPosition={pickPosition}
      />
    </div>
  );
}
