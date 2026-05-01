/**
 * OutfitCard — saved-outfit summary tile.
 *
 * Layout (Phase A):
 *
 *   ┌──────────────────────────────────────┐
 *   │  Name                            ⋯   │   font-bold + kebab DropdownMenu
 *   │  ───────────────────────────────     │   <Separator>
 *   │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐  +N        │   up to 5 thumbs + overflow chip
 *   │  └──┘ └──┘ └──┘ └──┘ └──┘            │
 *   │                                      │
 *   │  (Phase B: fashion style chip)       │
 *   │  (Phase C: legendary / mantle badges)│
 *   │  (Phase D: bonus list)               │
 *   │                                      │
 *   │  [   Wear   ]    [ Edit ]            │
 *   └──────────────────────────────────────┘
 *
 * Hover lifts via framer-motion (1.0 → 1.01 scale + shadow ramp, 200ms).
 */

import { motion } from 'framer-motion';
import { MoreVertical, Pencil, Shirt, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { Outfit, OutfitSlot } from '../types';

interface OutfitCardProps {
  outfit: Outfit;
  onWear?: (outfitId: number) => void;
  onEdit?: (outfitId: number) => void;
  onDelete?: (outfitId: number) => void;
  onItemClick?: (itemId: number) => void;
  className?: string;
}

const MAX_VISIBLE_THUMBS = 5;

export function OutfitCard({
  outfit,
  onWear,
  onEdit,
  onDelete,
  onItemClick,
  className,
}: OutfitCardProps) {
  const visibleSlots = outfit.slots.slice(0, MAX_VISIBLE_THUMBS);
  const overflow = Math.max(0, outfit.slots.length - MAX_VISIBLE_THUMBS);

  return (
    <motion.div
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={cn(
        'group flex flex-col rounded-xl border bg-card text-card-foreground shadow-sm transition-shadow hover:shadow-md',
        className
      )}
    >
      <div className="flex items-start justify-between p-4 pb-2">
        <h3 className="truncate text-base font-bold">{outfit.name}</h3>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="-mr-2 -mt-1 h-7 w-7"
              aria-label="More options"
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => onEdit?.(outfit.id)}>
              <Pencil className="mr-2 h-4 w-4" /> Edit
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => onDelete?.(outfit.id)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Separator />

      <div className="flex-1 px-4 py-3">
        {visibleSlots.length === 0 ? (
          <p className="text-xs italic text-muted-foreground">No items in this outfit.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {visibleSlots.map((slot) => (
              <OutfitThumb
                key={slot.id}
                slot={slot}
                onClick={onItemClick ? () => onItemClick(slot.item_instance.id) : undefined}
              />
            ))}
            {overflow > 0 && (
              <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
                +{overflow}
              </span>
            )}
          </div>
        )}

        {/*
          Phase B–D placeholders. Future tickets render content here:
            <div data-placeholder="fashion-style"> ... </div>
            <div data-placeholder="legendary-badge"> ... </div>
            <div data-placeholder="mantle-badge"> ... </div>
            <div data-placeholder="bonus-list"> ... </div>
          Empty placeholders are intentionally not rendered to keep the DOM clean.
        */}
      </div>

      <div className="flex items-center justify-end gap-2 px-4 pb-4">
        <Button size="sm" variant="outline" onClick={() => onEdit?.(outfit.id)}>
          Edit
        </Button>
        <Button size="sm" onClick={() => onWear?.(outfit.id)}>
          <Shirt className="mr-1.5 h-3.5 w-3.5" />
          Wear
        </Button>
      </div>
    </motion.div>
  );
}

interface OutfitThumbProps {
  slot: OutfitSlot;
  onClick?: () => void;
}

function OutfitThumb({ slot, onClick }: OutfitThumbProps) {
  const item = slot.item_instance;
  const tierColor = item.quality_tier?.color_hex || '';
  const initial = item.display_name.trim().charAt(0).toUpperCase() || '?';
  const Tag: 'button' | 'div' = onClick ? 'button' : 'div';

  return (
    <Tag
      type={onClick ? 'button' : undefined}
      data-outfit-thumb
      onClick={onClick}
      style={tierColor ? { borderColor: tierColor } : undefined}
      title={item.display_name}
      className={cn(
        'flex h-10 w-10 items-center justify-center overflow-hidden rounded-md border-2 bg-muted text-muted-foreground',
        onClick && 'cursor-pointer transition-opacity hover:opacity-90'
      )}
      aria-label={item.display_name}
    >
      {item.display_image_url ? (
        <img
          src={item.display_image_url}
          alt={item.display_name}
          className="h-full w-full object-cover"
        />
      ) : (
        <span className="text-sm font-bold">{initial}</span>
      )}
    </Tag>
  );
}
