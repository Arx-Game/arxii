/**
 * Drawing pieces of the battle map (#4670): palette, label chips, cover badges,
 * mark glyphs and portrait tokens. Pure SVG renderers; BattleMap owns the clicks.
 */

import type { MouseEvent, ReactNode } from 'react';
import { EyeOff, House, Shield, ShieldCheck, ShieldPlus, Swords } from 'lucide-react';

import type { PositionEdgeLike, PositionNodeLike } from '@/areas/components/TacticalMap';
import type { OccupantMarkKind, OccupantSummary } from '@/areas/components/PositionMapNode';
import { CELL } from '../battleMapLayout';
import type { MapArea, Square } from '../battleMapLayout';

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
const SIDE_RING: Record<CombatSide, string> = {
  ally: '#d6a650',
  enemy: '#d64a5c',
  bystander: '#9a9a9a',
};
const DISPLAY_FONT = 'Cinzel, Georgia, serif';
const TAG_FONT = '"IBM Plex Mono", ui-monospace, monospace';

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

const MARK_STYLE: Record<OccupantMarkKind, { icon: typeof Swords; fill: string }> = {
  locked: { icon: Swords, fill: '#e11d48' },
  covering: { icon: ShieldPlus, fill: '#0284c7' },
  covered: { icon: ShieldCheck, fill: '#0284c7' },
};

function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = Math.trunc(hash * 31 + name.charCodeAt(i));
  return `hsl(${Math.abs(hash) % 360}, 55%, 35%)`;
}

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

const chipWidth = (text: string) => text.length * 6.6 + 8;

/** A dark chip with the place's name, at a point in viewBox units. */
export function LabelChip({
  x,
  y,
  text,
  color,
  badges,
  anchor = 'start',
}: {
  x: number;
  y: number;
  text: string;
  color: string;
  badges?: ReactNode;
  anchor?: 'start' | 'end';
}) {
  const width = chipWidth(text);
  const left = anchor === 'end' ? x - width : x;
  return (
    <g pointerEvents="none">
      <rect
        x={left - 3}
        y={y - 11}
        width={width}
        height={15}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.75}
      />
      <text x={left} y={y} fontFamily={DISPLAY_FONT} fontSize={11} letterSpacing={0.5} fill={color}>
        {text}
      </text>
      {badges && (
        <g transform={`translate(${left + width - 1}, ${y - 11})`} pointerEvents="auto">
          {badges}
        </g>
      )}
    </g>
  );
}

/** A route's gate or wall text, centred on the route's midpoint. */
export function RouteLabel({
  x,
  y,
  text,
  color,
  testId,
}: {
  x: number;
  y: number;
  text: string;
  color: string;
  testId: string;
}) {
  const width = text.length * 5.6 + 10;
  return (
    <g data-testid={testId} pointerEvents="none">
      <rect
        x={x - width / 2}
        y={y - 8}
        width={width}
        height={14}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.85}
      />
      <text x={x} y={y + 3} textAnchor="middle" fontFamily={TAG_FONT} fontSize={9} fill={color}>
        {text}
      </text>
    </g>
  );
}

export function CoverBadges({ node }: { node: PositionNodeLike }) {
  if (!node.is_roofed && !node.screens_ranged) return null;
  return (
    <>
      {node.is_roofed && (
        <g data-testid="position-roof-badge" aria-label="Roofed">
          <title>Roofed</title>
          <rect width={15} height={15} rx={3} fill={LABEL_BG} fillOpacity={0.75} />
          <House x={2} y={2} width={11} height={11} color="#fcd34d" aria-hidden="true" />
        </g>
      )}
      {node.screens_ranged && (
        <g
          data-testid="position-screen-badge"
          aria-label="Screened"
          transform={`translate(${node.is_roofed ? 17 : 0}, 0)`}
        >
          <title>Screened</title>
          <rect width={15} height={15} rx={3} fill={LABEL_BG} fillOpacity={0.75} />
          <EyeOff x={2} y={2} width={11} height={11} color="#7dd3fc" aria-hidden="true" />
        </g>
      )}
    </>
  );
}

export function MarkGlyph({
  kind,
  title,
  cx,
  cy,
  icon: Icon,
  fill,
  testId,
}: {
  kind: string;
  title: string;
  cx: number;
  cy: number;
  icon: typeof Swords;
  fill: string;
  testId: string;
}) {
  return (
    <g data-testid={testId} data-mark={kind} aria-label={title} role="img" pointerEvents="auto">
      <title>{title}</title>
      <circle cx={cx} cy={cy} r={6} fill={fill} stroke={LABEL_BG} strokeWidth={1} />
      <Icon x={cx - 4} y={cy - 4} width={8} height={8} color="#fff" aria-hidden="true" />
    </g>
  );
}

