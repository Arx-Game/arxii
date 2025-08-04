import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { GameMessage } from '../hooks/types';

interface GameState {
  isConnected: boolean;
  currentCharacter: string | null;
  messages: Array<GameMessage & { id: string }>;
}

const initialState: GameState = {
  isConnected: false,
  currentCharacter: null,
  messages: [],
};

export const gameSlice = createSlice({
  name: 'game',
  initialState,
  reducers: {
    setConnectionStatus: (state, action: PayloadAction<boolean>) => {
      state.isConnected = action.payload;
    },
    setCurrentCharacter: (state, action: PayloadAction<string | null>) => {
      state.currentCharacter = action.payload;
    },
    addMessage: (state, action: PayloadAction<GameMessage>) => {
      state.messages.push({ ...action.payload, id: Date.now().toString() });
    },
    clearMessages: (state) => {
      state.messages = [];
    },
  },
});

export const { setConnectionStatus, setCurrentCharacter, addMessage, clearMessages } =
  gameSlice.actions;
