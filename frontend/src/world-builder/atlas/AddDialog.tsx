/**
 * AddDialog (#3477 Task 5, exit mode added Task 6) — the Lattice's realize
 * dialog: turns a planned square into a real area or room. Copy rule: leads
 * with the name field, no heading ceremony (`DialogTitle` stays
 * screen-reader-only), Cancel in the footer, primary button reads "Add" —
 * never "Make It Real" (areas/rooms modes) or "Link it"/"Dig it" (exit mode).
 *
 * Areas mode asks what the square becomes (2026-09-09, the reviewer plotting
 * Arx: the city center is an open-air room of its neighborhood, and buildings
 * stand beside it, so a map above BUILDING holds both): an area at any level
 * that fits under this one (`areaLevelOptions`, the next level down first) or
 * a room right here. An area hands back `{kind:'area', name, level, entrance}`
 * — `entrance` names the room on this map it opens from, the exit words each
 * way and the new area's first room, so a building gets its door the moment
 * it exists; the caller (`Lattice`) dispatches `create_area` and chains the
 * dig and the link. A room here takes rooms mode's shape below. Rooms mode
 * shows Entrance-from/Exit-to — each a room picker
 * + a free-text exit-name input, auto-filled from `defaultNeighbor` (the
 * plotted cell's one adjacent realized room, computed by `Lattice` from grid
 * position — `null` when the plot is free-standing) and independently
 * removable via ✕; both removed shows the free-standing note. This dialog
 * only *assembles* the payload — it never dispatches `staff_link_rooms`
 * itself, since the new room's id doesn't exist until the dig lands; the
 * caller resolves the link once the tile appears (see `Lattice.tsx`).
 *
 * Rooms mode has the same implicit fork for a room that already exists in this
 * area but sits nowhere on the grid (dug from an exit, or seeded): typing its
 * name exactly (case-insensitively, against `unplacedOptions`) means "place that
 * room on this square" — the caller dispatches `staff_place_room`; any other
 * name digs a new room. Before this the only way onto the grid was a fresh dig,
 * so an unplaced room could never be placed from the Atlas at all.
 *
 * Exit mode (#3477 Task 6, `RoomDocument`'s "⊕ dig or link an exit…") is the
 * prototype's implicit dig/link fork: one "Leads to" field, no mode toggle to
 * pre-answer it. Typing a name that exactly matches one of `roomOptions`
 * (case-insensitive) means "link to that room" — the caller dispatches
 * `staff_link_rooms`; any other text means "dig a new room by that name" —
 * the caller dispatches `staff_dig_room` (unplaced, same pattern as
 * `Lattice`'s own dig-then-link-when-the-id-appears flow, since neither
 * action returns the new row's id). This dialog only computes which fork
 * applies (`matchedRoomId`) and hands back the raw field values — it never
 * dispatches anything itself, matching the other two modes' contract.
 */
import { useEffect, useRef, useState } from 'react';

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

export interface AddDialogAreaEntrance {
  /** The room on this map the new area opens from. */
  roomId: number;
  /** The exit word from that room into the new area's first room. */
  exitName: string;
  /** The exit word back out. */
  exitBack: string;
  /** The new area's first room, dug at its origin and linked to `roomId`. */
  firstRoomName: string;
}

export interface AddDialogLevelOption {
  value: number;
  label: string;
}

export type AddDialogRealizePayload =
  | {
      kind: 'area';
      name: string;
      /** The chosen level; absent when the caller offered no `areaLevelOptions` (its default applies). */
      level?: number;
      entrance: AddDialogAreaEntrance | null;
    }
  | {
      kind: 'room';
      name: string;
      /** Set when `name` exactly (case-insensitively) matched an `unplacedOptions` entry: place it, don't dig. */
      matchedRoomId: number | null;
      entrance: AddDialogConnection | null;
      exit: AddDialogConnection | null;
    }
  | {
      kind: 'exit';
      /** The typed "Leads to" name — the dig name when `matchedRoomId` is null. */
      name: string;
      /** Set when `name` exactly (case-insensitively) matched a `roomOptions` entry. */
      matchedRoomId: number | null;
      exitThere: string;
      exitBack: string;
    };

/**
 * The per-mode copy. Three separate ternary chains used to spell this out one
 * string at a time; keeping the variants together means you can read all of a
 * mode's wording in one place, and adding a mode is one entry rather than three
 * edits scattered through the JSX.
 */
