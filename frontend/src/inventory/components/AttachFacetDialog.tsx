/**
 * AttachFacetDialog — modal for attaching a facet to an item instance.
 *
 * The quality of the attached facet is determined server-side by the
 * crafter's Enchanting skill — the player selects only which facet to attach.
 *
 * Current facets on the item are displayed as removable chips so the player
 * can see (and remove) what is already applied before attaching more.
 */

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
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
import { useFacets } from '@/character-creation/queries';
import { useCraftAttachFacet, useItemFacets, useRemoveItemFacet } from '../hooks/useItemFacets';

interface AttachFacetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  itemInstanceId: number;
}

export function AttachFacetDialog({ open, onOpenChange, itemInstanceId }: AttachFacetDialogProps) {
  const [selectedFacetId, setSelectedFacetId] = useState('');

  const facetsQuery = useFacets();
  const itemFacetsQuery = useItemFacets(itemInstanceId);
  const craftMutation = useCraftAttachFacet(itemInstanceId);
  const removeMutation = useRemoveItemFacet(itemInstanceId);

  // Reset selection when the dialog opens.
  useEffect(() => {
    if (open) {
      setSelectedFacetId('');
    }
  }, [open]);

  const comboboxItems = (facetsQuery.data ?? []).map((f) => ({
    value: String(f.id),
    label: f.full_path,
  }));

  function handleOpenChange(next: boolean) {
    if (craftMutation.isPending) return;
    onOpenChange(next);
  }

  function handleRemoveFacet(facetRowId: number) {
    removeMutation.mutate(facetRowId, {
      onSuccess: () => {
        toast.success('Facet removed.');
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : 'Failed to remove facet.');
      },
    });
  }

  function handleSubmit() {
    if (!selectedFacetId || craftMutation.isPending) return;
    craftMutation.mutate(
      { item_instance: itemInstanceId, facet: Number(selectedFacetId) },
      {
        onSuccess: (result) => {
          if (result.attached) {
            toast.success(
              `${result.outcome_name} → ${result.quality_tier?.name ?? 'unknown'} quality`
            );
            setSelectedFacetId('');
          } else {
            toast.error('Your attempt failed — no facet attached.');
          }
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to attach facet.');
        },
      }
    );
  }

  const currentFacets = itemFacetsQuery.data ?? [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Attach Facet</DialogTitle>
          <DialogDescription>
            Quality is determined by your Enchanting skill — you choose only which facet to attach.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          {currentFacets.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Attached facets</p>
              <ul className="flex flex-wrap gap-2">
                {currentFacets.map((row) => (
                  <li
                    key={row.id}
                    className="flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm"
                  >
                    <span>Facet #{row.facet}</span>
                    <button
                      type="button"
                      aria-label={`Remove facet ${row.facet}`}
                      onClick={() => handleRemoveFacet(row.id)}
                      className="ml-1 opacity-60 hover:opacity-100"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-1.5">
            <p className="text-sm font-medium">Select a facet to attach</p>
            <Combobox
              items={comboboxItems}
              value={selectedFacetId}
              onValueChange={setSelectedFacetId}
              placeholder="Choose a facet…"
              searchPlaceholder="Search facets…"
              emptyMessage="No facets found."
              disabled={facetsQuery.isLoading || craftMutation.isPending}
            />
          </div>
        </div>

        <DialogFooter className="mt-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={craftMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={!selectedFacetId || craftMutation.isPending}
          >
            {craftMutation.isPending
              ? 'Attaching…'
              : 'Attach (quality set by your Enchanting skill)'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
