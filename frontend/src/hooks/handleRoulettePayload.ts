import type { RoulettePayload } from '@/components/roulette/types';
import type { AppDispatch } from '@/store/store';
import { enqueueRoulette } from '@/store/rouletteSlice';

export function handleRoulettePayload(payload: RoulettePayload, dispatch: AppDispatch) {
  dispatch(enqueueRoulette(payload));
}
