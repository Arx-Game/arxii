import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface GameState {
  isConnected: boolean;
  currentCharacter: string | null;
  messages: Array<{
    id: string;
    content: string;
    timestamp: number;
    type: 'system' | 'chat' | 'action' | 'text' | 'channel' | 'error';
  }>;
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
    addMessage: (state, action: PayloadAction<Omit<GameState['messages'][0], 'id'>>) => {
      state.messages.push({
        ...action.payload,
        id: Date.now().toString(),
      });
    },
    clearMessages: (state) => {
      state.messages = [];
    },
  },
});

export const { setConnectionStatus, setCurrentCharacter, addMessage, clearMessages } =
  gameSlice.actions;
