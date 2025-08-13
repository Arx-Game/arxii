import type { RoomStatePayload } from './types';
import type { AppDispatch } from '../store/store';
import { setSessionRoom, setSessionScene } from '../store/gameSlice';

export function handleRoomStatePayload(
  character: string,
  payload: RoomStatePayload,
  dispatch: AppDispatch
) {
  const roomId = parseInt(payload.room.dbref.replace('#', ''), 10);
  dispatch(setSessionRoom({ character, room: { id: roomId, name: payload.room.name } }));
  dispatch(setSessionScene({ character, scene: payload.scene ?? null }));
}
