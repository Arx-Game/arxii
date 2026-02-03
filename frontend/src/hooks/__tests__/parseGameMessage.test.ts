/**
 * Tests for parseGameMessage function
 *
 * Tests parsing of incoming WebSocket messages from the game server
 * into structured GameMessage objects.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { parseGameMessage } from '../parseGameMessage';
import { GAME_MESSAGE_TYPE, WS_MESSAGE_TYPE } from '../types';
import type { IncomingMessage } from '../types';

describe('parseGameMessage', () => {
  const MOCK_TIMESTAMP = 1700000000000;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(MOCK_TIMESTAMP);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('TEXT messages', () => {
    it('parses basic text message', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.TEXT, ['Hello world'], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Hello world');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.TEXT);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns CHANNEL type when from_channel is true', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.TEXT, ['Hello'], { from_channel: true }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Hello');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.CHANNEL);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns TEXT type when from_channel is false', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.TEXT, ['Hello'], { from_channel: false }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Hello');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.TEXT);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('handles empty text array by falling through to JSON stringify', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.TEXT, [], {}];

      const result = parseGameMessage(input);

      // Empty args array means the TEXT branch condition fails, falls through to else
      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('converts non-string content to string', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.TEXT, [12345], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe('12345');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.TEXT);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('handles missing kwargs (defaults to empty object)', () => {
      // TypeScript requires 3 elements, but runtime may have 2
      const input = [WS_MESSAGE_TYPE.TEXT, ['Hello']] as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe('Hello');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.TEXT);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });

  describe('LOGGED_IN messages', () => {
    it('returns fixed success content', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.LOGGED_IN, [], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Successfully logged in!');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('ignores args and kwargs', () => {
      const input: IncomingMessage = [
        WS_MESSAGE_TYPE.LOGGED_IN,
        ['ignored', 'data'],
        { also: 'ignored' },
      ];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Successfully logged in!');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });

  describe('VN_MESSAGE messages', () => {
    it('extracts text from kwargs', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.VN_MESSAGE, [], { text: 'Hello from VN' }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('Hello from VN');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ACTION);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns empty string when text is missing', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.VN_MESSAGE, [], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe('');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ACTION);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns empty string when text is null', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.VN_MESSAGE, [], { text: null }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ACTION);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns empty string when text is undefined', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.VN_MESSAGE, [], { text: undefined }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ACTION);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('converts non-string text to string', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.VN_MESSAGE, [], { text: 42 }];

      const result = parseGameMessage(input);

      expect(result.content).toBe('42');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ACTION);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });

  describe('MESSAGE_REACTION messages', () => {
    it('JSON stringifies kwargs', () => {
      const kwargs = { message_id: '123', reaction: 'thumbsup', actor: { name: 'Player' } };
      const input: IncomingMessage = [WS_MESSAGE_TYPE.MESSAGE_REACTION, [], kwargs];

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(kwargs));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('handles empty kwargs', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.MESSAGE_REACTION, [], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe('{}');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });

  describe('unknown message types', () => {
    it('falls through to JSON stringify for COMMANDS type', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.COMMANDS, [{ command: 'look' }], {}];

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('falls through to JSON stringify for ROOM_STATE type', () => {
      const input: IncomingMessage = [WS_MESSAGE_TYPE.ROOM_STATE, [], { room: { name: 'Test' } }];

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('falls through to JSON stringify for SCENE type', () => {
      const input: IncomingMessage = [
        WS_MESSAGE_TYPE.SCENE,
        [],
        { action: 'start', scene: { id: 1 } },
      ];

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('falls through to JSON stringify for COMMAND_ERROR type', () => {
      const input: IncomingMessage = [
        WS_MESSAGE_TYPE.COMMAND_ERROR,
        [],
        { command: 'foo', error: 'Unknown command' },
      ];

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.SYSTEM);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });

  describe('invalid formats', () => {
    it('returns ERROR type for non-array input (object)', () => {
      const input = { type: 'text', content: 'Hello' } as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for null input', () => {
      const input = null as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe('null');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for undefined input', () => {
      const input = undefined as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      // JSON.stringify(undefined) returns undefined, which becomes 'undefined' string
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for array with length < 2', () => {
      const input = ['text'] as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe(JSON.stringify(input));
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for empty array', () => {
      const input = [] as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe('[]');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for string input', () => {
      const input = 'Hello world' as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe('"Hello world"');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });

    it('returns ERROR type for number input', () => {
      const input = 42 as unknown as IncomingMessage;

      const result = parseGameMessage(input);

      expect(result.content).toBe('42');
      expect(result.type).toBe(GAME_MESSAGE_TYPE.ERROR);
      expect(result.timestamp).toBe(MOCK_TIMESTAMP);
    });
  });
});
