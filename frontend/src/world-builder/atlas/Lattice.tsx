/**
 * Lattice (#3477 Task 5) — the one grid dialect every altitude of the Atlas
 * shares (brief ruling: "one lattice dialect at every altitude"). `mode`
 * picks what a plotted square realizes into and what tiles mean:
 * `'areas'` (every level above BUILDING) holds child areas *and* this area's
 * own direct rooms as tiles, and realizes new child areas (`create_area`);
 * `'rooms'` (a BUILDING) holds only that building's rooms, one floor at a
 * time via the floors rail, and realizes new rooms (`staff_dig_room`). The
 * prototype (`docs/superpowers/plans/commonplace-atlas-reference.html`) is
 * the gesture spec: click-to-plan, right-click/✂-prune carve cycle,
 * drag-to-swap with a 5px threshold, ⊕ edge growth, and (rooms mode) the
 * floors rail + ⟛ connect tool.
 *
 * Two backend gaps neither `create_area` nor `staff_dig_room` closes force a
 * two-step "realize, then resolve" flow instead of one dispatch:
 *
 * - `create_area` has no `grid_x`/`grid_y` kwargs at all (only `edit_area`
 *   does) — matches `CreateAreaDialog`'s existing precedent of leaving a
 *   freshly created area unplaced until an `edit_area`/arrange follow-up.
 * - Neither action's `ActionResult` returns the new row's id, so this can't
 *   just dispatch a follow-up immediately — it has to wait for the id to
 *   show up. Once dispatched, the plotted cell's name goes into
 *   `pendingPlacements`/`pendingLinks`; an effect watching the `tiles` prop
 *   resolves each entry the moment the area-manager refetch (already wired
 *   by `useWorldBuilderAction`'s cache invalidation) surfaces the new row,
 *   then dispatches `edit_area` (position) or `staff_link_rooms`
 *   (entrance/exit, via `AddDialog`'s payload) and clears the entry. A dig
 *   that never lands (a refused dispatch) leaves its entry stranded for the
 *   session — harmless, since nothing new is likely to land on that exact
 *   cell/name by coincidence, but worth knowing if this needs hardening
 *   later.
 *
 * Drag-to-swap gives `staff_move_room` (typed since #2449, never dispatched)
 * its first real caller: dropping a ROOM tile onto an AREA tile — reachable
 * only in `'areas'` mode, where both kinds of tile coexist — re-parents the
 * room into that area/building (mirrors the action's own semantics: grid
 * coordinates reset to unplaced, so no coordinate math is needed here).
 * Every other drop (same-kind, or onto open ground) is a position-only
 * dispatch (`edit_area`/`staff_place_room`), swapping the two tiles' cells
 * when the drop lands on an occupied one.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Plate } from '@/components/folio';
import { cn } from '@/lib/utils';
import { useAccount } from '@/store/hooks';

import { AddDialog, type AddDialogConnection, type AddDialogRealizePayload } from './AddDialog';
import {
  boundsContaining,
  CARDINALS,
  carveCell,
  cellKey,
  computeFloorRail,
  directionBetween,
  FANCIFUL_EXIT_NAME,
  growBounds,
  growFloor,
  parseCellKey,
  planCell,
  readGrownFloors,
  readLatticeSketch,
  unplanCell,
  writeGrownFloors,
  writeLatticeSketch,
  type CellKey,
  type LatticeSketch,
} from './latticeState';

export interface LatticeTile {
  id: number;
  kind: 'area' | 'room';
  name: string;
  kindLabel: string;
  unpublished: boolean;
  /** `null` means "dug/created but not yet placed on this grid" (see the module doc). */
  gridX: number | null;
  gridY: number | null;
  /** Rooms only — which floor this tile belongs to. Ignored for area tiles. */
  floor: number;
  /** Area tiles only — passed through so the caller can route `onOpen` without a second lookup. */
  level?: number;
}

