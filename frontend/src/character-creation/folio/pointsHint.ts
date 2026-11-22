/**
 * What the "CG points" row of the selections panel says on hover (#5201).
 *
 * Unspent CG points convert to XP when the character is approved, and until #5201 that was
 * first said on Review, seven stages after the points are spent. The row is on the nine
 * stages that show the selections panel (Review has no panel and says it in its own
 * sentence), so the page gives the sentence once, here, and `RecordRail` puts it on the
 * row `cgRecord` marks `points`. It is undefined until the budget has loaded, and the row
 * then has no hover. With no budget row in the database the API answers the default
 * rate, 2.
 */
import { createContext, useContext } from 'react';

export const PointsHint = createContext<string | undefined>(undefined);

export function usePointsHint(): string | undefined {
  return useContext(PointsHint);
}

/** The sentence for a budget's rate, in the words the Review stage uses for the same fact. */
export function pointsHint(xpPerPoint: number): string {
  return `CG points left unspent convert to XP when the character is approved, ${xpPerPoint} XP for each point.`;
}
