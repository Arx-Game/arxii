/**
 * Upbringing prompts (#3617, extended into typed lineage questions #3660).
 *
 * Slot prompts scoped to the resolved family path (`applies_to`) and to the
 * shown/follow-up rules mirrored in `types.ts` (`shownSlotIds`). Each kind
 * PATCHes a different draft_data bucket: 'text' -> origin_slots, 'pick' ->
 * origin_choices, 'group' -> origin_anchors (+ origin_choices when the
 * question also offers a stance), 'person' -> origin_figures. Pick/group
 * choices price off influence (the claimed family's for most questions, the
 * chosen group's own influence for a GROUP question).
 */

import { useEffect, useRef, useState } from 'react';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useUpdateDraft } from '../../queries';
import {
  choiceCost,
  chosenGroupForSlot,
  CONNECTION_KIND_LABELS,
  groupsFor,
  isAnswered,
  LIFE_STAGE_LABELS,
  questionInfluence,
  shownSlotIds,
  type CGExplanations,
  type CharacterDraft,
  type FamilyPath,
  type OriginTemplate,
  type OriginTemplateSlot,
} from '../../types';

interface Props {
  draft: CharacterDraft;
  template: OriginTemplate;
  path: FamilyPath | '';
  influence: number;
  copy: CGExplanations | undefined;
  /** 'any' renders prompts for every path; 'path' renders only this path's prompts. */
  scope: 'any' | 'path';
}

export function UpbringingPrompts({ draft, template, path, influence, copy, scope }: Props) {
  const updateDraft = useUpdateDraft();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const texts = draft.draft_data.origin_slots ?? {};
  const picks = draft.draft_data.origin_choices ?? {};
  const anchors = draft.draft_data.origin_anchors ?? {};
  const figures = draft.draft_data.origin_figures ?? {};

  const shown = shownSlotIds(template, draft, path);
  const visible = template.slots
    .filter((s) => shown.has(s.id))
    .filter((s) =>
      scope === 'any' ? s.applies_to === 'any' : path !== '' && s.applies_to === path
    )
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);

  if (visible.length === 0) return null;

  const setText = (slotId: number, value: string) =>
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { origin_slots: { ...texts, [slotId]: value } } },
    });
  const setChoice = (slotId: number, choiceId: number | null) =>
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { origin_choices: { ...picks, [slotId]: choiceId } } },
    });
  const setAnchor = (slotId: number, orgId: number | null) =>
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { origin_anchors: { ...anchors, [slotId]: orgId } } },
    });
  const setFigure = (slotId: number, value: string) =>
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { origin_figures: { ...figures, [slotId]: value } } },
    });

  const toggleExpanded = (slotId: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(slotId)) {
        next.delete(slotId);
      } else {
        next.add(slotId);
      }
      return next;
    });

  return (
    <section className="space-y-6">
      {visible.map((slot) => {
        const answered = isAnswered(slot, draft);
        // A follow-up's own reveal already gated it behind answering the
        // question it follows; folding it a second time is redundant
        // friction, so only a plain top-level optional question folds.
        const isOpen =
          slot.is_required || answered || slot.follow_up_to != null || expanded.has(slot.id);
        if (!isOpen) {
          return (
            <Button
              key={slot.id}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => toggleExpanded(slot.id)}
            >
              Add: {slot.prompt}
            </Button>
          );
        }
        if (slot.kind === 'group') {
          return (
            <GroupQuestion
              key={slot.id}
              slot={slot}
              template={template}
              draft={draft}
              path={path}
              copy={copy}
              picked={picks[String(slot.id)] ?? null}
              anchorId={anchors[String(slot.id)] ?? null}
              text={texts[String(slot.id)] ?? ''}
              onSetChoice={(choiceId) => setChoice(slot.id, choiceId)}
              onSetAnchor={(orgId) => setAnchor(slot.id, orgId)}
              onSetText={(value) => setText(slot.id, value)}
            />
          );
        }
        if (slot.kind === 'person') {
          return (
            <PersonQuestion
              key={slot.id}
              slot={slot}
              template={template}
              draft={draft}
              copy={copy}
              value={figures[String(slot.id)] ?? ''}
              onSetFigure={(value) => setFigure(slot.id, value)}
            />
          );
        }
        return (
          <TextOrPickQuestion
            key={slot.id}
            slot={slot}
            influence={influence}
            picked={picks[String(slot.id)] ?? null}
            text={texts[String(slot.id)] ?? ''}
            onSetChoice={(choiceId) => setChoice(slot.id, choiceId)}
            onSetText={(value) => setText(slot.id, value)}
          />
        );
      })}
    </section>
  );
}

