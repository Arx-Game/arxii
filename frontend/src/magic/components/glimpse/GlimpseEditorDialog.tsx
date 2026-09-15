/**
 * GlimpseEditorDialog — the "finish later" Glimpse editor mounted on the
 * own-character sheet (#2427 Task 6).
 *
 * Hosts the shared `GlimpseFlow` in live mode: catalog via `useGlimpseTags()`
 * (the same catalog CG's `GlimpseSection` reads), selection seeded from the
 * aura's current `glimpse_tags`/`glimpse_story`, writes through the Task 4
 * aura action mutations (`useSetGlimpseTags`/`useSetGlimpseProse`/
 * `useToggleGlimpseDistinction`, `@/magic/queries`). `showDeferralControls`
 * is false: closing the dialog IS the deferral; there is no separate "skip"
 * affordance once a character already exists (unlike CG, which can't finish
 * later any other way).
 *
 * `GlimpseFlowProps` dropped its link-distinction props (#3675: CG offers
 * distinctions by chapter now, rendered through `renderOffers`, not by tag
 * suggestion). That is a CG-only change: this mount's own link/unlink of the
 * character's *existing* distinctions is a different feature (not a CG
 * offer) and stays, now rendered directly here via `DistinctionLinkChips`
 * below `GlimpseFlow` instead of inside it.
 *
 * ID-SPACE NOTE, read before touching `linkableDistinctions` /
 * `onToggleDistinctionLink`: CG links a distinction to the Glimpse through
 * the offer that produced the pick (`offer_ids` naming a Glimpse tag offer,
 * see `magic/types.ts`). This live-sheet mount links by
 * **CharacterDistinction row id** instead, the id the aura's
 * `link-glimpse-distinction`/`unlink-glimpse-distinction` endpoints require
 * (`character_distinction_id`), which is exactly what
 * `CharacterSheetDistinction.id` already carries (see
 * `world.character_sheets.serializers._build_distinctions`:
 * `DistinctionEntry(id=cd.pk, ...)`). Never pass a catalog Distinction id
 * here: the two id spaces are not interchangeable.
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
import {
  useSetGlimpseProse,
  useSetGlimpseTags,
  useToggleGlimpseDistinction,
} from '@/magic/queries';
import type { CharacterSheetAura, CharacterSheetDistinction } from '@/character_sheets/api';
import { DistinctionLinkChips } from './DistinctionLinkChips';
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
  distinctions,
}: GlimpseEditorDialogProps) {
  const { data: tags } = useGlimpseTags();
  const setTags = useSetGlimpseTags(aura.id, characterId);
  const setProse = useSetGlimpseProse(aura.id, characterId);
  const toggleDistinction = useToggleGlimpseDistinction(aura.id, characterId);

  const [prose, setProseDraft] = useState(aura.glimpse_story);

  const selectedTagIds = aura.glimpse_tags.map((tag) => tag.id);

  // Live-sheet linking is by CharacterDistinction row id (see file header),
  // distinct from CG's offer-based linking.
  const linkedDistinctionIds = distinctions
    .filter((distinction) => distinction.is_from_glimpse)
    .map((distinction) => distinction.id);
  const linkableDistinctions = distinctions.map((distinction) => ({
    id: distinction.id,
    name: distinction.name,
  }));

  const handleChangeAxis = (axis: GlimpseTagOption['axis'], tagIds: number[]) => {
    setTags.mutate({ axis, tag_ids: tagIds });
  };

  const handleToggleDistinctionLink = (distinctionId: number) => {
    const isCurrentlyLinked = linkedDistinctionIds.includes(distinctionId);
    toggleDistinction.toggle(distinctionId, isCurrentlyLinked);
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
        <DistinctionLinkChips
          distinctions={linkableDistinctions}
          linkedIds={new Set(linkedDistinctionIds)}
          onToggle={handleToggleDistinctionLink}
          label="Link a distinction to your glimpse"
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
