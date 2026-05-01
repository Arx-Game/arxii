/**
 * PaperDoll — minimalist heraldic silhouette with one slot per BodyRegion.
 *
 * Empty slot: dashed muted border, click triggers `onSlotClick(region)` so
 * callers can filter the all-items list by that region.
 *
 * Occupied slot: solid border in the worn item's quality tier color, with
 * either a small thumbnail or the first letter of the item name as fallback.
 * Click triggers `onItemClick(itemId)` so callers can open the detail panel.
 *
 * The figure is intentionally abstract — symmetric standing pose suggested
 * via stroke-only SVG paths in `currentColor` at 30% opacity. No anatomy.
 */

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { BodyRegion } from '../types';

/**
 * Minimal shape needed by PaperDoll for an equipped item.
 *
 * Decoupled from `EquippedItem` (REST schema) so the parent can compose this
 * value from either an `EquippedItemRead` join + an `ItemInstanceRead` lookup,
 * or from an outfit's `OutfitSlotRead.item_instance` directly.
 */
export interface EquippedItemDisplay {
  /** ItemInstance id — what onItemClick returns. */
  id: number;
  body_region: BodyRegion;
  equipment_layer?: string;
  display_name: string;
  display_image_url: string | null;
  /** Quality tier color_hex used for the slot border accent. */
  quality_color_hex: string;
}

interface PaperDollProps {
  equipped: EquippedItemDisplay[];
  onSlotClick?: (region: BodyRegion) => void;
  onItemClick?: (itemId: number) => void;
  className?: string;
}

interface SlotPosition {
  region: BodyRegion;
  /** SVG-space center coordinates (viewBox 0 0 200 320). */
  x: number;
  y: number;
  /** Slot width / height in SVG units. */
  w: number;
  h: number;
}

// Slot grid: positioned approximately on a stylized humanoid outline.
// viewBox is 200x320 — keep slots inside the silhouette stroke.
const SLOT_LAYOUT: SlotPosition[] = [
  { region: 'head', x: 100, y: 28, w: 40, h: 24 },
  { region: 'face', x: 100, y: 50, w: 36, h: 14 },
  { region: 'left_ear', x: 78, y: 36, w: 12, h: 12 },
  { region: 'right_ear', x: 122, y: 36, w: 12, h: 12 },
  { region: 'neck', x: 100, y: 72, w: 30, h: 12 },
  { region: 'shoulders', x: 100, y: 92, w: 80, h: 14 },
  { region: 'torso', x: 100, y: 130, w: 60, h: 36 },
  { region: 'back', x: 100, y: 174, w: 60, h: 14 },
  { region: 'waist', x: 100, y: 198, w: 60, h: 12 },
  { region: 'left_arm', x: 50, y: 130, w: 22, h: 36 },
  { region: 'right_arm', x: 150, y: 130, w: 22, h: 36 },
  { region: 'left_hand', x: 42, y: 178, w: 22, h: 22 },
  { region: 'right_hand', x: 158, y: 178, w: 22, h: 22 },
  { region: 'left_finger', x: 42, y: 204, w: 14, h: 10 },
  { region: 'right_finger', x: 158, y: 204, w: 14, h: 10 },
  { region: 'left_leg', x: 80, y: 250, w: 22, h: 40 },
  { region: 'right_leg', x: 120, y: 250, w: 22, h: 40 },
  { region: 'feet', x: 100, y: 300, w: 60, h: 14 },
];

const MUTED_STROKE = 'currentColor';

