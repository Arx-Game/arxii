/**
 * RoomDetailPanel (staff variant) — the selected room's editor in the
 * world-builder canvas (#2449): identity/flags via `staff_edit_room`,
 * fixture-key/origin display, promotion, exits (rename/unlink), and removal.
 *
 * Distinct from buildings' `RoomDetailPanel`
 * (`@/buildings/components/RoomDetailPanel`) — no ownership/tenancy/comfort
 * sections (this is staff tooling over the shared map, not a player's
 * building), and it surfaces fields buildings never show (`fixture_key`,
 * `origin`, `occupant_count`). The link-rooms flow lives in a separate
 * `LinkRoomsDialog` (cross-area picker) rather than inline, unlike buildings'
 * same-building-only inline form.
 */
import { useEffect, useState } from 'react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

import { ROOM_ENCLOSURES } from '../types';
import type { WorldBuilderActionKey, WorldBuilderExit, WorldBuilderRoom } from '../types';

export interface RoomDetailPanelProps {
  room: WorldBuilderRoom;
  /** Every exit in the area; the panel filters to this room's outgoing ones. */
  exits: WorldBuilderExit[];
  runAction: (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => void;
  onLinkRooms: () => void;
}

export function RoomDetailPanel({ room, exits, runAction, onLinkRooms }: RoomDetailPanelProps) {
  const [name, setName] = useState(room.name);
  const [description, setDescription] = useState(room.description);
  const [isPublic, setIsPublic] = useState(room.is_public);
  const [isSocialHub, setIsSocialHub] = useState(room.is_social_hub);
  const [isOutdoor, setIsOutdoor] = useState(room.is_outdoor);
  const [enclosure, setEnclosure] = useState(room.enclosure);
  const [renames, setRenames] = useState<Record<number, string>>({});

  useEffect(() => {
    setName(room.name);
    setDescription(room.description);
    setIsPublic(room.is_public);
    setIsSocialHub(room.is_social_hub);
    setIsOutdoor(room.is_outdoor);
    setEnclosure(room.enclosure);
    setRenames({});
  }, [
    room.id,
    room.name,
    room.description,
    room.is_public,
    room.is_social_hub,
    room.is_outdoor,
    room.enclosure,
  ]);

  const dirty =
    name !== room.name ||
    description !== room.description ||
    isPublic !== room.is_public ||
    isSocialHub !== room.is_social_hub ||
    isOutdoor !== room.is_outdoor ||
    enclosure !== room.enclosure;

  const saveChanges = () => {
    const kwargs: Record<string, unknown> = { room_id: room.id };
    if (name !== room.name) kwargs.name = name;
    if (description !== room.description) kwargs.description = description;
    if (isPublic !== room.is_public) kwargs.is_public = isPublic;
    if (isSocialHub !== room.is_social_hub) kwargs.is_social_hub = isSocialHub;
    if (isOutdoor !== room.is_outdoor) kwargs.is_outdoor = isOutdoor;
    if (enclosure !== room.enclosure) kwargs.enclosure = enclosure;
    runAction('staff_edit_room', kwargs);
  };

  const myExits = exits.filter((exit) => exit.from_room_id === room.id);

  return (
    <div className="flex flex-col gap-4" data-testid="room-detail-panel">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="truncate text-base font-semibold">{room.name}</h3>
          <Badge variant={room.origin === 'authored' ? 'default' : 'secondary'}>
            {room.origin}
          </Badge>
        </div>
        {room.fixture_key && (
          <p className="text-xs text-muted-foreground">
            Fixture key: <code>{room.fixture_key}</code>
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {room.occupant_count} {room.occupant_count === 1 ? 'character' : 'characters'} present
        </p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="world-room-name">Name</Label>
          <Input
            id="world-room-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="world-room-description">Description</Label>
          <Textarea
            id="world-room-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="world-room-public">Publicly listed</Label>
          <Switch id="world-room-public" checked={isPublic} onCheckedChange={setIsPublic} />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="world-room-social-hub">Social hub</Label>
          <Switch
            id="world-room-social-hub"
            checked={isSocialHub}
            onCheckedChange={setIsSocialHub}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="world-room-outdoor">Outdoor</Label>
          <Switch id="world-room-outdoor" checked={isOutdoor} onCheckedChange={setIsOutdoor} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="world-room-enclosure">Enclosure</Label>
          <Select value={enclosure} onValueChange={setEnclosure}>
            <SelectTrigger id="world-room-enclosure">
              <SelectValue placeholder="Pick an enclosure" />
            </SelectTrigger>
            <SelectContent>
              {ROOM_ENCLOSURES.map((choice) => (
                <SelectItem key={choice.value} value={choice.value}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button size="sm" onClick={saveChanges} disabled={!dirty}>
          Save changes
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">Exits</h4>
        {myExits.length === 0 && <p className="text-xs text-muted-foreground">No exits yet.</p>}
        {myExits.map((exit) => {
          const pending = renames[exit.id] ?? exit.name;
          return (
            <div key={exit.id} className="flex items-center gap-1.5">
              <Input
                value={pending}
                onChange={(event) =>
                  setRenames((prev) => ({ ...prev, [exit.id]: event.target.value }))
                }
                className="h-8 flex-1"
              />
              <span className="whitespace-nowrap text-xs text-muted-foreground">
                → {exit.to_room_name ?? 'elsewhere'}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={pending.trim() === exit.name || !pending.trim()}
                onClick={() =>
                  runAction('staff_rename_exit', { exit_id: exit.id, name: pending.trim() })
                }
              >
                Rename
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => runAction('staff_unlink_rooms', { exit_id: exit.id })}
              >
                ✕
              </Button>
            </div>
          );
        })}
        <Button size="sm" variant="outline" onClick={onLinkRooms}>
          Link to another room
        </Button>
      </div>

      <div className="flex flex-col gap-2 rounded-md border p-2">
        <h4 className="text-sm font-semibold">Promote</h4>
        <p className="text-xs text-muted-foreground">
          Stamps a permanent fixture key and marks this room AUTHORED for export.
        </p>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="sm" variant="outline" disabled={room.origin === 'authored'}>
              Promote {room.name}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Promote {room.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                This stamps a permanent fixture key and marks the room AUTHORED — it will export to
                the lore repo. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => runAction('promote_room', { room_id: room.id })}>
                Promote
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-destructive/40 p-2">
        <h4 className="text-sm font-semibold text-destructive">Remove room</h4>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm">
              Remove {room.name}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove {room.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                Refused if the room has any contents, an installed feature, or is already exported —
                empty or unexport it first.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => runAction('staff_remove_room', { room_id: room.id })}
              >
                Remove it
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
