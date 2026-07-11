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
  /** Inbound: slim ping — a battle's round transitioned; clients refetch the REST aggregate. */
  BATTLE_STATE: 'battle_state',
  INTERACTION: 'interaction',
  PUPPET_CHANGED: 'puppet_changed',
  /** Inbound: result of an `execute_action` invocation. */
  ACTION_RESULT: 'action_result',
  /** Outbound: invoke a registered action by name with kwargs. */
  EXECUTE_ACTION: 'execute_action',
  /** Inbound: someone applauded your content; anonymous. */
  KUDOS_RECEIVED: 'kudos_received',
  /** Inbound: a new letter arrived for one of the recipient's tenures (#2160). */
  MAIL_ARRIVED: 'mail_arrived',
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
  /** Whether the viewing character's active persona owns this room (#1470). */
  is_owner?: boolean;
  /** Whether the room is publicly listed (the editor's privacy toggle state). */
  is_public?: boolean;
}

/** One local tiding carried by a room's civic-hub feature (#1450). */
export interface HubTidingsItem {
  /** Feed row kind: 'DEED' or 'SCANDAL'. */
  kind: string;
  headline: string;
  subject: string;
  /** Authored scandal-category label ("Treacherous Scandal") when the row carries one. */
  category: string | null;
  occurred_at: string;
}

/** The room's civic-hub tidings block: present only where a board/crier stands (#1450). */
export interface HubTidings {
  /** Feature strategy: 'NOTICE_BOARD' or 'TOWN_CRIER'. */
  kind: string;
  /** The feature kind's display name ("Notice Board", "Town Crier"). */
  name: string;
  items: HubTidingsItem[];
}

export interface RoomStatePayload {
  room: RoomStateObject;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  scene?: SceneSummary | null;
  hub?: HubTidings | null;
}

export interface SceneSummary {
  id: number;
  name: string;
  description: string;
  is_owner: boolean;
  has_unseen_observer: boolean;
}

export interface ScenePayload {
  action: 'start' | 'update' | 'end';
  scene: SceneSummary;
}

export interface CommandErrorPayload {
  command: string;
  error: string;
}

/**
 * Payload for `kudos_received` messages — anonymous by design (ADR-0033).
 * Carries no giver identity: `description` is the audited, already-anonymized
 * text from the KudosTransaction; `source_category` is the applause axis
 * (pose chip, writeup commend, weekly engagement, spread-assist).
 */
export interface KudosReceivedPayload {
  amount: number;
  source_category: string;
  description: string;
 * Slim arrival ping for `mail_arrived` messages (#2160). Anonymity boundary:
 * `sender_display` is the sender tenure's display name only, never an
 * account id/username. Carries no mail body — clients refetch the mail list
 * / unread count on receipt.
 */
export interface MailArrivedPayload {
  mail_id: number;
  sender_display: string;
  subject: string;
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
