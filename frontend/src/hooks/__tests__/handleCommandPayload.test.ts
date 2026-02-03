/**
 * Tests for handleCommandPayload function
 *
 * Tests the dispatch of command specifications to the Redux store,
 * including command array handling and character name processing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleCommandPayload } from '../handleCommandPayload';
import { setSessionCommands } from '@/store/gameSlice';
import { store } from '@/store/store';
import type { CommandSpec, ParamSchema } from '@/game/types';

vi.mock('@/store/store', () => ({
  store: {
    dispatch: vi.fn(),
  },
}));

vi.mock('@/store/gameSlice', () => ({
  setSessionCommands: vi.fn((payload) => ({ type: 'game/setSessionCommands', payload })),
}));

describe('handleCommandPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const createCommandSpec = (
    action: string,
    prompt: string,
    params_schema: Record<string, ParamSchema> = {},
    icon: string = 'default-icon',
    options: Partial<Omit<CommandSpec, 'action' | 'prompt' | 'params_schema' | 'icon'>> = {}
  ): CommandSpec => ({
    action,
    prompt,
    params_schema,
    icon,
    ...options,
  });

  describe('basic command dispatch', () => {
    it('dispatches commands for character', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [createCommandSpec('look', 'Look around')];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands,
      });
      expect(store.dispatch).toHaveBeenCalledTimes(1);
    });

    it('commands array is passed through correctly', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [
        createCommandSpec('look', 'Look around', {}, 'eye-icon'),
        createCommandSpec('move', 'Move to location', {}, 'foot-icon'),
      ];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands,
      });
    });

    it('dispatches the correct action type', () => {
      const character = 'TestChar';
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test command')];

      handleCommandPayload(character, commands);

      const dispatchedAction = (store.dispatch as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][0];
      expect(dispatchedAction.type).toBe('game/setSessionCommands');
    });

    it('calls dispatch exactly once per call', () => {
      handleCommandPayload('Char1', [createCommandSpec('cmd1', 'Command 1')]);
      handleCommandPayload('Char2', [createCommandSpec('cmd2', 'Command 2')]);

      expect(store.dispatch).toHaveBeenCalledTimes(2);
    });
  });

  describe('character name handling', () => {
    it('character name is passed correctly', () => {
      const commands: CommandSpec[] = [createCommandSpec('look', 'Look around')];

      handleCommandPayload('Sir Galahad', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Sir Galahad',
        })
      );
    });

    it('handles character names with spaces', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload('Lady Morgana of the Lake', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Lady Morgana of the Lake',
        })
      );
    });

    it('handles character names with special characters', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload("O'Brien the Third", commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: "O'Brien the Third",
        })
      );
    });

    it('handles character names with numbers', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload('Knight42', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Knight42',
        })
      );
    });

    it('handles empty character name', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload('', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: '',
        })
      );
    });

    it('handles single character name', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload('X', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'X',
        })
      );
    });

    it('handles long character name', () => {
      const longName = 'A'.repeat(200);
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload(longName, commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: longName,
        })
      );
    });

    it('handles character names with unicode characters', () => {
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test')];

      handleCommandPayload('Naomi', commands);

      expect(setSessionCommands).toHaveBeenCalledWith(
        expect.objectContaining({
          character: 'Naomi',
        })
      );
    });
  });

  describe('commands array handling', () => {
    it('handles empty commands array', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [],
      });
    });

    it('handles single command', () => {
      const character = 'TestCharacter';
      const command = createCommandSpec('look', 'Look around', {}, 'eye');
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [command],
      });
    });

    it('handles multiple commands', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [
        createCommandSpec('look', 'Look around', {}, 'eye'),
        createCommandSpec('move', 'Move to location', {}, 'foot'),
        createCommandSpec('say', 'Say something', {}, 'speech'),
      ];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands,
      });
      expect(
        (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0].commands
      ).toHaveLength(3);
    });

    it('handles commands with all fields populated', () => {
      const character = 'TestCharacter';
      const paramsSchema: Record<string, ParamSchema> = {
        target: {
          type: 'string',
          required: true,
          match: '^[a-zA-Z]+$',
          widget: 'text',
        },
        amount: {
          type: 'integer',
          required: false,
          widget: 'number',
          options_endpoint: '/api/amounts/',
        },
      };
      const command: CommandSpec = {
        action: 'give',
        prompt: 'Give item to target',
        params_schema: paramsSchema,
        icon: 'gift-icon',
        name: 'Give Item',
        category: 'interaction',
        help: 'Use this command to give an item to another character.',
      };
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [
          {
            action: 'give',
            prompt: 'Give item to target',
            params_schema: paramsSchema,
            icon: 'gift-icon',
            name: 'Give Item',
            category: 'interaction',
            help: 'Use this command to give an item to another character.',
          },
        ],
      });
    });

    it('handles commands with empty params_schema', () => {
      const character = 'TestCharacter';
      const command = createCommandSpec('simple', 'A simple command', {}, 'simple-icon');
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [
          expect.objectContaining({
            params_schema: {},
          }),
        ],
      });
    });

    it('handles commands with complex params_schema', () => {
      const character = 'TestCharacter';
      const paramsSchema: Record<string, ParamSchema> = {
        target: {
          type: 'object',
          required: true,
          widget: 'select',
          options_endpoint: '/api/targets/',
        },
        message: { type: 'string', required: true, match: '.+' },
        silent: { type: 'boolean', required: false },
      };
      const command = createCommandSpec(
        'whisper',
        'Whisper to someone',
        paramsSchema,
        'whisper-icon'
      );
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [
          expect.objectContaining({
            params_schema: paramsSchema,
          }),
        ],
      });
    });

    it('handles large number of commands', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = Array.from({ length: 100 }, (_, i) =>
        createCommandSpec(`action_${i}`, `Command ${i}`, {}, `icon_${i}`)
      );

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands,
      });
      expect(
        (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0].commands
      ).toHaveLength(100);
    });

    it('handles commands with optional fields undefined', () => {
      const character = 'TestCharacter';
      const command: CommandSpec = {
        action: 'minimal',
        prompt: 'Minimal command',
        params_schema: {},
        icon: 'min-icon',
        // name, category, help are optional and not provided
      };
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [command],
      });
    });

    it('handles commands with all optional fields populated', () => {
      const character = 'TestCharacter';
      const command: CommandSpec = {
        action: 'full',
        prompt: 'Full command',
        params_schema: { param: { type: 'string', required: true } },
        icon: 'full-icon',
        name: 'Full Command Name',
        category: 'testing',
        help: 'This is a complete help text for the command.',
      };
      const commands: CommandSpec[] = [command];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'TestCharacter',
        commands: [
          expect.objectContaining({
            name: 'Full Command Name',
            category: 'testing',
            help: 'This is a complete help text for the command.',
          }),
        ],
      });
    });

    it('preserves command order', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [
        createCommandSpec('first', 'First command'),
        createCommandSpec('second', 'Second command'),
        createCommandSpec('third', 'Third command'),
      ];

      handleCommandPayload(character, commands);

      const dispatchedCommands = (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][0].commands;
      expect(dispatchedCommands[0].action).toBe('first');
      expect(dispatchedCommands[1].action).toBe('second');
      expect(dispatchedCommands[2].action).toBe('third');
    });
  });

  describe('complete integration scenarios', () => {
    it('handles typical game command set', () => {
      const character = 'Adventurer';
      const commands: CommandSpec[] = [
        {
          action: 'look',
          prompt: 'Look at your surroundings',
          params_schema: {},
          icon: 'eye',
          name: 'Look',
          category: 'navigation',
          help: 'Examine your current location and see what is around you.',
        },
        {
          action: 'move',
          prompt: 'Move in a direction',
          params_schema: {
            direction: {
              type: 'string',
              required: true,
              widget: 'select',
              options_endpoint: '/api/exits/',
            },
          },
          icon: 'footsteps',
          name: 'Move',
          category: 'navigation',
          help: 'Travel through an available exit.',
        },
        {
          action: 'say',
          prompt: 'Say something',
          params_schema: {
            message: { type: 'string', required: true, match: '.+' },
          },
          icon: 'chat-bubble',
          name: 'Say',
          category: 'communication',
          help: 'Speak out loud for everyone in the room to hear.',
        },
      ];

      handleCommandPayload(character, commands);

      expect(setSessionCommands).toHaveBeenCalledWith({
        character: 'Adventurer',
        commands,
      });
    });

    it('handles command update scenario (replacing existing commands)', () => {
      const character = 'TestCharacter';

      // First command set
      const initialCommands: CommandSpec[] = [createCommandSpec('look', 'Look around')];
      handleCommandPayload(character, initialCommands);

      // Updated command set (simulating entering a new room with different commands)
      const updatedCommands: CommandSpec[] = [
        createCommandSpec('look', 'Look around'),
        createCommandSpec('unlock', 'Unlock the chest'),
        createCommandSpec('open', 'Open the door'),
      ];
      handleCommandPayload(character, updatedCommands);

      // Verify both dispatches happened
      expect(store.dispatch).toHaveBeenCalledTimes(2);

      // Verify the second call had the updated commands
      const secondCall = (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock
        .calls[1][0];
      expect(secondCall.commands).toHaveLength(3);
      expect(secondCall.commands[1].action).toBe('unlock');
    });

    it('handles multiple characters with different command sets', () => {
      const char1Commands: CommandSpec[] = [
        createCommandSpec('cast', 'Cast a spell', { spell: { type: 'string', required: true } }),
      ];
      const char2Commands: CommandSpec[] = [
        createCommandSpec('attack', 'Attack an enemy', {
          target: { type: 'string', required: true },
        }),
      ];

      handleCommandPayload('Wizard', char1Commands);
      handleCommandPayload('Warrior', char2Commands);

      const calls = (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls[0][0]).toEqual({ character: 'Wizard', commands: char1Commands });
      expect(calls[1][0]).toEqual({ character: 'Warrior', commands: char2Commands });
    });
  });

  describe('payload structure validation', () => {
    it('dispatches action with correct payload structure', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test command')];

      handleCommandPayload(character, commands);

      const dispatchedAction = (store.dispatch as unknown as ReturnType<typeof vi.fn>).mock
        .calls[0][0];
      expect(dispatchedAction).toHaveProperty('type', 'game/setSessionCommands');
      expect(dispatchedAction).toHaveProperty('payload');
      expect(dispatchedAction.payload).toHaveProperty('character', 'TestCharacter');
      expect(dispatchedAction.payload).toHaveProperty('commands');
    });

    it('payload contains exact commands array reference', () => {
      const character = 'TestCharacter';
      const commands: CommandSpec[] = [createCommandSpec('test', 'Test command')];

      handleCommandPayload(character, commands);

      const payload = (setSessionCommands as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(payload.commands).toBe(commands);
    });
  });
});
