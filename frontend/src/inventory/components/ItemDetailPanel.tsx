/**
 * ItemDetailPanel — slide-in side drawer for reading an item.
 *
 * Layout (top to bottom):
 *   - hero image (or initial fallback) with quality color as the left border
 *   - item name + quality tier badge
 *   - markdown description (react-markdown + remark-gfm) in a manual prose wrapper
 *   - stats grid (weight / size / value)
 *   - facet chips (live data from useItemFacets; facetLabels prop accepted but unused)
 *   - actions row (Wear/Remove, Drop, Give, Put in, Attach Facet)
 *
 * Open/close is parent-controlled via `open` + `onOpenChange` (standard
 * shadcn Sheet pattern). Action callbacks are optional — the parent decides
 * which buttons fire which mutations.
 */

import { useState } from 'react';
import { Hand, Package, Sparkles, Trash2, Users, X, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { useFacets } from '@/character-creation/queries';
import type { ItemInstance, UseItemResult } from '../types';
import { useItemFacets, useQualityTiers, useRemoveItemFacet } from '../hooks/useItemFacets';
import { useUseItem } from '../hooks/useUseItem';
import { AttachFacetDialog } from './AttachFacetDialog';

interface ItemDetailPanelProps {
  /** Item to display. When null the panel renders nothing of substance. */
  item: ItemInstance | null;
  /** Accepted for backward-compat; live facet data is loaded internally. */
  facetLabels?: string[];
  /** True when the parent has determined this item is currently equipped. */
  isEquipped?: boolean;
  /** Character id — required for the Use mutation; optional so existing tests compile. */
  characterId?: number;

  // Sheet state
  open: boolean;
  onOpenChange: (open: boolean) => void;

  // Actions — all optional, parent decides what to wire up.
  onWear?: (itemId: number) => void;
  onRemove?: (itemId: number) => void;
  onDrop?: (itemId: number) => void;
  onGive?: (itemId: number) => void;
  onPutIn?: (itemId: number) => void;
}

export function ItemDetailPanel({
  item,
  // facetLabels accepted for backward-compat; live data replaces it internally.
  facetLabels: _facetLabels = [],
  isEquipped = false,
  characterId,
  open,
  onOpenChange,
  onWear,
  onRemove,
  onDrop,
  onGive,
  onPutIn,
}: ItemDetailPanelProps) {
  // Hooks must be called unconditionally — pass item?.id (undefined when null)
  // which is already enabled-guarded inside useItemFacets.
  const itemFacetsQuery = useItemFacets(item?.id);
  const facetsQuery = useFacets();
  const tiersQuery = useQualityTiers();

  const [attachOpen, setAttachOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-md"
      >
        {item ? (
          <>
            <ItemContent
              key={item.id}
              item={item}
              itemFacetsQuery={itemFacetsQuery}
              facetsQuery={facetsQuery}
              tiersQuery={tiersQuery}
              isEquipped={isEquipped}
              characterId={characterId}
              onWear={onWear}
              onRemove={onRemove}
              onDrop={onDrop}
              onGive={onGive}
              onPutIn={onPutIn}
              onAttachFacet={() => setAttachOpen(true)}
            />
            <AttachFacetDialog
              open={attachOpen}
              onOpenChange={setAttachOpen}
              itemInstanceId={item.id}
            />
          </>
        ) : (
          <SheetHeader className="p-6">
            <SheetTitle>No item selected</SheetTitle>
            <SheetDescription>Choose an item to inspect its details.</SheetDescription>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  );
}

interface ItemFacetRow {
  id: number;
  item_instance: number;
  facet: number;
  attachment_quality_tier: number;
  applied_by_account: number | null;
  applied_at: string;
}

interface FacetRecord {
  id: number;
  name: string;
  full_path: string;
}

interface QualityTierRecord {
  id: number;
  name: string;
  color_hex: string;
}

interface ItemContentProps {
  item: ItemInstance;
  itemFacetsQuery: { data?: ItemFacetRow[] };
  facetsQuery: { data?: FacetRecord[] };
  tiersQuery: { data?: QualityTierRecord[] };
  isEquipped: boolean;
  characterId?: number;
  onWear?: (itemId: number) => void;
  onRemove?: (itemId: number) => void;
  onDrop?: (itemId: number) => void;
  onGive?: (itemId: number) => void;
  onPutIn?: (itemId: number) => void;
  onAttachFacet: () => void;
}

function ItemContent({
  item,
  itemFacetsQuery,
  facetsQuery,
  tiersQuery,
  isEquipped,
  characterId,
  onWear,
  onRemove,
  onDrop,
  onGive,
  onPutIn,
  onAttachFacet,
}: ItemContentProps) {
  const tier = item.quality_tier;
  const tierColor = tier?.color_hex || '';
  const tintedBackground = tierColor ? `${tierColor}20` : undefined;
  const initial = item.display_name.trim().charAt(0).toUpperCase() || '?';

  const removeMutation = useRemoveItemFacet(item.id);

  // characterId is optional on the panel; ?? -1 mirrors useInventory's sentinel.
  // Use is only rendered when item.is_usable, and real renders always supply characterId.
  const useMutation = useUseItem(characterId ?? -1);
  const [useResult, setUseResult] = useState<UseItemResult | null>(null);
  const isConsumable = item.template?.is_consumable ?? false;
  const useDisabled = useMutation.isPending || (isConsumable && item.charges <= 0);

  function handleUse() {
    useMutation.mutate(item.id, {
      onSuccess: (result) => setUseResult(result),
      onError: (err) => {
        setUseResult(null);
        toast.error(err instanceof Error ? err.message : 'Failed to use item.');
      },
    });
  }

  const liveFacets = itemFacetsQuery.data ?? [];
  const facetMap = new Map<number, FacetRecord>((facetsQuery.data ?? []).map((f) => [f.id, f]));
  const tierMap = new Map<number, QualityTierRecord>((tiersQuery.data ?? []).map((t) => [t.id, t]));

  function handleRemoveFacet(rowId: number) {
    removeMutation.mutate(rowId, {
      onSuccess: () => {
        toast.success('Facet removed.');
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : 'Failed to remove facet.');
      },
    });
  }

  return (
    <>
      <div className="flex flex-col gap-4 p-6 pb-4">
        <div
          style={tierColor ? { borderLeftColor: tierColor } : undefined}
          className="mx-auto flex aspect-square w-full max-w-[280px] items-center justify-center overflow-hidden rounded-lg border border-l-[3px] bg-muted"
        >
          {item.display_image_url ? (
            <img
              src={item.display_image_url}
              alt={item.display_name}
              className="h-full w-full object-cover"
            />
          ) : (
            <span data-fallback-initial className="text-6xl font-bold text-muted-foreground">
              {initial}
            </span>
          )}
        </div>

        <SheetHeader className="space-y-2 text-left">
          <SheetTitle className="text-2xl font-bold">{item.display_name}</SheetTitle>
          <div className="flex items-center gap-2">
            {tier?.name && (
              <Badge
                variant="outline"
                style={tintedBackground ? { backgroundColor: tintedBackground } : undefined}
                className="border-transparent"
              >
                {tier.name}
              </Badge>
            )}
            {isEquipped && (
              <Badge variant="secondary" className="text-xs">
                Worn
              </Badge>
            )}
          </div>
          {/* SheetDescription required for Radix a11y; description content lives below */}
          <SheetDescription className="sr-only">
            Detailed view of {item.display_name}
          </SheetDescription>
        </SheetHeader>
      </div>

      <Separator />

      <div className="flex flex-col gap-6 p-6">
        {item.display_description && (
          <div className={cn('max-w-none text-base leading-relaxed', proseClasses)}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.display_description}</ReactMarkdown>
          </div>
        )}

        <StatsGrid item={item} />

        {liveFacets.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Facets
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {liveFacets.map((row) => {
                const facetRecord = facetMap.get(row.facet);
                const facetLabel = facetRecord?.full_path ?? `Facet #${row.facet}`;
                const tierRecord = tierMap.get(row.attachment_quality_tier);
                const dotColor = tierRecord?.color_hex;
                return (
                  <span
                    key={row.id}
                    className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {dotColor && (
                      <span
                        aria-hidden="true"
                        className="inline-block h-2 w-2 flex-shrink-0 rounded-full"
                        style={{ backgroundColor: dotColor }}
                      />
                    )}
                    {facetLabel}
                    <button
                      type="button"
                      aria-label={`Remove facet ${row.facet}`}
                      onClick={() => handleRemoveFacet(row.id)}
                      className="ml-0.5 opacity-60 hover:opacity-100"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {useResult && (
        <div
          data-testid="use-result"
          className="mx-4 mb-2 rounded-md border bg-muted/40 p-3 text-sm text-foreground"
        >
          {isConsumable
            ? useResult.destroyed
              ? 'Consumed — last charge spent.'
              : `Used — ${useResult.charges_remaining} charge(s) remaining.`
            : 'Used.'}
          {useResult.applied_effect_count > 0 && (
            <span className="ml-1 text-muted-foreground">
              {useResult.applied_effect_count} effect(s) applied.
            </span>
          )}
        </div>
      )}

      <div className="mt-auto border-t bg-muted/30 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {item.is_usable && (
            <Button
              size="sm"
              variant="default"
              onClick={handleUse}
              disabled={useDisabled}
              title={isConsumable && item.charges <= 0 ? 'No uses left' : undefined}
            >
              <Zap className="mr-1.5 h-3.5 w-3.5" />
              Use
            </Button>
          )}
          {isEquipped ? (
            <Button size="sm" variant="default" onClick={() => onRemove?.(item.id)}>
              Remove
            </Button>
          ) : (
            <Button size="sm" variant="default" onClick={() => onWear?.(item.id)}>
              Wear
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => onDrop?.(item.id)}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Drop
          </Button>
          <Button size="sm" variant="outline" onClick={() => onGive?.(item.id)}>
            <Users className="mr-1.5 h-3.5 w-3.5" />
            Give
          </Button>
          <Button size="sm" variant="outline" onClick={() => onPutIn?.(item.id)}>
            <Package className="mr-1.5 h-3.5 w-3.5" />
            Put in
          </Button>
          <Button size="sm" variant="outline" onClick={onAttachFacet}>
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Attach Facet
          </Button>
        </div>
      </div>
    </>
  );
}

interface StatsGridProps {
  item: ItemInstance;
}

function StatsGrid({ item }: StatsGridProps) {
  const template = item.template;
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
      <Stat label="Weight" value={template?.weight ?? '—'} />
      <Stat label="Size" value={template ? String(template.size) : '—'} />
      <Stat label="Value" value={template ? String(template.value) : '—'} />
      {item.quantity > 1 && <Stat label="Quantity" value={String(item.quantity)} />}
      {item.charges > 0 && <Stat label="Charges" value={String(item.charges)} />}
    </div>
  );
}

interface StatProps {
  label: string;
  value: string;
}

function Stat({ label, value }: StatProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <Hand className="h-3 w-3 opacity-60" aria-hidden="true" />
        {label}
      </span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

/**
 * Manual editorial typography — `@tailwindcss/typography` is not installed.
 * Mimics a small subset of `prose dark:prose-invert max-w-none`.
 */
const proseClasses = [
  '[&_p]:my-3',
  '[&_p:first-child]:mt-0',
  '[&_p:last-child]:mb-0',
  '[&_strong]:font-semibold',
  '[&_em]:italic',
  '[&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5',
  '[&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5',
  '[&_li]:my-1',
  '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-muted-foreground',
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-sm',
  '[&_a]:text-primary [&_a]:underline-offset-2 hover:[&_a]:underline',
].join(' ');
