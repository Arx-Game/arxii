/**
 * Upbringing prompts (#3617).
 *
 * Slot prompts scoped to the resolved family path (`applies_to`). A write-in
 * prompt PATCHes draft_data.origin_slots; a pick-list prompt PATCHes
 * draft_data.origin_choices and prices each choice off the claimed family's
 * influence.
 */

import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useUpdateDraft } from '../../queries';
import { choiceCost, type CharacterDraft, type FamilyPath, type OriginTemplate } from '../../types';

interface Props {
  draft: CharacterDraft;
  template: OriginTemplate;
  path: FamilyPath | '';
  influence: number;
  /** 'any' renders prompts for every path; 'path' renders only this path's prompts. */
  scope: 'any' | 'path';
}

export function UpbringingPrompts({ draft, template, path, influence, scope }: Props) {
  const updateDraft = useUpdateDraft();
  const texts = draft.draft_data.origin_slots ?? {};
  const picks = draft.draft_data.origin_choices ?? {};
  const visible = template.slots.filter((s) =>
    scope === 'any' ? s.applies_to === 'any' : path !== '' && s.applies_to === path
  );
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

  return (
    <section className="space-y-6">
      {visible.map((slot) => {
        const picked = picks[String(slot.id)] ?? null;
        return (
          <div key={slot.id} className="space-y-2">
            <Label htmlFor={`origin-slot-${slot.id}`}>
              {slot.prompt}
              {slot.is_required && <span className="ml-1 text-destructive">*</span>}
            </Label>
            {slot.choices.length > 0 && (
              <div className="grid gap-2 sm:grid-cols-2">
                {slot.choices.map((choice) => {
                  const cost = choiceCost(choice, influence);
                  return (
                    <button
                      key={choice.id}
                      type="button"
                      aria-pressed={picked === choice.id}
                      onClick={() => setChoice(slot.id, picked === choice.id ? null : choice.id)}
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
                        <span className="block text-xs text-muted-foreground">
                          {choice.description}
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
                value={texts[String(slot.id)] ?? ''}
                onChange={(e) => setText(slot.id, e.target.value)}
                placeholder={
                  slot.example || (slot.choices.length > 0 ? 'Or describe another...' : '...')
                }
                rows={3}
                className="resize-y"
              />
            )}
            {slot.example && (
              <p className="text-xs text-muted-foreground">Example: {slot.example}</p>
            )}
          </div>
        );
      })}
    </section>
  );
}
