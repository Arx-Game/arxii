/**
 * GiftSelector (#3630) — gifts as index entries, second step of the Gift
 * funnel.
 *
 * Lists the gifts pickable for the draft's chosen tradition + path
 * (GET /api/character-creation/gifts/?draft_id=). Selecting a gift resets any
 * previously chosen techniques, since the technique catalog is scoped per-gift.
 */

import { useEffect } from 'react';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { Entry, EntryDoors, EntryList } from '../../folio';
import { useCGGifts, useUpdateDraft } from '../../queries';
import type { CharacterDraft } from '../../types';

interface GiftSelectorProps {
  draft: CharacterDraft;
}

export function GiftSelector({ draft }: GiftSelectorProps) {
  const updateDraft = useUpdateDraft();
  const { data: gifts, isLoading, isFetching } = useCGGifts(draft.id);
  const selectedGiftId = draft.draft_data.selected_gift_id ?? null;

  const handleSelect = (giftId: number) => {
    if (giftId === selectedGiftId) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          selected_gift_id: giftId,
          // Techniques are scoped to the chosen gift's catalog — clear stale picks.
          selected_technique_ids: [],
        },
      },
    });
  };

  // Clear a stale gift pick (and its now-orphaned technique picks) once the
  // fetched gift list has settled and no longer contains it — e.g. after a
  // tradition switch, the previously chosen gift may not belong to the new
  // tradition's catalog. Mirrors TechniqueSelector's defensive reset one
  // level down. Gated on `!isFetching` so it never fires against a stale
  // cached list while a refetch (triggered by the tradition switch) is
  // still in flight.
  useEffect(() => {
    if (isFetching || !gifts) return;
    if (selectedGiftId === null) return;
    if (gifts.some((gift) => gift.id === selectedGiftId)) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          selected_gift_id: null,
          selected_technique_ids: [],
        },
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when the fetched gift list settles, not on every draft mutation
  }, [gifts, isFetching]);

  if (!draft.selected_tradition) {
    return <p className="ledger-line">Select a tradition above to see your gifts.</p>;
  }

  if (!draft.selected_path) {
    return <p className="ledger-line">Select a Path in the Path stage to see available gifts.</p>;
  }

  if (isLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading gifts…
      </p>
    );
  }

  if (!gifts || gifts.length === 0) {
    return <p className="ledger-line">No gifts are available for your tradition and path.</p>;
  }

  return (
    <EntryList label="Gifts">
      {gifts.map((gift) => {
        const isSelected = selectedGiftId === gift.id;
        return (
          <Entry
            key={gift.id}
            name={gift.name}
            tag={gift.kind}
            chosen={isSelected}
            open={isSelected}
          >
            <p>{gift.description}</p>
            {gift.codex_entry_id != null && (
              <p className="ledger-line">
                <CodexTerm entryId={gift.codex_entry_id}>Codex: {gift.name}</CodexTerm>
              </p>
            )}
            <EntryDoors
              chooseLabel={`Choose ${gift.name}`}
              onChoose={() => handleSelect(gift.id)}
              chosen={isSelected}
            />
          </Entry>
        );
      })}
    </EntryList>
  );
}
