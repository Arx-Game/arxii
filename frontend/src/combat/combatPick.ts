/**
 * The cast-time position pick context and its hook (#2206, #4670). The provider
 * lives in CombatPickContext.tsx.
 */

import { createContext, useContext } from 'react';
import type { CastPosition, PositionTargetShape } from '@/actions/types';

export interface CombatPickValue {
  castPosition: CastPosition;
  setCastPosition: (next: CastPosition) => void;
  positionShape: PositionTargetShape;
  setPositionShape: (shape: PositionTargetShape) => void;
  pickPosition: (positionId: number) => boolean;
}

export const CombatPickContext = createContext<CombatPickValue | null>(null);

export function useCombatPick(): CombatPickValue {
  const value = useContext(CombatPickContext);
  if (!value) throw new Error('useCombatPick must be used inside a CombatPickProvider');
  return value;
}
