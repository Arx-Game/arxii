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
import {
  useCraftAttachFacet,
  useCraftingQuote,
  useItemFacets,
  useRemoveItemFacet,
} from '../hooks/useItemFacets';
import type { CraftingQuote } from '../api';

// ---------------------------------------------------------------------------
// Failure-risk consumption labels
// ---------------------------------------------------------------------------

const CONSUMPTION_LABELS: Record<string, string> = {
  none: 'nothing lost',
  partial: 'some materials/effort lost',
  full: 'all materials & effort lost',
};

// ---------------------------------------------------------------------------
// CraftingQuotePanel — cost / cap / risk summary for a facet selection
// ---------------------------------------------------------------------------

interface CraftingQuotePanelProps {
  isLoading: boolean;
  quote: CraftingQuote | undefined;
}

function CraftingQuotePanel({ isLoading, quote }: CraftingQuotePanelProps) {
  if (isLoading) {
    return <p className="text-xs text-muted-foreground">Loading cost estimate…</p>;
  }
  if (!quote) return null;

  const { costs, affordable, max_quality_tier, failure_risk } = quote;

  // Build a cost summary line, omitting zero-cost vectors.
  const costParts: string[] = [];
  if (costs.action_points > 0) {
    costParts.push(`${costs.action_points_have}/${costs.action_points} AP`);
  }
  if (costs.anima > 0) {
    costParts.push(`${costs.anima_have}/${costs.anima} Anima`);
  }
  for (const mat of costs.materials) {
    costParts.push(`${mat.have}/${mat.quantity_required} ${mat.name}`);
  }

  return (
    <div
      className="space-y-1 rounded-md border bg-muted/40 px-3 py-2 text-sm"
      data-testid="crafting-quote-panel"
    >
      {costParts.length > 0 && (
        <p>
          <span className="font-medium">Costs:</span>{' '}
          <span className={affordable ? '' : 'text-destructive'}>{costParts.join(' · ')}</span>
        </p>
      )}

      {max_quality_tier != null ? (
        <p>
          <span className="font-medium">Skill cap:</span> {max_quality_tier.name}
        </p>
      ) : (
        <p className="text-muted-foreground">No skill cap</p>
      )}

      {failure_risk.length > 0 && (
        <p>
          <span className="font-medium">On failure:</span>{' '}
          {failure_risk
            .map((r) => r.label ?? CONSUMPTION_LABELS[r.cost_consumption] ?? r.cost_consumption)
            .join(', ')}
        </p>
      )}
    </div>
  );
}

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

  const selectedFacetIdNum = selectedFacetId ? Number(selectedFacetId) : undefined;
  const quoteQuery = useCraftingQuote(itemInstanceId, selectedFacetIdNum);

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
            const parts = [
              `${result.outcome_name} → ${result.quality_tier?.name ?? 'unknown'} quality`,
            ];
            if (result.consequence_label) parts.push(result.consequence_label);
            toast.success(parts.join(' · '));
            setSelectedFacetId('');
          } else {
            const failParts = ['Your attempt failed — no facet attached.'];
            if (result.consequence_label) failParts.push(result.consequence_label);
            toast.error(failParts.join(' · '));
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

          {selectedFacetId && (
            <CraftingQuotePanel isLoading={quoteQuery.isLoading} quote={quoteQuery.data} />
          )}
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
            disabled={
              !selectedFacetId ||
              craftMutation.isPending ||
              (quoteQuery.data != null && !quoteQuery.data.affordable)
            }
          >
            {craftMutation.isPending
              ? 'Attaching…'
              : quoteQuery.data != null && !quoteQuery.data.affordable
                ? "Can't afford"
                : 'Attach (quality set by your Enchanting skill)'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
