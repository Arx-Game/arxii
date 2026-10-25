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

import { computeTacticalLayout } from '@/areas/tacticalLayout';
import type {
  OccupantLink,
  PositionEdgeLike,
  PositionNodeLike,
} from '@/areas/components/TacticalMap';
import type { PlayerAction } from '@/scenes/actionTypes';
import { CELL, isAerialOverlay, mapBounds, placeAreas, tokenSquares } from '../battleMapLayout';
import type { MapArea, PlacedToken, Square } from '../battleMapLayout';
import {
  AIR,
  AIR_INSET,
  AIR_LIFT,
  BACKGROUND,
  GOLD,
  HELD,
  LABEL_TEXT,
  TARGET_OUTLINE_HOVER,
  TARGET_OUTLINE_PICKING,
  TERRAIN_TILE,
  center,
  chipWidth,
  kindFill,
  kindTint,
  placeAriaLabel,
  rampartRing,
  routeStyle,
} from '../battleMapPalette';
import type { BattleOccupant } from '../battleMapPalette';
import { CoverBadges, LabelChip, RouteLabel, Token } from './battleMapPieces';

export type { BattleOccupant, CombatSide } from '../battleMapPalette';

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

const keyOf = (x: number, y: number) => `${x},${y}`;
const NO_SQUARES = 'This place has no squares to pick.';
const CANNOT_MOVE = "You can't move there this turn.";

interface PlaceHandlers {
  onPlace: (positionId: number, square: Square | null) => void;
  onKey: (positionId: number) => (event: KeyboardEvent) => void;
}

function PlaceArea({
  node,
  area,
  tokens,
  holders,
  canMove,
  picking,
  ariaLabel,
  uid,
  onPlace,
  onKey,
}: PlaceHandlers & {
  node: PositionNodeLike;
  area: MapArea;
  tokens: PlacedToken<BattleOccupant>[];
  holders: readonly string[] | undefined;
  canMove: boolean;
  picking: boolean;
  ariaLabel: string;
  uid: string;
}) {
  const held = (holders?.length ?? 0) > 0;
  const tint = kindTint(node.kind);
  const ring = rampartRing(node);
  const label = held ? `${node.name} · Held by ${holders!.join(', ')}` : node.name;
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
            onPlace(node.id, { x: sx, y: sy });
          }}
        />
      );
    }
  }
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      data-testid={`tactical-map-node-${node.id}`}
      data-position-id={node.id}
      data-position-kind={node.kind}
      data-can-move={canMove ? 'true' : undefined}
      data-held={held ? 'true' : undefined}
      data-derived={area.derived ? 'true' : undefined}
      className="group cursor-pointer outline-none"
      onClick={() => onPlace(node.id, null)}
      onKeyDown={onKey(node.id)}
    >
      <rect
        x={area.x * CELL}
        y={area.y * CELL}
        width={area.w * CELL}
        height={area.h * CELL}
        fill={held ? HELD : tint}
        fillOpacity={held ? 0.22 : 0.1}
        stroke={held ? HELD : tint}
        strokeOpacity={held ? 0.7 : 1}
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
          pointerEvents="stroke"
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
          className={picking ? TARGET_OUTLINE_PICKING : TARGET_OUTLINE_HOVER}
        />
      )}
      {tokens.map((t, index) => (
        <Token
          key={`tok-${node.id}-${index}`}
          occupant={t.occupant}
          cx={(t.x + 0.5) * CELL}
          cy={(t.y + 0.5) * CELL}
          clipId={`${uid}-clip-${node.id}-${index}`}
          aerial={false}
          rampartElement={node.rampart_element}
          onClick={() => onPlace(node.id, { x: t.x, y: t.y })}
        />
      ))}
      <LabelChip
        x={area.x * CELL + 6}
        y={area.y * CELL + 15}
        text={label}
        color={held ? '#ff9aa6' : LABEL_TEXT}
        badges={<CoverBadges node={node} />}
      />
    </g>
  );
}

