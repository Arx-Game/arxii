/**
 * GlimpseAxes: the CG mount's own axis-by-axis layout for "The Glimpse"
 * (#3675 fix round 1), in the folio grammar (`.field`/`.picks`/`.tags`/
 * `.conditional`), replacing the shared `GlimpseFlow`'s shadcn accordion
 * for this one mount. Every axis renders as its own `.field` at once (no
 * single-open accordion hiding two axes at a time, the demo-fidelity
 * defect Task 13 shipped), each with a `.picks` row of pill buttons.
 *
 * A chosen tag opens its own `ChapterOffers` sub-block directly under the
 * pick row, one sub-block PER TAG (not one per axis, Task 13's shape); two
 * tags chosen on the same axis (e.g. Consequence: Mark + Loss) each get
 * their own heading, matching the demo's "What the mark is" / "What the
 * loss was" side by side under one axis. Each sub-block's heading carries
 * an "optional" `.tag.soft` chip (`headingTag`, #3675 fix round 2), and its
 * `closedFilter` scopes the closed-offers hint to `opener_ids` matching the
 * tag's own offer ids (#3675 final fix F4 -- never `opener_labels`/`tag.name`,
 * a display string that can collide or drift, #3676) so a route-closed
 * distinction prints once, under the tag that would have opened it, not under
 * every chosen tag's sub-block.
 *
 * The sheet's live editor (`magic/components/glimpse/GlimpseEditorDialog.tsx`)
 * still mounts the shared `GlimpseFlow` unchanged; this component is
 * CG-only. `GlimpseSection` stays the thin state binder around this: draft
 * reads, `updateDraft` writes, and the copy query.
 */

import type { ChangeEvent } from 'react';
import { AXIS_STEPS } from '@/magic/components/glimpse/GlimpseFlow';
import type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';
import { Field } from '../../folio';
import type { CGExplanations, CharacterDraft } from '../../types';
import { ChapterOffers } from '../offers/ChapterOffers';

// `AXIS_STEPS` never carries a SENSORY entry (GlimpseAxes never renders a
// field for it, same as GlimpseFlow), but `GlimpseTagOption['axis']` is the
// full 7-member union; both maps carry an unreachable SENSORY entry purely
// to satisfy `Record<GlimpseTagOption['axis'], string>`. These are the
// fallback behind a `glimpse_axis_<axis>_chip` copy key (mirrors
// `GlimpseTagAxis`'s own choice labels in `world.magic.constants`, the
// authoritative source this literal must not drift from).
const AXIS_DISPLAY_NAME: Record<GlimpseTagOption['axis'], string> = {
  TRIGGER: 'Trigger',
  CHOOSING: 'The Choosing',
  REFLECTION: 'The Reflection',
  TONE: 'Tone',
  CONSEQUENCE: 'Consequence',
  WITNESS: 'Witness & Secrecy',
  SENSORY: '',
};

// Demo copy (Screen 3); GlimpseFlow's own question-style label
// (`AXIS_STEPS`) is GlimpseFlow-only and not reused for these prompts.
const AXIS_PROMPT_FALLBACK: Record<GlimpseTagOption['axis'], string> = {
  TRIGGER: 'What was happening',
  CHOOSING: 'How it claimed you',
  REFLECTION: 'What you saw in yourself',
  TONE: 'How it felt',
  CONSEQUENCE: 'What it left behind',
  WITNESS: 'Who saw',
  SENSORY: '',
};

interface GlimpseAxesProps {
  draft: CharacterDraft;
  /** Full active catalog (SENSORY tags are not shown here; parity with GlimpseFlow). */
  tags: GlimpseTagOption[];
  selectedTagIds: number[];
  copy: CGExplanations | undefined;
  /** Replace the selection for one axis (already arity-enforced by the UI). */
  onChangeAxis: (axis: GlimpseTagOption['axis'], tagIds: number[]) => void;
  prose: string;
  onChangeProse: (text: string) => void;
}

