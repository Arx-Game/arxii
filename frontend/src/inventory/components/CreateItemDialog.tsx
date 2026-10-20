/**
 * CreateItemDialog — modal for minting a new item from a recipe (#2211 core, #2240 web).
 *
 * The player picks a recipe (an item template they can craft), optionally names
 * and describes it, sees a cost/quality quote, and crafts. Quality is decided
 * server-side by the crafter's skill + the roll — the player only picks the
 * recipe and the flavor. The crafter may also make the piece for one other character
 * (a permanent dedication) and work one held item into it: the item is used up and
 * recorded on the new piece (#4512).
 */

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCraftCreateItem,
  useCraftableRecipes,
  useCreateItemQuote,
  useItemMeaning,
} from '../hooks/useItemCreation';
import type { ItemInstance } from '../types';
import { CraftingQuotePanel } from './CraftingQuotePanel';
import { DedicateToField, type DedicatePersona } from './DedicateToField';

interface CreateItemDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Items the crafter holds, offered as "Worked from". */
  items?: ItemInstance[];
  /** The crafter's persona name, left out of "Made for". */
  myName?: string | null;
}

export function CreateItemDialog({
  open,
  onOpenChange,
  items = [],
  myName = null,
}: CreateItemDialogProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');
  const [madeFor, setMadeFor] = useState<DedicatePersona | null>(null);
  const [workedFromId, setWorkedFromId] = useState('');

  const recipesQuery = useCraftableRecipes();
  const craftMutation = useCraftCreateItem();

  const selectedTemplateIdNum = selectedTemplateId ? Number(selectedTemplateId) : undefined;
  const quoteQuery = useCreateItemQuote(selectedTemplateIdNum);
  const workedFrom = items.find((item) => String(item.id) === workedFromId);
  const meaningQuery = useItemMeaning(workedFrom?.id);

  // Reset the form when the dialog opens.
  useEffect(() => {
    if (open) {
      setSelectedTemplateId('');
      setCustomName('');
      setCustomDescription('');
      setMadeFor(null);
      setWorkedFromId('');
    }
  }, [open]);

  const comboboxItems = (recipesQuery.data ?? []).map((t) => ({
    value: String(t.id),
    label: t.name,
  }));

  function handleOpenChange(next: boolean) {
    if (craftMutation.isPending) return;
    onOpenChange(next);
  }

  function handleCraft() {
    if (selectedTemplateIdNum == null) return;
    craftMutation.mutate(
      {
        template: selectedTemplateIdNum,
        custom_name: customName.trim() || undefined,
        custom_description: customDescription.trim() || undefined,
        made_for: madeFor?.id,
        worked_from: workedFrom?.id,
      },
      {
        onSuccess: (result) => {
          if (result.created) {
            const tier = result.quality_tier ? ` (${result.quality_tier})` : '';
            toast.success(`You crafted a new item${tier}.`);
          } else {
            toast.warning(
              result.consequence_label
                ? `The attempt failed: ${result.consequence_label}.`
                : 'The attempt failed.'
            );
          }
          onOpenChange(false);
        },
        onError: (err: unknown) => {
          toast.error(err instanceof Error ? err.message : 'Failed to craft item.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Craft an item</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="create-item-recipe">Recipe</Label>
            <Combobox
              items={comboboxItems}
              value={selectedTemplateId}
              onValueChange={setSelectedTemplateId}
              placeholder={
                recipesQuery.isLoading ? 'Loading recipes…' : 'Choose something to craft…'
              }
              emptyMessage="You don't know any recipes yet."
            />
          </div>

          {selectedTemplateIdNum != null && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="create-item-name">Name (optional)</Label>
                <Input
                  id="create-item-name"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="A name for your work"
                  maxLength={200}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create-item-description">Description (optional)</Label>
                <Textarea
                  id="create-item-description"
                  value={customDescription}
                  onChange={(e) => setCustomDescription(e.target.value)}
                  placeholder="How it looks"
                  rows={3}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Left blank, whoever holds the piece can write its design later, on a finishing pass
                or on any commission for it, and is then credited as designer.
              </p>
              <DedicateToField
                idPrefix="create-item"
                label="Made for (optional, permanent)"
                value={madeFor}
                onChange={setMadeFor}
                excludeName={myName}
              />
              <div className="space-y-1.5">
                <Label htmlFor="create-item-worked-from">
                  Worked from (optional; the chosen item is used up)
                </Label>
                <Combobox
                  items={items.map((item) => ({
                    value: String(item.id),
                    label: item.display_name,
                  }))}
                  value={workedFromId}
                  onValueChange={setWorkedFromId}
                  placeholder="nothing chosen"
                  emptyMessage="You are not holding anything."
                  allowDeselect
                />
                {workedFrom && (
                  <div
                    className="space-y-1 rounded-md border bg-muted/40 px-3 py-2 text-sm"
                    data-testid="worked-from-meaning"
                  >
                    <p className="font-medium">What it means to you</p>
                    {meaningQuery.isLoading && <p>Reading its record...</p>}
                    {(meaningQuery.data?.lines ?? []).map((line) => (
                      <p key={`${line.label}-${line.detail}`}>
                        {line.label}
                        {line.detail ? `: ${line.detail}` : ''} ({line.points})
                      </p>
                    ))}
                    {meaningQuery.data && (
                      <p>
                        {meaningQuery.data.total} point{meaningQuery.data.total === 1 ? '' : 's'};{' '}
                        {Math.min(meaningQuery.data.total, meaningQuery.data.made_from_cap)}{' '}
                        recorded on the new piece
                        {meaningQuery.data.total > meaningQuery.data.made_from_cap && ' (the cap)'}.
                      </p>
                    )}
                    <p className="text-destructive">
                      {workedFrom.display_name} is used up by the making; its design and record are
                      kept. The piece records that it was made from it.
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Only the item you choose here is recorded. Recipe materials are allocated as
                      today and record nothing.
                    </p>
                  </div>
                )}
              </div>
              <CraftingQuotePanel isLoading={quoteQuery.isLoading} quote={quoteQuery.data} />
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCraft}
            disabled={selectedTemplateIdNum == null || craftMutation.isPending}
          >
            {craftMutation.isPending ? 'Crafting…' : 'Craft'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
