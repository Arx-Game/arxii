import type { InteractionWsPayload } from './types';
import type { AppDispatch } from '@/store/store';
import { addSceneInteraction } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

export function handleInteractionPayload(
  character: MyRosterEntry['name'],
  payload: InteractionWsPayload,
  dispatch: AppDispatch
) {
  dispatch(addSceneInteraction({ character, interaction: payload }));
}
