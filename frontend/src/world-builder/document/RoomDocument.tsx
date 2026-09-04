/**
 * RoomDocument (#3477 Task 6) — the Commonplace Atlas's room manuscript:
 * full-width name + description (drafted locally via `useDraft`, published
 * data only ever changes on Save/Publish), the `VariantsPanel` fold, the
 * exits band (chips + the exit-mode `AddDialog`), `Compass` ("where you
 * stand"), always-visible `Marginalia`, and the savebar (Save/Publish/Next
 * unpublished/delete).
 *
 * Split into an outer loading gate (`RoomDocument`) and an inner body
 * (`RoomDocumentBody`) deliberately: `useDraft` seeds its in-memory value
 * from `room.name`/`room.description` ONCE at mount and never re-syncs from
 * a later prop change (so a background refetch triggered by some OTHER
 * dispatch — renaming an exit, say — can never stomp text the viewer is
 * mid-typing). That means `RoomDocumentBody` must not exist yet while
 * `fetchRoomDetail` is still loading — mounting it only once `detail` is
 * non-null guarantees its very first mount already has the real server
 * values, and switching rooms (a fresh `roomId`) naturally unmounts/
 * remounts it as `detail` cycles back through `undefined`.
 */
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';

import { AddDialog, type AddDialogRealizePayload } from '../atlas/AddDialog';
import { ArtDialog } from './ArtDialog';
import { CategoryDoorDialog } from './CategoryDoorDialog';
import {
  useAreaManagerQuery,
  useRoomDetailQuery,
  useRoomSearchQuery,
  useWorldBuilderAction,
} from '../queries';
import type {
  WorldBuilderActionKey,
  WorldBuilderExitDetail,
  WorldBuilderRoomDetail,
} from '../types';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import { Compass } from './Compass';
import { ExitEditorDialog } from './ExitEditorDialog';
import { Marginalia, type MarginaliaDoor } from './Marginalia';
import { PreviewDialog } from './PreviewDialog';
import { useDraft } from './useDraft';
import { VariantsPanel } from './VariantsPanel';

export interface RoomDocumentProps {
  roomId: number;
  /** Navigate to another room's document — Compass neighbors, "Next unpublished". */
  onNavigateRoom: (roomId: number) => void;
  /** Fires after a successful delete, with the room's (now former) area id to land on. */
  onDeleted: (areaId: number) => void;
}

export function RoomDocument({ roomId, onNavigateRoom, onDeleted }: RoomDocumentProps) {
  const { data: detail } = useRoomDetailQuery(roomId);

  if (!detail) {
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="room-document-loading">
        Loading the room…
      </div>
    );
  }

  return (
    <RoomDocumentBody
      roomId={roomId}
      detail={detail}
      onNavigateRoom={onNavigateRoom}
      onDeleted={onDeleted}
    />
  );
}

interface PendingExitLink {
  destinationName: string;
  entranceExitName: string;
  exitExitName: string;
  /** Sibling-room ids known at dig time — the freshly dug room is the one
   * whose id was NOT here, so a pre-existing room with the same name (the
   * area already had a "Cellar") can never be linked in its place while the
   * new dig is stranded exitless and invisible. */
  knownRoomIds: Set<number>;
}

