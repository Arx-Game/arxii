/**
 * GiftSelector — second step of the GiftStage funnel (#2426 Task 10).
 *
 * Lists the gifts pickable for the draft's chosen tradition + path
 * (GET /api/character-creation/gifts/?draft_id=). Selecting a gift resets any
 * previously chosen techniques, since the technique catalog is scoped per-gift.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { cn } from '@/lib/utils';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { useEffect } from 'react';
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
          ...draft.draft_data,
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
          ...draft.draft_data,
          selected_gift_id: null,
          selected_technique_ids: [],
        },
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when the fetched gift list settles, not on every draft mutation
  }, [gifts, isFetching]);

  if (!draft.selected_tradition) {
    return (
      <p className="text-sm text-muted-foreground">Select a tradition above to see your gifts.</p>
    );
  }

  if (!draft.selected_path) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a Path in the Path stage to see available gifts.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading gifts...</span>
      </div>
    );
  }

  if (!gifts || gifts.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No gifts are available for your tradition and path.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {gifts.map((gift) => {
        const isSelected = selectedGiftId === gift.id;
        return (
          <Card
            key={gift.id}
            className={cn(
              'cursor-pointer transition-all',
              isSelected && 'ring-2 ring-primary',
              !isSelected && 'hover:ring-1 hover:ring-primary/50'
            )}
            onClick={() => handleSelect(gift.id)}
          >
            <CardHeader className="p-3">
              <CardTitle className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {gift.codex_entry_id != null ? (
                    <CodexTerm entryId={gift.codex_entry_id}>{gift.name}</CodexTerm>
                  ) : (
                    gift.name
                  )}
                </span>
                {isSelected && <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-3 pb-3 pt-0">
              <CardDescription className="text-xs">{gift.description}</CardDescription>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