export interface LatticeProps {
  mode: 'areas' | 'rooms';
  nodeId: number;
  tiles: LatticeTile[];
  onOpen: (tile: LatticeTile) => void;
  /** Fires once a realize dispatch has gone out — a convenience signal, not tied to success/failure. */
  onRealize?: () => void;
  /** Keyed generically so this also satisfies the story palette's own action-key union. */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
  /** Areas mode only — the level new child areas realize at (`create_area`'s `level`). */
  childAreaLevel?: number;
  /**
   * A search-hit landing on this grid (#3477 Task 6, spec §1) — the matching
   * tile gets a brief highlight ring. The caller (`AtlasPage`) owns clearing
   * it (a timeout); Lattice only renders whichever id it's handed.
   */
  highlightTileId?: number | null;
}

const DRAG_THRESHOLD_PX = 5;

function findAdjacent(tiles: LatticeTile[], x: number, y: number): LatticeTile | null {
  for (const dir of CARDINALS) {
    const hit = tiles.find((t) => t.gridX === x + dir.dx && t.gridY === y + dir.dy);
    if (hit) return hit;
  }
  return null;
}

function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'area';
}

function cellState(key: CellKey, sketch: LatticeSketch): 'planned' | 'void' | 'empty' {
  if (sketch.planned.includes(key)) return 'planned';
  if (sketch.voids.includes(key)) return 'void';
  return 'empty';
}

interface PendingLink {
  x: number;
  y: number;
  /** Captured at dig time — the resolve effect must match the dug room's own
   * floor, not whatever floor the rail has switched to since (a pre-existing
   * room at the same (x,y) on the newly-viewed floor would receive the links
   * and orphan the actually-dug room). */
  floor: number;
  entrance: AddDialogConnection | null;
  exit: AddDialogConnection | null;
}

function pendingLinkKey(x: number, y: number, floor: number): string {
  return `${x},${y}@${floor}`;
}

