import { configureStore } from '@reduxjs/toolkit'
import { gameSlice } from '@/store/gameSlice'
import { authSlice } from '@/store/authSlice'

export const store = configureStore({
  reducer: {
    game: gameSlice.reducer,
    auth: authSlice.reducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
