import { configureStore } from '@reduxjs/toolkit';
import { gameSlice } from './gameSlice';
import { authSlice } from './authSlice';
import { rouletteSlice } from './rouletteSlice';
import { deepLinkModalSlice } from './deepLinkModalSlice';

export const store = configureStore({
  reducer: {
    game: gameSlice.reducer,
    auth: authSlice.reducer,
    roulette: rouletteSlice.reducer,
    deepLinkModal: deepLinkModalSlice.reducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
