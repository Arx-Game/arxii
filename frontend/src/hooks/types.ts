import type { FeedKind } from '@/game/feedKinds';

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
  /** Inbound: an environmental hazard entered a damaging stage; show the response card (#2846). */
  HAZARD_PROMPT: 'hazard_prompt',
  REQUEST_ROOM_STATE: 'request_room_state',
  STATE_RESYNC: 'state_resync',
  STATE_RESYNC_ERROR: 'state_resync_error',
  /** Outbound: puppet a character on this socket's session (#3933). */
  PUPPET: 'puppet',
  /** Inbound: the death condolence line, kwargs `{character, body}` (#3933). */
  CHARACTER_DIED: 'character_died',
  /** Inbound: an estate settlement opened; the REST view owns it (#3933). */
  ESTATE_SETTLEMENT_OPENED: 'estate_settlement_opened',
  /** Inbound: Evennia's own out-of-band echo (#3933). */
  OOB: 'oob',
  /** Inbound: Evennia's client-settings frame (#3933). */
  WEBCLIENT_OPTIONS: 'webclient_options',
} as const;

export type SocketMessageType = (typeof WS_MESSAGE_TYPE)[keyof typeof WS_MESSAGE_TYPE];

/** Evennia's own client-protocol frames; no Arx meaning, never story content (#3933). */
export const EVENNIA_CONTROL_TYPES: ReadonlySet<string> = new Set([
  'channel',
  'ping',
  'heartbeat',
  'reconnect',
  'nickname',
  'subscribe',
  'unsubscribe',
  'repeat',
  'monitored',
  'send',
  'role',
  'session',
  'privmsg',
  'request_nicklist',
  'reportable_variables',
  'reported_variables',
  'sendable_variables',
]);

export interface GameMessage {
  content: string;
  timestamp: number;
  type: GameMessageType;
}

/**
 * One typed text line in the feed (#3856): a look result, an item line, an
 * error, an arrival or departure, a narrative emit, or a plain system line.
 * Built by the socket hook from a `text` frame and its `kwargs.type`
 * (`game/feedKinds.ts` maps the wire type to the kind); rendered by both
 * readers at its timestamp among the interactions.
 */
export interface FeedNote {
  id: string;
  kind: FeedKind;
  content: string;
  /** What a look was at, when the server names it (`kwargs.subject`). */
  subject?: string;
  /** ISO-8601, client clock at receipt; sorts as a string against interaction timestamps. */
  timestamp: string;
}

/**
 * One line of the staff console (#3857): the Commands-mode line as sent
 * (`sent`), or what the server said back to it.
 */
export interface ConsoleLine {
  id: string;
  content: string;
  /** The staff member's own line, echoed above its answers. */
  sent?: boolean;
  timestamp: string;
}

export type IncomingMessage = [SocketMessageType, unknown[], Record<string, unknown>?];

export type OutgoingMessage =
  | [typeof WS_MESSAGE_TYPE.TEXT, [string], Record<string, unknown>]
  | [typeof WS_MESSAGE_TYPE.EXECUTE_ACTION, [], { action: string; kwargs: Record<string, unknown> }]
  | [typeof WS_MESSAGE_TYPE.REQUEST_ROOM_STATE, [], { client_request_id: string }]
  | [typeof WS_MESSAGE_TYPE.PUPPET, [], { character: string }];

/**
 * Result payload for an `execute_action` round-trip. Mirrors the dataclass
 * returned by the backend's action dispatcher: success indicates whether the
 * service succeeded, message is a human-readable string (may be null when the
 * action has no message), and data carries any structured payload the action
 * elects to return. `client_request_id` echoes the id the dispatching client
 * sent in its `kwargs`, when it sent one (#3781) — a listener that tracks a
 * specific dispatch should compare this against its own id rather than
 * assuming the next `action_result` event on the bus is theirs.
 */
export interface ActionResultPayload {
  success: boolean;
  message: string | null;
  data: Record<string, unknown> | null;
  client_request_id?: string | null;
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
  /** Whether this object has an active BOARD-kind MissionGiver bound to it (#3044). */
  is_mission_board?: boolean;
  /** The Place this character currently occupies, if any (#3810). Only ever set on `characters` entries. */
  place_id?: number | null;
  /**
   * Whether this character has entered the room's live scene (#3867): false at the
   * threshold (present, no line of their own yet), null with no live scene. Only ever
   * set on `characters` entries.
   */
  in_scene?: boolean | null;
}

/** An active class-1+ NPC placement (Functionary) standing in this room (#3044). */
export interface NpcGiver {
  /** The NPCRole pk — the kwarg `startInteraction`/`NPCInteractionDialog` expect. */
  role_id: number;
  name: string;
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
  /** The hub's area pk — anchors the public wanted board (#1826); null when unareaed. */
  area_id?: number | null;
  items: HubTidingsItem[];
}

export interface RoomStatePayload {
  room: RoomStateObject;
  /** Server revision used to reject stale same-socket snapshots. */
  state_epoch?: string;
  state_sequence?: number;
  /** Correlates a targeted resync snapshot with its acknowledgement. */
  resync_request_id?: string;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  /** The caller's own current Place, if any (#3810); excluded from `characters` by design. */
  viewer_place_id?: number | null;
  scene?: SceneSummary | null;
  hub?: HubTidings | null;
  /** Active NPC placements in this room (#3044); absent/empty when none stand here. */
  npc_givers?: NpcGiver[];
  /** Placed decoration names, oldest first (#2991) — decor legible in scenes. */
  decorations?: string[];
  /** The room's bare 1-10 comfort level (#2991), no per-character offset. */
  comfort_level?: number;
  /**
   * #3288 — mandatory OOC disclosure: true when ANY occupant is concealed
   * (sneaking, invisible, whatever). Identity-free by construction; room-derived,
   * so it works with or without an active scene.
   */
  has_unseen_presence?: boolean;
}

export interface SceneSummary {
  id: number;
  name: string;
  description: string;
  is_owner: boolean;
  has_unseen_observer: boolean;
  /** Whether the viewing character has entered this scene (#3867); false until their first line. */
  viewer_entered?: boolean;
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
}

/**
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

/**
 * An environmental-hazard condition (sunlight bane/allergy, #2846) crossed
 * into a damaging stage. `endure_action`/`retreat_action` are action keys the
 * client dispatches through the normal action-dispatch endpoint; cover-up and
 * seek-shade route to existing wardrobe / room surfaces.
 */
export interface HazardPromptPayload {
  character_id: number;
  condition_name: string;
  stage_name: string;
  severity: number;
  player_text: string;
  endure_action: string;
  retreat_action: string;
}

export interface InteractionWsPayload {
  id: number;
  persona: { id: number; name: string; thumbnail_url: string };
  content: string;
  /** The whole sentence for this viewer (#3858), the actor in the line; see `Interaction.line`. */
  line?: string;
  mode: string;
  timestamp: string;
  scene_id: number | null;
  place_id: number | null;
  place_name: string | null;
  receiver_persona_ids: number[];
  target_persona_ids: number[];
  /** Explicit narrative topology when supplied by the play protocol. */
  thread_id?: string | null;
  /** Top of the nesting tree this row's exchange belongs to (#3787). */
  root_thread_id?: string | null;
  reply_to?: { id: string; timestamp: string } | null;
  /** Cosmetic companion pose attribution (#3294); null/absent for a normal pose. */
  attributed_companion_id?: number | null;
  attributed_companion_name?: string | null;
}
