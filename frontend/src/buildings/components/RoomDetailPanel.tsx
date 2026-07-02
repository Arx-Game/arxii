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
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
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

import type { ManagerExit, ManagerRoom, RoomBuilderActionKey, RoomSizeTier } from '../types';
import { ComfortSection } from './ComfortSection';
import { TenantSection } from './TenantSection';

interface RoomDetailPanelProps {
  room: ManagerRoom;
  /** The active puppet's ObjectDB pk (comfort HUD read context). */
  characterId: number;
  /** Every room in the building (for the link-to picker). */
  rooms: ManagerRoom[];
  /** Every exit in the building; the panel filters to this room's. */
  exits: ManagerExit[];
  sizeTiers: RoomSizeTier[];
  isEntry: boolean;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
  onDigFrom: () => void;
  onDuplicate: () => void;
  onDecorateRoom: () => void;
}

/**
 * The selected room's editor: identity (name/desc/privacy), size, exits,
 * tenants, decoration, removal. Every verb is a small targeted dispatch —
 * the shipped only-supplied-fields semantics, never a monster form.
 */
export function RoomDetailPanel({
  room,
  characterId,
  rooms,
  exits,
  sizeTiers,
  isEntry,
  runAction,
  onDigFrom,
  onDuplicate,
  onDecorateRoom,
}: RoomDetailPanelProps) {
  const [name, setName] = useState(room.name);
  const [description, setDescription] = useState(room.description);
  const [isPublic, setIsPublic] = useState(room.is_public);
  const [linkTarget, setLinkTarget] = useState('');
  const [linkThere, setLinkThere] = useState('');
  const [linkBack, setLinkBack] = useState('');
  const [renames, setRenames] = useState<Record<number, string>>({});

  useEffect(() => {
    setName(room.name);
    setDescription(room.description);
    setIsPublic(room.is_public);
    setRenames({});
  }, [room.id, room.name, room.description, room.is_public]);

  const dirty =
    name !== room.name || description !== room.description || isPublic !== room.is_public;

  const saveIdentity = () => {
    const kwargs: Record<string, unknown> = { room_id: room.id };
    if (name !== room.name) kwargs.name = name;
    if (description !== room.description) kwargs.description = description;
    if (isPublic !== room.is_public) kwargs.is_public = isPublic;
    runAction('edit_room', kwargs);
  };

  const myExits = exits.filter((exit) => exit.from_room_id === room.id);
  const linkableRooms = rooms.filter((other) => other.id !== room.id);

  const submitLink = () => {
    if (!linkTarget || !linkThere.trim() || !linkBack.trim()) return;
    runAction('link_rooms', {
      room_id: room.id,
      to_room_id: Number(linkTarget),
      name_there: linkThere.trim(),
      name_back: linkBack.trim(),
    });
    setLinkTarget('');
    setLinkThere('');
    setLinkBack('');
  };

  return (
    <div className="flex flex-col gap-4" data-testid="room-detail-panel">
      <div className="flex flex-col gap-2">
        <h3 className="text-base font-semibold">{room.name}</h3>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="room-name">Name</Label>
          <Input id="room-name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="room-description">Description</Label>
          <Textarea
            id="room-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="room-public">Publicly listed</Label>
          <Switch id="room-public" checked={isPublic} onCheckedChange={setIsPublic} />
        </div>
        <Button size="sm" onClick={saveIdentity} disabled={!dirty}>
          Save changes
        </Button>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="room-size">Size</Label>
        <Select
          value={room.size_name ?? ''}
          onValueChange={(value) => runAction('resize_room', { room_id: room.id, size: value })}
        >
          <SelectTrigger id="room-size">
            <SelectValue placeholder="Pick a size" />
          </SelectTrigger>
          <SelectContent>
            {sizeTiers.map((tier) => (
              <SelectItem key={tier.id} value={tier.name}>
                {tier.name} ({tier.units} units)
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onDigFrom}>
          Dig from here
        </Button>
        <Button size="sm" variant="outline" onClick={onDuplicate}>
          Duplicate
        </Button>
        <Button size="sm" variant="outline" onClick={onDecorateRoom}>
          Decorate room
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">Exits</h4>
        {myExits.length === 0 && <p className="text-xs text-muted-foreground">No exits yet.</p>}
        {myExits.map((exit) => {
          const targetName = rooms.find((other) => other.id === exit.to_room_id)?.name ?? '?';
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
                → {targetName}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={pending.trim() === exit.name || !pending.trim()}
                onClick={() =>
                  runAction('rename_exit', {
                    room_id: room.id,
                    exit_id: exit.id,
                    name: pending.trim(),
                  })
                }
              >
                Rename
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => runAction('unlink_rooms', { room_id: room.id, exit_id: exit.id })}
              >
                ✕
              </Button>
            </div>
          );
        })}
        <div className="flex flex-col gap-1.5 rounded-md border p-2">
          <Label>Link to another room</Label>
          <Combobox
            items={linkableRooms.map((other) => ({
              value: String(other.id),
              label: other.name,
            }))}
            value={linkTarget}
            onValueChange={setLinkTarget}
            placeholder="Pick a room"
          />
          <Input
            value={linkThere}
            onChange={(event) => setLinkThere(event.target.value)}
            placeholder="Exit name from here"
            className="h-8"
          />
          <Input
            value={linkBack}
            onChange={(event) => setLinkBack(event.target.value)}
            placeholder="Exit name coming back"
            className="h-8"
          />
          <Button
            size="sm"
            variant="outline"
            onClick={submitLink}
            disabled={!linkTarget || !linkThere.trim() || !linkBack.trim()}
          >
            Link rooms
          </Button>
        </div>
      </div>

      <ComfortSection roomId={room.id} characterId={characterId} runAction={runAction} />

      <TenantSection room={room} runAction={runAction} />

      <div className="flex flex-col gap-2 rounded-md border border-destructive/40 p-2">
        <h4 className="text-sm font-semibold text-destructive">Remove room</h4>
        {isEntry ? (
          <p className="text-xs text-muted-foreground">
            The entry room can&apos;t be removed — it&apos;s the building&apos;s way in.
          </p>
        ) : (
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
                  Tenancies end, everyone and everything moves to the entry room, its exits are
                  deleted, and its space returns to the budget. If removal would cut rooms off, it
                  is refused and the stranded rooms are named.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => runAction('remove_room', { room_id: room.id })}>
                  Remove it
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </div>
  );
}
