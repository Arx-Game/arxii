/**
 * ItemCard — compact horizontal row representing one ItemInstance.
 *
 * - Quality tier color appears as a 2px left-border accent.
 * - Optional facet "chip" indicators (max 3 visible, then "+N").
 * - Click delegates to a parent `onClick(itemId)` to open the detail panel.
 */

import { Shirt } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ItemInstance } from '../types';

interface ItemCardProps {
  item: ItemInstance;
  /** Optional facet chip labels (caller provides resolved names). */
  facetLabels?: string[];
  onClick?: (itemId: number) => void;
  className?: string;
}

const MAX_FACET_CHIPS = 3;

export function ItemCard({ item, facetLabels = [], onClick, className }: ItemCardProps) {
  const tier = item.quality_tier;
  const tierColor = tier?.color_hex || '';
  const tintedBackground = tierColor ? `${tierColor}20` : undefined;

  const visibleFacets = facetLabels.slice(0, MAX_FACET_CHIPS);
  const overflow = Math.max(0, facetLabels.length - MAX_FACET_CHIPS);

  return (
    <button
      type="button"
      onClick={() => onClick?.(item.id)}
      style={tierColor ? { borderLeftColor: tierColor } : undefined}
      className={cn(
        'group flex w-full items-start gap-3 rounded-md border border-l-2 border-border bg-card p-3 text-left text-card-foreground transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      <Thumbnail item={item} tierColor={tierColor} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-sm font-bold">{item.display_name}</span>
          {tier?.name && (
            <Badge
              variant="outline"
              style={tintedBackground ? { backgroundColor: tintedBackground } : undefined}
              className="shrink-0 border-transparent text-[10px]"
            >
              {tier.name}
            </Badge>
          )}
        </div>
        {visibleFacets.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {visibleFacets.map((label) => (
              <span
                key={label}
                className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {label}
              </span>
            ))}
            {overflow > 0 && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                +{overflow}
              </span>
            )}
          </div>
        )}
      </div>
    </button>
  );
}

interface ThumbnailProps {
  item: ItemInstance;
  tierColor: string;
}

function Thumbnail({ item, tierColor }: ThumbnailProps) {
  const initial = item.display_name.trim().charAt(0).toUpperCase() || '?';
  const tierStyle = tierColor ? { borderColor: tierColor } : undefined;

  if (item.display_image_url) {
    return (
      <img
        src={item.display_image_url}
        alt={item.display_name}
        style={tierStyle}
        className="h-12 w-12 shrink-0 rounded-md border-2 object-cover"
      />
    );
  }

  return (
    <div
      style={tierStyle}
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border-2 bg-muted text-muted-foreground"
      aria-hidden="true"
    >
      {item.template?.image_url ? (
        <Shirt className="h-5 w-5" />
      ) : (
        <span className="text-base font-bold">{initial}</span>
      )}
    </div>
  );
}