function RoomDocumentBody({
  roomId,
  detail,
  onNavigateRoom,
  onDeleted,
}: {
  roomId: number;
  detail: WorldBuilderRoomDetail;
  onNavigateRoom: (roomId: number) => void;
  onDeleted: (areaId: number) => void;
}) {
  const room = detail.room;
  const areaId = room.area_id;

  const { data: manager } = useAreaManagerQuery(areaId);
  const characterId = useWorldBuilderActor();
  const { mutate: runMutation } = useWorldBuilderAction(characterId ?? 0, areaId);

  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation({ key: key as WorldBuilderActionKey, kwargs });
  };

  const nameDraft = useDraft(roomId, 'name', room.name);
  const descDraft = useDraft(roomId, 'description', room.description);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [exitDialogExit, setExitDialogExit] = useState<WorldBuilderExitDetail | null>(null);
  const [addExitOpen, setAddExitOpen] = useState(false);
  const [artOpen, setArtOpen] = useState(false);
  const [openDoor, setOpenDoor] = useState<MarginaliaDoor | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [exitSearchTerm, setExitSearchTerm] = useState('');
  const { data: exitSearchHits } = useRoomSearchQuery(exitSearchTerm);

  const exitRoomOptions = (exitSearchHits ?? [])
    .filter((hit) => hit.id !== roomId)
    .map((hit) => ({ id: hit.id, name: hit.name }));

  // Only one exit-mode dig can be pending at a time (the dialog is modal),
  // so — like `Compass` — a single ref slot rather than a Map.
  const pendingExitLinkRef = useRef<PendingExitLink | null>(null);

  useEffect(() => {
    const pending = pendingExitLinkRef.current;
    if (!pending) return;
    const rooms = manager?.rooms ?? [];
    const newRoom = rooms.find(
      (r) =>
        !pending.knownRoomIds.has(r.id) &&
        r.name.toLowerCase() === pending.destinationName.toLowerCase()
    );
    if (!newRoom) return;
    runAction('staff_link_rooms', {
      room_a_id: newRoom.id,
      room_b_id: roomId,
      name_ab: pending.exitExitName,
      name_ba: pending.entranceExitName,
    });
    pendingExitLinkRef.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manager?.rooms]);

  const handleExitConfirm = (payload: AddDialogRealizePayload) => {
    if (payload.kind !== 'exit') return;
    const siblingRooms = manager?.rooms ?? [];
    // The dialog's matchedRoomId comes from the async search — a submit that
    // outruns it would dig a duplicate of a room the user meant to link, so
    // the same-area siblings (already in hand, synchronous) get a second
    // chance at the match before the dig fork wins.
    const matchedRoomId =
      payload.matchedRoomId ??
      siblingRooms.find(
        (r) => r.id !== roomId && r.name.toLowerCase() === payload.name.trim().toLowerCase()
      )?.id ??
      null;
    if (matchedRoomId != null) {
      runAction('staff_link_rooms', {
        room_a_id: roomId,
        room_b_id: matchedRoomId,
        name_ab: payload.exitThere,
        name_ba: payload.exitBack,
      });
    } else if (areaId != null) {
      runAction('staff_dig_room', { area_id: areaId, name: payload.name });
      pendingExitLinkRef.current = {
        destinationName: payload.name,
        entranceExitName: payload.exitThere,
        exitExitName: payload.exitBack,
        knownRoomIds: new Set(siblingRooms.map((r) => r.id)),
      };
    } else {
      toast.error('This room has no area to dig into.');
    }
    setAddExitOpen(false);
  };

  const handleSave = () => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation(
      {
        key: 'staff_edit_room',
        kwargs: { room_id: roomId, name: nameDraft.value, description: descDraft.value },
      },
      {
        onSuccess: (result) => {
          if (result.success !== false) {
            nameDraft.clearDraft();
            descDraft.clearDraft();
          }
        },
      }
    );
  };

  const handlePublish = () => runAction('staff_publish_room', { room_id: roomId });

  const unpublishedRooms = (manager?.rooms ?? []).filter((r) => !r.published_at);
  const handleNextUnpublished = () => {
    if (unpublishedRooms.length === 0) return;
    const index = unpublishedRooms.findIndex((r) => r.id === roomId);
    const next = unpublishedRooms[(index + 1) % unpublishedRooms.length];
    onNavigateRoom(next.id);
  };

  const handleDelete = () => {
    setDeleteConfirmOpen(false);
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation(
      { key: 'staff_remove_room', kwargs: { room_id: roomId } },
      {
        onSuccess: (result) => {
          if (result.success !== false && areaId != null) {
            onDeleted(areaId);
          }
        },
      }
    );
  };

  return (
    <div className="grid grid-cols-[1fr_320px] gap-6 p-8" data-testid="room-document">
      <div>
        <div className="flex items-center gap-3">
          <input
            className="theme-heading min-w-0 flex-1 border-0 bg-transparent text-2xl [font-variant:small-caps] focus:outline-none"
            value={nameDraft.value}
            onChange={(event) => nameDraft.setValue(event.target.value)}
            aria-label="Room name"
            data-testid="room-name-input"
          />
          {!room.published_at && (
            <span
              className="border px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground"
              data-testid="unpublished-flag"
            >
              unpublished
            </span>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setPreviewOpen(true)}
            data-testid="preview-button"
          >
            Preview
          </Button>
        </div>

        <Textarea
          className="mt-3 min-h-60 resize-y border-0 border-l font-body text-base leading-relaxed focus-visible:border-l-primary focus-visible:ring-0"
          value={descDraft.value}
          onChange={(event) => descDraft.setValue(event.target.value)}
          placeholder="Nothing written yet — this is the blank page the skeleton pass left you."
          aria-label="Room description"
          data-testid="room-description-input"
        />

        <VariantsPanel roomId={roomId} variants={room.desc_variants} runAction={runAction} />

        <div
          className="mt-6 flex flex-wrap items-center gap-3 border-t pt-4"
          data-testid="room-document-savebar"
        >
          <span className="mr-auto font-body text-xs italic text-muted-foreground">
            draft kept as you type · nothing is live until you publish
          </span>
          <Button type="button" size="sm" onClick={handleSave} data-testid="save-button">
            Save
          </Button>
          <Button type="button" size="sm" onClick={handlePublish} data-testid="publish-button">
            Publish
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={unpublishedRooms.length === 0}
            onClick={handleNextUnpublished}
            data-testid="next-unpublished-button"
          >
            Next unpublished ❯
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={() => setDeleteConfirmOpen(true)}
            data-testid="delete-button"
          >
            delete…
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {areaId != null ? (
          <Compass
            areaId={areaId}
            currentRoom={{
              id: roomId,
              name: room.name,
              gridX: room.grid_x,
              gridY: room.grid_y,
              floor: room.floor,
            }}
            rooms={manager?.rooms ?? []}
            onOpenRoom={onNavigateRoom}
            runAction={runAction}
          />
        ) : (
          <p
            className="font-body text-xs italic text-muted-foreground"
            data-testid="compass-no-area-note"
          >
            this room has no area to place it within
          </p>
        )}

        <Marginalia
          room={room}
          exits={detail.exits}
          comfort={detail.comfort}
          cluesCount={room.clues.length}
          clueTriggersCount={room.clue_triggers.length}
          onOpenExit={setExitDialogExit}
          onAddExit={() => setAddExitOpen(true)}
          onOpenArt={() => setArtOpen(true)}
          onOpenDoor={setOpenDoor}
          resonances={detail.resonances}
          dominantAffinity={detail.dominant_affinity}
        />
      </div>

      <ExitEditorDialog
        open={exitDialogExit != null}
        onOpenChange={(open) => {
          if (!open) setExitDialogExit(null);
        }}
        exit={exitDialogExit}
        runAction={runAction}
      />

      <AddDialog
        mode="exit"
        open={addExitOpen}
        onOpenChange={setAddExitOpen}
        onConfirm={handleExitConfirm}
        roomOptions={exitRoomOptions}
        onDestinationInput={setExitSearchTerm}
      />

      <CategoryDoorDialog
        door={openDoor}
        onClose={() => setOpenDoor(null)}
        room={room}
        catalogs={detail.catalogs}
        runAction={runAction}
      />

      <ArtDialog
        open={artOpen}
        onOpenChange={setArtOpen}
        subjectName={room.name}
        currentArtUrl={room.art_url}
        onHang={(mediaId) => runAction('staff_edit_room', { room_id: roomId, art_id: mediaId })}
        onTakeDown={() => runAction('staff_edit_room', { room_id: roomId, art_id: 0 })}
      />

      <PreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        name={nameDraft.value}
        description={descDraft.value}
        locationPath={detail.breadcrumb.map((entry) => entry.name)}
        exitNames={detail.exits.map((exit) => exit.name)}
        artUrl={room.art_url}
      />

      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {room.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This empties the room's exits and deletes it. Occupied, feature-installed, or exported
              rooms refuse.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} data-testid="confirm-delete-button">
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
