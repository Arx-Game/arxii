/**
 * TraditionStep — first step of the GiftStage funnel (#2426 Task 10).
 *
 * Thin wrapper around the existing `TraditionPicker` (cards + hover detail +
 * CodexTerm lore + useSelectTradition already live there — see #2410). Guards
 * on the draft having a selected Beginning, which gates tradition availability.
 */

import type { CharacterDraft } from '../../types';
import { TraditionPicker } from '../TraditionPicker';

interface TraditionStepProps {
  draft: CharacterDraft;
}

export function TraditionStep({ draft }: TraditionStepProps) {
  const beginningId = draft.selected_beginnings?.id;

  if (!beginningId) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a Beginning in the Heritage stage to see available traditions.
      </p>
    );
  }

  return <TraditionPicker draft={draft} beginningId={beginningId} />;
}