function AirInset({
  node,
  anchorArea,
  label,
  tokens,
  canMove,
  picking,
  ariaLabel,
  uid,
  onPlace,
  onKey,
}: PlaceHandlers & {
  node: PositionNodeLike;
  anchorArea: MapArea;
  label: string;
  tokens: PlacedToken<BattleOccupant>[];
  canMove: boolean;
  picking: boolean;
  ariaLabel: string;
  uid: string;
}) {
  const x = (anchorArea.x + AIR_INSET) * CELL;
  const y = (anchorArea.y + AIR_INSET) * CELL;
  const w = (anchorArea.w - 2 * AIR_INSET) * CELL;
  const h = (anchorArea.h - 2 * AIR_INSET) * CELL;
  const width = chipWidth(label);
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      data-testid={`tactical-map-node-${node.id}`}
      data-position-id={node.id}
      data-position-kind={node.kind}
      data-can-move={canMove ? 'true' : undefined}
      className="group cursor-pointer outline-none"
      onClick={() => onPlace(node.id, null)}
      onKeyDown={onKey(node.id)}
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
          className={picking ? TARGET_OUTLINE_PICKING : TARGET_OUTLINE_HOVER}
        />
      )}
      {/* The chip is the air's own click target; the ground below stays clickable. */}
      <rect
        data-testid={`battle-map-air-chip-${node.id}`}
        x={x + w - width - 6}
        y={y + 4}
        width={width}
        height={15}
        fill="transparent"
      />
      <LabelChip x={x + w - 3} y={y + 15} text={label} color={AIR} anchor="end" />
      {tokens.map((t, index) => (
        <Token
          key={`air-tok-${node.id}-${index}`}
          occupant={t.occupant}
          cx={(t.x + 0.5) * CELL}
          cy={(t.y + 0.5) * CELL - AIR_LIFT}
          clipId={`${uid}-airclip-${node.id}-${index}`}
          aerial
          rampartElement={null}
          onClick={() => onPlace(node.id, null)}
        />
      ))}
    </g>
  );
}

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
    const occupants = (occupantsByPosition.get(node.id) ?? []).map((o) => ({
      ...o,
      square: null,
    }));
    aerialTokens.set(
      node.id,
      tokenSquares(areas.get(node.elevation_anchor_id!)!, occupants, {
        blocked: drawnSquares.get(node.elevation_anchor_id!),
        fromEnd: true,
      })
    );
  }
  const viewerSquare =
    ownPositionId === null
      ? undefined
      : groundTokens.get(ownPositionId)?.find((t) => t.occupant.isViewer);

  // A route or link end: the place's area centre; the air resolves to its anchor, lifted.
  const routePoint = (positionId: number): { x: number; y: number } | null => {
    const area = areas.get(positionId);
    if (area) return center(area);
    const node = nodesById.get(positionId);
    const anchorArea = node?.elevation_anchor_id != null && areas.get(node.elevation_anchor_id);
    if (!anchorArea) return null;
    const p = center(anchorArea);
    return { x: p.x, y: p.y - AIR_LIFT };
  };
  const routeEnds = (aId: number, bId: number) => {
    const p = routePoint(aId);
    const q = routePoint(bId);
    if (!p || !q || (p.x === q.x && p.y === q.y)) return null;
    return { p, q };
  };

  const handlePlace = (positionId: number, square: Square | null) => {
    if (onPickPosition?.(positionId)) return;
    if (onGMPlace?.(positionId)) return;
    const area = areas.get(positionId);
    const hasSquares = area !== undefined && !area.derived;
    if (positionId === ownPositionId) {
      if (square === null) return;
      if (!hasSquares) {
        toast.error(NO_SQUARES);
        return;
      }
      if (viewerSquare && viewerSquare.x === square.x && viewerSquare.y === square.y) return;
      onStepToSquare(square);
      return;
    }
    const action = moveActionByPositionId.get(positionId);
    if (action) {
      onDispatchMove(action, hasSquares ? square : null);
      return;
    }
    toast.error(CANNOT_MOVE);
  };

  const handleKey = (positionId: number) => (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handlePlace(positionId, null);
    }
  };

  const picking = onPickPosition !== undefined;

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
              fill={patternId ? `url(#${patternId})` : kindFill(node.kind)}
            />
          );
        })}

        <g stroke="#000" strokeOpacity={0.2} strokeWidth={1} pointerEvents="none">
          {gridLines}
        </g>

        {/* Routes between places. */}
        <g pointerEvents="none">
          {edges.map((edge, index) => {
            const ends = routeEnds(edge.position_a_id, edge.position_b_id);
            if (!ends) return null;
            const style = routeStyle(edge);
            return (
              <line
                key={`edge-${edge.position_a_id}-${edge.position_b_id}-${index}`}
                data-testid={`battle-map-edge-${edge.position_a_id}-${edge.position_b_id}`}
                x1={ends.p.x}
                y1={ends.p.y}
                x2={ends.q.x}
                y2={ends.q.y}
                stroke={style.stroke}
                strokeOpacity={style.opacity}
                strokeWidth={2}
                strokeDasharray={style.dash}
              >
                {style.label && <title>{style.label}</title>}
              </line>
            );
          })}
        </g>

        {/* Places: tint, outline, label, clickable squares and their tokens. */}
        {groundNodes.map((node) => (
          <PlaceArea
            key={`area-${node.id}`}
            node={node}
            area={areas.get(node.id)!}
            tokens={groundTokens.get(node.id) ?? []}
            holders={heldBy.get(node.id)}
            canMove={moveActionByPositionId.has(node.id)}
            picking={picking}
            ariaLabel={placeAriaLabel(node.name, occupantsByPosition.get(node.id) ?? [])}
            uid={uid}
            onPlace={handlePlace}
            onKey={handleKey}
          />
        ))}

        {/* Gate and wall labels, over the places so they stay readable. */}
        {edges.map((edge, index) => {
          const style = routeStyle(edge);
          const ends = style.label ? routeEnds(edge.position_a_id, edge.position_b_id) : null;
          if (!ends || !style.label) return null;
          return (
            <RouteLabel
              key={`route-label-${edge.position_a_id}-${edge.position_b_id}-${index}`}
              testId={`battle-map-route-label-${edge.position_a_id}-${edge.position_b_id}`}
              x={(ends.p.x + ends.q.x) / 2}
              y={(ends.p.y + ends.q.y) / 2}
              text={style.label}
              color={style.stroke}
            />
          );
        })}

        {/* Engagement locks: a dashed rose line; the locked marks carry the words. */}
        {(links ?? [])
          .filter((link) => link.positionAId !== link.positionBId)
          .map((link) => {
            const ends = routeEnds(link.positionAId, link.positionBId);
            if (!ends) return null;
            return (
              <line
                key={link.id}
                data-testid={`battle-map-link-${link.id}`}
                aria-label={link.label}
                x1={ends.p.x}
                y1={ends.p.y}
                x2={ends.q.x}
                y2={ends.q.y}
                stroke="#f43f5e"
                strokeWidth={2}
                strokeDasharray="8 4"
                pointerEvents="none"
              />
            );
          })}

        {/* The air above a place: an inset over its anchor, with lifted tokens. */}
        {aerialNodes.map((node) => {
          const anchor = nodesById.get(node.elevation_anchor_id!);
          const label = `Above ${anchor?.name ?? node.name}`;
          return (
            <AirInset
              key={`air-${node.id}`}
              node={node}
              anchorArea={areas.get(node.elevation_anchor_id!)!}
              label={label}
              tokens={aerialTokens.get(node.id) ?? []}
              canMove={moveActionByPositionId.has(node.id)}
              picking={picking}
              ariaLabel={placeAriaLabel(label, occupantsByPosition.get(node.id) ?? [])}
              uid={uid}
              onPlace={handlePlace}
              onKey={handleKey}
            />
          );
        })}
      </svg>
    </div>
  );
}
