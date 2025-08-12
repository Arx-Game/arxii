import type { RoomStatePayload } from './types';

export function handleRoomStatePayload(payload: RoomStatePayload) {
  // TODO: dispatch room state to update frontend state
  console.debug('Received room state payload', payload);
}
