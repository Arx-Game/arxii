/**
 * CombatPickContext - cast-time position selection shared between Your Turn
 * (the rail) and the battle map (the main column) (#2206, #4670).
 *
 * YourTurn reports the focused technique's position shape; the map's place
 * clicks fill `castPosition` through `pickPosition`. Single shape toggles the
 * one destination; pair shape fills whichever of A/B is empty, and clicking a
 * place already in a slot clears just that slot. `pickPosition` returns false
 * (consumes nothing) unless a position-shaped technique is selected, so the
 * map's move dispatch runs unchanged otherwise.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { CastPosition, PositionTargetShape } from '@/actions/types';
import { CombatPickContext } from '@/combat/combatPick';

/** Picks belong to one encounter: they clear when `encounterId` changes (fight end, new fight). */
export function CombatPickProvider({
  encounterId,
  children,
}: {
  encounterId: number | null;
  children: ReactNode;
}) {
  const [castPosition, setCastPosition] = useState<CastPosition>({});
  const [positionShape, setPositionShape] = useState<PositionTargetShape>('none');

  useEffect(() => {
    setCastPosition({});
    setPositionShape('none');
  }, [encounterId]);

  const pickPosition = useCallback(
    (positionId: number): boolean => {
      if (positionShape === 'none') return false;
      if (positionShape === 'single') {
        setCastPosition((prev) =>
          prev.destinationId === positionId
            ? { ...prev, destinationId: undefined }
            : { ...prev, destinationId: positionId }
        );
        return true;
      }
      setCastPosition((prev) => {
        if (prev.pairA === positionId) return { ...prev, pairA: undefined };
        if (prev.pairB === positionId) return { ...prev, pairB: undefined };
        if (prev.pairA === undefined) return { ...prev, pairA: positionId };
        return { ...prev, pairB: positionId };
      });
      return true;
    },
    [positionShape]
  );

  const value = useMemo(
    () => ({ castPosition, setCastPosition, positionShape, setPositionShape, pickPosition }),
    [castPosition, positionShape, pickPosition]
  );

  return <CombatPickContext.Provider value={value}>{children}</CombatPickContext.Provider>;
}
