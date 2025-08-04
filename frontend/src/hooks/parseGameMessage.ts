import type { GameMessage, GameMessageType, IncomingMessage } from './types';
import { GAME_MESSAGE_TYPE, WS_MESSAGE_TYPE } from './types';

export function parseGameMessage(data: string): GameMessage {
  try {
    const parsed: IncomingMessage = JSON.parse(data);
    if (Array.isArray(parsed) && parsed.length >= 2) {
      const [msgType, args, kwargs = {}] = parsed;
      let content = '';
      let messageType: GameMessageType = GAME_MESSAGE_TYPE.SYSTEM;

      if (msgType === WS_MESSAGE_TYPE.TEXT && Array.isArray(args) && args.length > 0) {
        content = String(args[0]);
        messageType = (kwargs as Record<string, unknown>).from_channel
          ? GAME_MESSAGE_TYPE.CHANNEL
          : GAME_MESSAGE_TYPE.TEXT;
      } else if (msgType === WS_MESSAGE_TYPE.LOGGED_IN) {
        content = 'Successfully logged in!';
      } else {
        content = JSON.stringify(parsed);
      }

      return { content, timestamp: Date.now(), type: messageType };
    }
  } catch {
    // fall through to error case
  }

  return { content: data, timestamp: Date.now(), type: GAME_MESSAGE_TYPE.ERROR };
}
