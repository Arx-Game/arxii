import type { RoomStatePayload } from './types';
import type { AppDispatch } from '@/store/store';
import { setSessionRoom, setSessionScene } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

export function handleRoomStatePayload(
  character: MyRosterEntry['name'],
  payload: RoomStatePayload,
  dispatch: AppDispatch
): boolean {
  if (payload === null || typeof payload !== 'object') return false;
  const room = payload.room;
  if (
    room === null ||
    typeof room !== 'object' ||
    typeof room.dbref !== 'string' ||
    !/^#\d+$/.test(room.dbref) ||
    typeof room.name !== 'string' ||
    !Array.isArray(payload.characters) ||
    !Array.isArray(payload.objects) ||
    !Array.isArray(payload.exits)
  ) {
    return false;
  }
  const scene = payload.scene;
  if (
    scene !== undefined &&
    scene !== null &&
    (typeof scene !== 'object' ||
      typeof scene.id !== 'number' ||
      !Number.isInteger(scene.id) ||
      typeof scene.name !== 'string' ||
      typeof scene.description !== 'string')
  ) {
    return false;
  }
  const hasEpoch = typeof payload.state_epoch === 'string';
  const hasSequence =
    typeof payload.state_sequence === 'number' &&
    Number.isInteger(payload.state_sequence) &&
    payload.state_sequence >= 0;
  if (hasEpoch !== hasSequence || (payload.state_epoch !== undefined && !hasEpoch)) return false;
  const roomId = Number.parseInt(room.dbref.slice(1), 10);
  const revision =
    hasEpoch && hasSequence
      ? { epoch: payload.state_epoch as string, sequence: payload.state_sequence as number }
      : undefined;
  dispatch(
    setSessionRoom({
      character,
      room: {
        id: roomId,
        name: room.name,
        description: room.description ?? '',
        thumbnail_url: room.thumbnail_url,
        characters: payload.characters,
        objects: payload.objects,
        exits: payload.exits,
        decorations: payload.decorations ?? [],
        comfort_level: payload.comfort_level,
        is_owner: room.is_owner ?? false,
        is_public: room.is_public ?? false,
        hub: payload.hub ?? null,
        npc_givers: payload.npc_givers ?? [],
        has_unseen_presence: payload.has_unseen_presence ?? false,
        viewer_place_id: payload.viewer_place_id ?? null,
      },
      ...(revision ? { revision, scene: payload.scene ?? null } : {}),
    })
  );
  if (revision) return true;
  // setSessionScene owns the scene-transition reset (baseline, tabs, and the
  // WS interaction buffer) — guarded on an actual scene-id change, so the
  // room_state broadcast fired by every arrival no longer wipes the live feed.
  dispatch(
    setSessionScene({
      character,
      scene: payload.scene ?? null,
      ...(revision ? { revision } : {}),
    })
  );
  return true;
}
