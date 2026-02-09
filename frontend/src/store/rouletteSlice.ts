import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RoulettePayload } from '@/components/roulette/types';

interface RouletteState {
  current: RoulettePayload | null;
  queue: RoulettePayload[];
  skipRequested: boolean;
}

const initialState: RouletteState = {
  current: null,
  queue: [],
  skipRequested: false,
};

export const rouletteSlice = createSlice({
  name: 'roulette',
  initialState,
  reducers: {
    enqueueRoulette: (state, action: PayloadAction<RoulettePayload>) => {
      if (!state.current) {
        state.current = action.payload;
      } else {
        state.queue.push(action.payload);
      }
    },
    dismissRoulette: (state) => {
      if (state.queue.length > 0) {
        state.current = state.queue.shift()!;
      } else {
        state.current = null;
      }
      state.skipRequested = false;
    },
    requestSkip: (state) => {
      state.skipRequested = true;
    },
  },
});

export const { enqueueRoulette, dismissRoulette, requestSkip } = rouletteSlice.actions;