export function PaperDoll({ equipped, onSlotClick, onItemClick, className }: PaperDollProps) {
  // Build a lookup keyed by body region. If multiple items share a region
  // (e.g. base + over), pick the outermost layer so the visible accessory wins.
  const byRegion = useMemo(() => {
    const map = new Map<BodyRegion, EquippedItemDisplay>();
    const layerOrder = ['skin', 'under', 'base', 'over', 'outer', 'accessory'];
    for (const item of equipped) {
      const existing = map.get(item.body_region);
      if (!existing) {
        map.set(item.body_region, item);
        continue;
      }
      const newRank = layerOrder.indexOf(item.equipment_layer ?? 'base');
      const oldRank = layerOrder.indexOf(existing.equipment_layer ?? 'base');
      if (newRank > oldRank) {
        map.set(item.body_region, item);
      }
    }
    return map;
  }, [equipped]);

  return (
    <div
      className={cn(
        'mx-auto aspect-[5/8] w-full max-w-xs rounded-xl border bg-card p-4 text-foreground shadow-sm',
        className
      )}
    >
      <svg
        role="img"
        aria-label="Paper doll silhouette"
        viewBox="0 0 200 320"
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <Silhouette />
        {SLOT_LAYOUT.map((slot) => {
          const item = byRegion.get(slot.region);
          if (item) {
            return (
              <OccupiedSlot
                key={slot.region}
                slot={slot}
                item={item}
                onClick={() => onItemClick?.(item.id)}
              />
            );
          }
          return (
            <EmptySlot key={slot.region} slot={slot} onClick={() => onSlotClick?.(slot.region)} />
          );
        })}
      </svg>
    </div>
  );
}

function Silhouette() {
  // Stroke-only abstract figure.
  return (
    <g stroke={MUTED_STROKE} strokeWidth={1.2} fill="none" opacity={0.3}>
      {/* Head */}
      <ellipse cx={100} cy={32} rx={22} ry={26} />
      {/* Neck */}
      <line x1={92} y1={56} x2={92} y2={68} />
      <line x1={108} y1={56} x2={108} y2={68} />
      {/* Shoulders + torso */}
      <path d="M60 90 L140 90 L132 200 L68 200 Z" />
      {/* Arms */}
      <path d="M60 92 L40 170 L46 200" />
      <path d="M140 92 L160 170 L154 200" />
      {/* Legs */}
      <path d="M75 200 L70 296" />
      <path d="M125 200 L130 296" />
      {/* Pedestal */}
      <line x1={50} y1={310} x2={150} y2={310} strokeDasharray="2 4" />
    </g>
  );
}

interface SlotProps {
  slot: SlotPosition;
  onClick: () => void;
}

function EmptySlot({ slot, onClick }: SlotProps) {
  const { region, x, y, w, h } = slot;
  return (
    <rect
      data-slot={region}
      data-occupied="false"
      x={x - w / 2}
      y={y - h / 2}
      width={w}
      height={h}
      rx={4}
      ry={4}
      fill="transparent"
      stroke="currentColor"
      strokeOpacity={0.4}
      strokeWidth={1}
      strokeDasharray="3 3"
      className="cursor-pointer text-muted-foreground transition-opacity hover:opacity-100 focus:outline-none"
      onClick={onClick}
      tabIndex={0}
      role="button"
      aria-label={`Empty ${region.replace(/_/g, ' ')} slot`}
    />
  );
}

interface OccupiedSlotProps extends SlotProps {
  item: EquippedItemDisplay;
}

function OccupiedSlot({ slot, item, onClick }: OccupiedSlotProps) {
  const { region, x, y, w, h } = slot;
  const left = x - w / 2;
  const top = y - h / 2;
  const initial = item.display_name.trim().charAt(0).toUpperCase() || '?';

  return (
    <g className="cursor-pointer" onClick={onClick}>
      {item.display_image_url ? (
        <image
          data-slot={region}
          data-occupied="true"
          href={item.display_image_url}
          x={left}
          y={top}
          width={w}
          height={h}
          preserveAspectRatio="xMidYMid slice"
          stroke={item.quality_color_hex}
        />
      ) : null}
      <rect
        data-slot={region}
        data-occupied="true"
        x={left}
        y={top}
        width={w}
        height={h}
        rx={4}
        ry={4}
        fill={item.display_image_url ? 'transparent' : 'hsl(var(--muted))'}
        stroke={item.quality_color_hex}
        strokeWidth={2}
        role="button"
        aria-label={item.display_name}
        tabIndex={0}
      />
      {!item.display_image_url && (
        <text
          data-fallback-initial
          x={x}
          y={y + 4}
          textAnchor="middle"
          className="fill-foreground text-[10px] font-bold"
        >
          {initial}
        </text>
      )}
    </g>
  );
}