export function GlimpseAxes({
  draft,
  tags,
  selectedTagIds,
  copy,
  onChangeAxis,
  prose,
  onChangeProse,
}: GlimpseAxesProps) {
  const tagsByAxis = new Map<GlimpseTagOption['axis'], GlimpseTagOption[]>();
  for (const tag of tags) {
    if (tag.axis === 'SENSORY') continue;
    const list = tagsByAxis.get(tag.axis);
    if (list) {
      list.push(tag);
    } else {
      tagsByAxis.set(tag.axis, [tag]);
    }
  }
  for (const list of tagsByAxis.values()) {
    list.sort((a, b) => a.sort_order - b.sort_order);
  }

  const selectedTagIdSet = new Set(selectedTagIds);

  // Axes with zero authored tags don't render, same rule GlimpseFlow uses.
  const visibleSteps = AXIS_STEPS.filter((step) => (tagsByAxis.get(step.axis)?.length ?? 0) > 0);

  const handleTagClick = (axis: GlimpseTagOption['axis'], multi: boolean, tagId: number) => {
    const axisTagIds = new Set((tagsByAxis.get(axis) ?? []).map((tag) => tag.id));
    const currentSelection = selectedTagIds.filter((id) => axisTagIds.has(id));
    if (multi) {
      const next = currentSelection.includes(tagId)
        ? currentSelection.filter((id) => id !== tagId)
        : [...currentSelection, tagId];
      onChangeAxis(axis, next);
    } else {
      onChangeAxis(axis, currentSelection.includes(tagId) ? [] : [tagId]);
    }
  };

  return (
    <>
      {visibleSteps.map((step) => {
        const axisTags = tagsByAxis.get(step.axis) ?? [];
        return (
          <div className="field" key={step.axis}>
            <label>
              {copy?.[`glimpse_axis_${step.axis.toLowerCase()}_prompt`] ??
                AXIS_PROMPT_FALLBACK[step.axis]}
              <span className="tags">
                <span className="tag soft">
                  {copy?.[`glimpse_axis_${step.axis.toLowerCase()}_chip`] ??
                    AXIS_DISPLAY_NAME[step.axis]}
                </span>
                <span className="tag soft">
                  {step.multi
                    ? (copy?.glimpse_choose_any ?? 'choose any')
                    : (copy?.glimpse_choose_one ?? 'choose one')}
                </span>
              </span>
            </label>
            <div className="picks">
              {axisTags.map((tag) => {
                const isSelected = selectedTagIdSet.has(tag.id);
                return (
                  <button
                    key={tag.id}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => handleTagClick(step.axis, step.multi, tag.id)}
                  >
                    {tag.name}
                    <small>{tag.description}</small>
                  </button>
                );
              })}
            </div>
            {axisTags
              .filter((tag) => selectedTagIdSet.has(tag.id) && tag.offers.length > 0)
              .map((tag) => {
                // Match by offer_id, the id the tag's own `offers` already carry -
                // never by opener_label/tag.name, a display string that can collide
                // or drift (#3676: never designate by matching strings in code).
                const tagOfferIds = new Set(tag.offers.map((offer) => offer.offer_id));
                return (
                  <div className="conditional" key={tag.id}>
                    <ChapterOffers
                      draft={draft}
                      chapter="glimpse"
                      filter={(offer) => tagOfferIds.has(offer.offer_id)}
                      heading={
                        copy?.[`glimpse_offers_heading_${tag.slug}`] ??
                        copy?.[`glimpse_offers_heading_${step.axis.toLowerCase()}`] ??
                        copy?.glimpse_offers_heading ??
                        'What it left in you'
                      }
                      headingTag={copy?.offers_optional_chip ?? 'optional'}
                      showOpener={false}
                      closedFilter={(closed) => closed.opener_ids.some((id) => tagOfferIds.has(id))}
                      syncErrorHint={
                        copy?.offers_sync_error ?? 'That pick did not save. Try again.'
                      }
                      wordBundled={copy?.offers_word_bundled}
                      wordPerRank={copy?.offers_word_per_rank}
                      wordSpent={copy?.offers_word_spent}
                      wordAwards={copy?.offers_word_awards}
                    />
                  </div>
                );
              })}
          </div>
        );
      })}

      <Field
        id="glimpse-story"
        label={copy?.glimpse_story_label ?? 'Your story'}
        hint={
          copy?.glimpse_story_hint ??
          'The detail behind any of the picks above goes here; the picks stay short.'
        }
      >
        <textarea
          id="glimpse-story"
          rows={4}
          value={prose}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChangeProse(event.target.value)}
        />
      </Field>
    </>
  );
}
