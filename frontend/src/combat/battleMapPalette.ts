/**
 * Palette and pure drawing helpers for the battle map (#4670): demo Screen 1 colours,
 * sizes, route and rampart styles, and the places' screen-reader labels.
 */

import type { PositionEdgeLike, PositionNodeLike } from '@/areas/components/TacticalMap';
import type { OccupantSummary } from '@/areas/components/PositionMapNode';
import { CELL } from './battleMapLayout';
import type { MapArea, Square } from './battleMapLayout';

export type CombatSide = 'ally' | 'enemy' | 'bystander';

export interface BattleOccupant extends OccupantSummary {
  side: CombatSide;
  /** The square the server holds for this occupant; null when it stands on none. */
  square: Square | null;
  /** The viewer's own token: drawn with a dashed gold halo. */
  isViewer?: boolean;
}

// Demo palette (Screen 1).
export const BACKGROUND = '#1d1712';
export const LABEL_BG = '#120d0a';
export const LABEL_TEXT = '#f1e3c8';
export const GOLD = '#f4d27a';
export const AIR = '#9fd3ff';
export const HELD = '#d64a5c';
export const SIDE_RING: Record<CombatSide, string> = {
  ally: '#d6a650',
  enemy: '#d64a5c',
  bystander: '#9a9a9a',
};
export const DISPLAY_FONT = 'Cinzel, Georgia, serif';
export const TAG_FONT = '"IBM Plex Mono", ui-monospace, monospace';

// A place with no terrain art: a muted fill and an outline tint by kind.
const KIND_FILL: Record<string, string> = {
  primary: '#3b2e22',
  feature: '#352b21',
  elevated: '#2c333a',
  chasm: '#1a0c0e',
  barrier_side: '#2f2b26',
};
const KIND_TINT: Record<string, string> = {
  primary: '#e0c48f',
  feature: '#d9b36f',
  elevated: '#a9b7c4',
  chasm: '#d64a5c',
  barrier_side: '#b8b0a2',
};
export const kindFill = (kind: string) => KIND_FILL[kind] ?? '#352b21';
export const kindTint = (kind: string) => KIND_TINT[kind] ?? '#d9b36f';

const RAMPART_COLOR: Record<string, string> = {
  stone: '#94a3b8',
  wind: '#38bdf8',
  fire: '#fb923c',
  thorn: '#4ade80',
};
const RAMPART_FALLBACK = '#a1a1aa';
// Solid when intact, dashed when cracked, sparse when crumbling.
const RAMPART_DASH: Record<string, string> = { cracked: '6 3', crumbling: '2 4' };

// One terrain tile spans this many squares, so the art reads at map scale.
export const TERRAIN_TILE = 3 * CELL;
export const TOKEN_R = 16;
export const AIR_LIFT = 6;
export const AIR_INSET = 0.2;

/** A move target's gold outline: shown on hover/focus, or always while picking. */
export const TARGET_OUTLINE_HOVER =
  'opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100';
export const TARGET_OUTLINE_PICKING = 'opacity-70';

export function center(area: MapArea): { x: number; y: number } {
  return { x: (area.x + area.w / 2) * CELL, y: (area.y + area.h / 2) * CELL };
}

export interface RouteStyle {
  stroke: string;
  dash?: string;
  opacity: number;
  /** The gate's name and a wall's strength, as the old map's edge label read. */
  label?: string;
}

export function routeStyle(edge: PositionEdgeLike): RouteStyle {
  const strength =
    edge.integrity != null && edge.max_integrity != null
      ? `${edge.integrity}/${edge.max_integrity}`
      : null;
  if (edge.gating_challenge_name) {
    return {
      stroke: '#f59e0b',
      dash: '6 5',
      opacity: 0.85,
      label: strength ? `${edge.gating_challenge_name} ${strength}` : edge.gating_challenge_name,
    };
  }
  if (!edge.is_passable) {
    return { stroke: HELD, dash: '2 4', opacity: 0.75, label: strength ?? undefined };
  }
  return { stroke: LABEL_TEXT, opacity: 0.22 };
}

export function rampartRing(
  node: PositionNodeLike
): { stroke: string; dash?: string; title: string } | null {
  if (node.rampart_element == null) return null;
  return {
    stroke: RAMPART_COLOR[node.rampart_element.toLowerCase()] ?? RAMPART_FALLBACK,
    dash: RAMPART_DASH[node.rampart_crack_state ?? ''],
    title: `${node.rampart_element} Rampart ${node.rampart_integrity ?? '?'}/${node.rampart_max_integrity ?? '?'}`,
  };
}

export const chipWidth = (text: string) => text.length * 6.6 + 8;

/** The text cut with an ellipsis so its chip fits `maxWidth`; unchanged when it fits. */
export function fitChipText(text: string, maxWidth: number): string {
  if (chipWidth(text) <= maxWidth) return text;
  const chars = Math.max(1, Math.floor((maxWidth - 8) / 6.6) - 1);
  return `${text.slice(0, chars).trimEnd()}…`;
}

/**
 * A place's screen-reader label: "<place>: <name> (<mark>), <name>". A mark title
 * reads "<name>: locked with X"; the name prefix is dropped inside the brackets.
 */
export function placeAriaLabel(placeName: string, occupants: BattleOccupant[]): string {
  if (occupants.length === 0) return placeName;
  const people = occupants.map((o) => {
    const notes = (o.marks ?? []).map((m) =>
      m.title.startsWith(`${o.name}: `) ? m.title.slice(o.name.length + 2) : m.title
    );
    return notes.length > 0 ? `${o.name} (${notes.join(', ')})` : o.name;
  });
  return `${placeName}: ${people.join(', ')}`;
}
