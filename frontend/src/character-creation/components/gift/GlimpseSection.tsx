/**
 * CG mount of the guided Glimpse flow (#2427).
 *
 * Reads the catalog via useGlimpseTags and binds GlimpseFlow to draft_data
 * keys (glimpse_tag_ids / glimpse_story / glimpse_linked_distinction_ids),
 * persisting through useUpdateDraft on change (same PATCH-merge contract as
 * the funnel steps). Linkable distinctions = the draft's already-chosen
 * distinctions; suggestion links to not-yet-chosen distinctions are kept in
 * glimpse_linked_distinction_ids and reconciled at finalize (unmatched ids
 * are ignored server-side).
 *
 * Prose stays on the parent GiftStage's shared react-hook-form instance
 * (`register('glimpse_story')`, passed down — `AnimaCheckStep`'s
 * `ritualNameField` prop is the precedent) so it still saves via
 * `saveFormFields` on stage leave; tag/link picks write immediately via
 * `updateDraft`, like `GiftSelector`'s `selected_gift_id`.
 */

import { Button } from '@/components/ui/button';
import { GlimpseFlow } from '@/magic/components/glimpse/GlimpseFlow';
import { useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { useDraftDistinctions } from '@/hooks/useDistinctions';
import { useGlimpseTags, useUpdateDraft } from '../../queries';
import type { CharacterDraft, GlimpseTagOption } from '../../types';

interface GlimpseSectionProps {
  draft: CharacterDraft;
  /** Registration for the prose field — owned by GiftStage's shared form so a
   * single beforeLeave save covers ritual name + motif + glimpse. */
  glimpseProseField: UseFormRegisterReturn<'glimpse_story'>;
  /**
   * Staff-authorable section heading, threaded down from GiftStage's
   * `copy?.magic_glimpse_heading` (GiftStage holds the `useCGExplanations()`
   * query — GlimpseSection stays a thin pass-through so GlimpseFlow itself
   * stays presentational). Falls back to GlimpseFlow's own default when
   * omitted.
   */
  heading?: string;
}

export function GlimpseSection({ draft, glimpseProseField, heading }: GlimpseSectionProps) {
  const updateDraft = useUpdateDraft();
  const { data: tags } = useGlimpseTags(draft.selected_path?.id);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);

  const [isCollapsed, setIsCollapsed] = useState(false);
  // Prose is uncontrolled from RHF's point of view (no `value` on a register
  // return) — this local copy exists purely to give GlimpseFlow a controlled
  // display value that starts from the last-saved draft_data.
  const [prose, setProse] = useState(() => draft.draft_data.glimpse_story ?? '');

  const selectedTagIds = draft.draft_data.glimpse_tag_ids ?? [];
  const linkedDistinctionIds = draft.draft_data.glimpse_linked_distinction_ids ?? [];

  const linkableDistinctions = useMemo(
    () =>
      (draftDistinctions ?? []).map((entry) => ({
        id: entry.distinction_id,
        name: entry.distinction_name,
      })),
    [draftDistinctions]
  );

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

  const handleToggleDistinctionLink = (distinctionId: number) => {
    const next = linkedDistinctionIds.includes(distinctionId)
      ? linkedDistinctionIds.filter((id) => id !== distinctionId)
      : [...linkedDistinctionIds, distinctionId];
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          glimpse_linked_distinction_ids: next,
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
      <div className="flex items-center justify-between gap-3 rounded-md border border-dashed p-4">
        <p className="text-sm text-muted-foreground">
          The Glimpse is set aside for now — your tag picks are saved.
        </p>
        <Button type="button" variant="outline" size="sm" onClick={() => setIsCollapsed(false)}>
          Resume
        </Button>
      </div>
    );
  }

  // GlimpseFlow renders its own top-of-flow heading (defaults to 'The
  // Glimpse' when `heading` is omitted) — no extra wrapping heading here.
  return (
    <GlimpseFlow
      heading={heading}
      tags={tags ?? []}
      selectedTagIds={selectedTagIds}
      prose={prose}
      linkedDistinctionIds={linkedDistinctionIds}
      onChangeAxis={handleChangeAxis}
      onChangeProse={handleChangeProse}
      onToggleDistinctionLink={handleToggleDistinctionLink}
      onSkip={() => setIsCollapsed(true)}
      showDeferralControls
      linkableDistinctions={linkableDistinctions}
    />
  );
}
