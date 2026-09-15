/**
 * CG mount of the guided Glimpse flow (#2427).
 *
 * Reads the catalog via useGlimpseTags and binds `GlimpseAxes` (#3675 fix
 * round 1's folio-grammar redesign, replacing the shared `GlimpseFlow`'s
 * shadcn accordion for this one mount; the sheet's live editor still uses
 * `GlimpseFlow` unchanged) to draft_data keys (glimpse_tag_ids /
 * glimpse_story), persisting through useUpdateDraft on change (same
 * PATCH-merge contract as the funnel steps). `GlimpseAxes` owns its own
 * per-tag offers layout and story box; `GlimpseSection` stays the thin
 * state binder: draft reads, `updateDraft` writes, the isCollapsed
 * deferral affordance, and the copy query (threaded straight to
 * `GlimpseAxes` rather than resolved into individual strings here, since
 * `GlimpseAxes` needs several per-axis/per-tag copy keys, not just one
 * heading).
 *
 * No heading of its own: GiftStage's own `section-h` already prints the
 * chapter heading above this mount (`copy?.magic_glimpse_heading`); a
 * second heading rendered in here was a demo-fidelity defect (fix round 1).
 *
 * Prose stays on the parent GiftStage's shared react-hook-form instance
 * (`register('glimpse_story')`, passed down — `AnimaCheckStep`'s
 * `ritualNameField` prop is the precedent) so it still saves via
 * `saveFormFields` on stage leave; tag picks write immediately via
 * `updateDraft`, like `GiftSelector`'s `selected_gift_id`.
 */

import { useState } from 'react';
import type { ChangeEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { useCGExplanations, useGlimpseTags, useUpdateDraft } from '../../queries';
import type { CharacterDraft, GlimpseTagOption } from '../../types';
import { GlimpseAxes } from './GlimpseAxes';

interface GlimpseSectionProps {
  draft: CharacterDraft;
  /** Registration for the prose field — owned by GiftStage's shared form so a
   * single beforeLeave save covers ritual name + motif + glimpse. */
  glimpseProseField: UseFormRegisterReturn<'glimpse_story'>;
}

export function GlimpseSection({ draft, glimpseProseField }: GlimpseSectionProps) {
  const updateDraft = useUpdateDraft();
  const { data: tags } = useGlimpseTags(draft.selected_path?.id);
  const { data: copy } = useCGExplanations();

  const [isCollapsed, setIsCollapsed] = useState(false);
  // Prose is uncontrolled from RHF's point of view (no `value` on a register
  // return) so this local copy exists purely to give GlimpseAxes a controlled
  // display value that starts from the last-saved draft_data.
  const [prose, setProse] = useState(() => draft.draft_data.glimpse_story ?? '');

  const selectedTagIds = draft.draft_data.glimpse_tag_ids ?? [];

  const handleChangeAxis = (axis: GlimpseTagOption['axis'], tagIds: number[]) => {
    if (!tags) return;
    const axisTagIds = new Set(tags.filter((tag) => tag.axis === axis).map((tag) => tag.id));
    const otherAxisSelections = selectedTagIds.filter((id) => !axisTagIds.has(id));
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          glimpse_tag_ids: [...otherAxisSelections, ...tagIds],
        },
      },
    });
  };

  const handleChangeProse = (text: string) => {
    setProse(text);
    // Manually driving register()'s onChange (rather than attaching its ref)
    // is RHF's documented pattern for wiring a non-native/controlled input —
    // it still updates the form's internal value and dirty state so
    // GiftStage's saveFormFields/getValues() picks up the edit on stage leave.
    glimpseProseField.onChange({
      target: { name: 'glimpse_story', value: text },
      type: 'change',
    } as unknown as ChangeEvent<HTMLTextAreaElement>);
  };

  if (isCollapsed) {
    return (
      <p className="ledger-line">
        The Glimpse is set aside for now; your tag picks are saved.{' '}
        <button type="button" className="btn-small" onClick={() => setIsCollapsed(false)}>
          Resume
        </button>
      </p>
    );
  }

  return (
    <>
      <GlimpseAxes
        draft={draft}
        tags={tags ?? []}
        selectedTagIds={selectedTagIds}
        copy={copy}
        onChangeAxis={handleChangeAxis}
        prose={prose}
        onChangeProse={handleChangeProse}
      />
      {/* The pre-#3675-fix-round-1 deferral affordance (write the tags now,
          finish the prose later); GlimpseAxes' own contract doesn't render
          this (not in the demo), so it stays here, one level up, the same
          way "Resume" above already does. */}
      <button type="button" className="btn-small" onClick={() => setIsCollapsed(true)}>
        Skip for now
      </button>
    </>
  );
}