function QuestionLabel({ slot }: { slot: OriginTemplateSlot }) {
  return (
    <Label htmlFor={`origin-slot-${slot.id}`}>
      {slot.prompt}
      {slot.is_required && <span className="ml-1 text-destructive">*</span>}
    </Label>
  );
}

// =============================================================================
// TextOrPickQuestion — a write-in prompt or a priced pick-list, as before #3660
// =============================================================================

interface TextOrPickProps {
  slot: OriginTemplateSlot;
  influence: number;
  picked: number | null;
  text: string;
  onSetChoice: (choiceId: number | null) => void;
  onSetText: (value: string) => void;
}

function TextOrPickQuestion({
  slot,
  influence,
  picked,
  text,
  onSetChoice,
  onSetText,
}: TextOrPickProps) {
  return (
    <div className="space-y-2">
      <QuestionLabel slot={slot} />
      {slot.choices.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {slot.choices.map((choice) => {
            const cost = choiceCost(choice, influence);
            return (
              <button
                key={choice.id}
                type="button"
                aria-pressed={picked === choice.id}
                onClick={() => onSetChoice(picked === choice.id ? null : choice.id)}
                className={cn(
                  'rounded-md border p-2 text-left text-sm transition-colors',
                  picked === choice.id ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-medium">{choice.name}</span>
                  <Badge variant="outline">{cost === 0 ? 'Free' : `${cost} pts`}</Badge>
                </span>
                {choice.description && (
                  <span className="block text-xs text-muted-foreground">{choice.description}</span>
                )}
                {choice.grants_distinction && (
                  <span className="block text-xs text-muted-foreground">
                    grants {choice.grants_distinction.name}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {slot.allows_text && (
        <Textarea
          id={`origin-slot-${slot.id}`}
          value={text}
          onChange={(e) => onSetText(e.target.value)}
          placeholder={slot.example || (slot.choices.length > 0 ? 'Or describe another...' : '...')}
          rows={3}
          className="resize-y"
        />
      )}
      {slot.example && <p className="text-xs text-muted-foreground">Example: {slot.example}</p>}
    </div>
  );
}

// =============================================================================
// GroupQuestion — anchors the answer to a real Organization (#3660)
// =============================================================================

interface GroupQuestionProps {
  slot: OriginTemplateSlot;
  template: OriginTemplate;
  draft: CharacterDraft;
  path: FamilyPath | '';
  copy: CGExplanations | undefined;
  picked: number | null;
  anchorId: number | null;
  text: string;
  onSetChoice: (choiceId: number | null) => void;
  onSetAnchor: (orgId: number | null) => void;
  onSetText: (value: string) => void;
}

function GroupQuestion({
  slot,
  template,
  draft,
  path,
  copy,
  picked,
  anchorId,
  text,
  onSetChoice,
  onSetAnchor,
  onSetText,
}: GroupQuestionProps) {
  const groups = groupsFor(slot, template, draft);
  const isDerivedAnchor =
    slot.anchor_source === 'own_family' || slot.anchor_source === 'served_house';
  // A ref, not state: the guard must take effect the instant it's set, with
  // no render lag, or a re-render triggered by the PATCH itself (a new
  // onSetAnchor closure, a mutation-pending flip) can slip through before a
  // state update commits and re-fire the auto-PATCH — an infinite loop.
  const patchedRef = useRef(false);

  // A single-group list is shown as a fact; auto-PATCH it once, the first
  // time it's unanswered (own_family/served_house need no origin_anchors
  // entry at all: the server resolves those, #3660).
  useEffect(() => {
    if (patchedRef.current || isDerivedAnchor || anchorId != null) return;
    if (groups.length === 1) {
      patchedRef.current = true;
      onSetAnchor(groups[0].id);
    }
  }, [isDerivedAnchor, anchorId, groups, onSetAnchor]);

  const chosenGroup = chosenGroupForSlot(slot, template, draft);
  const groupInfluence = questionInfluence(slot, chosenGroup, draft, path);
  const hint =
    slot.anchor_source === 'same_as'
      ? (copy?.origin_same_group_hint ?? 'About the group you chose above.')
      : (copy?.origin_group_hint ??
        'The group is real and staff wrote it. What you were to it is yours.');

  return (
    <div className="space-y-2">
      <QuestionLabel slot={slot} />
      <div className="flex flex-wrap gap-1">
        <Badge variant="secondary">
          {CONNECTION_KIND_LABELS[slot.connection_kind] ?? slot.connection_kind}
        </Badge>
        <Badge variant="secondary">{LIFE_STAGE_LABELS[slot.life_stage] ?? slot.life_stage}</Badge>
        {!slot.is_required && <Badge variant="outline">Optional</Badge>}
      </div>
      {groups.length === 1 ? (
        <div className="rounded-md border p-2 text-sm" data-testid={`origin-group-fact-${slot.id}`}>
          <span className="font-medium">{groups[0].name}</span>
          {groups[0].gloss && (
            <span className="block text-xs text-muted-foreground">{groups[0].gloss}</span>
          )}
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {groups.map((group) => (
            <button
              key={group.id}
              type="button"
              aria-pressed={anchorId === group.id}
              onClick={() => onSetAnchor(anchorId === group.id ? null : group.id)}
              className={cn(
                'rounded-md border p-2 text-left text-sm transition-colors',
                anchorId === group.id ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
              )}
            >
              <span className="font-medium">{group.name}</span>
              {group.gloss && (
                <span className="block text-xs text-muted-foreground">{group.gloss}</span>
              )}
            </button>
          ))}
        </div>
      )}
      {slot.choices.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {slot.choices.map((choice) => {
            const cost = choiceCost(choice, groupInfluence);
            return (
              <button
                key={choice.id}
                type="button"
                aria-pressed={picked === choice.id}
                onClick={() => onSetChoice(picked === choice.id ? null : choice.id)}
                className={cn(
                  'rounded-md border p-2 text-left text-sm transition-colors',
                  picked === choice.id ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-medium">{choice.name}</span>
                  <Badge variant="outline">{cost === 0 ? 'Free' : `${cost} pts`}</Badge>
                </span>
                {choice.description && (
                  <span className="block text-xs text-muted-foreground">{choice.description}</span>
                )}
                {choice.grants_distinction && (
                  <span className="block text-xs text-muted-foreground">
                    grants {choice.grants_distinction.name}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {slot.allows_text && (
        <Textarea
          value={text}
          onChange={(e) => onSetText(e.target.value)}
          placeholder={slot.example || 'Or describe another...'}
          rows={3}
          className="resize-y"
        />
      )}
      <p className="text-xs text-muted-foreground">{hint}</p>
      {slot.example && <p className="text-xs text-muted-foreground">Example: {slot.example}</p>}
    </div>
  );
}

// =============================================================================
// PersonQuestion — names someone of the player's own (#3660)
// =============================================================================

interface PersonQuestionProps {
  slot: OriginTemplateSlot;
  template: OriginTemplate;
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
  value: string;
  onSetFigure: (value: string) => void;
}

function PersonQuestion({ slot, template, draft, copy, value, onSetFigure }: PersonQuestionProps) {
  const anchorSlot =
    slot.same_anchor_as != null
      ? template.slots.find((s) => s.id === slot.same_anchor_as)
      : undefined;
  const groupName = anchorSlot ? chosenGroupForSlot(anchorSlot, template, draft)?.name : undefined;

  return (
    <div className="space-y-2">
      <QuestionLabel slot={slot} />
      <div className="flex flex-wrap gap-1">
        <Badge variant="secondary">A person</Badge>
        {groupName && <Badge variant="secondary">In {groupName}</Badge>}
      </div>
      <Input
        id={`origin-slot-${slot.id}`}
        value={value}
        onChange={(e) => onSetFigure(e.target.value)}
        placeholder={slot.example || 'Name...'}
      />
      <p className="text-xs text-muted-foreground">
        {copy?.origin_person_hint ?? "Someone of your own, below the group's leaders."}
      </p>
    </div>
  );
}