export function Token({
  occupant,
  cx,
  cy,
  clipId,
  aerial,
  rampartElement,
  onClick,
}: {
  occupant: BattleOccupant;
  cx: number;
  cy: number;
  clipId: string;
  aerial: boolean;
  rampartElement: string | null;
  /** The same as a click on the square (or the air) the token stands on. */
  onClick: () => void;
}) {
  const url = occupant.thumbnailMediaUrl ?? occupant.thumbnailUrl ?? null;
  const ring = aerial ? AIR : SIDE_RING[occupant.side];
  const bystander = occupant.side === 'bystander';
  const tagWidth = occupant.name.length * 5.4 + 8;
  const title = bystander ? `${occupant.name} (bystander)` : occupant.name;
  const handleClick = (event: MouseEvent) => {
    event.stopPropagation();
    onClick();
  };
  return (
    <g
      data-testid="occupant-token"
      data-side={occupant.side}
      data-bystander={bystander ? 'true' : undefined}
      data-viewer={occupant.isViewer ? 'true' : undefined}
      data-aerial={aerial ? 'true' : undefined}
      opacity={bystander ? 0.45 : 1}
      pointerEvents="auto"
      onClick={handleClick}
    >
      <title>{title}</title>
      <defs>
        <clipPath id={clipId}>
          <circle cx={cx} cy={cy} r={TOKEN_R} />
        </clipPath>
      </defs>
      {occupant.isViewer && (
        <circle
          data-testid="viewer-halo"
          cx={cx}
          cy={cy}
          r={TOKEN_R + 6}
          fill="none"
          stroke={GOLD}
          strokeWidth={2}
          strokeDasharray="3 3"
        />
      )}
      <circle
        cx={cx}
        cy={cy + (aerial ? AIR_LIFT + 4 : 2)}
        r={TOKEN_R + 1}
        fill="#000"
        opacity={aerial ? 0.3 : 0.5}
      />
      <circle cx={cx} cy={cy} r={TOKEN_R} fill={colorForName(occupant.name)} />
      {url ? (
        <image
          href={url}
          x={cx - TOKEN_R}
          y={cy - TOKEN_R}
          width={TOKEN_R * 2}
          height={TOKEN_R * 2}
          preserveAspectRatio="xMidYMid slice"
          clipPath={`url(#${clipId})`}
          role="img"
          aria-label={occupant.name}
        />
      ) : (
        <text
          x={cx}
          y={cy + 5}
          textAnchor="middle"
          fontSize={14}
          fontWeight={600}
          fill="#fff"
          aria-hidden="true"
        >
          {(occupant.name.trim()[0] ?? '?').toUpperCase()}
        </text>
      )}
      <circle cx={cx} cy={cy} r={TOKEN_R} fill="none" stroke={ring} strokeWidth={2.5} />
      {rampartElement != null && (
        <MarkGlyph
          kind="cover"
          testId="occupant-mark-cover"
          title={`${occupant.name}: behind ${rampartElement} rampart`}
          cx={cx - TOKEN_R + 2}
          cy={cy + TOKEN_R - 2}
          icon={Shield}
          fill="#047857"
        />
      )}
      {(occupant.marks ?? []).map((mark) => (
        <MarkGlyph
          key={mark.kind}
          kind={mark.kind}
          testId={`occupant-mark-${mark.kind}`}
          title={mark.title}
          cx={cx + TOKEN_R - 2}
          cy={mark.kind === 'locked' ? cy - TOKEN_R + 2 : cy + TOKEN_R - 2}
          icon={MARK_STYLE[mark.kind].icon}
          fill={MARK_STYLE[mark.kind].fill}
        />
      ))}
      <rect
        x={cx - tagWidth / 2}
        y={cy + TOKEN_R + 1}
        width={tagWidth}
        height={11}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.8}
      />
      <text
        x={cx}
        y={cy + TOKEN_R + 9.5}
        textAnchor="middle"
        fontFamily={TAG_FONT}
        fontSize={8.5}
        fill={LABEL_TEXT}
      >
        {occupant.name}
      </text>
    </g>
  );
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

export { chipWidth };
