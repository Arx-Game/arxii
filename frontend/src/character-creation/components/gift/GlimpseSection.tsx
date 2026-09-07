/**
 * CG mount of the guided Glimpse flow (#2427).
 *
 * Reads the catalog via useGlimpseTags and binds GlimpseFlow to draft_data
 * keys (glimpse_tag_ids / glimpse_story), persisting through useUpdateDraft
 * on change (same PATCH-merge contract as the funnel steps).
 *
 * Distinction offers are surfaced by chapter now, not linked via a
 * draft_data id list (#3675): `renderOffers` mounts `ChapterOffers` inside
 * each axis's own accordion item (`GlimpseFlow` calls it right after that
 * axis's tag grid), scoped to that axis with a `filter` keeping only offers
 * whose `opener_label` names one of the axis's currently selected tags; an
 * axis with nothing selected passes zero ids and `ChapterOffers` renders
 * nothing. `useCGExplanations()` is read directly here (mirrors
 * `AnimaCheckStep`'s own copy read) for the offers heading/hint and the
 * story-box hint, rather than threading `copy` down from GiftStage.
 *
 * Prose stays on the parent GiftStage's shared react-hook-form instance
 * (`register('glimpse_story')`, passed down — `AnimaCheckStep`'s
 * `ritualNameField` prop is the precedent) so it still saves via
 * `saveFormFields` on stage leave; tag picks write immediately via
 * `updateDraft`, like `GiftSelector`'s `selected_gift_id`.
 */

import { GlimpseFlow } from '@/magic/components/glimpse/GlimpseFlow';
import { useState } from 'react';
import type { ChangeEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { ChapterOffers } from '../offers/ChapterOffers';
import { useCGExplanations, useGlimpseTags, useUpdateDraft } from '../../queries';
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
  const { data: copy } = useCGExplanations();

  const [isCollapsed, setIsCollapsed] = useState(false);
  // Prose is uncontrolled from RHF's point of view (no `value` on a register
  // return) — this local copy exists purely to give GlimpseFlow a controlled
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

  // Maps an axis's selected tag ids to their names, the value a Glimpse
  // offer's opener_label carries (the backend's opener_label for a Glimpse
  // offer is the tag's name that opened it).
  const selectedTagNamesForAxis = (ids: number[]): Set<string> => {
    const idSet = new Set(ids);
    return new Set((tags ?? []).filter((tag) => idSet.has(tag.id)).map((tag) => tag.name));
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

  // GlimpseFlow renders its own top-of-flow heading (defaults to 'The
  // Glimpse' when `heading` is omitted) — no extra wrapping heading here.
  return (
    <GlimpseFlow
      heading={heading}
      tags={tags ?? []}
      selectedTagIds={selectedTagIds}
      prose={prose}
      onChangeAxis={handleChangeAxis}
      onChangeProse={handleChangeProse}
      onSkip={() => setIsCollapsed(true)}
      showDeferralControls
      storyHint={
        copy?.glimpse_story_hint ??
        'The detail behind any of the picks above goes here; the picks stay short.'
      }
      renderOffers={(axis, ids) =>
        ids.length ? (
          <ChapterOffers
            draft={draft}
            chapter="glimpse"
            filter={(offer) => selectedTagNamesForAxis(ids).has(offer.opener_label)}
            heading={
              copy?.[`glimpse_offers_heading_${axis.toLowerCase()}`] ??
              copy?.glimpse_offers_heading ??
              'What it left in you'
            }
            hint={copy?.glimpse_offers_hint}
          />
        ) : null
      }
    />
  );
}
