import type { ScenePayload } from './types';
import type { AppDispatch } from '@/store/store';
import { setSessionScene } from '@/store/gameSlice';

export function handleScenePayload(
  character: string,
  payload: ScenePayload,
  dispatch: AppDispatch
) {
  const scene = payload.action === 'end' ? null : payload.scene;
  dispatch(setSessionScene({ character, scene }));
}
