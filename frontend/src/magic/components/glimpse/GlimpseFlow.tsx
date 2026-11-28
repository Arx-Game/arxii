/**
 * GlimpseFlow — the guided flow for authoring "The Glimpse" (#2427).
 *
 * Presentational only: props in, callbacks out — no queries or mutations.
 * Mounted by the character sheet's Glimpse editor (`GlimpseEditorDialog`).
 * Character creation draws its own layout (`GlimpseAxes`) and shares this
 * file's `AXIS_STEPS`.
 *
 * Structure: a staff-authorable `heading` (defaults to `'The Glimpse'`,
 * mirrors `magic_motif_heading`'s CGExplanation pattern on the sibling Motif
 * field — review fix, previously hardcoded) rendered at the top, then a Radix
 * `Accordion type="single" collapsible` with one item per axis, then an
 * always-visible story step. Every part takes one answer (#5292). SENSORY
 * doesn't get an accordion item — its tags render as optional toggle chips
 * inside the story step (`GLIMPSE_AXIS_CONFIG`'s `prose_prompt` rendering),
 * alongside the sensory prompts themselves.
 *
 * An answer that gives a card shows the card on itself (#5292): its name and
 * its mechanics line. A part in `closedAxes` shows its saved answer and takes
 * no click, and a part in `hiddenAxes` is not drawn.
 *
 * The axis tag Cards are `role="button" tabIndex={0}` (not native buttons),
 * so they carry an explicit `onKeyDown` (Enter/Space) for keyboard
 * activation — review fix; the SENSORY chips are native `<button>`s and get
 * this for free.
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';
import { useMemo } from 'react';
import type { KeyboardEvent } from 'react';
import { nextAxisSelection } from './axisSelection';
import type { GlimpseAxisStep, GlimpseFlowProps, GlimpseTagOption } from './glimpseTypes';

const part = (
  axis: GlimpseTagOption['axis'],
  label: string,
  rule: { givesCard?: boolean; lostInBlackout?: boolean } = {}
): GlimpseAxisStep => ({
  axis,
  label,
  multi: false,
  givesCard: rule.givesCard ?? false,
  lostInBlackout: rule.lostInBlackout ?? false,
});

// The parts in the order they are asked, with each part's rule (#5292): every part
// takes one answer; Trigger, The Reflection, Tone and Consequence give a card; a
// blackout takes The Reflection and Tone. A copy of `GLIMPSE_AXIS_CONFIG` and
// `GLIMPSE_AXIS_ORDER` in `world.magic.constants`.
// CHOOSING tags are all path-scoped to the Path of the Chosen, so the step
// self-hides for other paths (axes with zero catalog tags don't render).
// Exported so GlimpseAxes (the CG mount's own folio-grammar layout, #3675
// fix round 1) can reuse this axis order and rule without redeclaring it;
// only this component's own question-style `label` text is GlimpseFlow-only.
export const AXIS_STEPS: GlimpseAxisStep[] = [
  part('TRIGGER', 'Trigger: what was happening?', { givesCard: true }),
  part('CHOOSING', 'The Choosing: how did it claim you?'),
  part('REFLECTION', 'The Reflection: what did you see in yourself?', {
    givesCard: true,
    lostInBlackout: true,
  }),
  part('TONE', 'Tone: how did it feel?', { givesCard: true, lostInBlackout: true }),
  part('CONSEQUENCE', 'Consequence: what did it leave behind?', { givesCard: true }),
  part('WITNESS', 'Witness & Secrecy: who saw?'),
];

/** The sensory chips beside the story take one answer, like every part (#5292). */
const SENSORY_TAKES_SEVERAL = false;

