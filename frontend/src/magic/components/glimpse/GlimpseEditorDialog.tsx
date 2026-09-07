/**
 * GlimpseEditorDialog — the "finish later" Glimpse editor mounted on the
 * own-character sheet (#2427 Task 6).
 *
 * Hosts the shared `GlimpseFlow` in live mode: catalog via `useGlimpseTags()`
 * (the same catalog CG's `GlimpseSection` reads), selection seeded from the
 * aura's current `glimpse_tags`/`glimpse_story`, writes through the Task 4
 * aura action mutation `useSetGlimpseTags`/`useSetGlimpseProse`
 * (`@/magic/queries`). `showDeferralControls` is false: closing the dialog
 * IS the deferral; there is no separate "skip" affordance once a character
 * already exists (unlike CG, which can't finish later any other way).
 *
 * `GlimpseFlowProps` dropped its link-distinction props (#3675: CG offers
 * distinctions by chapter now, not by tag suggestion); this mount's own
 * link/unlink UI (CharacterDistinction row id, distinct from CG's catalog
 * Distinction id, see git history for `useToggleGlimpseDistinction`) went
 * with them. Re-wiring a post-CG distinction editor onto the offers model is
 * a separate follow-up, not part of #3675.
 */

import { useState } from 'react';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useGlimpseTags } from '@/character-creation/queries';
import { useSetGlimpseProse, useSetGlimpseTags } from '@/magic/queries';
import type { CharacterSheetAura, CharacterSheetDistinction } from '@/character_sheets/api';
import { GlimpseFlow } from './GlimpseFlow';
import type { GlimpseTagOption } from './glimpseTypes';

interface GlimpseEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** CharacterSheet pk — backs the character-sheet query invalidated after every write. */
  characterId: number;
  aura: CharacterSheetAura;
  /** The sheet payload's own `distinctions` list — no separate fetch (#2427 constraint). */
  distinctions: CharacterSheetDistinction[];
}

export function GlimpseEditorDialog({
  open,
  onOpenChange,
  characterId,
  aura,
  // Reserved for the post-CG offers-model re-wire (#3675 follow-up; see file
  // header): the sheet's distinctions list still comes in as a prop (no
  // separate fetch, #2427 constraint) but this dialog has nothing to link
  // them to right now.
  distinctions: _distinctions,
}: GlimpseEditorDialogProps) {
  const { data: tags } = useGlimpseTags();
  const setTags = useSetGlimpseTags(aura.id, characterId);
  const setProse = useSetGlimpseProse(aura.id, characterId);

  const [prose, setProseDraft] = useState(aura.glimpse_story);

  const selectedTagIds = aura.glimpse_tags.map((tag) => tag.id);

  const handleChangeAxis = (axis: GlimpseTagOption['axis'], tagIds: number[]) => {
    setTags.mutate({ axis, tag_ids: tagIds });
  };

  const proseDirty = prose !== aura.glimpse_story;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        data-testid="glimpse-editor-dialog"
      >
        <DialogHeader>
          <DialogTitle>Finish your Glimpse</DialogTitle>
        </DialogHeader>
        <GlimpseFlow
          tags={tags ?? []}
          selectedTagIds={selectedTagIds}
          prose={prose}
          onChangeAxis={handleChangeAxis}
          onChangeProse={setProseDraft}
          showDeferralControls={false}
        />
        <DialogFooter>
          <Button
            type="button"
            onClick={() => setProse.mutate({ text: prose })}
            disabled={!proseDirty || setProse.isPending}
            data-testid="glimpse-save-story"
          >
            Save story
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
