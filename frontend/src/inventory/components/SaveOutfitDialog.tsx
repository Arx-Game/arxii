/**
 * SaveOutfitDialog — modal opened from a "Save current look" button.
 *
 * Snapshot's the character's currently equipped items into a new outfit
 * via `POST /api/items/outfits/`. The backend's save_outfit service is the
 * one actually creating the slot rows from the present equipment.
 *
 * Edge cases:
 *   - No reachable wardrobe → friendly empty state, no submit button.
 *   - Single wardrobe → auto-selected, the field becomes read-only-ish.
 *   - Multiple wardrobes → first is the default, user can change.
 */

import { useEffect, useState } from 'react';
import { Shirt } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCreateOutfit } from '../hooks/useOutfits';
import type { ItemInstance } from '../types';

const MAX_NAME_LENGTH = 100;

interface SaveOutfitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  characterSheetId: number;
  /** Wardrobes the character can see — usually just one. */
  reachableWardrobes: ItemInstance[];
}

export function SaveOutfitDialog({
  open,
  onOpenChange,
  characterSheetId,
  reachableWardrobes,
}: SaveOutfitDialogProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [wardrobeId, setWardrobeId] = useState<string>(
    reachableWardrobes[0] ? String(reachableWardrobes[0].id) : ''
  );

  const createMutation = useCreateOutfit();
  const hasNoWardrobes = reachableWardrobes.length === 0;
  const trimmedName = name.trim();
  const isValid = trimmedName.length > 0 && wardrobeId !== '' && !hasNoWardrobes;

  // Reset internal state when the dialog opens or the wardrobe list changes.
  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
      setWardrobeId(reachableWardrobes[0] ? String(reachableWardrobes[0].id) : '');
    }
  }, [open, reachableWardrobes]);

  function handleOpenChange(next: boolean) {
    if (createMutation.isPending) return;
    onOpenChange(next);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;
    createMutation.mutate(
      {
        character_sheet: characterSheetId,
        wardrobe: Number(wardrobeId),
        name: trimmedName,
        description: description.trim() || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Outfit saved.');
          onOpenChange(false);
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Couldn't save outfit.";
          toast.error(message);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Save current look</DialogTitle>
          <DialogDescription>
            Snapshot what you&apos;re currently wearing as a saved outfit.
          </DialogDescription>
        </DialogHeader>

        {hasNoWardrobes ? (
          <EmptyWardrobeState />
        ) : (
          <form onSubmit={handleSubmit} className="grid gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="save-outfit-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="save-outfit-name"
                value={name}
                onChange={(e) => setName(e.target.value.slice(0, MAX_NAME_LENGTH))}
                placeholder="Court Attire"
                maxLength={MAX_NAME_LENGTH}
                autoFocus
                required
              />
              {trimmedName.length === 0 && name.length > 0 && (
                <p className="text-xs text-destructive">Name cannot be empty.</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="save-outfit-description">Description</Label>
              <Textarea
                id="save-outfit-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="A few words about the outfit…"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">Supports formatting.</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="save-outfit-wardrobe">Wardrobe</Label>
              {reachableWardrobes.length === 1 ? (
                <Input
                  id="save-outfit-wardrobe"
                  value={reachableWardrobes[0].display_name}
                  readOnly
                  className="bg-muted/40"
                />
              ) : (
                <Select value={wardrobeId} onValueChange={setWardrobeId}>
                  <SelectTrigger id="save-outfit-wardrobe">
                    <SelectValue placeholder="Choose a wardrobe…" />
                  </SelectTrigger>
                  <SelectContent>
                    {reachableWardrobes.map((wardrobe) => (
                      <SelectItem key={wardrobe.id} value={String(wardrobe.id)}>
                        {wardrobe.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <DialogFooter className="mt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={createMutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!isValid || createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save Outfit'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function EmptyWardrobeState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-4 py-8 text-center">
      <div
        aria-hidden="true"
        className="flex h-14 w-14 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <Shirt className="h-6 w-6 opacity-60" />
      </div>
      <p className="text-sm text-muted-foreground">You need a wardrobe to save outfits.</p>
    </div>
  );
}
