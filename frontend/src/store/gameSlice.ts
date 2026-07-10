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
  /**
   * Highest interaction id present the moment the current scene's threading
   * was baselined (#2156 review fix). `countUnread` falls back to this scalar
   * for any thread key with no `threadLastSeen` entry, so a brand-new thread
   * that appears mid-session (e.g. a first whisper) badges unread starting
   * from its first message, while threads that already existed at scene load
   * stay zeroed. `null` before the baseline effect has run for this scene.
   */
  sceneBaselineId: number | null;
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
          sceneBaselineId: null,
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
        // A scene change (including a brand-new scene at the same room)
        // invalidates any previous scene's baseline — the baseline effect
        // must re-run for the new scene id (#2156 review fix).
        const previousId = session.scene?.id ?? null;
        const nextId = scene?.id ?? null;
        if (previousId !== nextId) {
          session.sceneBaselineId = null;
        }
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
    // Deliberately does NOT touch `sceneBaselineId` (#2156 review fix 2): this
    // reducer is dispatched on every ROOM_STATE broadcast (handleRoomStatePayload),
    // which fires on ordinary room churn (anyone entering/leaving) — not just
    // scene changes. Nulling the baseline here made it stick at null for the
    // rest of the scene, since GamePage's one-shot baseline ref never re-fires
    // for the same scene id. The scene-CHANGE reset lives in `setSessionScene`
    // (guarded on an actual scene-id change), which pairs correctly with that ref.
    clearSceneInteractions: (state, action: PayloadAction<MyRosterEntry['name']>) => {
      const session = state.sessions[action.payload];
      if (session) {
        session.sceneInteractions = [];
      }
    },
    // Scene-load baseline scalar (#2156 review fix): set once by GamePage's
    // baseline effect the first time it runs for a given scene id. See the
    // `sceneBaselineId` field doc for why this replaced the old per-thread-key
    // baseline (it one-shotted per KEY, so a brand-new thread's first message
    // got marked seen on arrival instead of badging unread).
    setSceneBaseline: (
      state,
      action: PayloadAction<{ character: MyRosterEntry['name']; baselineId: number | null }>
    ) => {
      const { character, baselineId } = action.payload;
      const session = state.sessions[character];
      if (session) {
        session.sceneBaselineId = baselineId;
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
  setSceneBaseline,
  resetGame,
} = gameSlice.actions;
