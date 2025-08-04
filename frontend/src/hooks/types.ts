export const GAME_MESSAGE_TYPE = {
  SYSTEM: 'system',
  CHAT: 'chat',
  ACTION: 'action',
  TEXT: 'text',
  CHANNEL: 'channel',
  ERROR: 'error',
} as const;

export type GameMessageType = (typeof GAME_MESSAGE_TYPE)[keyof typeof GAME_MESSAGE_TYPE];

export const WS_MESSAGE_TYPE = {
  TEXT: 'text',
  LOGGED_IN: 'logged_in',
} as const;

export type SocketMessageType = (typeof WS_MESSAGE_TYPE)[keyof typeof WS_MESSAGE_TYPE];

export interface GameMessage {
  content: string;
  timestamp: number;
  type: GameMessageType;
}

export type IncomingMessage = [SocketMessageType, unknown[], Record<string, unknown>?];

export type OutgoingMessage = [typeof WS_MESSAGE_TYPE.TEXT, [string], Record<string, unknown>];
