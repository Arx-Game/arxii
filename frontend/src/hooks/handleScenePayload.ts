import type { ScenePayload } from './types';
import type { AppDispatch } from '@/store/store';
import { setSessionScene } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

export function handleScenePayload(
  character: MyRosterEntry['name'],
  payload: ScenePayload,
  dispatch: AppDispatch
) {
  const scene = payload.action === 'end' ? null : payload.scene;
  dispatch(setSessionScene({ character, scene }));
}
