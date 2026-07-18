/**
 * LinkRoomsDialog — link the selected room to another world room (#2449),
 * same area (a combobox over the current area's manager payload — no extra
 * fetch) or a different one (an area picker + a second combobox that fetches
 * that area's manager payload for its room list).
 *
 * The area picker fetches page 1 of `/api/world-builder/areas/` (unfiltered,
 * no search param on that endpoint) — a known cap for very large area counts,
 * acceptable for this slice; see task-6 report.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useAreaManagerQuery, useWorldBuilderAreasQuery } from '../queries';
import type { WorldBuilderRoom } from '../types';

export interface LinkRoomsDialogProps {
  fromRoom: WorldBuilderRoom;
  /** Every other room in the current area, for the same-area combobox. */
  sameAreaRooms: WorldBuilderRoom[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keyed generically (not `WorldBuilderActionKey`) so the story palette's own action-key union type-checks too (#2450). */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
  /**
   * `'story'` (#2450) hides the cross-area picker (story rooms only link
   * within the GM's currently selected story area in this slice — the
   * `story_link_rooms` action itself does allow linking across a GM's own
   * story areas, but this dialog doesn't expose that yet, same call as
   * skipping the staff-only area-picker data source here) and dispatches
   * `story_link_rooms` with `name`/`reverse_name` kwargs instead of
   * `staff_link_rooms`'s `name_ab`/`name_ba`. Defaults to `'staff'`.
   */
  palette?: 'staff' | 'story';
}

export function LinkRoomsDialog({
  fromRoom,
  sameAreaRooms,
  open,
  onOpenChange,
  runAction,
  palette = 'staff',
}: LinkRoomsDialogProps) {
  const isStory = palette === 'story';
  const [crossArea, setCrossArea] = useState(false);
  const [pickedAreaId, setPickedAreaId] = useState('');
  const [targetRoomId, setTargetRoomId] = useState('');
  const [nameAB, setNameAB] = useState('');
  const [nameBA, setNameBA] = useState('');

  const { data: areasData } = useWorldBuilderAreasQuery({}, !isStory && crossArea);
  const areaOptions = areasData?.results ?? [];
  const crossAreaId = !isStory && crossArea && pickedAreaId ? Number(pickedAreaId) : null;
  const { data: crossManager } = useAreaManagerQuery(crossAreaId);

  const targetOptions =
    !isStory && crossArea
      ? (crossManager?.rooms ?? []).map((room) => ({ value: String(room.id), label: room.name }))
      : sameAreaRooms.map((room) => ({ value: String(room.id), label: room.name }));

  const canSubmit = targetRoomId !== '' && nameAB.trim() !== '' && nameBA.trim() !== '';

  const reset = () => {
    setCrossArea(false);
    setPickedAreaId('');
    setTargetRoomId('');
    setNameAB('');
    setNameBA('');
  };

  const submit = () => {
    const kwargs: Record<string, unknown> = isStory
      ? {
          room_a_id: fromRoom.id,
          room_b_id: Number(targetRoomId),
          name: nameAB.trim(),
          reverse_name: nameBA.trim(),
        }
      : {
          room_a_id: fromRoom.id,
          room_b_id: Number(targetRoomId),
          name_ab: nameAB.trim(),
          name_ba: nameBA.trim(),
        };
    runAction(isStory ? 'story_link_rooms' : 'staff_link_rooms', kwargs);
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Link {fromRoom.name} to another room</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {!isStory && (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant={crossArea ? 'outline' : 'default'}
                onClick={() => {
                  setCrossArea(false);
                  setTargetRoomId('');
                }}
              >
                This area
              </Button>
              <Button
                type="button"
                size="sm"
                variant={crossArea ? 'default' : 'outline'}
                onClick={() => {
                  setCrossArea(true);
                  setTargetRoomId('');
                }}
                data-testid="link-rooms-cross-area-toggle"
              >
                Another area
              </Button>
            </div>
          )}
          {!isStory && crossArea && (
            <div className="flex flex-col gap-1.5">
              <Label>Area</Label>
              <Combobox
                items={areaOptions.map((area) => ({ value: String(area.id), label: area.name }))}
                value={pickedAreaId}
                onValueChange={(value) => {
                  setPickedAreaId(value);
                  setTargetRoomId('');
                }}
                placeholder="Pick an area"
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label>Room</Label>
            <Combobox
              items={targetOptions}
              value={targetRoomId}
              onValueChange={setTargetRoomId}
              placeholder="Pick a room"
              disabled={crossArea && !pickedAreaId}
            />
          </div>
          <Input
            value={nameAB}
            onChange={(event) => setNameAB(event.target.value)}
            placeholder="Exit name from here"
          />
          <Input
            value={nameBA}
            onChange={(event) => setNameBA(event.target.value)}
            placeholder="Exit name coming back"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="link-rooms-submit">
            Link rooms
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
