/**
 * GlimpseAxes: the CG mount's own axis-by-axis layout for "The Glimpse"
 * (#3675 fix round 1; cards and headings #5191), replacing the shared
 * `GlimpseFlow`'s shadcn accordion for this one mount. Every axis renders
 * as its own `.field` at once (no single-open accordion hiding two axes at
 * a time, the demo-fidelity defect Task 13 shipped).
 *
 * An axis is headed by its name ("Trigger"), with a lead-in line under it
 * ("The Circumstances Around Your Glimpse:") in muted italic: 14px against
 * the heading's 13px capitals, so its capitals are no taller than the
 * heading's and the rest of it is lowercase. Its tags are the
 * life page's cards in look (`ul.stances.grid.pair` of `button.stance`): one width,
 * two across because a description can run to several sentences, the name
 * over its description, a round mark on an axis that takes one answer and
 * a square mark on one that takes several. Owner ruling
 * 2026-11-18 (#5191): the pill buttons this replaced were each as wide as
 * their own text and read as a run of uneven boxes; the question was a bad
 * title; "choose one" is not printed. An axis that takes several answers
 * keeps "choose any", because that is the exception.
 *
 * A chosen tag opens its own `ChapterOffers` sub-block directly under the
 * cards, one sub-block PER TAG (not one per axis, Task 13's shape); two
 * tags chosen on the same axis (e.g. Consequence: Mark + Loss) each get
 * their own heading, matching the demo's "What the mark is" / "What the
 * loss was" side by side under one axis. Each sub-block's heading carries
 * an "optional" `.tag.soft` chip (`headingTag`, #3675 fix round 2). A
 * distinction the route closes is absent from the tag's offers and named
 * nowhere (#4979).
 *
 * The sheet's live editor (`magic/components/glimpse/GlimpseEditorDialog.tsx`)
 * still mounts the shared `GlimpseFlow` unchanged; this component is
 * CG-only. `GlimpseSection` stays the thin state binder around this: draft
 * reads, `updateDraft` writes, and the copy query.
 */

import type { ChangeEvent } from 'react';
import { cn } from '@/lib/utils';
import { nextAxisSelection } from '@/magic/components/glimpse/axisSelection';
import { AXIS_STEPS } from '@/magic/components/glimpse/GlimpseFlow';
import type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';
import { Field } from '../../folio';
import type { CGExplanations, CharacterDraft } from '../../types';
import { ChapterOffers } from '../offers/ChapterOffers';

// `AXIS_STEPS` never carries a SENSORY entry (GlimpseAxes never renders a
// field for it, same as GlimpseFlow), but `GlimpseTagOption['axis']` is the
// full 7-member union; both maps carry an unreachable SENSORY entry purely
// to satisfy `Record<GlimpseTagOption['axis'], string>`. The axis name is
// the fallback behind a `glimpse_axis_<axis>_chip` copy key (mirrors
// `GlimpseTagAxis`'s own choice labels in `world.magic.constants`, the
// authoritative source this literal must not drift from). The key keeps the
// name it had when the axis name was a chip beside the question, so a row
// staff already edited still applies now that the name is the heading.
const AXIS_DISPLAY_NAME: Record<GlimpseTagOption['axis'], string> = {
  TRIGGER: 'Trigger',
  CHOOSING: 'The Choosing',
  REFLECTION: 'The Reflection',
  TONE: 'Tone',
  CONSEQUENCE: 'Consequence',
  WITNESS: 'Witness & Secrecy',
  SENSORY: '',
};

// The lead-in line under each axis name, read via
// `glimpse_axis_<axis>_lead_in` (#5191). The keys are new on purpose: copy
// rows already authored under the retired `glimpse_axis_<axis>_prompt` keys
// hold the old headings, and a row beats this fallback.
const AXIS_LEAD_IN_FALLBACK: Record<GlimpseTagOption['axis'], string> = {
  TRIGGER: 'The Circumstances Around Your Glimpse:',
  CHOOSING: 'How It Claimed You:',
  REFLECTION: 'What You Saw in Yourself:',
  TONE: 'How It Felt:',
  CONSEQUENCE: 'What It Left Behind:',
  WITNESS: 'Who Saw:',
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
    onChangeAxis(axis, nextAxisSelection(tagsByAxis.get(axis) ?? [], selectedTagIds, tagId, multi));
  };

  return (
    <>
      {visibleSteps.map((step) => {
        const axisTags = tagsByAxis.get(step.axis) ?? [];
        const axisKey = step.axis.toLowerCase();
        const headingId = `glimpse-axis-${axisKey}`;
        return (
          <fieldset className="field" aria-labelledby={headingId} key={step.axis}>
            <h3 className="label" id={headingId}>
              {copy?.[`glimpse_axis_${axisKey}_chip`] ?? AXIS_DISPLAY_NAME[step.axis]}
              {step.multi && (
                <span className="tags">
                  <span className="tag soft">{copy?.glimpse_choose_any ?? 'choose any'}</span>
                </span>
              )}
            </h3>
            <p className="lead-in">
              {copy?.[`glimpse_axis_${axisKey}_lead_in`] ?? AXIS_LEAD_IN_FALLBACK[step.axis]}
            </p>
            <ul className={cn('stances', 'grid', 'pair', !step.multi && 'oneof')}>
              {axisTags.map((tag) => (
                <li key={tag.id}>
                  <button
                    type="button"
                    className="stance"
                    aria-pressed={selectedTagIdSet.has(tag.id)}
                    onClick={() => handleTagClick(step.axis, step.multi, tag.id)}
                  >
                    <span className={step.multi ? 'dot sq' : 'dot'} />
                    <span>
                      <b>{tag.name}</b>
                      {tag.description && <span className="g">{tag.description}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
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
          </fieldset>
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
