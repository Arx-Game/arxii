/**
 * Compass (#3477 Task 6) — the manuscript's "Where you stand" marginalia: a
 * 3×3 neighborhood centered on the open room, built from the area's room
 * list (the same `WorldBuilderRoom[]` `RoomDocument` already holds via
 * `useAreaManagerQuery`). A filled cell opens that neighbor's own document;
 * an empty cell's ⊕ opens `AddDialog` in the existing `'rooms'` cell mode
 * (Task 5 — the same realize dialog `Lattice` uses for its own plotted
 * squares), pre-wired to link back to the room you're standing in.
 *
 * The dig/link math (cardinal naming, the "a fated passage" fallback for a
 * diagonal neighbor) is `Lattice`'s own — imported, not re-derived, so the
 * two ⊕ affordances can never drift on what a diagonal neighbor's exit gets
 * called. What Compass does NOT share with `Lattice` is the pending-link
 * bookkeeping: `Lattice` tracks a whole plotted grid's worth of pending
 * digs keyed by cell, whereas Compass only ever has one dialog open against
 * one neighbor cell at a time, so a single `useRef` (not a `Map`) is enough
 * — the "realize, then resolve once the id shows up" pattern is identical
 * (neither `staff_dig_room` nor `staff_link_rooms` returns the new row's
 * id), just simpler here because there's only ever one in flight.
 *
 * The silent-no-op bug Dan caught in the prototype was a ⊕ that opened the
 * dialog but never actually linked anything back — the pending-link effect
 * below exists specifically to close that gap for real.
 */
import { useEffect, useRef, useState } from 'react';

import { Plate, PlateHead } from '@/components/folio';
import { cn } from '@/lib/utils';

import { AddDialog, type AddDialogRealizePayload } from '../atlas/AddDialog';
import { directionBetween, FANCIFUL_EXIT_NAME } from '../atlas/latticeState';
import type { WorldBuilderRoom } from '../types';

const COMPASS_OFFSETS: { dx: number; dy: number }[] = [
  { dx: -1, dy: 1 },
  { dx: 0, dy: 1 },
  { dx: 1, dy: 1 },
  { dx: -1, dy: 0 },
  { dx: 0, dy: 0 },
  { dx: 1, dy: 0 },
  { dx: -1, dy: -1 },
  { dx: 0, dy: -1 },
  { dx: 1, dy: -1 },
];

export interface CompassRoom {
  id: number;
  name: string;
  gridX: number | null;
  gridY: number | null;
  floor: number;
}

