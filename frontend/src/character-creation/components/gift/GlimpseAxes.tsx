/**
 * GlimpseAxes: the CG mount's own part-by-part layout for "The Glimpse"
 * (#3675 fix round 1; cards and headings #5191; one bonus from each of four
 * parts #5292). Every part renders as its own `.field.part` at once.
 *
 * A part is headed by its name ("Trigger") as a ruled heading clearly larger
 * than an answer's name (owner ruling 2026-11-22: "Larger Part titles are
 * good"). Under it reads the part's explanation, body text the owner writes
 * (copy `glimpse_axis_<axis>_explanation`); a part whose explanation is not
 * written yet keeps the muted italic lead-in line of #5191 ("How It Felt:"),
 * so the stage is never bare.
 *
 * Its answers are the life page's cards (`ul.stances.grid.pair` of
 * `button.stance`): one width, two across (one on a phone), the name over its
 * description. Every part takes one answer (owner ruling 2026-11-24), so every
 * mark is round and a second pick replaces the first; the square mark and the
 * "choose any" tag stay for a part set to take several, which none is.
 *
 * An answer that gives a card shows the card on itself, before it is picked:
 * the card's name and its mechanics line in a `.bonus` block. Choosing the
 * answer takes the card, free; there is no second list and nothing else to
 * pick (the per-answer `ChapterOffers` block of #3675 is gone). An answer with
 * no card shows only its own words.
 *
 * Between Trigger and The Reflection sits the blackout: one square toggle with
 * the owner's words. Ticked, the two parts a blackout takes (The Reflection
 * and Tone, `lostInBlackout`) are not drawn; their answers stay in the draft.
 *
 * The sheet's live editor (`magic/components/glimpse/GlimpseEditorDialog.tsx`)
 * mounts the shared `GlimpseFlow`; this component is CG-only. `GlimpseSection`
 * is the state binder around it: draft reads, `updateDraft` writes, the three
 * ways into the Glimpse, and the copy query.
 */

import type { ChangeEvent } from 'react';
import { cn } from '@/lib/utils';
import { nextAxisSelection } from '@/magic/components/glimpse/axisSelection';
import { AXIS_STEPS } from '@/magic/components/glimpse/GlimpseFlow';
import type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';
import { Field } from '../../folio';
import type { CGExplanations } from '../../types';
import { AXIS_DISPLAY_NAME } from './glimpseParts';

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

/** The part the blackout toggle sits above: the first of the two it takes. */
const BLACKOUT_BEFORE: GlimpseTagOption['axis'] = 'REFLECTION';

// The owner's words for the blackout (ruling 2026-11-22), shown on the toggle. A copy
// row under `glimpse_blackout_text` replaces them.
const BLACKOUT_TEXT_FALLBACK =
  'When your Glimpse triggered, you have no memory of it at all. It came to you, and you woke ' +
  'up dealing with the consequences. Your Glimpse is a mystery, and it is more than a little ' +
  'unnerving you cannot remember it, and can be unraveled by GMing. You gain the Glimpse ' +
  'Mystery distinction.';

interface GlimpseAxesProps {
  /** Full active catalog (SENSORY tags are not shown here; parity with GlimpseFlow). */
  tags: GlimpseTagOption[];
  selectedTagIds: number[];
  copy: CGExplanations | undefined;
  /** Replace the selection for one axis (already arity-enforced by the UI). */
  onChangeAxis: (axis: GlimpseTagOption['axis'], tagIds: number[]) => void;
  /** The character blacked out of The Reflection and Tone. */
  blackedOut: boolean;
  onChangeBlackedOut: (blackedOut: boolean) => void;
  prose: string;
  onChangeProse: (text: string) => void;
}

export function GlimpseAxes({
  tags,
  selectedTagIds,
  copy,
  onChangeAxis,
  blackedOut,
  onChangeBlackedOut,
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

  const blackout = (
    <ul className="stances blackout grid" key="blackout">
      <li>
        <button
          type="button"
          className="stance"
          aria-pressed={blackedOut}
          onClick={() => onChangeBlackedOut(!blackedOut)}
        >
          <span className="dot sq" />
          <span>
            <b>{copy?.glimpse_blackout_label ?? 'Blacked out'}</b>
            <span className="g">{copy?.glimpse_blackout_text ?? BLACKOUT_TEXT_FALLBACK}</span>
          </span>
        </button>
      </li>
    </ul>
  );

  return (
    <>
      {visibleSteps.map((step) => {
        const axisTags = tagsByAxis.get(step.axis) ?? [];
        const axisKey = step.axis.toLowerCase();
        const headingId = `glimpse-axis-${axisKey}`;
        const explanation = copy?.[`glimpse_axis_${axisKey}_explanation`];
        const part =
          blackedOut && step.lostInBlackout ? null : (
            <fieldset className="field part" aria-labelledby={headingId} key={step.axis}>
              <h3 className="label" id={headingId}>
                {copy?.[`glimpse_axis_${axisKey}_chip`] ?? AXIS_DISPLAY_NAME[step.axis]}
                {step.multi && (
                  <span className="tags">
                    <span className="tag soft">{copy?.glimpse_choose_any ?? 'choose any'}</span>
                  </span>
                )}
              </h3>
              {explanation ? (
                <p className="explain">{explanation}</p>
              ) : (
                <p className="lead-in">
                  {copy?.[`glimpse_axis_${axisKey}_lead_in`] ?? AXIS_LEAD_IN_FALLBACK[step.axis]}
                </p>
              )}
              <ul className={cn('stances', 'grid', 'pair', !step.multi && 'oneof')}>
                {axisTags.map((tag) => {
                  // An answer gives one card (#5292); the model holds a second line out.
                  const card = tag.offers[0];
                  return (
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
                          {card && (
                            <span className="bonus">
                              <span className="card-name">{card.name}</span>
                              {card.effect_line}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          );
        return step.axis === BLACKOUT_BEFORE ? [blackout, part] : part;
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
