/**
 * Tests for gameSlice reducers
 *
 * Tests the Redux slice for game session management, including multi-character
 * session handling, message management, connection status, and state transitions.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  gameSlice,
  startSession,
  setActiveSession,
  setSessionConnectionStatus,
  addSessionMessage,
  clearSessionMessages,
  setSessionCommands,
  setSessionRoom,
  setSessionScene,
  resetGame,
} from '../gameSlice';
import type { GameMessage, RoomStateObject, SceneSummary } from '@/hooks/types';
import { GAME_MESSAGE_TYPE } from '@/hooks/types';
import type { CommandSpec } from '@/game/types';

const reducer = gameSlice.reducer;

// --- Test Data Helpers ---

interface RoomData {
  id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
}

interface Session {
  isConnected: boolean;
  messages: Array<GameMessage & { id: string }>;
  unread: number;
  commands: CommandSpec[];
  room: RoomData | null;
  scene: SceneSummary | null;
}

interface GameState {
  sessions: Record<string, Session>;
  active: string | null;
}

const createDefaultSession = (overrides: Partial<Session> = {}): Session => ({
  isConnected: false,
  messages: [],
  unread: 0,
  commands: [],
  room: null,
  scene: null,
  ...overrides,
});

const createGameMessage = (
  content: string,
  type: GameMessage['type'] = GAME_MESSAGE_TYPE.TEXT,
  timestamp: number = Date.now()
): GameMessage => ({
  content,
  type,
  timestamp,
});

const createRoomData = (
  id: number,
  name: string,
  thumbnail_url: string | null = null,
  objects: RoomStateObject[] = [],
  exits: RoomStateObject[] = []
): RoomData => ({
  id,
  name,
  description: '',
  thumbnail_url,
  characters: [],
  objects,
  exits,
});

const createRoomStateObject = (
  dbref: string,
  name: string,
  thumbnail_url: string | null = null,
  commands: string[] = []
): RoomStateObject => ({
  dbref,
  name,
  thumbnail_url,
  commands,
});

const createSceneSummary = (
  id: number,
  name: string,
  description: string = '',
  is_owner: boolean = false
): SceneSummary => ({
  id,
  name,
  description,
  is_owner,
});

const createCommandSpec = (
  action: string,
  prompt: string,
  icon: string = 'default'
): CommandSpec => ({
  action,
  prompt,
  params_schema: {},
  icon,
});

const createStateWithSession = (
  sessionName: string,
  sessionData: Partial<Session> = {},
  active: string | null = null
): GameState => ({
  sessions: {
    [sessionName]: createDefaultSession(sessionData),
  },
  active,
});

const createStateWithMultipleSessions = (
  sessionsData: Record<string, Partial<Session>>,
  active: string | null = null
): GameState => ({
  sessions: Object.fromEntries(
    Object.entries(sessionsData).map(([name, data]) => [name, createDefaultSession(data)])
  ),
  active,
});

// --- Tests ---

describe('gameSlice', () => {
  const MOCK_TIMESTAMP = 1700000000000;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(MOCK_TIMESTAMP);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('initial state', () => {
    it('returns initial state for unknown action', () => {
      const result = reducer(undefined, { type: 'unknown' });

      expect(result).toEqual({ sessions: {}, active: null });
    });

    it('initial state has empty sessions object', () => {
      const result = reducer(undefined, { type: 'unknown' });

      expect(result.sessions).toEqual({});
    });

    it('initial state has null active', () => {
      const result = reducer(undefined, { type: 'unknown' });

      expect(result.active).toBeNull();
    });
  });

  describe('startSession', () => {
    describe('creating new sessions', () => {
      it('creates new session if it does not exist', () => {
        const initialState: GameState = { sessions: {}, active: null };

        const result = reducer(initialState, startSession('TestCharacter'));

        expect(result.sessions['TestCharacter']).toBeDefined();
      });

      it('creates session with default values', () => {
        const initialState: GameState = { sessions: {}, active: null };

        const result = reducer(initialState, startSession('TestCharacter'));

        expect(result.sessions['TestCharacter']).toEqual({
          isConnected: false,
          messages: [],
          unread: 0,
          commands: [],
          room: null,
          scene: null,
        });
      });

      it('sets new session as active', () => {
        const initialState: GameState = { sessions: {}, active: null };

        const result = reducer(initialState, startSession('TestCharacter'));

        expect(result.active).toBe('TestCharacter');
      });

      it('creates session and changes active from another session', () => {
        const initialState = createStateWithSession('OldCharacter', {}, 'OldCharacter');

        const result = reducer(initialState, startSession('NewCharacter'));

        expect(result.active).toBe('NewCharacter');
        expect(result.sessions['NewCharacter']).toBeDefined();
        expect(result.sessions['OldCharacter']).toBeDefined();
      });
    });

    describe('existing sessions', () => {
      it('preserves existing session data when session already exists', () => {
        const existingMessages = [{ ...createGameMessage('Hello'), id: '123' }];
        const existingRoom = createRoomData(1, 'Test Room');
        const existingScene = createSceneSummary(1, 'Test Scene');
        const existingCommands = [createCommandSpec('look', 'Look around')];

        const initialState = createStateWithSession('TestCharacter', {
          isConnected: true,
          messages: existingMessages,
          unread: 5,
          commands: existingCommands,
          room: existingRoom,
          scene: existingScene,
        });

        const result = reducer(initialState, startSession('TestCharacter'));

        expect(result.sessions['TestCharacter'].isConnected).toBe(true);
        expect(result.sessions['TestCharacter'].messages).toEqual(existingMessages);
        expect(result.sessions['TestCharacter'].commands).toEqual(existingCommands);
        expect(result.sessions['TestCharacter'].room).toEqual(existingRoom);
        expect(result.sessions['TestCharacter'].scene).toEqual(existingScene);
      });

      it('resets unread to 0 when starting existing session', () => {
        const initialState = createStateWithSession('TestCharacter', { unread: 10 });

        const result = reducer(initialState, startSession('TestCharacter'));

        expect(result.sessions['TestCharacter'].unread).toBe(0);
      });

      it('sets existing session as active', () => {
        const initialState = createStateWithMultipleSessions(
          { CharacterA: {}, CharacterB: {} },
          'CharacterA'
        );

        const result = reducer(initialState, startSession('CharacterB'));

        expect(result.active).toBe('CharacterB');
      });
    });

    describe('edge cases', () => {
      it('handles empty string as session name', () => {
        const initialState: GameState = { sessions: {}, active: null };

        const result = reducer(initialState, startSession(''));

        expect(result.sessions['']).toBeDefined();
        expect(result.active).toBe('');
      });

      it('handles character names with special characters', () => {
        const initialState: GameState = { sessions: {}, active: null };
        const specialName = "O'Brien the Third";

        const result = reducer(initialState, startSession(specialName));

        expect(result.sessions[specialName]).toBeDefined();
        expect(result.active).toBe(specialName);
      });

      it('handles character names with unicode', () => {
        const initialState: GameState = { sessions: {}, active: null };
        const unicodeName = 'Character\u2019s Name';

        const result = reducer(initialState, startSession(unicodeName));

        expect(result.sessions[unicodeName]).toBeDefined();
        expect(result.active).toBe(unicodeName);
      });
    });
  });

  describe('setActiveSession', () => {
    describe('setting active session', () => {
      it('sets active to given name if session exists', () => {
        const initialState = createStateWithMultipleSessions(
          { CharacterA: {}, CharacterB: {} },
          'CharacterA'
        );

        const result = reducer(initialState, setActiveSession('CharacterB'));

        expect(result.active).toBe('CharacterB');
      });

      it('resets unread to 0 for the activated session', () => {
        const initialState = createStateWithMultipleSessions(
          { CharacterA: { unread: 0 }, CharacterB: { unread: 15 } },
          'CharacterA'
        );

        const result = reducer(initialState, setActiveSession('CharacterB'));

        expect(result.sessions['CharacterB'].unread).toBe(0);
      });

      it('does not affect unread of other sessions', () => {
        const initialState = createStateWithMultipleSessions(
          { CharacterA: { unread: 5 }, CharacterB: { unread: 15 } },
          null
        );

        const result = reducer(initialState, setActiveSession('CharacterB'));

        expect(result.sessions['CharacterA'].unread).toBe(5);
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('CharacterA', {}, 'CharacterA');

        const result = reducer(initialState, setActiveSession('NonExistent'));

        expect(result.active).toBe('CharacterA');
        expect(result.sessions['NonExistent']).toBeUndefined();
      });

      it('does not modify state when session does not exist', () => {
        const initialState = createStateWithSession('CharacterA', { unread: 5 }, 'CharacterA');

        const result = reducer(initialState, setActiveSession('NonExistent'));

        expect(result).toEqual(initialState);
      });
    });

    describe('edge cases', () => {
      it('handles setting active when active is already null', () => {
        const initialState = createStateWithSession('CharacterA', {}, null);

        const result = reducer(initialState, setActiveSession('CharacterA'));

        expect(result.active).toBe('CharacterA');
      });

      it('handles setting active to already active session', () => {
        const initialState = createStateWithSession('CharacterA', { unread: 3 }, 'CharacterA');

        const result = reducer(initialState, setActiveSession('CharacterA'));

        expect(result.active).toBe('CharacterA');
        expect(result.sessions['CharacterA'].unread).toBe(0);
      });
    });
  });

  describe('setSessionConnectionStatus', () => {
    describe('updating connection status', () => {
      it('sets isConnected to true for existing session', () => {
        const initialState = createStateWithSession('TestCharacter', { isConnected: false });

        const result = reducer(
          initialState,
          setSessionConnectionStatus({ character: 'TestCharacter', status: true })
        );

        expect(result.sessions['TestCharacter'].isConnected).toBe(true);
      });

      it('sets isConnected to false for existing session', () => {
        const initialState = createStateWithSession('TestCharacter', { isConnected: true });

        const result = reducer(
          initialState,
          setSessionConnectionStatus({ character: 'TestCharacter', status: false })
        );

        expect(result.sessions['TestCharacter'].isConnected).toBe(false);
      });

      it('does not affect other session properties', () => {
        const messages = [{ ...createGameMessage('Hello'), id: '123' }];
        const initialState = createStateWithSession('TestCharacter', {
          isConnected: false,
          messages,
          unread: 5,
        });

        const result = reducer(
          initialState,
          setSessionConnectionStatus({ character: 'TestCharacter', status: true })
        );

        expect(result.sessions['TestCharacter'].messages).toEqual(messages);
        expect(result.sessions['TestCharacter'].unread).toBe(5);
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});

        const result = reducer(
          initialState,
          setSessionConnectionStatus({ character: 'NonExistent', status: true })
        );

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('multiple sessions', () => {
      it('updates only the specified session', () => {
        const initialState = createStateWithMultipleSessions({
          CharacterA: { isConnected: false },
          CharacterB: { isConnected: false },
        });

        const result = reducer(
          initialState,
          setSessionConnectionStatus({ character: 'CharacterA', status: true })
        );

        expect(result.sessions['CharacterA'].isConnected).toBe(true);
        expect(result.sessions['CharacterB'].isConnected).toBe(false);
      });
    });
  });

  describe('addSessionMessage', () => {
    describe('adding messages', () => {
      it('adds message with generated id to session', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('Hello world');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].messages).toHaveLength(1);
        expect(result.sessions['TestCharacter'].messages[0].content).toBe('Hello world');
      });

      it('generates id using Date.now().toString()', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('Hello');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].messages[0].id).toBe(MOCK_TIMESTAMP.toString());
      });

      it('preserves all message properties', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('Test content', GAME_MESSAGE_TYPE.ACTION, 1234567890);

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        const addedMessage = result.sessions['TestCharacter'].messages[0];
        expect(addedMessage.content).toBe('Test content');
        expect(addedMessage.type).toBe(GAME_MESSAGE_TYPE.ACTION);
        expect(addedMessage.timestamp).toBe(1234567890);
        expect(addedMessage.id).toBe(MOCK_TIMESTAMP.toString());
      });

      it('appends to existing messages', () => {
        const existingMessage = { ...createGameMessage('First'), id: '1' };
        const initialState = createStateWithSession(
          'TestCharacter',
          { messages: [existingMessage] },
          'TestCharacter'
        );
        const newMessage = createGameMessage('Second');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message: newMessage })
        );

        expect(result.sessions['TestCharacter'].messages).toHaveLength(2);
        expect(result.sessions['TestCharacter'].messages[0].content).toBe('First');
        expect(result.sessions['TestCharacter'].messages[1].content).toBe('Second');
      });
    });

    describe('unread count', () => {
      it('does NOT increment unread if session is active', () => {
        const initialState = createStateWithSession(
          'TestCharacter',
          { unread: 0 },
          'TestCharacter'
        );
        const message = createGameMessage('Hello');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].unread).toBe(0);
      });

      it('increments unread if session is NOT active', () => {
        const initialState = createStateWithMultipleSessions(
          { CharacterA: { unread: 0 }, CharacterB: { unread: 0 } },
          'CharacterA'
        );
        const message = createGameMessage('Hello');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'CharacterB', message })
        );

        expect(result.sessions['CharacterB'].unread).toBe(1);
      });

      it('increments unread when active is null', () => {
        const initialState = createStateWithSession('TestCharacter', { unread: 0 }, null);
        const message = createGameMessage('Hello');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].unread).toBe(1);
      });

      it('increments unread correctly for multiple messages', () => {
        let state = createStateWithMultipleSessions(
          { CharacterA: { unread: 0 }, CharacterB: { unread: 0 } },
          'CharacterA'
        );

        state = reducer(
          state,
          addSessionMessage({ character: 'CharacterB', message: createGameMessage('1') })
        );
        state = reducer(
          state,
          addSessionMessage({ character: 'CharacterB', message: createGameMessage('2') })
        );
        state = reducer(
          state,
          addSessionMessage({ character: 'CharacterB', message: createGameMessage('3') })
        );

        expect(state.sessions['CharacterB'].unread).toBe(3);
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});
        const message = createGameMessage('Hello');

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'NonExistent', message })
        );

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('message types', () => {
      it('handles SYSTEM message type', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('System notice', GAME_MESSAGE_TYPE.SYSTEM);

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].messages[0].type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      });

      it('handles ERROR message type', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('Error occurred', GAME_MESSAGE_TYPE.ERROR);

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].messages[0].type).toBe(GAME_MESSAGE_TYPE.ERROR);
      });

      it('handles CHANNEL message type', () => {
        const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');
        const message = createGameMessage('Channel message', GAME_MESSAGE_TYPE.CHANNEL);

        const result = reducer(
          initialState,
          addSessionMessage({ character: 'TestCharacter', message })
        );

        expect(result.sessions['TestCharacter'].messages[0].type).toBe(GAME_MESSAGE_TYPE.CHANNEL);
      });
    });
  });

  describe('clearSessionMessages', () => {
    describe('clearing messages', () => {
      it('clears messages array for existing session', () => {
        const messages = [
          { ...createGameMessage('First'), id: '1' },
          { ...createGameMessage('Second'), id: '2' },
        ];
        const initialState = createStateWithSession('TestCharacter', { messages });

        const result = reducer(initialState, clearSessionMessages('TestCharacter'));

        expect(result.sessions['TestCharacter'].messages).toEqual([]);
      });

      it('does not affect other session properties', () => {
        const messages = [{ ...createGameMessage('Test'), id: '1' }];
        const initialState = createStateWithSession('TestCharacter', {
          messages,
          unread: 5,
          isConnected: true,
        });

        const result = reducer(initialState, clearSessionMessages('TestCharacter'));

        expect(result.sessions['TestCharacter'].unread).toBe(5);
        expect(result.sessions['TestCharacter'].isConnected).toBe(true);
      });

      it('handles already empty messages array', () => {
        const initialState = createStateWithSession('TestCharacter', { messages: [] });

        const result = reducer(initialState, clearSessionMessages('TestCharacter'));

        expect(result.sessions['TestCharacter'].messages).toEqual([]);
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});

        const result = reducer(initialState, clearSessionMessages('NonExistent'));

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('multiple sessions', () => {
      it('clears only the specified session messages', () => {
        const messagesA = [{ ...createGameMessage('A'), id: '1' }];
        const messagesB = [{ ...createGameMessage('B'), id: '2' }];
        const initialState = createStateWithMultipleSessions({
          CharacterA: { messages: messagesA },
          CharacterB: { messages: messagesB },
        });

        const result = reducer(initialState, clearSessionMessages('CharacterA'));

        expect(result.sessions['CharacterA'].messages).toEqual([]);
        expect(result.sessions['CharacterB'].messages).toEqual(messagesB);
      });
    });
  });

  describe('setSessionCommands', () => {
    describe('setting commands', () => {
      it('sets commands for existing session', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const commands = [
          createCommandSpec('look', 'Look around'),
          createCommandSpec('say', 'Say something'),
        ];

        const result = reducer(
          initialState,
          setSessionCommands({ character: 'TestCharacter', commands })
        );

        expect(result.sessions['TestCharacter'].commands).toEqual(commands);
      });

      it('replaces existing commands', () => {
        const oldCommands = [createCommandSpec('old', 'Old command')];
        const initialState = createStateWithSession('TestCharacter', {
          commands: oldCommands,
        });
        const newCommands = [createCommandSpec('new', 'New command')];

        const result = reducer(
          initialState,
          setSessionCommands({ character: 'TestCharacter', commands: newCommands })
        );

        expect(result.sessions['TestCharacter'].commands).toEqual(newCommands);
      });

      it('can set empty commands array', () => {
        const commands = [createCommandSpec('look', 'Look')];
        const initialState = createStateWithSession('TestCharacter', { commands });

        const result = reducer(
          initialState,
          setSessionCommands({ character: 'TestCharacter', commands: [] })
        );

        expect(result.sessions['TestCharacter'].commands).toEqual([]);
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});
        const commands = [createCommandSpec('look', 'Look')];

        const result = reducer(
          initialState,
          setSessionCommands({ character: 'NonExistent', commands })
        );

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('command spec preservation', () => {
      it('preserves full command spec structure', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const command: CommandSpec = {
          action: 'complex',
          prompt: 'Complex action',
          params_schema: {
            target: { type: 'string', required: true },
            modifier: { type: 'number', required: false },
          },
          icon: 'complex-icon',
          name: 'Complex Command',
          category: 'Combat',
          help: 'Perform a complex action',
        };

        const result = reducer(
          initialState,
          setSessionCommands({ character: 'TestCharacter', commands: [command] })
        );

        expect(result.sessions['TestCharacter'].commands[0]).toEqual(command);
      });
    });
  });

  describe('setSessionRoom', () => {
    describe('setting room', () => {
      it('sets room for existing session', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const room = createRoomData(123, 'Test Room', '/images/room.png');

        const result = reducer(initialState, setSessionRoom({ character: 'TestCharacter', room }));

        expect(result.sessions['TestCharacter'].room).toEqual(room);
      });

      it('replaces existing room', () => {
        const oldRoom = createRoomData(1, 'Old Room');
        const initialState = createStateWithSession('TestCharacter', { room: oldRoom });
        const newRoom = createRoomData(2, 'New Room');

        const result = reducer(
          initialState,
          setSessionRoom({ character: 'TestCharacter', room: newRoom })
        );

        expect(result.sessions['TestCharacter'].room).toEqual(newRoom);
      });

      it('can set room to null', () => {
        const room = createRoomData(1, 'Test Room');
        const initialState = createStateWithSession('TestCharacter', { room });

        const result = reducer(
          initialState,
          setSessionRoom({ character: 'TestCharacter', room: null })
        );

        expect(result.sessions['TestCharacter'].room).toBeNull();
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});
        const room = createRoomData(1, 'Test Room');

        const result = reducer(initialState, setSessionRoom({ character: 'NonExistent', room }));

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('room data preservation', () => {
      it('preserves all room fields including objects and exits', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const objects = [
          createRoomStateObject('#200', 'Sword', '/images/sword.png', ['take', 'examine']),
          createRoomStateObject('#201', 'Shield', null, ['take']),
        ];
        const exits = [
          createRoomStateObject('#300', 'North', null, ['go']),
          createRoomStateObject('#301', 'South', '/images/south.png', ['go', 'look']),
        ];
        const room = createRoomData(100, 'Armory', '/images/armory.jpg', objects, exits);

        const result = reducer(initialState, setSessionRoom({ character: 'TestCharacter', room }));

        expect(result.sessions['TestCharacter'].room).toEqual(room);
        expect(result.sessions['TestCharacter'].room?.objects).toHaveLength(2);
        expect(result.sessions['TestCharacter'].room?.exits).toHaveLength(2);
      });

      it('handles room with null thumbnail_url', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const room = createRoomData(1, 'Dark Room', null);

        const result = reducer(initialState, setSessionRoom({ character: 'TestCharacter', room }));

        expect(result.sessions['TestCharacter'].room?.thumbnail_url).toBeNull();
      });
    });
  });

  describe('setSessionScene', () => {
    describe('setting scene', () => {
      it('sets scene for existing session', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const scene = createSceneSummary(42, 'Epic Battle', 'A fierce combat ensues', true);

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene })
        );

        expect(result.sessions['TestCharacter'].scene).toEqual(scene);
      });

      it('replaces existing scene', () => {
        const oldScene = createSceneSummary(1, 'Old Scene');
        const initialState = createStateWithSession('TestCharacter', { scene: oldScene });
        const newScene = createSceneSummary(2, 'New Scene');

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene: newScene })
        );

        expect(result.sessions['TestCharacter'].scene).toEqual(newScene);
      });

      it('can set scene to null', () => {
        const scene = createSceneSummary(1, 'Test Scene');
        const initialState = createStateWithSession('TestCharacter', { scene });

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene: null })
        );

        expect(result.sessions['TestCharacter'].scene).toBeNull();
      });
    });

    describe('non-existent session', () => {
      it('does nothing if session does not exist', () => {
        const initialState = createStateWithSession('ExistingCharacter', {});
        const scene = createSceneSummary(1, 'Test Scene');

        const result = reducer(initialState, setSessionScene({ character: 'NonExistent', scene }));

        expect(result.sessions['NonExistent']).toBeUndefined();
        expect(result).toEqual(initialState);
      });
    });

    describe('scene data preservation', () => {
      it('preserves all scene fields', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const scene: SceneSummary = {
          id: 999,
          name: 'The Grand Finale',
          description: 'Everything comes together in an epic conclusion',
          is_owner: true,
        };

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene })
        );

        expect(result.sessions['TestCharacter'].scene).toEqual(scene);
      });

      it('handles scene with is_owner false', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const scene = createSceneSummary(1, 'Joined Scene', 'A scene I joined', false);

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene })
        );

        expect(result.sessions['TestCharacter'].scene?.is_owner).toBe(false);
      });

      it('handles scene with empty description', () => {
        const initialState = createStateWithSession('TestCharacter', {});
        const scene = createSceneSummary(1, 'Minimal Scene', '');

        const result = reducer(
          initialState,
          setSessionScene({ character: 'TestCharacter', scene })
        );

        expect(result.sessions['TestCharacter'].scene?.description).toBe('');
      });
    });
  });

  describe('resetGame', () => {
    it('returns to initial state', () => {
      const initialState = createStateWithMultipleSessions(
        {
          CharacterA: {
            isConnected: true,
            messages: [{ ...createGameMessage('Hello'), id: '1' }],
            unread: 5,
          },
          CharacterB: {
            isConnected: true,
            messages: [{ ...createGameMessage('World'), id: '2' }],
            unread: 3,
          },
        },
        'CharacterA'
      );

      const result = reducer(initialState, resetGame());

      expect(result).toEqual({ sessions: {}, active: null });
    });

    it('clears all sessions', () => {
      const initialState = createStateWithMultipleSessions({
        A: {},
        B: {},
        C: {},
      });

      const result = reducer(initialState, resetGame());

      expect(result.sessions).toEqual({});
      expect(Object.keys(result.sessions)).toHaveLength(0);
    });

    it('sets active to null', () => {
      const initialState = createStateWithSession('TestCharacter', {}, 'TestCharacter');

      const result = reducer(initialState, resetGame());

      expect(result.active).toBeNull();
    });

    it('works from already initial state', () => {
      const initialState: GameState = { sessions: {}, active: null };

      const result = reducer(initialState, resetGame());

      expect(result).toEqual({ sessions: {}, active: null });
    });

    it('clears complex session data', () => {
      const complexState: GameState = {
        sessions: {
          Hero: {
            isConnected: true,
            messages: [
              { ...createGameMessage('Msg 1'), id: '1' },
              { ...createGameMessage('Msg 2'), id: '2' },
            ],
            unread: 10,
            commands: [createCommandSpec('attack', 'Attack')],
            room: createRoomData(
              1,
              'Castle',
              '/castle.jpg',
              [createRoomStateObject('#100', 'Door')],
              [createRoomStateObject('#200', 'North')]
            ),
            scene: createSceneSummary(1, 'Battle', 'An epic battle', true),
          },
        },
        active: 'Hero',
      };

      const result = reducer(complexState, resetGame());

      expect(result.sessions).toEqual({});
      expect(result.active).toBeNull();
    });
  });

  describe('integration scenarios', () => {
    it('handles typical session lifecycle', () => {
      let state: GameState = { sessions: {}, active: null };

      // Start session
      state = reducer(state, startSession('Hero'));
      expect(state.active).toBe('Hero');
      expect(state.sessions['Hero']).toBeDefined();

      // Connect
      state = reducer(state, setSessionConnectionStatus({ character: 'Hero', status: true }));
      expect(state.sessions['Hero'].isConnected).toBe(true);

      // Receive commands
      const commands = [createCommandSpec('look', 'Look around')];
      state = reducer(state, setSessionCommands({ character: 'Hero', commands }));
      expect(state.sessions['Hero'].commands).toEqual(commands);

      // Enter room
      const room = createRoomData(1, 'Starting Room');
      state = reducer(state, setSessionRoom({ character: 'Hero', room }));
      expect(state.sessions['Hero'].room).toEqual(room);

      // Receive messages
      state = reducer(
        state,
        addSessionMessage({ character: 'Hero', message: createGameMessage('Welcome!') })
      );
      expect(state.sessions['Hero'].messages).toHaveLength(1);
      expect(state.sessions['Hero'].unread).toBe(0); // Active session

      // Start scene
      const scene = createSceneSummary(1, 'Adventure Begins');
      state = reducer(state, setSessionScene({ character: 'Hero', scene }));
      expect(state.sessions['Hero'].scene).toEqual(scene);

      // Disconnect
      state = reducer(state, setSessionConnectionStatus({ character: 'Hero', status: false }));
      expect(state.sessions['Hero'].isConnected).toBe(false);
    });

    it('handles multi-character scenario with tab switching', () => {
      let state: GameState = { sessions: {}, active: null };

      // Start first character
      state = reducer(state, startSession('CharacterA'));
      expect(state.active).toBe('CharacterA');

      // Start second character
      state = reducer(state, startSession('CharacterB'));
      expect(state.active).toBe('CharacterB');
      expect(Object.keys(state.sessions)).toHaveLength(2);

      // Messages to inactive CharacterA should increment unread
      state = reducer(
        state,
        addSessionMessage({ character: 'CharacterA', message: createGameMessage('Hello A') })
      );
      expect(state.sessions['CharacterA'].unread).toBe(1);
      expect(state.sessions['CharacterB'].unread).toBe(0);

      // Switch to CharacterA - unread resets
      state = reducer(state, setActiveSession('CharacterA'));
      expect(state.active).toBe('CharacterA');
      expect(state.sessions['CharacterA'].unread).toBe(0);

      // Messages to inactive CharacterB now increment
      state = reducer(
        state,
        addSessionMessage({ character: 'CharacterB', message: createGameMessage('Hello B') })
      );
      expect(state.sessions['CharacterB'].unread).toBe(1);
    });

    it('handles reset and restart scenario', () => {
      let state: GameState = { sessions: {}, active: null };

      // Build up state
      state = reducer(state, startSession('Hero'));
      state = reducer(
        state,
        addSessionMessage({ character: 'Hero', message: createGameMessage('Test') })
      );
      state = reducer(
        state,
        setSessionRoom({ character: 'Hero', room: createRoomData(1, 'Room') })
      );

      // Reset everything
      state = reducer(state, resetGame());
      expect(state.sessions).toEqual({});
      expect(state.active).toBeNull();

      // Start fresh
      state = reducer(state, startSession('NewHero'));
      expect(state.active).toBe('NewHero');
      expect(state.sessions['NewHero'].messages).toEqual([]);
      expect(state.sessions['Hero']).toBeUndefined();
    });
  });
});
