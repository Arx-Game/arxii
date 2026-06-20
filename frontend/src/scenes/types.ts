export interface RosterEntryRef {
  id: number;
  name: string;
  profile_url?: string;
}

export interface SceneParticipant {
  id: number;
  name: string;
  roster_entry?: RosterEntryRef | null;
}

export interface SceneParticipantRef extends SceneParticipant {
  roster_entry: RosterEntryRef;
}

export interface SceneSummary {
  id: number;
  name: string;
  participants: SceneParticipantRef[];
}

export interface SceneLocation {
  id: number;
  name: string;
}

export interface SceneListItem {
  id: number;
  name: string;
  description: string;
  date_started: string;
  location?: SceneLocation | null;
  participants: SceneParticipant[];
}

/** A persona present in a scene (has posed/participated) — the whisper-audience pool (#907). */
export interface ScenePersona {
  id: number;
  name: string;
  persona_type?: string;
}

/** Compact public representation of a room position (id + name). */
export interface PositionSummary {
  id: number;
  name: string;
}

/** Adjacency graph entry for one position. */
export interface PositionAdjacencyItem {
  position_id: number;
  adjacent_position_ids: number[];
}

/** A persona present in the scene and the position it currently occupies (or null). */
export interface PersonaPosition {
  persona_id: number;
  position: PositionSummary | null;
}

export interface SceneDetail extends SceneListItem {
  is_active: boolean;
  is_owner: boolean;
  /** True when the viewer is the scene GM/owner or has staff privileges. */
  viewer_can_gm: boolean;
  /** Personas reachable via the scene's interactions; the delivery-receiver pool. */
  personas?: ScenePersona[];
  /** Room positions defined for this scene's location (#1017). */
  positions: PositionSummary[];
  /** Adjacency graph — which positions are reachable from each position (#1017). */
  position_adjacency: PositionAdjacencyItem[];
  /** Current position for each persona in the scene (#1017). */
  persona_positions: PersonaPosition[];
}

export interface InteractionPersona {
  id: number;
  name: string;
  thumbnail_url?: string;
}

export interface EndorserBadge {
  persona_id: number;
  persona_name: string;
  thumbnail_url: string;
  resonance_id: number;
}

export interface InteractionReaction {
  emoji: string;
  count: number;
  reacted: boolean;
}

/** Minimal ACTION Interaction embedded inside an action-link chip. */
export interface InlineActionInteraction {
  id: number;
  content: string;
  mode: string;
  timestamp: string;
}

/** Bridge row linking a POSE Interaction to a linked ACTION Interaction. */
export interface ActionLink {
  id: number;
  ordering: number;
  action_interaction: InlineActionInteraction;
  /**
   * Cheap critical-outcome signal (#996): true when the linked action defeated
   * its focused opponent. Drives first-paint auto-expand of the detail panel.
   * Optional for fixture/cache leniency — absent is treated as non-critical.
   */
  has_critical_effect?: boolean;
}

/** One selectable reaction chip on a window (#904). */
export interface ReactionWindowChoice {
  slug: string;
  label: string;
}

/** One persona's recorded reaction (public kinds only). */
export interface WindowReactionRow {
  persona_id: number;
  persona_name: string;
  choice: string;
}

/** A reaction window attached to a scene event (#904). */
export interface ReactionWindowPayload {
  id: number;
  kind: string;
  is_open: boolean;
  public: boolean;
  choices: ReactionWindowChoice[];
  reactions: WindowReactionRow[];
  counts: Record<string, number>;
  my_reaction: string | null;
}

/** Compact dramatic-moment tag embedded in interaction payloads (#1139). */
export interface DramaticMomentTagSummary {
  moment_type_label: string;
  character_sheet_id: number | null;
}

export interface Interaction {
  id: number;
  persona: InteractionPersona;
  content: string;
  mode: string;
  visibility: string;
  timestamp: string;
  scene: number | null;
  reactions: InteractionReaction[];
  /** Reaction windows on this event (#904); absent/empty for most rows. */
  reaction_windows?: ReactionWindowPayload[];
  is_favorited: boolean;
  place: number | null;
  place_name: string | null;
  /** IDs of personas permitted to see this interaction (access control — whispers, place-scoped). */
  receiver_persona_ids: number[];
  /** IDs of personas this action is directed at (threading/narrative — visible to everyone). */
  target_persona_ids: number[];
  /** ACTION Interactions linked to this POSE (populated only for POSE-mode rows). */
  action_links?: ActionLink[];
  /** Dramatic-moment tags on this interaction (#1139); absent/empty for untagged rows. */
  dramatic_moment_tags?: DramaticMomentTagSummary[];
  /** Classifies the pose for entry-endorsement filtering. Matches PoseKind TextChoices (lowercase wire format). */
  pose_kind: 'standard' | 'entry' | 'departure';
  endorsee_sheet_id: number | null;
  endorsable_resonances: { id: number; name: string }[];
  pose_endorsers: EndorserBadge[];
  my_pose_endorsement: { id: number; resonance_id: number; settled: boolean } | null;
  entry_endorsers: EndorserBadge[];
  entry_endorsed_by_me: boolean;
}

/** The single featured (fully sealed) moment of a scene's highlight reel (#1241). */
export interface HighlightReelFeatured {
  interaction_id: number;
}

/** One sealed, ranked entry in the index below the featured moment (#1241). */
export interface HighlightReelEntry {
  interaction_id: number;
  rank: number;
}

/**
 * A scene's highlight reel (#1241): a sealed featured moment + a ranked index.
 * `featured` is null when the scene has no tagged moments and no reacted poses
 * (an empty reel — the section is hidden). The payload carries ids only; a pose
 * is revealed by fetching the interaction-detail endpoint on demand.
 */
export interface HighlightReel {
  featured: HighlightReelFeatured | null;
  index: HighlightReelEntry[];
}
