/**
 * Tests for handleRoomStatePayload function
 *
 * Tests the transformation of WebSocket room state payloads into Redux actions,
 * including dbref parsing, room data transformation, and scene handling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleRoomStatePayload } from '../handleRoomStatePayload';
import { setSessionRoom, setSessionScene } from '@/store/gameSlice';
import type { RoomStatePayload, RoomStateObject, SceneSummary } from '../types';
import type { AppDispatch } from '@/store/store';

vi.mock('@/store/gameSlice', () => ({
  setSessionRoom: vi.fn((payload) => ({ type: 'game/setSessionRoom', payload })),
  setSessionScene: vi.fn((payload) => ({ type: 'game/setSessionScene', payload })),
}));

describe('handleRoomStatePayload', () => {
  let mockDispatch: AppDispatch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch = vi.fn() as unknown as AppDispatch;
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

  describe('basic room state dispatch', () => {
    it('dispatches setSessionRoom with correct room data', () => {
      const character = 'TestCharacter';
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#123', 'Test Room', '/images/room.png'),
        characters: [],
        objects: [createRoomStateObject('#456', 'Object One')],
        exits: [createRoomStateObject('#789', 'North')],
      };

      handleRoomStatePayload(character, payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith({
        character: 'TestCharacter',
        room: {
          id: 123,
          name: 'Test Room',
          description: '',
          thumbnail_url: '/images/room.png',
          characters: [],
          objects: payload.objects,
          exits: payload.exits,
        },
      });
      expect(mockDispatch).toHaveBeenCalledTimes(2);
    });

    it('dispatches setSessionScene with scene data when present', () => {
      const character = 'TestCharacter';
      const scene = createSceneSummary(42, 'Epic Scene', 'A dramatic scene', true);
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Scene Room'),
        characters: [],
        objects: [],
        exits: [],
        scene,
      };

      handleRoomStatePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestCharacter',
        scene,
      });
    });

    it('dispatches actions in correct order (room first, scene second)', () => {
      const character = 'TestCharacter';
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Test Room'),
        characters: [],
        objects: [],
        exits: [],
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleRoomStatePayload(character, payload, mockDispatch);

      const calls = (mockDispatch as unknown as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.length).toBe(2);
      expect(calls[0][0].type).toBe('game/setSessionRoom');
      expect(calls[1][0].type).toBe('game/setSessionScene');
    });
  });

  describe('dbref parsing', () => {
    it('parses #123 to 123', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#123', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({ id: 123 }),
        })
      );
    });

    it('parses #1 to 1', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#1', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({ id: 1 }),
        })
      );
    });

    it('parses #999999 to 999999', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#999999', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({ id: 999999 }),
        })
      );
    });

    it('parses #0 to 0', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#0', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({ id: 0 }),
        })
      );
    });

    it('parses large dbref #2147483647 correctly', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#2147483647', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({ id: 2147483647 }),
        })
      );
    });
  });

  describe('scene handling', () => {
    it('dispatches scene when payload.scene exists', () => {
      const scene = createSceneSummary(10, 'Active Scene');
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
        scene,
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Character',
        scene,
      });
    });

    it('dispatches null when payload.scene is undefined', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Character',
        scene: null,
      });
    });

    it('dispatches null when payload.scene is null', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
        scene: null,
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Character',
        scene: null,
      });
    });

    it('preserves all scene properties when dispatching', () => {
      const scene: SceneSummary = {
        id: 42,
        name: 'Full Scene',
        description: 'A complete scene with all fields',
        is_owner: true,
      };
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
        scene,
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Character',
        scene: {
          id: 42,
          name: 'Full Scene',
          description: 'A complete scene with all fields',
          is_owner: true,
        },
      });
    });
  });

  describe('character name passing', () => {
    it('passes character name correctly to setSessionRoom', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Sir Galahad', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Sir Galahad',
        })
      );
    });

    it('passes character name correctly to setSessionScene', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Lady Morgana', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Lady Morgana',
        })
      );
    });

    it('handles character names with special characters', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload("O'Brien the Third", payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          character: "O'Brien the Third",
        })
      );
      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: "O'Brien the Third",
        })
      );
    });

    it('handles empty character name', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          character: '',
        })
      );
      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: '',
        })
      );
    });
  });

  describe('full payload structure', () => {
    it('transforms room with all fields correctly', () => {
      const payload: RoomStatePayload = {
        room: {
          dbref: '#500',
          name: 'Grand Hall',
          thumbnail_url: '/images/grand_hall.jpg',
          commands: ['look', 'examine'],
        },
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith({
        character: 'Character',
        room: {
          id: 500,
          name: 'Grand Hall',
          description: '',
          thumbnail_url: '/images/grand_hall.jpg',
          characters: [],
          objects: [],
          exits: [],
        },
      });
    });

    it('passes objects array through correctly', () => {
      const objects: RoomStateObject[] = [
        createRoomStateObject('#200', 'Sword', '/images/sword.png', ['take', 'examine']),
        createRoomStateObject('#201', 'Shield', null, ['take']),
        createRoomStateObject('#202', 'Potion', '/images/potion.png', []),
      ];
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects,
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({
            objects,
          }),
        })
      );
    });

    it('passes exits array through correctly', () => {
      const exits: RoomStateObject[] = [
        createRoomStateObject('#300', 'North', null, ['go']),
        createRoomStateObject('#301', 'South', null, ['go']),
        createRoomStateObject('#302', 'Secret Door', '/images/door.png', ['open', 'go']),
      ];
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Room'),
        characters: [],
        objects: [],
        exits,
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({
            exits,
          }),
        })
      );
    });

    it('handles room with null thumbnail_url', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Dark Room', null),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({
            thumbnail_url: null,
          }),
        })
      );
    });

    it('handles empty objects and exits arrays', () => {
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Empty Room'),
        characters: [],
        objects: [],
        exits: [],
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith({
        character: 'Character',
        room: {
          id: 100,
          name: 'Empty Room',
          description: '',
          thumbnail_url: null,
          characters: [],
          objects: [],
          exits: [],
        },
      });
    });

    it('handles payload with many objects and exits', () => {
      const objects: RoomStateObject[] = Array.from({ length: 50 }, (_, i) =>
        createRoomStateObject(`#${200 + i}`, `Object ${i}`)
      );
      const exits: RoomStateObject[] = Array.from({ length: 10 }, (_, i) =>
        createRoomStateObject(`#${300 + i}`, `Exit ${i}`)
      );
      const payload: RoomStatePayload = {
        room: createRoomStateObject('#100', 'Crowded Room'),
        characters: [],
        objects,
        exits,
      };

      handleRoomStatePayload('Character', payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith(
        expect.objectContaining({
          room: expect.objectContaining({
            objects: expect.arrayContaining([
              expect.objectContaining({ dbref: '#200', name: 'Object 0' }),
              expect.objectContaining({ dbref: '#249', name: 'Object 49' }),
            ]),
            exits: expect.arrayContaining([
              expect.objectContaining({ dbref: '#300', name: 'Exit 0' }),
              expect.objectContaining({ dbref: '#309', name: 'Exit 9' }),
            ]),
          }),
        })
      );
    });
  });

  describe('complete integration', () => {
    it('handles complete payload with all fields populated', () => {
      const character = 'Sir Lancelot';
      const room: RoomStateObject = {
        dbref: '#777',
        name: 'Castle Throne Room',
        thumbnail_url: '/images/throne.jpg',
        commands: ['look', 'bow'],
      };
      const objects: RoomStateObject[] = [
        {
          dbref: '#888',
          name: 'Golden Throne',
          thumbnail_url: '/images/throne_item.jpg',
          commands: ['examine', 'sit'],
        },
      ];
      const exits: RoomStateObject[] = [
        {
          dbref: '#999',
          name: 'Exit to Courtyard',
          thumbnail_url: null,
          commands: ['go'],
        },
      ];
      const scene: SceneSummary = {
        id: 123,
        name: 'The Coronation',
        description: 'A grand ceremony is underway',
        is_owner: false,
      };

      const payload: RoomStatePayload = { room, characters: [], objects, exits, scene };

      handleRoomStatePayload(character, payload, mockDispatch);

      expect(setSessionRoom).toHaveBeenCalledWith({
        character: 'Sir Lancelot',
        room: {
          id: 777,
          name: 'Castle Throne Room',
          description: '',
          thumbnail_url: '/images/throne.jpg',
          characters: [],
          objects,
          exits,
        },
      });

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Sir Lancelot',
        scene: {
          id: 123,
          name: 'The Coronation',
          description: 'A grand ceremony is underway',
          is_owner: false,
        },
      });
    });
  });
});
