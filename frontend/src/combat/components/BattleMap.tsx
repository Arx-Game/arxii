/**
 * BattleMap — the drawn fight map (#4670, slice 1 of #4651): each place is an area of
 * squares filled with its terrain, every combatant a round portrait token on a square.
 *
 * Places stay the rules. A square is only where a token stands inside its place: a
 * click on a square in the viewer's own place steps there (free), a click on a square
 * in a place a move action reaches moves there, and the server refuses anything else.
 * An aerial place has no area of its own; it is drawn as a dashed sky-blue inset over
 * its anchor's area, its tokens lifted and ringed in sky blue.
 *
 * Plain SVG: no canvas library, no pan or zoom. The viewBox is the bounding box of the
 * areas, scaled to the container width.
 */

import { useId, useMemo } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { toast } from 'sonner';
import { EyeOff, House, Shield, ShieldCheck, ShieldPlus, Swords } from 'lucide-react';

import { computeTacticalLayout } from '@/areas/tacticalLayout';
import type {
  OccupantLink,
  PositionEdgeLike,
  PositionNodeLike,
} from '@/areas/components/TacticalMap';
import type { OccupantMarkKind, OccupantSummary } from '@/areas/components/PositionMapNode';
import type { PlayerAction } from '@/scenes/actionTypes';
import { CELL, isAerialOverlay, mapBounds, placeAreas, tokenSquares } from '../battleMapLayout';
import type { MapArea, PlacedToken, Square } from '../battleMapLayout';

export type CombatSide = 'ally' | 'enemy' | 'bystander';

export interface BattleOccupant extends OccupantSummary {
  side: CombatSide;
  /** The square the server holds for this occupant; null when it stands on none. */
  square: Square | null;
  /** The viewer's own token: drawn with a dashed gold halo. */
  isViewer?: boolean;
}

export interface HeldPlace {
  position_id: number;
  holder_names: readonly string[];
}

export interface BattleMapProps {
  nodes: PositionNodeLike[];
  edges: PositionEdgeLike[];
  occupantsByPosition: Map<number, BattleOccupant[]>;
  heldPositions: readonly HeldPlace[];
  moveActions: PlayerAction[];
  /** The place the viewer stands in; a square there is a free step. */
  ownPositionId: number | null;
  /** Move to a place; `square` is null for a place with no authored area. */
  onDispatchMove: (action: PlayerAction, square: Square | null) => void;
  onStepToSquare: (square: Square) => void;
  /** Present only while a position-shaped technique is selected (#2206). */
  onPickPosition?: (positionId: number) => boolean;
  /** Present only while a GM placement target is selected (#3385). */
  onGMPlace?: (positionId: number) => boolean;
  /** Engagement locks drawn between places (#3555). */
  links?: OccupantLink[];
}

// Demo palette (Screen 1).
const BACKGROUND = '#1d1712';
const LABEL_BG = '#120d0a';
const LABEL_TEXT = '#f1e3c8';
const GOLD = '#f4d27a';
const AIR = '#9fd3ff';
const HELD = '#d64a5c';
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
const DEFAULT_FILL = '#352b21';
const DEFAULT_TINT = '#d9b36f';

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
const TERRAIN_TILE = 3 * CELL;
const TOKEN_R = 16;
const AIR_LIFT = 6;
const AIR_INSET = 0.2;

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

function center(area: MapArea): { x: number; y: number } {
  return { x: (area.x + area.w / 2) * CELL, y: (area.y + area.h / 2) * CELL };
}

function edgeStroke(edge: PositionEdgeLike): {
  stroke: string;
  dash?: string;
  opacity: number;
  title?: string;
} {
  const strength =
    edge.integrity != null && edge.max_integrity != null
      ? `${edge.integrity}/${edge.max_integrity}`
      : null;
  if (edge.gating_challenge_name) {
    return {
      stroke: '#f59e0b',
      dash: '6 5',
      opacity: 0.85,
      title: strength ? `${edge.gating_challenge_name} ${strength}` : edge.gating_challenge_name,
    };
  }
  if (!edge.is_passable) {
    return { stroke: HELD, dash: '2 4', opacity: 0.75, title: strength ?? undefined };
  }
  return { stroke: LABEL_TEXT, opacity: 0.22 };
}