export function Lattice({
  mode,
  nodeId,
  tiles,
  onOpen,
  onRealize,
  runAction,
  childAreaLevel,
  highlightTileId = null,
}: LatticeProps) {
  const account = useAccount();
  const accountId = account?.id ?? 'anon';

  const [floor, setFloor] = useState(0);
  const [grownFloors, setGrownFloors] = useState<number[]>(() =>
    readGrownFloors(accountId, nodeId)
  );
  const dataFloors = useMemo(
    () => (mode === 'rooms' ? Array.from(new Set(tiles.map((t) => t.floor))) : []),
    [mode, tiles]
  );
  const floorRail = useMemo(
    () => (mode === 'rooms' ? computeFloorRail(dataFloors, grownFloors) : []),
    [mode, dataFloors, grownFloors]
  );
  useEffect(() => {
    if (mode === 'rooms' && floorRail.length > 0 && !floorRail.includes(floor)) {
      setFloor(floorRail[0]);
    }
  }, [mode, floorRail, floor]);

  const sketchFloor = mode === 'rooms' ? floor : null;
  const [sketch, setSketch] = useState<LatticeSketch>(() =>
    readLatticeSketch(accountId, mode, nodeId, sketchFloor)
  );
  useEffect(() => {
    setSketch(readLatticeSketch(accountId, mode, nodeId, sketchFloor));
  }, [accountId, mode, nodeId, sketchFloor]);

  const updateSketch = (updater: (prev: LatticeSketch) => LatticeSketch) => {
    setSketch((prev) => {
      const next = updater(prev);
      writeLatticeSketch(accountId, mode, nodeId, sketchFloor, next);
      return next;
    });
  };

  const placedTiles = useMemo(
    () =>
      tiles.filter(
        (t) => t.gridX != null && t.gridY != null && (mode === 'areas' || t.floor === floor)
      ),
    [tiles, mode, floor]
  );

  const bounds = useMemo(
    () =>
      boundsContaining(
        sketch.bounds,
        placedTiles.map((t) => ({ gridX: t.gridX as number, gridY: t.gridY as number }))
      ),
    [sketch.bounds, placedTiles]
  );

  const tileAt = useMemo(() => {
    const map = new Map<CellKey, LatticeTile>();
    for (const t of placedTiles) map.set(cellKey(t.gridX as number, t.gridY as number), t);
    return map;
  }, [placedTiles]);

  const roomOptions = useMemo(
    () =>
      tiles
        .filter((t) => t.kind === 'room' && t.gridX != null && t.gridY != null)
        .map((t) => ({ id: t.id, name: t.name })),
    [tiles]
  );

  // ---- tools: prune and connect are mutually exclusive; connect is rooms-only ----
  const [pruning, setPruning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectSrc, setConnectSrc] = useState<LatticeTile | null>(null);

  const togglePrune = () => {
    setPruning((prev) => {
      const next = !prev;
      if (next) {
        setConnecting(false);
        setConnectSrc(null);
      }
      return next;
    });
  };

  const toggleConnect = () => {
    setConnecting((prev) => {
      const next = !prev;
      if (next) setPruning(false);
      return next;
    });
    setConnectSrc(null);
  };

  const handleConnectClick = (tile: LatticeTile) => {
    if (!connectSrc) {
      setConnectSrc(tile);
      return;
    }
    if (connectSrc.id === tile.id) {
      setConnectSrc(null);
      return;
    }
    const forward = directionBetween(connectSrc, tile);
    const nameAb = forward ? forward.name : FANCIFUL_EXIT_NAME;
    const nameBa = forward ? forward.opposite : FANCIFUL_EXIT_NAME;
    runAction('staff_link_rooms', {
      room_a_id: connectSrc.id,
      room_b_id: tile.id,
      name_ab: nameAb,
      name_ba: nameBa,
    });
    setConnectSrc(null);
    setConnecting(false); // mode auto-exits after one join
  };

  // ---- carve cycle: plan -> clear, empty -> void, void -> restore ----
  const handleCellLeftClick = (key: CellKey, state: 'planned' | 'void' | 'empty') => {
    if (pruning) {
      updateSketch((prev) => carveCell(prev, key));
      return;
    }
    if (state === 'empty') {
      updateSketch((prev) => planCell(prev, key));
    } else if (state === 'planned') {
      const [x, y] = parseCellKey(key);
      setAddCell({ x, y });
    }
    // void: inert on a plain left click — only carving (right-click / prune) touches it.
  };

  const handleCellRightClick = (event: React.MouseEvent, key: CellKey) => {
    event.preventDefault();
    updateSketch((prev) => carveCell(prev, key));
  };

  // ---- growth: all four edges, never shifting existing coordinates ----
  const grow = (edge: 'north' | 'south' | 'east' | 'west') => {
    updateSketch((prev) => ({ ...prev, bounds: growBounds(bounds, edge) }));
  };

  const growFloorRail = (edge: 'up' | 'down') => {
    const next = growFloor(floorRail, edge);
    setGrownFloors((prev) => {
      const updated = [...prev, next];
      writeGrownFloors(accountId, nodeId, updated);
      return updated;
    });
    setFloor(next);
  };

  // ---- realize: AddDialog owns the plotted cell until it's dispatched ----
  const [addCell, setAddCell] = useState<{ x: number; y: number } | null>(null);
  const defaultNeighbor = useMemo(() => {
    if (!addCell) return null;
    const neighbor = findAdjacent(placedTiles, addCell.x, addCell.y);
    if (!neighbor) return null;
    const toNeighbor = directionBetween(
      { gridX: addCell.x, gridY: addCell.y } as LatticeTile,
      neighbor
    );
    if (!toNeighbor) return null;
    return { roomId: neighbor.id, intoName: toNeighbor.opposite, outName: toNeighbor.name };
  }, [addCell, placedTiles]);

  // Cells awaiting an id that only the next `tiles` refetch will reveal —
  // see the module doc's "realize, then resolve" note.
  const pendingLinksRef = useRef<Map<string, PendingLink>>(new Map());
  const pendingAreaPlacementsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  useEffect(() => {
    for (const [key, pending] of pendingLinksRef.current) {
      const newRoom = tiles.find(
        (t) =>
          t.kind === 'room' &&
          t.gridX === pending.x &&
          t.gridY === pending.y &&
          t.floor === pending.floor
      );
      if (!newRoom) continue;
      const { entrance, exit } = pending;
      if (entrance && exit && entrance.roomId === exit.roomId) {
        runAction('staff_link_rooms', {
          room_a_id: newRoom.id,
          room_b_id: entrance.roomId,
          name_ab: exit.exitName,
          name_ba: entrance.exitName,
        });
      } else {
        if (entrance) {
          runAction('staff_link_rooms', {
            room_a_id: entrance.roomId,
            room_b_id: newRoom.id,
            name_ab: entrance.exitName,
            name_ba: entrance.exitName,
          });
        }
        if (exit) {
          runAction('staff_link_rooms', {
            room_a_id: newRoom.id,
            room_b_id: exit.roomId,
            name_ab: exit.exitName,
            name_ba: exit.exitName,
          });
        }
      }
      pendingLinksRef.current.delete(key);
    }
    for (const [name, pending] of pendingAreaPlacementsRef.current) {
      const newArea = tiles.find((t) => t.kind === 'area' && t.name === name && t.gridX == null);
      if (!newArea) continue;
      runAction('edit_area', { area_id: newArea.id, grid_x: pending.x, grid_y: pending.y });
      pendingAreaPlacementsRef.current.delete(name);
    }
  }, [tiles, runAction]);

  const handleConfirmRealize = (payload: AddDialogRealizePayload) => {
    if (!addCell) return;
    const { x, y } = addCell;
    onRealize?.();
    if (payload.kind === 'area') {
      runAction('create_area', {
        name: payload.name,
        slug: slugify(payload.name),
        level: childAreaLevel,
        parent_id: nodeId,
      });
      pendingAreaPlacementsRef.current.set(payload.name, { x, y });
    } else if (payload.kind === 'room') {
      runAction('staff_dig_room', {
        area_id: nodeId,
        name: payload.name,
        floor,
        grid_x: x,
        grid_y: y,
      });
      if (payload.entrance || payload.exit) {
        pendingLinksRef.current.set(pendingLinkKey(x, y, floor), {
          x,
          y,
          floor,
          entrance: payload.entrance,
          exit: payload.exit,
        });
      }
    }
    updateSketch((prev) => unplanCell(prev, cellKey(x, y)));
    setAddCell(null);
  };

  // ---- drag-to-swap: 5px threshold, drop-target highlight, click suppression ----
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dragOverKey, setDragOverKey] = useState<CellKey | null>(null);
  const suppressClickRef = useRef(false);

  const placeTile = (tile: LatticeTile, x: number, y: number) => {
    if (tile.kind === 'area') {
      runAction('edit_area', { area_id: tile.id, grid_x: x, grid_y: y });
    } else {
      runAction('staff_place_room', { room_id: tile.id, grid_x: x, grid_y: y, floor: tile.floor });
    }
  };

  const resolveDrop = (dragged: LatticeTile, overKey: CellKey) => {
    const [x, y] = parseCellKey(overKey);
    const target = tileAt.get(overKey) ?? null;
    if (target && target.id === dragged.id) return;
    if (target && dragged.kind === 'room' && target.kind === 'area') {
      runAction('staff_move_room', { room_id: dragged.id, area_id: target.id });
      return;
    }
    const originX = dragged.gridX as number;
    const originY = dragged.gridY as number;
    placeTile(dragged, x, y);
    if (target) placeTile(target, originX, originY);
  };

  const handlePointerDown = (tile: LatticeTile, event: React.PointerEvent) => {
    if (event.button !== 0) return;
    const startX = event.clientX;
    const startY = event.clientY;
    let moved = false;

    const onMove = (moveEvent: PointerEvent) => {
      if (
        !moved &&
        Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < DRAG_THRESHOLD_PX
      ) {
        return;
      }
      moved = true;
      setDraggingId(tile.id);
      const el = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY);
      const cellEl = el?.closest<HTMLElement>('[data-cell-key]');
      setDragOverKey((cellEl?.dataset.cellKey as CellKey | undefined) ?? null);
    };

    const onUp = (upEvent: PointerEvent) => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setDraggingId(null);
      setDragOverKey(null);
      if (!moved) return; // no threshold crossed — an ordinary click, nothing to resolve
      suppressClickRef.current = true;
      const el = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
      const overKey = el?.closest<HTMLElement>('[data-cell-key]')?.dataset.cellKey as
        | CellKey
        | undefined;
      if (overKey) resolveDrop(tile, overKey);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const handleTileClick = (tile: LatticeTile) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    if (connecting && mode === 'rooms') {
      handleConnectClick(tile);
      return;
    }
    onOpen(tile);
  };

  const rows = bounds.maxY - bounds.minY + 1;
  const cols = bounds.maxX - bounds.minX + 1;
  const gridCells: { x: number; y: number }[] = [];
  for (let r = 0; r < rows; r += 1) {
    const y = bounds.maxY - r;
    for (let c = 0; c < cols; c += 1) {
      gridCells.push({ x: bounds.minX + c, y });
    }
  }

  return (
    <div data-testid="lattice" data-mode={mode}>
      {mode === 'rooms' && (
        <div
          className="mb-2 flex flex-wrap items-center gap-1"
          role="group"
          aria-label="Floors of this build"
          data-testid="lattice-floor-rail"
        >
          <button
            type="button"
            className="px-1 font-body text-xs italic text-muted-foreground hover:text-primary"
            title="a build grows floors as you dig them"
            onClick={() => growFloorRail('up')}
            data-testid="lattice-floor-grow-up"
          >
            ⊕
          </button>
          {floorRail.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={f === floor}
              className={cn(
                'border px-2 py-0.5 text-xs',
                f === floor ? 'border-primary text-primary' : 'text-muted-foreground'
              )}
              onClick={() => setFloor(f)}
              data-testid={`lattice-floor-${f}`}
            >
              {f === 0 ? 'G' : f}
            </button>
          ))}
          <button
            type="button"
            className="px-1 font-body text-xs italic text-muted-foreground hover:text-primary"
            title="a build grows floors as you dig them"
            onClick={() => growFloorRail('down')}
            data-testid="lattice-floor-grow-down"
          >
            ⊕
          </button>
        </div>
      )}

      <div className="flex justify-center">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => grow('north')}
          data-testid="lattice-grow-north"
        >
          ⊕ row north
        </Button>
      </div>
      <div className="flex items-stretch gap-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => grow('west')}
          data-testid="lattice-grow-west"
        >
          ⊕
        </Button>
        <Plate className="flex-1 overflow-x-auto rounded-none p-0.5">
          <div
            className="grid gap-0.5"
            style={{ gridTemplateColumns: `repeat(${cols}, minmax(7rem, 1fr))` }}
            data-testid="lattice-grid"
          >
            {gridCells.map(({ x, y }) => {
              const key = cellKey(x, y);
              const tile = tileAt.get(key);
              if (tile) {
                return (
                  <button
                    key={key}
                    type="button"
                    data-cell-key={key}
                    data-testid={`lattice-tile-${tile.id}`}
                    data-highlighted={highlightTileId === tile.id ? 'true' : undefined}
                    className={cn(
                      'flex min-h-24 flex-col rounded-none border bg-card px-2 py-1.5 text-left',
                      tile.unpublished && 'border-dashed',
                      draggingId === tile.id && 'opacity-60',
                      dragOverKey === key && draggingId !== tile.id && 'ring-2 ring-primary',
                      highlightTileId === tile.id && 'animate-pulse ring-2 ring-primary'
                    )}
                    onPointerDown={(event) => handlePointerDown(tile, event)}
                    onContextMenu={(event) => event.preventDefault()}
                    onClick={() => handleTileClick(tile)}
                  >
                    <span
                      className={cn(
                        'theme-heading text-sm [font-variant:small-caps]',
                        tile.unpublished && 'text-muted-foreground'
                      )}
                    >
                      {tile.name}
                      {connectSrc?.id === tile.id && ' ⟛'}
                    </span>
                    <span className="mt-1 text-[0.6rem] uppercase tracking-wide text-muted-foreground">
                      {tile.kindLabel}
                    </span>
                  </button>
                );
              }
              const state = cellState(key, sketch);
              return (
                <button
                  key={key}
                  type="button"
                  data-cell-key={key}
                  data-testid={`lattice-cell-${x}-${y}`}
                  data-cell-state={state}
                  aria-label={
                    state === 'planned'
                      ? 'planned square — click to add'
                      : state === 'void'
                        ? 'carved out — right-click to restore'
                        : 'empty ground — click to plan'
                  }
                  className={cn(
                    'relative flex min-h-24 flex-col justify-center rounded-none border px-2 py-1.5 text-left text-xs',
                    state === 'empty' && 'border-dotted text-muted-foreground',
                    state === 'planned' && 'border-dashed border-primary text-muted-foreground',
                    state === 'void' && 'border-transparent opacity-35'
                  )}
                  onClick={() => handleCellLeftClick(key, state)}
                  onContextMenu={(event) => handleCellRightClick(event, key)}
                >
                  {state === 'planned' && (
                    <>
                      <span className="italic">planned</span>
                      <span
                        role="button"
                        tabIndex={0}
                        aria-label="unplan this square"
                        title="remove from the plan"
                        className="absolute right-1 top-1 text-muted-foreground hover:text-primary"
                        onClick={(event) => {
                          event.stopPropagation();
                          updateSketch((prev) => unplanCell(prev, key));
                        }}
                        data-testid={`lattice-unplan-${x}-${y}`}
                      >
                        ✕
                      </span>
                    </>
                  )}
                  {state === 'empty' && <span aria-hidden>⊕</span>}
                </button>
              );
            })}
          </div>
        </Plate>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => grow('east')}
          data-testid="lattice-grow-east"
        >
          ⊕
        </Button>
      </div>
      <div className="flex justify-center">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => grow('south')}
          data-testid="lattice-grow-south"
        >
          ⊕ row south
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-3">
        {mode === 'rooms' && (
          <Button
            type="button"
            variant={connecting ? 'default' : 'outline'}
            size="sm"
            aria-pressed={connecting}
            onClick={toggleConnect}
            data-testid="lattice-connect-toggle"
          >
            ⟛ connect rooms
          </Button>
        )}
        <Button
          type="button"
          variant={pruning ? 'default' : 'outline'}
          size="sm"
          aria-pressed={pruning}
          onClick={togglePrune}
          data-testid="lattice-prune-toggle"
        >
          ✂ prune
        </Button>
        {mode === 'rooms' && (
          <span
            className="font-body text-xs italic text-muted-foreground"
            data-testid="lattice-connect-note"
          >
            {connecting
              ? connectSrc
                ? `now click the room to join ${connectSrc.name} to…`
                : 'click the first room…'
              : 'click it, then click two rooms to join them — or add exits from inside any room'}
          </span>
        )}
      </div>
      <p className="mt-1 font-body text-xs italic text-muted-foreground">
        ❧ rough positions, not measurements — drag to arrange, click empty ground to plan,
        right-click to carve.
      </p>

      <AddDialog
        mode={mode}
        open={addCell != null}
        onOpenChange={(open) => {
          if (!open) setAddCell(null);
        }}
        onConfirm={handleConfirmRealize}
        roomOptions={roomOptions}
        defaultNeighbor={defaultNeighbor}
      />
    </div>
  );
}
