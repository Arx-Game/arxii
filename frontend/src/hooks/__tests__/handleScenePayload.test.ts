/**
 * Tests for handleScenePayload function
 *
 * Tests the transformation of WebSocket scene payloads into Redux actions,
 * including scene start, update, and end actions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleScenePayload } from '../handleScenePayload';
import { setSessionScene } from '@/store/gameSlice';
import type { ScenePayload, SceneSummary } from '../types';
import type { AppDispatch } from '@/store/store';

vi.mock('@/store/gameSlice', () => ({
  setSessionScene: vi.fn((payload) => ({ type: 'game/setSessionScene', payload })),
}));

describe('handleScenePayload', () => {
  let mockDispatch: AppDispatch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch = vi.fn() as unknown as AppDispatch;
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

  describe('scene start action', () => {
    it('dispatches scene data when action is start', () => {
      const character = 'TestCharacter';
      const scene = createSceneSummary(1, 'Starting Scene', 'A new adventure begins', false);
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestCharacter',
        scene,
      });
      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('preserves scene summary correctly on start', () => {
      const character = 'Knight';
      const scene: SceneSummary = {
        id: 42,
        name: 'The Quest Begins',
        description: 'Our heroes gather at the tavern',
        is_owner: true,
      };
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Knight',
        scene: {
          id: 42,
          name: 'The Quest Begins',
          description: 'Our heroes gather at the tavern',
          is_owner: true,
        },
      });
    });
  });

  describe('scene update action', () => {
    it('dispatches scene data when action is update', () => {
      const character = 'TestCharacter';
      const scene = createSceneSummary(1, 'Updated Scene', 'The plot thickens', false);
      const payload: ScenePayload = {
        action: 'update',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestCharacter',
        scene,
      });
      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('passes updated scene fields through correctly', () => {
      const character = 'Mage';
      const scene: SceneSummary = {
        id: 100,
        name: 'Battle Scene - Round 2',
        description: 'The battle intensifies as reinforcements arrive',
        is_owner: false,
      };
      const payload: ScenePayload = {
        action: 'update',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Mage',
        scene: {
          id: 100,
          name: 'Battle Scene - Round 2',
          description: 'The battle intensifies as reinforcements arrive',
          is_owner: false,
        },
      });
    });

    it('handles owner change on update', () => {
      const character = 'Rogue';
      const scene = createSceneSummary(50, 'Heist Scene', 'Taking over the operation', true);
      const payload: ScenePayload = {
        action: 'update',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Rogue',
        scene: expect.objectContaining({
          is_owner: true,
        }),
      });
    });
  });

  describe('scene end action', () => {
    it('dispatches null for scene when action is end', () => {
      const character = 'TestCharacter';
      const scene = createSceneSummary(1, 'Ending Scene', 'The adventure concludes', false);
      const payload: ScenePayload = {
        action: 'end',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestCharacter',
        scene: null,
      });
      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('dispatches null even when payload.scene has data', () => {
      const character = 'Warrior';
      const scene: SceneSummary = {
        id: 999,
        name: 'Final Battle',
        description: 'The epic conclusion',
        is_owner: true,
      };
      const payload: ScenePayload = {
        action: 'end',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Warrior',
        scene: null,
      });
    });

    it('ignores scene data completely when ending', () => {
      const character = 'Archer';
      const payload: ScenePayload = {
        action: 'end',
        scene: {
          id: 12345,
          name: 'Should Be Ignored',
          description: 'This entire scene should be ignored',
          is_owner: true,
        },
      };

      handleScenePayload(character, payload, mockDispatch);

      const calls = (setSessionScene as unknown as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.length).toBe(1);
      expect(calls[0][0].scene).toBeNull();
    });
  });

  describe('character name handling', () => {
    it('passes character name correctly to setSessionScene', () => {
      const payload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleScenePayload('Sir Galahad', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Sir Galahad',
        })
      );
    });

    it('handles character names with special characters', () => {
      const payload: ScenePayload = {
        action: 'update',
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleScenePayload("O'Brien the Third", payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: "O'Brien the Third",
        })
      );
    });

    it('handles character names with spaces', () => {
      const payload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleScenePayload('Lady Morgana of the Lake', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Lady Morgana of the Lake',
        })
      );
    });

    it('handles empty character name', () => {
      const payload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleScenePayload('', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith(
        expect.objectContaining({
          character: '',
        })
      );
    });

    it('preserves character name on end action', () => {
      const payload: ScenePayload = {
        action: 'end',
        scene: createSceneSummary(1, 'Test Scene'),
      };

      handleScenePayload('Heroic Knight', payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Heroic Knight',
        scene: null,
      });
    });
  });

  describe('scene summary preservation', () => {
    it('preserves all scene fields on start action', () => {
      const character = 'TestChar';
      const scene: SceneSummary = {
        id: 777,
        name: 'Complete Scene',
        description: 'A scene with all fields populated',
        is_owner: true,
      };
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: {
          id: 777,
          name: 'Complete Scene',
          description: 'A scene with all fields populated',
          is_owner: true,
        },
      });
    });

    it('preserves all scene fields on update action', () => {
      const character = 'TestChar';
      const scene: SceneSummary = {
        id: 888,
        name: 'Updated Complete Scene',
        description: 'An updated scene with all fields',
        is_owner: false,
      };
      const payload: ScenePayload = {
        action: 'update',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: {
          id: 888,
          name: 'Updated Complete Scene',
          description: 'An updated scene with all fields',
          is_owner: false,
        },
      });
    });

    it('handles scene with empty description', () => {
      const character = 'TestChar';
      const scene: SceneSummary = {
        id: 50,
        name: 'Minimal Scene',
        description: '',
        is_owner: false,
      };
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: expect.objectContaining({
          description: '',
        }),
      });
    });

    it('handles scene with id of 0', () => {
      const character = 'TestChar';
      const scene: SceneSummary = {
        id: 0,
        name: 'Zero ID Scene',
        description: 'A scene with id 0',
        is_owner: false,
      };
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: expect.objectContaining({
          id: 0,
        }),
      });
    });

    it('handles scene with large id', () => {
      const character = 'TestChar';
      const scene: SceneSummary = {
        id: 2147483647,
        name: 'Large ID Scene',
        description: 'A scene with a very large id',
        is_owner: true,
      };
      const payload: ScenePayload = {
        action: 'update',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: expect.objectContaining({
          id: 2147483647,
        }),
      });
    });

    it('handles scene with long name and description', () => {
      const character = 'TestChar';
      const longName = 'A'.repeat(200);
      const longDescription = 'B'.repeat(1000);
      const scene: SceneSummary = {
        id: 99,
        name: longName,
        description: longDescription,
        is_owner: false,
      };
      const payload: ScenePayload = {
        action: 'start',
        scene,
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'TestChar',
        scene: expect.objectContaining({
          name: longName,
          description: longDescription,
        }),
      });
    });
  });

  describe('dispatch behavior', () => {
    it('calls dispatch exactly once for start action', () => {
      const payload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(1, 'Test'),
      };

      handleScenePayload('Char', payload, mockDispatch);

      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('calls dispatch exactly once for update action', () => {
      const payload: ScenePayload = {
        action: 'update',
        scene: createSceneSummary(1, 'Test'),
      };

      handleScenePayload('Char', payload, mockDispatch);

      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('calls dispatch exactly once for end action', () => {
      const payload: ScenePayload = {
        action: 'end',
        scene: createSceneSummary(1, 'Test'),
      };

      handleScenePayload('Char', payload, mockDispatch);

      expect(mockDispatch).toHaveBeenCalledTimes(1);
    });

    it('dispatches the correct action type', () => {
      const payload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(1, 'Test'),
      };

      handleScenePayload('Char', payload, mockDispatch);

      const dispatchedAction = (mockDispatch as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][0];
      expect(dispatchedAction.type).toBe('game/setSessionScene');
    });
  });

  describe('complete integration scenarios', () => {
    it('handles full scene lifecycle: start -> update -> end', () => {
      const character = 'Adventure Hero';

      // Start scene
      const startPayload: ScenePayload = {
        action: 'start',
        scene: createSceneSummary(10, 'Chapter 1', 'The journey begins', false),
      };
      handleScenePayload(character, startPayload, mockDispatch);

      expect(setSessionScene).toHaveBeenLastCalledWith({
        character: 'Adventure Hero',
        scene: expect.objectContaining({
          id: 10,
          name: 'Chapter 1',
        }),
      });

      // Update scene
      const updatePayload: ScenePayload = {
        action: 'update',
        scene: createSceneSummary(10, 'Chapter 1 - Part 2', 'The plot thickens', true),
      };
      handleScenePayload(character, updatePayload, mockDispatch);

      expect(setSessionScene).toHaveBeenLastCalledWith({
        character: 'Adventure Hero',
        scene: expect.objectContaining({
          id: 10,
          name: 'Chapter 1 - Part 2',
          is_owner: true,
        }),
      });

      // End scene
      const endPayload: ScenePayload = {
        action: 'end',
        scene: createSceneSummary(10, 'Chapter 1 - Part 2', 'The plot thickens', true),
      };
      handleScenePayload(character, endPayload, mockDispatch);

      expect(setSessionScene).toHaveBeenLastCalledWith({
        character: 'Adventure Hero',
        scene: null,
      });

      expect(mockDispatch).toHaveBeenCalledTimes(3);
    });

    it('handles complete payload with owner status true', () => {
      const character = 'Scene Master';
      const payload: ScenePayload = {
        action: 'start',
        scene: {
          id: 500,
          name: 'Grand Performance',
          description: 'A theatrical production in the great hall',
          is_owner: true,
        },
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Scene Master',
        scene: {
          id: 500,
          name: 'Grand Performance',
          description: 'A theatrical production in the great hall',
          is_owner: true,
        },
      });
    });

    it('handles complete payload with owner status false', () => {
      const character = 'Scene Participant';
      const payload: ScenePayload = {
        action: 'start',
        scene: {
          id: 501,
          name: 'Grand Performance',
          description: 'A theatrical production in the great hall',
          is_owner: false,
        },
      };

      handleScenePayload(character, payload, mockDispatch);

      expect(setSessionScene).toHaveBeenCalledWith({
        character: 'Scene Participant',
        scene: {
          id: 501,
          name: 'Grand Performance',
          description: 'A theatrical production in the great hall',
          is_owner: false,
        },
      });
    });
  });
});