const MODE_COPY: Record<
  AddDialogProps['mode'],
  { title: string; nameLabel: string; placeholder: string }
> = {
  areas: {
    title: 'New area',
    nameLabel: 'Area name',
    placeholder: 'The Grand Foyer',
  },
  exit: {
    title: 'New exit',
    nameLabel: 'Leads to',
    placeholder: 'name the room — existing rooms match as you type',
  },
  rooms: {
    title: 'New room',
    nameLabel: 'Room name',
    placeholder: 'The Wine Cellar',
  },
};

export interface AddDialogProps {
  mode: 'areas' | 'rooms' | 'exit';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (payload: AddDialogRealizePayload) => void;
  /** Rooms mode: pick targets for the connection rows. Exit mode: the dig/link match pool. */
  roomOptions?: AddDialogRoomOption[];
  /** Areas mode: the label of the level a plotted square becomes ("Ward"), so the dialog says which it is. */
  childLevelLabel?: string;
  /**
   * Areas mode: every level a plotted square may become, the default first.
   * With this set the dialog also offers "a room here" (rooms sit at any level).
   */
  areaLevelOptions?: AddDialogLevelOption[];
  /** Rooms mode: this area's rooms with no grid position yet — a name match places one instead of digging. */
  unplacedOptions?: AddDialogRoomOption[];
  /** Rooms mode only — the plotted cell's one adjacent realized room, if any. */
  defaultNeighbor?: AddDialogNeighbor | null;
  /** Exit mode only — fires as "Leads to" changes, so the caller can live-search room names. */
  onDestinationInput?: (value: string) => void;
}

/** What the exit field is about to do, in the player's terms. */
function exitNote(trimmedDestination: string, matched: AddDialogRoomOption | null): string {
  if (trimmedDestination === '') return 'name the room this exit leads to';
  if (matched) return 'joins two rooms that already exist — nothing new is made';
  return 'dug as a placeholder for the writing pass — you stay here';
}

/** Exit mode forks on whether the destination already exists; a room square on an unplaced match; areas just add. */
function submitLabel(
  mode: AddDialogProps['mode'],
  matched: AddDialogRoomOption | null,
  matchedUnplaced: AddDialogRoomOption | null = null
): string {
  if (mode === 'rooms') return matchedUnplaced ? 'Place' : 'Add';
  if (mode !== 'exit') return 'Add';
  return matched ? 'Link it' : 'Dig it';
}