function rampartRing(
  node: PositionNodeLike
): { stroke: string; dash?: string; title: string } | null {
  if (node.rampart_element == null) return null;
  const stroke = RAMPART_COLOR[node.rampart_element.toLowerCase()] ?? RAMPART_FALLBACK;
  const dash = RAMPART_DASH[node.rampart_crack_state ?? ''];
  return {
    stroke,
    dash,
    title: `${node.rampart_element} Rampart ${node.rampart_integrity ?? '?'}/${node.rampart_max_integrity ?? '?'}`,
  };
}

/** A dark chip with the place's name, at a point in viewBox units. */
function LabelChip({
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
  const width = text.length * 6.6 + 8;
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

function CoverBadges({ node }: { node: PositionNodeLike }) {
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

function MarkGlyph({
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
    <g data-testid={testId} data-mark={kind} aria-label={title} role="img">
      <title>{title}</title>
      <circle cx={cx} cy={cy} r={6} fill={fill} stroke={LABEL_BG} strokeWidth={1} />
      <Icon x={cx - 4} y={cy - 4} width={8} height={8} color="#fff" aria-hidden="true" />
    </g>
  );
}

function Token({
  occupant,
  cx,
  cy,
  clipId,
  aerial,
  rampartElement,
  interactive = false,
}: {
  occupant: BattleOccupant;
  cx: number;
  cy: number;
  clipId: string;
  aerial: boolean;
  rampartElement: string | null;
  /** Tokens over the air take clicks (for their place); ground tokens let them through. */
  interactive?: boolean;
}) {
  const url = occupant.thumbnailMediaUrl ?? occupant.thumbnailUrl ?? null;
  const ring = aerial ? AIR : SIDE_RING[occupant.side];
  const bystander = occupant.side === 'bystander';
  const tagWidth = occupant.name.length * 5.4 + 8;
  const title = bystander ? `${occupant.name} (bystander)` : occupant.name;
  return (
    <g
      data-testid="occupant-token"
      data-side={occupant.side}
      data-bystander={bystander ? 'true' : undefined}
      data-viewer={occupant.isViewer ? 'true' : undefined}
      data-aerial={aerial ? 'true' : undefined}
      opacity={bystander ? 0.45 : 1}
      pointerEvents={interactive ? 'auto' : 'none'}
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

const keyOf = (x: number, y: number) => `${x},${y}`;

export function BattleMap({
  nodes,
  edges,
  occupantsByPosition,
  heldPositions,
  moveActions,
  ownPositionId,
  onDispatchMove,
  onStepToSquare,
  onPickPosition,
  onGMPlace,
  links,
}: BattleMapProps) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '');

  const layout = useMemo(() => computeTacticalLayout(nodes, edges), [nodes, edges]);
  const areas = useMemo(() => placeAreas(nodes, layout), [nodes, layout]);
  const bounds = useMemo(() => mapBounds(areas.values()), [areas]);
  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const moveActionByPositionId = useMemo(() => {
    const map = new Map<number, PlayerAction>();
    for (const action of moveActions) {
      // The plain move comes first; a pass roll into the same held place stays a
      // panel choice, so a click never rolls by surprise (#4663).
      if (action.ref.position_id != null && !map.has(action.ref.position_id)) {
        map.set(action.ref.position_id, action);
      }
    }
    return map;
  }, [moveActions]);

  const heldBy = useMemo(
    () => new Map(heldPositions.map((h) => [h.position_id, h.holder_names])),
    [heldPositions]
  );

  // One pattern per distinct terrain image.
  const patternIdByUrl = useMemo(() => {
    const map = new Map<string, string>();
    for (const node of nodes) {
      if (node.terrain_art_url && !map.has(node.terrain_art_url)) {
        map.set(node.terrain_art_url, `${uid}-terrain-${map.size}`);
      }
    }
    return map;
  }, [nodes, uid]);

  const groundNodes = nodes.filter((n) => areas.has(n.id));
  const aerialNodes = nodes.filter(
    (n) => !areas.has(n.id) && isAerialOverlay(n) && areas.has(n.elevation_anchor_id!)
  );

  // Ground tokens first; aerial tokens then avoid their squares over the same area.
  const groundTokens = new Map<number, PlacedToken<BattleOccupant>[]>();
  const drawnSquares = new Map<number, Set<string>>();
  for (const node of groundNodes) {
    const area = areas.get(node.id)!;
    const occupants = occupantsByPosition.get(node.id) ?? [];
    // A derived area's squares are only drawing; a stored square cannot be inside it.
    const input = area.derived ? occupants.map((o) => ({ ...o, square: null })) : occupants;
    const placed = tokenSquares(area, input);
    groundTokens.set(node.id, placed);
    drawnSquares.set(node.id, new Set(placed.map((p) => keyOf(p.x, p.y))));
  }
  const aerialTokens = new Map<number, PlacedToken<BattleOccupant>[]>();
  for (const node of aerialNodes) {
    const anchorArea = areas.get(node.elevation_anchor_id!)!;
    const occupants = (occupantsByPosition.get(node.id) ?? []).map((o) => ({
      ...o,
      square: null,
    }));
    aerialTokens.set(
      node.id,
      tokenSquares(anchorArea, occupants, {
        blocked: drawnSquares.get(node.elevation_anchor_id!),
        fromEnd: true,
      })
    );
  }

  const handlePlace = (positionId: number, square: Square | null) => {
    if (onPickPosition?.(positionId)) return;
    if (onGMPlace?.(positionId)) return;
    const area = areas.get(positionId);
    const hasSquares = area !== undefined && !area.derived;
    if (positionId === ownPositionId) {
      if (square && hasSquares) onStepToSquare(square);
      return;
    }
    const action = moveActionByPositionId.get(positionId);
    if (action) {
      onDispatchMove(action, hasSquares ? square : null);
      return;
    }
    toast.error("You can't move there this turn.");
  };

  const handleKey = (positionId: number) => (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handlePlace(positionId, null);
    }
  };

  const picking = onPickPosition !== undefined;
  const ariaLabel = (name: string, positionId: number) => {
    const names = (occupantsByPosition.get(positionId) ?? []).map((o) => o.name);
    return names.length > 0 ? `${name}: ${names.join(', ')}` : name;
  };

  const gridLines: ReactNode[] = [];
  for (let x = bounds.x; x <= bounds.x + bounds.w; x += CELL) {
    gridLines.push(<line key={`gx${x}`} x1={x} y1={bounds.y} x2={x} y2={bounds.y + bounds.h} />);
  }
  for (let y = bounds.y; y <= bounds.y + bounds.h; y += CELL) {
    gridLines.push(<line key={`gy${y}`} x1={bounds.x} y1={y} x2={bounds.x + bounds.w} y2={y} />);
  }

  return (
    <div
      className="min-h-0 w-full flex-1 overflow-auto"
      style={{ background: BACKGROUND }}
      data-testid="tactical-map"
    >
      <svg
        viewBox={`${bounds.x} ${bounds.y} ${bounds.w} ${bounds.h}`}
        className="block h-auto w-full min-w-[560px]"
        role="group"
        aria-label="Battle map"
        data-testid="battle-map"
      >
        <defs>
          {[...patternIdByUrl].map(([url, id]) => (
            <pattern
              key={id}
              id={id}
              width={TERRAIN_TILE}
              height={TERRAIN_TILE}
              patternUnits="userSpaceOnUse"
            >
              <image
                href={url}
                width={TERRAIN_TILE}
                height={TERRAIN_TILE}
                preserveAspectRatio="xMidYMid slice"
              />
            </pattern>
          ))}
        </defs>
        <rect x={bounds.x} y={bounds.y} width={bounds.w} height={bounds.h} fill={BACKGROUND} />

        {/* Terrain. */}
        {groundNodes.map((node) => {
          const area = areas.get(node.id)!;
          const patternId = node.terrain_art_url
            ? patternIdByUrl.get(node.terrain_art_url)
            : undefined;
          return (
            <rect
              key={`terrain-${node.id}`}
              data-testid={`battle-map-terrain-${node.id}`}
              data-terrain={node.terrain_name ?? undefined}
              x={area.x * CELL}
              y={area.y * CELL}
              width={area.w * CELL}
              height={area.h * CELL}
              fill={patternId ? `url(#${patternId})` : (KIND_FILL[node.kind] ?? DEFAULT_FILL)}
            />
          );
        })}

        <g stroke="#000" strokeOpacity={0.2} strokeWidth={1} pointerEvents="none">
          {gridLines}
        </g>

        {/* Routes between places. */}
        <g pointerEvents="none">
          {edges.map((edge, index) => {
            const a = areas.get(edge.position_a_id);
            const b = areas.get(edge.position_b_id);
            if (!a || !b) return null;
            const p = center(a);
            const q = center(b);
            const style = edgeStroke(edge);
            return (
              <line
                key={`edge-${edge.position_a_id}-${edge.position_b_id}-${index}`}
                data-testid={`battle-map-edge-${edge.position_a_id}-${edge.position_b_id}`}
                x1={p.x}
                y1={p.y}
                x2={q.x}
                y2={q.y}
                stroke={style.stroke}
                strokeOpacity={style.opacity}
                strokeWidth={2}
                strokeDasharray={style.dash}
              >
                {style.title && <title>{style.title}</title>}
              </line>
            );
          })}
          {(links ?? [])
            .filter((link) => link.positionAId !== link.positionBId)
            .map((link) => {
              const a = areas.get(link.positionAId);
              const b = areas.get(link.positionBId);
              if (!a || !b) return null;
              const p = center(a);
              const q = center(b);
              return (
                <line
                  key={link.id}
                  data-testid={`battle-map-link-${link.id}`}
                  aria-label={link.label}
                  x1={p.x}
                  y1={p.y}
                  x2={q.x}
                  y2={q.y}
                  stroke="#f43f5e"
                  strokeWidth={2}
                  strokeDasharray="8 4"
                >
                  <title>{link.label}</title>
                </line>
              );
            })}
        </g>

        {/* Places: tint, outline, label and clickable squares. */}
        {groundNodes.map((node) => {
          const area = areas.get(node.id)!;
          const tint = KIND_TINT[node.kind] ?? DEFAULT_TINT;
          const holders = heldBy.get(node.id);
          const canMove = moveActionByPositionId.has(node.id);
          const ring = rampartRing(node);
          const label = holders?.length
            ? `${node.name} · Held by ${holders.join(', ')}`
            : node.name;
          const squares: ReactNode[] = [];
          for (let row = 0; row < area.h; row++) {
            for (let col = 0; col < area.w; col++) {
              const sx = area.x + col;
              const sy = area.y + row;
              squares.push(
                <rect
                  key={keyOf(sx, sy)}
                  data-testid={`battle-map-square-${node.id}-${sx}-${sy}`}
                  x={sx * CELL}
                  y={sy * CELL}
                  width={CELL}
                  height={CELL}
                  fill="transparent"
                  onClick={(event) => {
                    event.stopPropagation();
                    handlePlace(node.id, { x: sx, y: sy });
                  }}
                />
              );
            }
          }
          return (
            <g
              key={`area-${node.id}`}
              role="button"
              tabIndex={0}
              aria-label={ariaLabel(node.name, node.id)}
              data-testid={`tactical-map-node-${node.id}`}
              data-position-id={node.id}
              data-position-kind={node.kind}
              data-can-move={canMove ? 'true' : undefined}
              data-held={holders?.length ? 'true' : undefined}
              data-derived={area.derived ? 'true' : undefined}
              className="group cursor-pointer outline-none"
              onClick={() => handlePlace(node.id, null)}
              onKeyDown={handleKey(node.id)}
            >
              <rect
                x={area.x * CELL}
                y={area.y * CELL}
                width={area.w * CELL}
                height={area.h * CELL}
                fill={holders?.length ? HELD : tint}
                fillOpacity={holders?.length ? 0.22 : 0.1}
                stroke={holders?.length ? HELD : tint}
                strokeOpacity={holders?.length ? 0.7 : 1}
                strokeWidth={1.5}
                strokeDasharray="6 4"
              />
              {squares}
              {ring && (
                <rect
                  data-testid="rampart-ring"
                  data-rampart-crack-state={node.rampart_crack_state ?? undefined}
                  x={area.x * CELL - 3}
                  y={area.y * CELL - 3}
                  width={area.w * CELL + 6}
                  height={area.h * CELL + 6}
                  rx={4}
                  fill="none"
                  stroke={ring.stroke}
                  strokeWidth={2.5}
                  strokeDasharray={ring.dash}
                  pointerEvents="none"
                >
                  <title>{ring.title}</title>
                </rect>
              )}
              {(canMove || picking) && (
                <rect
                  data-testid={`battle-map-target-${node.id}`}
                  x={area.x * CELL}
                  y={area.y * CELL}
                  width={area.w * CELL}
                  height={area.h * CELL}
                  fill={GOLD}
                  fillOpacity={0.12}
                  stroke={GOLD}
                  strokeWidth={3}
                  pointerEvents="none"
                  className={
                    picking
                      ? 'opacity-70'
                      : 'opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100'
                  }
                />
              )}
              {(groundTokens.get(node.id) ?? []).map((t, index) => (
                <Token
                  key={`tok-${node.id}-${index}`}
                  occupant={t.occupant}
                  cx={(t.x + 0.5) * CELL}
                  cy={(t.y + 0.5) * CELL}
                  clipId={`${uid}-clip-${node.id}-${index}`}
                  aerial={false}
                  rampartElement={node.rampart_element}
                />
              ))}
              <LabelChip
                x={area.x * CELL + 6}
                y={area.y * CELL + 15}
                text={label}
                color={holders?.length ? '#ff9aa6' : LABEL_TEXT}
                badges={<CoverBadges node={node} />}
              />
            </g>
          );
        })}

        {/* The air above a place: an inset over its anchor, with lifted tokens. */}
        {aerialNodes.map((node) => {
          const anchor = nodesById.get(node.elevation_anchor_id!);
          const area = areas.get(node.elevation_anchor_id!)!;
          const x = (area.x + AIR_INSET) * CELL;
          const y = (area.y + AIR_INSET) * CELL;
          const w = (area.w - 2 * AIR_INSET) * CELL;
          const h = (area.h - 2 * AIR_INSET) * CELL;
          const canMove = moveActionByPositionId.has(node.id);
          const label = `Above ${anchor?.name ?? node.name}`;
          const chipWidth = label.length * 6.6 + 8;
          return (
            <g
              key={`air-${node.id}`}
              role="button"
              tabIndex={0}
              aria-label={ariaLabel(label, node.id)}
              data-testid={`tactical-map-node-${node.id}`}
              data-position-id={node.id}
              data-position-kind={node.kind}
              data-can-move={canMove ? 'true' : undefined}
              className="group cursor-pointer outline-none"
              onClick={() => handlePlace(node.id, null)}
              onKeyDown={handleKey(node.id)}
            >
              <rect
                x={x}
                y={y}
                width={w}
                height={h}
                fill={AIR}
                fillOpacity={0.08}
                stroke={AIR}
                strokeOpacity={0.6}
                strokeWidth={1.5}
                strokeDasharray="4 4"
                pointerEvents="none"
              />
              {(canMove || picking) && (
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  fill="none"
                  stroke={GOLD}
                  strokeWidth={3}
                  pointerEvents="none"
                  className={
                    picking
                      ? 'opacity-70'
                      : 'opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100'
                  }
                />
              )}
              {/* The chip is the air's own click target; the ground below stays clickable. */}
              <rect
                data-testid={`battle-map-air-chip-${node.id}`}
                x={x + w - chipWidth - 6}
                y={y + 4}
                width={chipWidth}
                height={15}
                fill="transparent"
              />
              <LabelChip x={x + w - 3} y={y + 15} text={label} color={AIR} anchor="end" />
              {(aerialTokens.get(node.id) ?? []).map((t, index) => (
                <Token
                  key={`air-tok-${node.id}-${index}`}
                  occupant={t.occupant}
                  cx={(t.x + 0.5) * CELL}
                  cy={(t.y + 0.5) * CELL - AIR_LIFT}
                  clipId={`${uid}-airclip-${node.id}-${index}`}
                  aerial
                  rampartElement={null}
                  interactive
                />
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
