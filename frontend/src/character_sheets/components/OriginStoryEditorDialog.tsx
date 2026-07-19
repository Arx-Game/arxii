/**
 * OriginStoryEditorDialog — the "finish later" origin-story editor mounted on
 * the own-character sheet (#2478).
 *
 * Mirrors GlimpseEditorDialog's shape (#2427): reads the character's existing
 * origin slots from the sheet payload, renders slot textareas for editing,
 * writes through the sheet API set-origin-slot / clear-origin-slot actions.
 * Slot values are saved immediately on change.
 *
 * Unlike the CG OriginStorySection (which fetches the template to show the
 * frame + all available slots), this editor only shows slots the player has
 * already started filling — the frame narrative is not re-shown (the player
 * saw it at CG). This keeps the dialog self-contained without needing the
 * character's beginning id.
 */

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';
import type { CharacterSheetPayload } from '@/character_sheets/api';

interface OriginStoryEditorDialogProps {
  /** The character sheet pk — backs the character-sheet query invalidated after every write. */
  characterId: number;
  /** The sheet payload — provides existing origin_slots for seeding. */
  sheet: CharacterSheetPayload;
}

async function setOriginSlot(sheetId: number, slotId: number, value: string): Promise<void> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/set-origin-slot/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot_id: slotId, value }),
  });
  if (!res.ok) throw new Error('Failed to set origin slot');
}

async function clearOriginSlot(sheetId: number, slotId: number): Promise<void> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/clear-origin-slot/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot_id: slotId }),
  });
  if (!res.ok) throw new Error('Failed to clear origin slot');
}

export function OriginStoryEditorDialog({ characterId, sheet }: OriginStoryEditorDialogProps) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const existingSlots = sheet.story.origin_slots ?? [];
  const state = sheet.story.origin_story_state ?? 'not_started';

  const handleSlotChange = async (slotId: number, value: string) => {
    await setOriginSlot(characterId, slotId, value);
    void queryClient.invalidateQueries({ queryKey: ['character-sheets', characterId] });
  };

  const handleClearSlot = async (slotId: number) => {
    await clearOriginSlot(characterId, slotId);
    void queryClient.invalidateQueries({ queryKey: ['character-sheets', characterId] });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="finish-origin-story-button">
          Finish Origin Story
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Origin Story</DialogTitle>
        </DialogHeader>
        {existingSlots.length > 0 ? (
          <div className="space-y-4">
            {existingSlots.map((slot) => (
              <div key={slot.slot_id} className="space-y-2">
                <Label htmlFor={`origin-slot-edit-${slot.slot_id}`}>{slot.slot_prompt}</Label>
                <Textarea
                  id={`origin-slot-edit-${slot.slot_id}`}
                  defaultValue={slot.value}
                  rows={3}
                  className="resize-y"
                  onChange={(e) => void handleSlotChange(slot.slot_id, e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleClearSlot(slot.slot_id)}
                >
                  Clear
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {state === 'not_started'
              ? 'No origin story has been started yet.'
              : 'Your origin story is complete.'}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
