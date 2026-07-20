/**
 * GlimpseFlow — the guided flow for authoring "The Glimpse" (#2427).
 *
 * Presentational only: props in, callbacks out — no queries or mutations.
 * Two mount points share this component: the CG GiftStage
 * (`character-creation/components/gift/GlimpseSection.tsx`) and the
 * character sheet (Task 6).
 *
 * Structure: a staff-authorable `heading` (defaults to `'The Glimpse'`,
 * mirrors `magic_motif_heading`'s CGExplanation pattern on the sibling Motif
 * field — review fix, previously hardcoded) rendered at the top, then a Radix
 * `Accordion type="single" collapsible` with one item per axis, then an
 * always-visible story step. TONE is single-select; CONSEQUENCE and WITNESS
 * are multi-select. SENSORY doesn't get an accordion item — its tags render
 * as optional toggle chips inside the story step (`GLIMPSE_AXIS_CONFIG`'s
 * `prose_prompt` rendering), alongside the sensory prompts themselves.
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';
import { useMemo } from 'react';
import type { KeyboardEvent } from 'react';
import type {
  GlimpseFlowProps,
  GlimpseSuggestedDistinction,
  GlimpseTagOption,
} from './glimpseTypes';

const AXIS_STEPS: { axis: GlimpseTagOption['axis']; label: string; multi: boolean }[] = [
  { axis: 'TRIGGER', label: 'Trigger', multi: false },
  { axis: 'TONE', label: 'Tone', multi: false },
  { axis: 'CONSEQUENCE', label: 'Consequence', multi: true },
  { axis: 'WITNESS', label: 'Witness & Secrecy', multi: true },
];

function DistinctionLinkChips({
  distinctions,
  linkedIds,
  onToggle,
}: {
  distinctions: GlimpseSuggestedDistinction[];
  linkedIds: Set<number>;
  onToggle: (distinctionId: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {distinctions.map((distinction) => {
        const isLinked = linkedIds.has(distinction.id);
        return (
          <Badge
            key={distinction.id}
            variant={isLinked ? 'default' : 'outline'}
            className="cursor-pointer select-none"
            onClick={() => onToggle(distinction.id)}
          >
            {isLinked && <Check className="mr-1 h-3 w-3" />}
            {distinction.name}
          </Badge>
        );
      })}
    </div>
  );
}

export function GlimpseFlow({
  heading = 'The Glimpse',
  tags,
  selectedTagIds,
  prose,
  linkedDistinctionIds,
  onChangeAxis,
  onChangeProse,
  onToggleDistinctionLink,
  onSkip,
  showDeferralControls,
  linkableDistinctions,
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
  const linkedIdSet = useMemo(() => new Set(linkedDistinctionIds), [linkedDistinctionIds]);

  // Dedupe suggested_distinctions across every selected tag, keeping first
  // occurrence order (a distinction suggested by two selected tags appears once).
  const suggestedDistinctions = useMemo(() => {
    const seen = new Set<number>();
    const result: GlimpseSuggestedDistinction[] = [];
    for (const tag of tags) {
      if (!selectedTagIdSet.has(tag.id)) continue;
      for (const distinction of tag.suggested_distinctions) {
        if (seen.has(distinction.id)) continue;
        seen.add(distinction.id);
        result.push(distinction);
      }
    }
    return result;
  }, [tags, selectedTagIdSet]);

  // Axes with zero authored tags don't render — an empty catalog collapses
  // the accordion entirely rather than showing empty steps.
  const visibleAxisSteps = AXIS_STEPS.filter(
    (step) => (tagsByAxis.get(step.axis)?.length ?? 0) > 0
  );

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
                    return (
                      <Card
                        key={tag.id}
                        role="button"
                        tabIndex={0}
                        className={cn(
                          'cursor-pointer transition-all',
                          isSelected && 'ring-2 ring-primary',
                          !isSelected && 'hover:ring-1 hover:ring-primary/50'
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
                  onClick={() => handleTagClick('SENSORY', true, tag.id)}
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
      </div>

      {selectedTagIds.length > 0 && suggestedDistinctions.length > 0 && (
        <div className="space-y-2">
          <Label>Suggested Distinctions</Label>
          <DistinctionLinkChips
            distinctions={suggestedDistinctions}
            linkedIds={linkedIdSet}
            onToggle={onToggleDistinctionLink}
          />
        </div>
      )}

      <div className="space-y-2">
        <Label>Link a distinction to your glimpse</Label>
        {linkableDistinctions.length > 0 ? (
          <DistinctionLinkChips
            distinctions={linkableDistinctions}
            linkedIds={linkedIdSet}
            onToggle={onToggleDistinctionLink}
          />
        ) : (
          <p className="text-xs text-muted-foreground">
            No distinctions to link yet — choose distinctions in the Distinctions stage first.
          </p>
        )}
      </div>

      {showDeferralControls && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={onSkip}>
            Skip for now
          </Button>
          <Button type="button" variant="ghost" onClick={onSkip}>
            Save tags — write the story later
          </Button>
        </div>
      )}
    </div>
  );
}