export function GlimpseFlow({
  heading = 'The Glimpse',
  tags,
  selectedTagIds,
  prose,
  onChangeAxis,
  onChangeProse,
  storyHint,
  closedAxes,
  hiddenAxes,
}: GlimpseFlowProps) {
  const tagsByAxis = useMemo(() => {
    const map = new Map<GlimpseTagOption['axis'], GlimpseTagOption[]>();
    for (const tag of tags) {
      const list = map.get(tag.axis);
      if (list) {
        list.push(tag);
      } else {
        map.set(tag.axis, [tag]);
      }
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.sort_order - b.sort_order);
    }
    return map;
  }, [tags]);

  const sensoryTags = tagsByAxis.get('SENSORY') ?? [];
  const selectedTagIdSet = useMemo(() => new Set(selectedTagIds), [selectedTagIds]);

  // Axes with zero authored tags don't render — an empty catalog collapses
  // the accordion entirely rather than showing empty steps.
  const visibleAxisSteps = AXIS_STEPS.filter(
    (step) => (tagsByAxis.get(step.axis)?.length ?? 0) > 0 && !hiddenAxes?.has(step.axis)
  );

  const handleTagClick = (axis: GlimpseTagOption['axis'], multi: boolean, tagId: number) => {
    if (closedAxes?.has(axis)) return;
    onChangeAxis(axis, nextAxisSelection(tagsByAxis.get(axis) ?? [], selectedTagIds, tagId, multi));
  };

  // Activates a role="button" tag card from the keyboard the same way a click
  // would — native buttons get this for free, but these are Cards.
  const handleTagKeyDown = (
    event: KeyboardEvent<HTMLDivElement>,
    axis: GlimpseTagOption['axis'],
    multi: boolean,
    tagId: number
  ) => {
    if (event.key === 'Enter' || event.key === ' ') {
      // Space also scrolls the page by default — suppress that, Enter has no
      // such side effect.
      if (event.key === ' ') {
        event.preventDefault();
      }
      handleTagClick(axis, multi, tagId);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label>{heading}</Label>
      </div>

      {visibleAxisSteps.length > 0 && (
        <Accordion type="single" collapsible defaultValue={visibleAxisSteps[0].axis}>
          {visibleAxisSteps.map((step) => (
            <AccordionItem key={step.axis} value={step.axis}>
              <AccordionTrigger>{step.label}</AccordionTrigger>
              <AccordionContent>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(tagsByAxis.get(step.axis) ?? []).map((tag) => {
                    const isSelected = selectedTagIdSet.has(tag.id);
                    const isClosed = closedAxes?.has(step.axis) ?? false;
                    const card = tag.offers[0];
                    return (
                      <Card
                        key={tag.id}
                        role="button"
                        tabIndex={isClosed ? -1 : 0}
                        aria-pressed={isSelected}
                        aria-disabled={isClosed || undefined}
                        className={cn(
                          'transition-all',
                          isSelected && 'ring-2 ring-primary',
                          isClosed && !isSelected && 'opacity-50',
                          !isClosed && 'cursor-pointer',
                          !isClosed && !isSelected && 'hover:ring-1 hover:ring-primary/50'
                        )}
                        onClick={() => handleTagClick(step.axis, step.multi, tag.id)}
                        onKeyDown={(event) =>
                          handleTagKeyDown(event, step.axis, step.multi, tag.id)
                        }
                      >
                        <CardHeader className="p-3">
                          <CardTitle className="flex items-center justify-between gap-2 text-sm">
                            <span>{tag.name}</span>
                            {isSelected && <Check className="h-4 w-4 shrink-0 text-primary" />}
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1 px-3 pb-3 pt-0">
                          <CardDescription className="text-xs">{tag.description}</CardDescription>
                          <p className="text-xs italic text-muted-foreground">{tag.example}</p>
                          {card && (
                            <p className="border-l-2 pl-2 text-xs" data-testid="glimpse-card">
                              <span className="block font-semibold">{card.name}</span>
                              {card.effect_line}
                            </p>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}

      <div className="space-y-3">
        <Label htmlFor="glimpse-flow-story">Your Story</Label>
        <p className="text-sm text-muted-foreground">
          What did you see? What did you hear? What did you <em>know</em>, after?
        </p>
        {sensoryTags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {sensoryTags.map((tag) => {
              const isSelected = selectedTagIdSet.has(tag.id);
              return (
                // Native <button> — Enter/Space activation is free, no
                // onKeyDown needed (unlike the role="button" axis Cards above).
                <button
                  key={tag.id}
                  type="button"
                  title={tag.description}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors',
                    isSelected
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-muted-foreground/30 text-muted-foreground hover:border-primary/50'
                  )}
                  disabled={closedAxes?.has('SENSORY')}
                  aria-pressed={isSelected}
                  onClick={() => handleTagClick('SENSORY', SENSORY_TAKES_SEVERAL, tag.id)}
                >
                  {tag.name}
                </button>
              );
            })}
          </div>
        )}
        <Textarea
          id="glimpse-flow-story"
          value={prose}
          onChange={(event) => onChangeProse(event.target.value)}
          placeholder="The first time you glimpsed the magical world..."
          rows={4}
          className="resize-y"
        />
        {storyHint && <p className="text-xs text-muted-foreground">{storyHint}</p>}
      </div>
    </div>
  );
}