export interface CompassProps {
  areaId: number;
  currentRoom: CompassRoom;
  /** Every room in the current room's area (siblings) — from the area manager payload. */
  rooms: WorldBuilderRoom[];
  onOpenRoom: (roomId: number) => void;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

interface PendingLink {
  cellX: number;
  cellY: number;
  floor: number;
  name: string;
  entranceExitName: string;
  exitExitName: string;
}

function roomAt(rooms: WorldBuilderRoom[], x: number, y: number, floor: number) {
  return rooms.find((r) => r.grid_x === x && r.grid_y === y && r.floor === floor);
}

export function Compass({ areaId, currentRoom, rooms, onOpenRoom, runAction }: CompassProps) {
  const placed = currentRoom.gridX != null && currentRoom.gridY != null;
  const [addCell, setAddCell] = useState<{ x: number; y: number } | null>(null);

  const roomOptions = rooms
    .filter((r) => r.grid_x != null && r.grid_y != null)
    .map((r) => ({ id: r.id, name: r.name }));

  // Only one ⊕ dialog is ever open at a time here (unlike Lattice's whole
  // plotted grid), so a single ref slot — not a Map — is enough.
  const pendingRef = useRef<PendingLink | null>(null);

  useEffect(() => {
    const pending = pendingRef.current;
    if (!pending) return;
    const newRoom = roomAt(rooms, pending.cellX, pending.cellY, pending.floor);
    if (!newRoom) return;
    // Mirrors `Lattice`'s own pendingLinksRef resolution exactly (room_a is
    // the freshly dug room, room_b the room you were standing in) so the two
    // ⊕ affordances can never disagree on which side gets which exit name.
    runAction('staff_link_rooms', {
      room_a_id: newRoom.id,
      room_b_id: currentRoom.id,
      name_ab: pending.exitExitName,
      name_ba: pending.entranceExitName,
    });
    pendingRef.current = null;
  }, [rooms, currentRoom.id, runAction]);

  const handleConfirm = (payload: AddDialogRealizePayload) => {
    if (!addCell || payload.kind !== 'room') return;
    const { x, y } = addCell;
    runAction('staff_dig_room', {
      area_id: areaId,
      name: payload.name,
      floor: currentRoom.floor,
      grid_x: x,
      grid_y: y,
    });
    // Both connection rows always point back at the room you're standing in
    // (see `defaultNeighbor` below) — the exit/entrance names are all that
    // varies, so one pending entry captures both directions.
    const exitName = payload.exit?.exitName ?? payload.entrance?.exitName ?? FANCIFUL_EXIT_NAME;
    const entranceName = payload.entrance?.exitName ?? payload.exit?.exitName ?? FANCIFUL_EXIT_NAME;
    pendingRef.current = {
      cellX: x,
      cellY: y,
      floor: currentRoom.floor,
      name: payload.name,
      entranceExitName: entranceName,
      exitExitName: exitName,
    };
    setAddCell(null);
  };

  const defaultNeighbor = (() => {
    if (!addCell) return null;
    const toCurrent = directionBetween(
      { gridX: addCell.x, gridY: addCell.y },
      { gridX: currentRoom.gridX, gridY: currentRoom.gridY }
    );
    const outName = toCurrent?.name ?? FANCIFUL_EXIT_NAME;
    const intoName = toCurrent?.opposite ?? FANCIFUL_EXIT_NAME;
    return { roomId: currentRoom.id, intoName, outName };
  })();

  return (
    <Plate className="p-2" data-testid="compass">
      <PlateHead as="h4" className="mb-2">
        Where you stand
      </PlateHead>
      {!placed && (
        <p
          className="mb-2 font-body text-xs italic text-muted-foreground"
          data-testid="compass-unplaced-note"
        >
          this room isn't placed on the grid yet — place it to build around it
        </p>
      )}
      <div className="grid grid-cols-3 gap-0.5" data-testid="compass-grid">
        {COMPASS_OFFSETS.map(({ dx, dy }) => {
          if (dx === 0 && dy === 0) {
            return (
              <div
                key="here"
                className="theme-heading flex min-h-12 items-center justify-center border bg-accent px-1 text-center text-[0.7rem] [font-variant:small-caps]"
                data-testid="compass-here"
                aria-label="this room"
              >
                {currentRoom.name}
              </div>
            );
          }
          if (!placed) {
            return (
              <div
                key={`${dx},${dy}`}
                className="min-h-12 border border-dotted opacity-40"
                aria-hidden="true"
              />
            );
          }
          const x = currentRoom.gridX! + dx;
          const y = currentRoom.gridY! + dy;
          const neighbor = roomAt(rooms, x, y, currentRoom.floor);
          if (neighbor) {
            return (
              <button
                key={`${dx},${dy}`}
                type="button"
                className={cn(
                  'min-h-12 border px-1 text-center text-[0.7rem] hover:bg-accent',
                  !neighbor.published_at && 'border-dashed text-muted-foreground'
                )}
                onClick={() => onOpenRoom(neighbor.id)}
                data-testid={`compass-neighbor-${neighbor.id}`}
              >
                {neighbor.name}
              </button>
            );
          }
          return (
            <button
              key={`${dx},${dy}`}
              type="button"
              className="min-h-12 border border-dotted text-muted-foreground hover:text-primary"
              aria-label="build a neighboring room here"
              onClick={() => setAddCell({ x, y })}
              data-testid={`compass-add-${x}-${y}`}
            >
              ⊕
            </button>
          );
        })}
      </div>

      <AddDialog
        mode="rooms"
        open={addCell != null}
        onOpenChange={(open) => {
          if (!open) setAddCell(null);
        }}
        onConfirm={handleConfirm}
        roomOptions={roomOptions}
        defaultNeighbor={defaultNeighbor}
      />
    </Plate>
  );
}
