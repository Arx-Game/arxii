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
  VN_MESSAGE: 'vn_message',
  MESSAGE_REACTION: 'message_reaction',
  COMMANDS: 'commands',
} as const;

export type SocketMessageType = (typeof WS_MESSAGE_TYPE)[keyof typeof WS_MESSAGE_TYPE];

export interface GameMessage {
  content: string;
  timestamp: number;
  type: GameMessageType;
}

export type IncomingMessage = [SocketMessageType, unknown[], Record<string, unknown>?];

export type OutgoingMessage = [typeof WS_MESSAGE_TYPE.TEXT, [string], Record<string, unknown>];

export interface VnMessagePayload {
  text: string;
  speaker: Record<string, unknown>;
  presentation: Record<string, unknown>;
  interaction: Record<string, unknown>;
  timing: Record<string, unknown>;
}

export interface MessageReactionPayload {
  message_id: string;
  reaction: string;
  actor: Record<string, unknown>;
  counts?: Record<string, number>;
}

export interface CommandPayload {
  command: string;
  params?: Record<string, unknown>;
}
