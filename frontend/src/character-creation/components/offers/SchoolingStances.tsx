/**
 * SchoolingStances (#3675), the standard schooling set under a
 * `living_masters` tradition: three stances (rank 0, 1, 2), authored once
 * and shown under every tradition with living teachers. Wording is staff's;
 * prices are the set's, never the tradition's own.
 *
 * Picking a stance syncs a Tradition Training entry at that stance's rank
 * (rank 0 clears the pick); every other CHOICE distinction on the draft is
 * resent unchanged, same as `ChapterOffers`.
 */

import { useCallback } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { CharacterDraft, SchoolingLineRow, Tradition } from '../../types';
import { choiceEntries } from './syncHelpers';

interface SchoolingStancesProps {
  draft: CharacterDraft;
  tradition: Tradition;
}

export function SchoolingStances({ draft, tradition }: SchoolingStancesProps) {
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);

  const schoolingOfferIds = new Set(
    tradition.schooling.map((row) => row.offer_id).filter((id): id is number => id != null)
  );
  const selectedEntry = (draftDistinctions ?? []).find((entry) =>
    entry.offer_ids.some((id) => typeof id === 'number' && schoolingOfferIds.has(id))
  );
  const selectedRank = selectedEntry?.rank ?? 0;

  const handlePick = useCallback(
    (row: SchoolingLineRow) => {
      const base = choiceEntries(draftDistinctions).filter(
        (e) => e.id !== selectedEntry?.distinction_id
      );
      if (row.rank === 0 || row.grants_distinction_id == null || row.offer_id == null) {
        syncDistinctions.mutate(base);
        return;
      }
      syncDistinctions.mutate([
        ...base,
        { id: row.grants_distinction_id, rank: row.rank, offer_id: row.offer_id },
      ]);
    },
    [draftDistinctions, selectedEntry, syncDistinctions]
  );

  return (
    <ul className="stances">
      {tradition.schooling.map((row) => {
        const pressed = selectedRank === row.rank;
        const disabled =
          row.rank > 0 && (row.grants_distinction_id == null || row.offer_id == null);
        return (
          <li key={row.schooling_line_id}>
            <button
              type="button"
              className="stance"
              aria-pressed={pressed}
              disabled={disabled}
              onClick={() => handlePick(row)}
            >
              <span className="dot" />
              <span>
                <b>{row.name}</b>
                <span className="g">{row.player_line}</span>
              </span>
              <span className="price">
                <span>{row.rank === 0 ? 'Free' : row.price}</span>
                <span className={row.rank > 0 ? 'grant' : undefined}>
                  {row.techniques} technique{row.techniques === 1 ? '' : 's'}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
