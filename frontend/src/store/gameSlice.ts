import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type {
  GameMessage,
  HubTidings,
  InteractionWsPayload,
  RoomStateObject,
  SceneSummary,
} from '@/hooks/types';
import type { MyRosterEntry } from '@/roster/types';
import type { CommandSpec } from '@/game/types';

interface RoomData {
  id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  is_owner: boolean;
  is_public: boolean;
  /** Civic-hub tidings block; null when no board/crier stands here (#1450). */
  hub: HubTidings | null;
}

interface Session {
  isConnected: boolean;
  messages: Array<GameMessage & { id: string }>;
  unread: number;
  commands: CommandSpec[];
  room: RoomData | null;
  scene: SceneSummary | null;
  sceneInteractions: InteractionWsPayload[];
  /** Highest interaction id seen per thread key (#2156 per-thread unread badges). */
  threadLastSeen: Record<string, number>;
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
        state.sessions[name] = {
          isConnected: false,
          messages: [],
          unread: 0,
          commands: [],
          room: null,
          scene: null,
          sceneInteractions: [],
          threadLastSeen: {},
        };
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
    setSessionCommands: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; commands: CommandSpec[] }>
    ) => {
      const { character, commands } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.commands = commands;
      }
    },
    setSessionRoom: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; room: RoomData | null }>
    ) => {
      const { character, room } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.room = room;
      }
    },
    setSessionScene: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; scene: SceneSummary | null }>
    ) => {
      const { character, scene } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.scene = scene;
      }
    },
    addSceneInteraction: (
      state,
      action: PayloadAction<{
        character: MyRosterEntry['name'];
        interaction: InteractionWsPayload;
      }>
    ) => {
      const { character, interaction } = action.payload;
      const session = state.sessions[character];
      if (session) {
        const MAX_WS_INTERACTIONS = 200;
        session.sceneInteractions.push(interaction);
        if (session.sceneInteractions.length > MAX_WS_INTERACTIONS) {
          session.sceneInteractions = session.sceneInteractions.slice(-MAX_WS_INTERACTIONS);
        }
      }
    },
    clearSceneInteractions: (state, action: PayloadAction<MyRosterEntry['name']>) => {
      const session = state.sessions[action.payload];
      if (session) {
        session.sceneInteractions = [];
      }
    },
    // Idempotent: never lowers an existing last-seen value for the thread key
    // (ratified unread semantics, #2156) — a stale/out-of-order dispatch must
    // not resurrect already-read interactions as unread.
    markThreadSeen: (
      state,
      action: PayloadAction<{
        character: MyRosterEntry['name'];
        threadKey: string;
        interactionId: number;
      }>
    ) => {
      const { character, threadKey, interactionId } = action.payload;
      const session = state.sessions[character];
      if (session) {
        const current = session.threadLastSeen[threadKey];
        if (current === undefined || interactionId > current) {
          session.threadLastSeen[threadKey] = interactionId;
        }
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
  setSessionCommands,
  setSessionRoom,
  setSessionScene,
  addSceneInteraction,
  clearSceneInteractions,
  markThreadSeen,
  resetGame,
} = gameSlice.actions;
