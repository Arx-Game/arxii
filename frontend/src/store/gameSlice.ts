import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { GameMessage } from '../hooks/types';
import type { MyRosterEntry } from '../roster/types';

interface Session {
  isConnected: boolean;
  messages: Array<GameMessage & { id: string }>;
  unread: number;
}

interface GameState {
  sessions: Record<string, Session>;
  active: MyRosterEntry['name'] | null;
}

const initialState: GameState = {
  sessions: {},
  active: null,
};

export const gameSlice = createSlice({
  name: 'game',
  initialState,
  reducers: {
    startSession: (state, action: PayloadAction<MyRosterEntry['name']>) => {
      const name = action.payload;
      if (!state.sessions[name]) {
        state.sessions[name] = { isConnected: false, messages: [], unread: 0 };
      }
      state.active = name;
      state.sessions[name].unread = 0;
    },
    setActiveSession: (state, action: PayloadAction<MyRosterEntry['name']>) => {
      const name = action.payload;
      if (state.sessions[name]) {
        state.active = name;
        state.sessions[name].unread = 0;
      }
    },
    setSessionConnectionStatus: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; status: boolean }>
    ) => {
      const { character, status } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.isConnected = status;
      }
    },
    addSessionMessage: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; message: GameMessage }>
    ) => {
      const { character, message } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.messages.push({ ...message, id: Date.now().toString() });
        if (state.active !== character) {
          session.unread += 1;
        }
      }
    },
    clearSessionMessages: (state, action: PayloadAction<MyRosterEntry['name']>) => {
      const session = state.sessions[action.payload];
      if (session) {
        session.messages = [];
      }
    },
    resetGame: () => initialState,
  },
});

export const {
  startSession,
  setActiveSession,
  setSessionConnectionStatus,
  addSessionMessage,
  clearSessionMessages,
  resetGame,
} = gameSlice.actions;
