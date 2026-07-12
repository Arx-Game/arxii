/**
 * CreateItemDialog — modal for minting a new item from a recipe (#2211 core, #2240 web).
 *
 * The player picks a recipe (an item template they can craft), optionally names
 * and describes it, sees a cost/quality quote, and crafts. Quality is decided
 * server-side by the crafter's skill + the roll — the player only picks the
 * recipe and the flavor.
 */

import { useEffect, useState } from 'react';
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
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCraftCreateItem,
  useCraftableRecipes,
  useCreateItemQuote,
} from '../hooks/useItemCreation';
import { CraftingQuotePanel } from './CraftingQuotePanel';

interface CreateItemDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateItemDialog({ open, onOpenChange }: CreateItemDialogProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [customName, setCustomName] = useState('');
  const [customDescription, setCustomDescription] = useState('');

  const recipesQuery = useCraftableRecipes();
  const craftMutation = useCraftCreateItem();

  const selectedTemplateIdNum = selectedTemplateId ? Number(selectedTemplateId) : undefined;
  const quoteQuery = useCreateItemQuote(selectedTemplateIdNum);

  // Reset the form when the dialog opens.
  useEffect(() => {
    if (open) {
      setSelectedTemplateId('');
      setCustomName('');
      setCustomDescription('');
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
      },
      {
        onSuccess: (result) => {
          if (result.created) {
            const tier = result.quality_tier ? ` (${result.quality_tier})` : '';
            toast.success(`You crafted a new item${tier}.`);
          } else {
            toast.warning(
              result.consequence_label
                ? `The attempt failed — ${result.consequence_label}.`
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
          <DialogDescription>
            Pick a recipe you know, name your work, and craft it. Quality depends on your skill and
            the roll.
          </DialogDescription>
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
