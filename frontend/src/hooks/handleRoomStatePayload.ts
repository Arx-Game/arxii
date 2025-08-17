import type { RoomStatePayload } from './types';
import type { AppDispatch } from '@/store/store';
import { setSessionRoom, setSessionScene } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

export function handleRoomStatePayload(
  character: MyRosterEntry['name'],
  payload: RoomStatePayload,
  dispatch: AppDispatch
) {
  const roomId = parseInt(payload.room.dbref.replace('#', ''), 10);
  dispatch(
    setSessionRoom({
      character,
      room: {
        id: roomId,
        name: payload.room.name,
        thumbnail_url: payload.room.thumbnail_url,
        objects: payload.objects,
        exits: payload.exits,
      },
    })
  );
  dispatch(setSessionScene({ character, scene: payload.scene ?? null }));
}