/** The value the "This square becomes" select uses for a room, beside the numeric area levels. */
const ROOM_HERE = 'room';

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
  unplacedOptions = [],
  childLevelLabel,
  areaLevelOptions = [],
  defaultNeighbor = null,
  onDestinationInput,
}: AddDialogProps) {
  const [name, setName] = useState('');
  // Areas mode's fork: which level the square becomes, or a room right here.
  const [becomes, setBecomes] = useState<string>(
    areaLevelOptions[0] ? String(areaLevelOptions[0].value) : ''
  );
  const [areaEntrance, setAreaEntrance] = useState<RowState>(() =>
    initialRow(defaultNeighbor?.roomId ?? null, '')
  );
  const [areaExitBack, setAreaExitBack] = useState('out');
  const [firstRoomName, setFirstRoomName] = useState('Entry');
  const [entrance, setEntrance] = useState<RowState>(() =>
    initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.intoName ?? 'in')
  );
  const [exit, setExit] = useState<RowState>(() =>
    initialRow(defaultNeighbor?.roomId ?? null, defaultNeighbor?.outName ?? 'out')
  );
  const [exitThere, setExitThere] = useState('');
  const [exitBack, setExitBack] = useState('');

  // Reset ONLY on the closed→open transition. `defaultNeighbor` is read
  // through a ref because both callers rebuild it every render — with it in
  // the deps, a background refetch re-rendering the parent while the dialog
  // is open would wipe whatever the user has half-typed (review finding,
  // #3477 fix round 2).
  const defaultNeighborRef = useRef(defaultNeighbor);
  defaultNeighborRef.current = defaultNeighbor;
  const areaLevelOptionsRef = useRef(areaLevelOptions);
  areaLevelOptionsRef.current = areaLevelOptions;
  useEffect(() => {
    if (!open) return;
    const neighbor = defaultNeighborRef.current;
    const firstLevel = areaLevelOptionsRef.current[0];
    setName('');
    setEntrance(initialRow(neighbor?.roomId ?? null, neighbor?.intoName ?? 'in'));
    setExit(initialRow(neighbor?.roomId ?? null, neighbor?.outName ?? 'out'));
    setExitThere('');
    setExitBack('');
    setBecomes(firstLevel ? String(firstLevel.value) : '');
    setAreaEntrance(initialRow(neighbor?.roomId ?? null, ''));
    setAreaExitBack('out');
    setFirstRoomName('Entry');
  }, [open]);

  const offersFork = mode === 'areas' && areaLevelOptions.length > 0;
  const chosenLevel = offersFork && becomes !== ROOM_HERE ? Number(becomes) : null;
  const chosenLevelLabel =
    areaLevelOptions.find((choice) => choice.value === chosenLevel)?.label ?? childLevelLabel;
  /** Rooms mode, or an areas-mode square that becomes a room: the dig shape. */
  const roomShape = mode === 'rooms' || (offersFork && becomes === ROOM_HERE);
  /** An areas-mode square that becomes an area, with rooms on this map to open from. */
  const areaEntranceOffered = mode === 'areas' && !roomShape && roomOptions.length > 0;

  const canSubmit =
    mode === 'exit' ? name.trim() !== '' && exitThere.trim() !== '' : name.trim() !== '';
  const freeStanding = roomShape && entrance.removed && exit.removed;

  // Exit mode's implicit fork — an exact (case-insensitive) name match means
  // "link to that room," anything else means "dig a new one by that name."
  const trimmedDestination = name.trim();
  const matched =
    mode === 'exit'
      ? (roomOptions.find(
          (option) => option.name.toLowerCase() === trimmedDestination.toLowerCase()
        ) ?? null)
      : null;
  const suggestions =
    mode === 'exit' && trimmedDestination !== ''
      ? roomOptions
          .filter((option) => option.name.toLowerCase().includes(trimmedDestination.toLowerCase()))
          .slice(0, 4)
      : [];

  // Rooms mode's fork — a name that exactly matches an unplaced room of this
  // area means "place that room here," anything else means "dig a new one."
  const matchedUnplaced = roomShape
    ? (unplacedOptions.find(
        (option) => option.name.toLowerCase() === trimmedDestination.toLowerCase()
      ) ?? null)
    : null;
  const unplacedSuggestions =
    roomShape && trimmedDestination !== ''
      ? unplacedOptions
          .filter((option) => option.name.toLowerCase().includes(trimmedDestination.toLowerCase()))
          .slice(0, 4)
      : [];

  const submit = () => {
    const trimmedName = name.trim();
    if (mode === 'areas' && !roomShape) {
      const entranceFrom: AddDialogAreaEntrance | null =
        areaEntranceOffered && !areaEntrance.removed && areaEntrance.roomId != null
          ? {
              roomId: areaEntrance.roomId,
              // The way in is named after the place by default: "Sleepers Chambers".
              exitName: areaEntrance.exitName.trim() || trimmedName,
              exitBack: areaExitBack.trim() || 'out',
              firstRoomName: firstRoomName.trim() || 'Entry',
            }
          : null;
      onConfirm({
        kind: 'area',
        name: trimmedName,
        ...(chosenLevel != null ? { level: chosenLevel } : {}),
        entrance: entranceFrom,
      });
    } else if (mode === 'exit') {
      onConfirm({
        kind: 'exit',
        name: trimmedName,
        matchedRoomId: matched?.id ?? null,
        exitThere: exitThere.trim(),
        exitBack: exitBack.trim(),
      });
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
        matchedRoomId: matchedUnplaced?.id ?? null,
        entrance: entranceConnection,
        exit: exitConnection,
      });
    }
    onOpenChange(false);
  };

  let copy = MODE_COPY[mode];
  if (roomShape && mode === 'areas') {
    copy = { ...MODE_COPY.rooms, placeholder: 'The City Center' };
  } else if (mode === 'areas' && chosenLevelLabel) {
    copy = {
      title: `New ${chosenLevelLabel.toLowerCase()}`,
      nameLabel: `${chosenLevelLabel} name`,
      placeholder: MODE_COPY.areas.placeholder,
    };
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogTitle className="sr-only">{copy.title}</DialogTitle>
        <div className="flex flex-col gap-3">
          {offersFork && (
            <div className="flex items-baseline gap-2" data-testid="add-dialog-becomes-row">
              <Label className="min-w-[6.5rem] shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
                This square is
              </Label>
              <Select value={becomes} onValueChange={setBecomes}>
                <SelectTrigger className="flex-1" data-testid="add-dialog-becomes">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {areaLevelOptions.map((choice) => (
                    <SelectItem key={choice.value} value={String(choice.value)}>
                      a {choice.label.toLowerCase()}
                    </SelectItem>
                  ))}
                  <SelectItem value={ROOM_HERE}>a room here (open air)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-dialog-name">{copy.nameLabel}</Label>
            <Input
              id="add-dialog-name"
              autoFocus
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (mode === 'exit') onDestinationInput?.(event.target.value);
              }}
              placeholder={copy.placeholder}
              autoComplete="off"
              data-testid="add-dialog-name"
            />
          </div>

          {mode === 'exit' && suggestions.length > 0 && (
            <div className="grid gap-1" data-testid="add-dialog-exit-suggestions">
              {suggestions.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className="text-left text-sm text-muted-foreground hover:text-primary"
                  onClick={() => setName(option.name)}
                  data-testid="add-dialog-exit-suggestion"
                >
                  ⇢ link to {option.name}
                </button>
              ))}
            </div>
          )}

          {mode === 'exit' && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="add-dialog-exit-there">Exit there</Label>
                <Input
                  id="add-dialog-exit-there"
                  value={exitThere}
                  onChange={(event) => setExitThere(event.target.value)}
                  placeholder="west"
                  data-testid="add-dialog-exit-there"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="add-dialog-exit-back">Exit back</Label>
                <Input
                  id="add-dialog-exit-back"
                  value={exitBack}
                  onChange={(event) => setExitBack(event.target.value)}
                  placeholder="east"
                  data-testid="add-dialog-exit-back"
                />
              </div>
              <p
                className="font-body text-xs italic text-muted-foreground"
                data-testid="add-dialog-exit-note"
              >
                {exitNote(trimmedDestination, matched)}
              </p>
            </>
          )}

          {areaEntranceOffered && (
            <>
              <ConnectionRow
                label="Entrance from"
                testId="area-entrance"
                row={areaEntrance}
                setRow={setAreaEntrance}
                roomOptions={roomOptions}
                exitNamePlaceholder={name.trim() || 'its name'}
              />
              {!areaEntrance.removed && (
                <div className="flex items-baseline gap-2" data-testid="add-dialog-area-door-row">
                  <Label className="min-w-[6.5rem] shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
                    First room
                  </Label>
                  <Input
                    value={firstRoomName}
                    onChange={(event) => setFirstRoomName(event.target.value)}
                    className="flex-1"
                    aria-label="First room name"
                    data-testid="add-dialog-first-room"
                  />
                  <Input
                    value={areaExitBack}
                    onChange={(event) => setAreaExitBack(event.target.value)}
                    placeholder="out"
                    className="w-28"
                    aria-label="Exit back name"
                    data-testid="add-dialog-area-exit-back"
                  />
                </div>
              )}
              {!areaEntrance.removed && areaEntrance.roomId != null && (
                <p
                  className="font-body text-xs italic text-muted-foreground"
                  data-testid="add-dialog-area-entrance-note"
                >
                  its first room is dug at its origin and linked from{' '}
                  {roomOptions.find((option) => option.id === areaEntrance.roomId)?.name ??
                    'that room'}
                  ; the rest of its map is plotted from inside
                </p>
              )}
            </>
          )}

          {roomShape && unplacedSuggestions.length > 0 && (
            <div className="grid gap-1" data-testid="add-dialog-place-suggestions">
              {unplacedSuggestions.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className="text-left text-sm text-muted-foreground hover:text-primary"
                  onClick={() => setName(option.name)}
                  data-testid="add-dialog-place-suggestion"
                >
                  ⌖ place {option.name} here
                </button>
              ))}
            </div>
          )}

          {roomShape && (
            <>
              {matchedUnplaced && (
                <p
                  className="font-body text-xs italic text-muted-foreground"
                  data-testid="add-dialog-place-note"
                >
                  {matchedUnplaced.name} already exists here without a place on the grid; Add puts
                  it on this square instead of digging another
                </p>
              )}
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
            {submitLabel(mode, matched, matchedUnplaced)}
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
  exitNamePlaceholder?: string;
}

function ConnectionRow({
  label,
  testId,
  row,
  setRow,
  roomOptions,
  exitNamePlaceholder = 'exit name',
}: ConnectionRowProps) {
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
        placeholder={exitNamePlaceholder}
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
