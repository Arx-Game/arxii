/**
 * SchoolingStances (#3675), the standard schooling set under a tradition: up to three
 * stances (rank 0, 1, 2), authored once. The server sends the rows the tradition's state
 * opens (living masters: all three; teachers gone: ranks 0 and 1; self-taught: none) and
 * the picker mounts this only when there are rows. Wording is staff's; prices are the
 * set's, never the tradition's own.
 *
 * Picking a stance syncs a Tradition Training entry at that stance's rank
 * (rank 0 clears the pick); every other CHOICE distinction on the draft is
 * resent unchanged, same as `ChapterOffers`.
 *
 * Each stance prints its Magic skill floor (#4457). Rank 0 grants none and says so; a
 * rank 1 or 2 stance whose floor staff have not set yet shows no Magic line at all.
 */

import { useCallback } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { CGExplanations, CharacterDraft, SchoolingLineRow, Tradition } from '../../types';
import { choiceEntries } from './syncHelpers';

/**
 * A stance's Magic skill line: its floor once staff set one, "No magic skills" on rank 0
 * (which grants none), and nothing for a rank 1 or 2 stance whose floor is still unset.
 */
function MagicSkillLine({ row, copy }: { row: SchoolingLineRow; copy?: CGExplanations }) {
  if (row.magic_skill_floor > 0) {
    return (
      <span className="grant">
        {(copy?.offers_magic_skill_floor ?? 'Magic skills {floor}').replace(
          '{floor}',
          String(row.magic_skill_floor)
        )}
      </span>
    );
  }
  if (row.rank === 0) {
    return <span className="none">{copy?.offers_magic_skill_floor_none ?? 'No magic skills'}</span>;
  }
  return null;
}

interface SchoolingStancesProps {
  draft: CharacterDraft;
  tradition: Tradition;
  copy?: CGExplanations;
}

export function SchoolingStances({ draft, tradition, copy }: SchoolingStancesProps) {
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
    <>
      <ul className="stances">
        {tradition.schooling.map((row) => {
          const pressed = selectedRank === row.rank;
          const disabled =
            (row.rank > 0 && (row.grants_distinction_id == null || row.offer_id == null)) ||
            syncDistinctions.isPending;
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
                  <span>{row.rank === 0 ? (copy?.offers_word_free ?? 'Free') : row.price}</span>
                  <span className={row.rank > 0 ? 'grant' : undefined}>
                    {row.techniques} technique{row.techniques === 1 ? '' : 's'}
                  </span>
                  <MagicSkillLine row={row} copy={copy} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {syncDistinctions.isError && (
        <span className="hint">
          {copy?.offers_sync_error ?? 'That pick did not save. Try again.'}
        </span>
      )}
    </>
  );
}
