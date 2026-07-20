/**
 * CG guided origin-story section (#2478).
 *
 * Replaces the free-text Background textarea in IdentityStage. Fetches the
 * active template for the draft's beginning and renders the frame narrative
 * + slot textareas. Slot answers write immediately to draft_data["origin_slots"]
 * via useUpdateDraft (same PATCH-merge contract as GlimpseSection).
 *
 * Graceful fallback: if no active template exists for the beginning, renders
 * the old free-text Background textarea (same graceful-empty-catalog behavior
 * #2427 established).
 */

import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useOriginTemplates, useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';

interface OriginStorySectionProps {
  draft: CharacterDraft;
}

export function OriginStorySection({ draft }: OriginStorySectionProps) {
  const updateDraft = useUpdateDraft();
  const beginningId = draft.selected_beginnings?.id ?? null;
  const { data: templates } = useOriginTemplates(beginningId);
  // Auto-assign the single active template (Decision 1 — player-selection UI deferred)
  const template = templates?.[0];

  const originSlots: Record<string, string> = draft.draft_data.origin_slots ?? {};

  if (!template) {
    // Graceful fallback: no template → old free-text Background textarea
    return (
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Background</h3>
        <div className="space-y-2">
          <Label htmlFor="background">Character History</Label>
          <Textarea
            id="background"
            value={draft.draft_data.background ?? ''}
            onChange={(e) =>
              updateDraft.mutate({
                draftId: draft.id,
                data: {
                  draft_data: { background: e.target.value },
                },
              })
            }
            placeholder="Tell us about your character's past..."
            rows={6}
            className="resize-y"
          />
          <p className="text-xs text-muted-foreground">
            Your character&apos;s history, motivations, and what brought them here.
          </p>
        </div>
      </section>
    );
  }

  const updateSlot = (slotId: number, value: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          origin_slots: { ...originSlots, [slotId]: value },
        },
      },
    });
  };

  return (
    <section className="space-y-4">
      <h3 className="theme-heading text-lg font-semibold">Origin Story</h3>
      <div className="rounded-md border border-border bg-muted/30 p-4">
        <p className="whitespace-pre-wrap text-sm italic text-muted-foreground">
          {template.frame_narrative}
        </p>
      </div>
      {template.slots.map((slot) => (
        <div key={slot.id} className="space-y-2">
          <Label htmlFor={`origin-slot-${slot.id}`}>{slot.prompt}</Label>
          <Textarea
            id={`origin-slot-${slot.id}`}
            value={originSlots[String(slot.id)] ?? ''}
            onChange={(e) => updateSlot(slot.id, e.target.value)}
            placeholder={slot.example || '...'}
            rows={3}
            className="resize-y"
          />
          {slot.example && <p className="text-xs text-muted-foreground">Example: {slot.example}</p>}
        </div>
      ))}
    </section>
  );
}
