export const GAME_MESSAGE_TYPE = {
  SYSTEM: 'system',
  CHAT: 'chat',
  ACTION: 'action',
  TEXT: 'text',
  CHANNEL: 'channel',
  ERROR: 'error',
  NARRATIVE: 'narrative',
  GEMIT: 'gemit',
} as const;

export type GameMessageType = (typeof GAME_MESSAGE_TYPE)[keyof typeof GAME_MESSAGE_TYPE];

export const WS_MESSAGE_TYPE = {
  TEXT: 'text',
  LOGGED_IN: 'logged_in',
  VN_MESSAGE: 'vn_message',
  MESSAGE_REACTION: 'message_reaction',
  COMMANDS: 'commands',
  ROOM_STATE: 'room_state',
  SCENE: 'scene',
  COMMAND_ERROR: 'command_error',
  ROULETTE_RESULT: 'roulette_result',
  INTERACTION: 'interaction',
  PUPPET_CHANGED: 'puppet_changed',
  /** Inbound: result of an `execute_action` invocation. */
  ACTION_RESULT: 'action_result',
  /** Outbound: invoke a registered action by name with kwargs. */
  EXECUTE_ACTION: 'execute_action',
} as const;

export type SocketMessageType = (typeof WS_MESSAGE_TYPE)[keyof typeof WS_MESSAGE_TYPE];

export interface GameMessage {
  content: string;
  timestamp: number;
  type: GameMessageType;
}

export type IncomingMessage = [SocketMessageType, unknown[], Record<string, unknown>?];

export type OutgoingMessage =
  | [typeof WS_MESSAGE_TYPE.TEXT, [string], Record<string, unknown>]
  | [
      typeof WS_MESSAGE_TYPE.EXECUTE_ACTION,
      [],
      { action: string; kwargs: Record<string, unknown> },
    ];

/**
 * Result payload for an `execute_action` round-trip. Mirrors the dataclass
 * returned by the backend's action dispatcher: success indicates whether the
 * service succeeded, message is a human-readable string (may be null when the
 * action has no message), and data carries any structured payload the action
 * elects to return.
 */
export interface ActionResultPayload {
  success: boolean;
  message: string | null;
  data: Record<string, unknown> | null;
}

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

export type CommandsPayload = CommandPayload[];

export interface RoomStateObject {
  dbref: string;
  name: string;
  thumbnail_url: string | null;
  commands: string[];
  description?: string;
}

export interface RoomStatePayload {
  room: RoomStateObject;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  scene?: SceneSummary | null;
}

export interface SceneSummary {
  id: number;
  name: string;
  description: string;
  is_owner: boolean;
}

export interface ScenePayload {
  action: 'start' | 'update' | 'end';
  scene: SceneSummary;
}

export interface CommandErrorPayload {
  command: string;
  error: string;
}

export interface InteractionWsPayload {
  id: number;
  persona: { id: number; name: string; thumbnail_url: string };
  content: string;
  mode: string;
  timestamp: string;
  scene_id: number | null;
  place_id: number | null;
  place_name: string | null;
  receiver_persona_ids: number[];
  target_persona_ids: number[];
}
