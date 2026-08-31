/**
 * AddDialog (#3477 Task 5) — the Lattice's realize dialog: turns a planned
 * square into a real area or room. Copy rule: leads with the name field, no
 * heading ceremony (`DialogTitle` stays screen-reader-only), Cancel in the
 * footer, primary button reads "Add" — never "Make It Real".
 *
 * Areas mode hides the connection rows entirely (an area has no exits) and
 * hands back `{kind:'area', name}`; the caller (`Lattice`) dispatches
 * `create_area`. Rooms mode shows Entrance-from/Exit-to — each a room picker
 * + a free-text exit-name input, auto-filled from `defaultNeighbor` (the
 * plotted cell's one adjacent realized room, computed by `Lattice` from grid
 * position — `null` when the plot is free-standing) and independently
 * removable via ✕; both removed shows the free-standing note. This dialog
 * only *assembles* the payload — it never dispatches `staff_link_rooms`
 * itself, since the new room's id doesn't exist until the dig lands; the
 * caller resolves the link once the tile appears (see `Lattice.tsx`).
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface AddDialogRoomOption {
  id: number;
  name: string;
}

export interface AddDialogNeighbor {
  roomId: number;
  /** The word for the exit *from that neighbor into* the new room (Entrance-from default). */
  intoName: string;
  /** The word for the exit *from the new room out to* the neighbor (Exit-to default). */
  outName: string;
}

export interface AddDialogConnection {
  roomId: number;
  exitName: string;
}

export type AddDialogRealizePayload =
  | { kind: 'area'; name: string }
  | {
      kind: 'room';
      name: string;
      entrance: AddDialogConnection | null;
      exit: AddDialogConnection | null;
    };

export interface AddDialogProps {
  mode: 'areas' | 'rooms';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (payload: AddDialogRealizePayload) => void;
  /** Rooms mode only — pick targets for the connection rows. */
  roomOptions?: AddDialogRoomOption[];
  /** Rooms mode only — the plotted cell's one adjacent realized room, if any. */
  defaultNeighbor?: AddDialogNeighbor | null;
}

interface RowState {
  removed: boolean;
  roomId: number | null;
  exitName: string;
}

function initialRow(roomId: number | null, exitName: string): RowState {
  return { removed: roomId == null, roomId, exitName };
}

export function AddDialog({
  mode,
  open,
  onOpenChange,
  onConfirm,
  roomOptions = [],
  defaultNeighbor = null,
}: AddDialogProps) {
  const [name, setName] = useState('');
  const [entrance, setEntrance] = useState<RowState>(() =>
    initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.intoName ?? 'in')
  );
  const [exit, setExit] = useState<RowState>(() =>
    initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.outName ?? 'out')
  );

  useEffect(() => {
    if (!open) return;
    setName('');
    setEntrance(initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.intoName ?? 'in'));
    setExit(initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.outName ?? 'out'));
  }, [open, defaultNeighbor]);

  const canSubmit = name.trim() !== '';
  const freeStanding = mode === 'rooms' && entrance.removed && exit.removed;

  const submit = () => {
    const trimmedName = name.trim();
    if (mode === 'areas') {
      onConfirm({ kind: 'area', name: trimmedName });
    } else {
      const entranceConnection: AddDialogConnection | null =
        !entrance.removed && entrance.roomId != null
          ? { roomId: entrance.roomId, exitName: entrance.exitName.trim() || 'in' }
          : null;
      const exitConnection: AddDialogConnection | null =
        !exit.removed && exit.roomId != null
          ? { roomId: exit.roomId, exitName: exit.exitName.trim() || 'out' }
          : null;
      onConfirm({
        kind: 'room',
        name: trimmedName,
        entrance: entranceConnection,
        exit: exitConnection,
      });
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogTitle className="sr-only">{mode === 'areas' ? 'New area' : 'New room'}</DialogTitle>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-dialog-name">{mode === 'areas' ? 'Area name' : 'Room name'}</Label>
            <Input
              id="add-dialog-name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={mode === 'areas' ? 'The Grand Foyer' : 'The Wine Cellar'}
              data-testid="add-dialog-name"
            />
          </div>

          {mode === 'rooms' && (
            <>
              <ConnectionRow
                label="Entrance from"
                testId="entrance"
                row={entrance}
                setRow={setEntrance}
                roomOptions={roomOptions}
              />
              <ConnectionRow
                label="Exit to"
                testId="exit"
                row={exit}
                setRow={setExit}
                roomOptions={roomOptions}
              />
              {freeStanding && (
                <p
                  className="font-body text-xs italic text-muted-foreground"
                  data-testid="add-dialog-freestanding-note"
                >
                  free-standing — no way in or out yet; add exits later from this room or its
                  neighbors
                </p>
              )}
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="add-dialog-submit">
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ConnectionRowProps {
  label: string;
  testId: string;
  row: RowState;
  setRow: (updater: (prev: RowState) => RowState) => void;
  roomOptions: AddDialogRoomOption[];
}

function ConnectionRow({ label, testId, row, setRow, roomOptions }: ConnectionRowProps) {
  if (row.removed) {
    return (
      <p
        className="font-body text-xs italic text-muted-foreground"
        data-testid={`add-dialog-${testId}-removed`}
      >
        {label}: none
      </p>
    );
  }

  return (
    <div className="flex items-baseline gap-2" data-testid={`add-dialog-${testId}-row`}>
      <Label className="min-w-[6.5rem] shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </Label>
      <Select
        value={row.roomId != null ? String(row.roomId) : ''}
        onValueChange={(value) => setRow((prev) => ({ ...prev, roomId: Number(value) }))}
      >
        <SelectTrigger className="flex-1">
          <SelectValue placeholder="Pick a room" />
        </SelectTrigger>
        <SelectContent>
          {roomOptions.map((option) => (
            <SelectItem key={option.id} value={String(option.id)}>
              {option.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        value={row.exitName}
        onChange={(event) => setRow((prev) => ({ ...prev, exitName: event.target.value }))}
        placeholder="exit name"
        className="w-28"
        aria-label={`${label} exit name`}
        data-testid={`add-dialog-${testId}-name`}
      />
      <button
        type="button"
        className="px-1 text-muted-foreground hover:text-primary"
        aria-label={`remove ${label.toLowerCase()}`}
        title="remove — add one later from either room"
        onClick={() => setRow((prev) => ({ ...prev, removed: true }))}
        data-testid={`add-dialog-${testId}-remove`}
      >
        ✕
      </button>
    </div>
  );
}
