import type { Gender } from '@/world/character_sheets/types';
import type { components } from '@/generated/api';

export interface MyRosterEntry {
  id: number;
  name: CharacterData['name'];
  /**
   * The underlying ObjectDB pk for the character. Doubles as the
   * character_sheet pk because CharacterSheet uses primary_key=True
   * on its OneToOne to ObjectDB.
   */
  character_id: number;
  profile_picture_url: string | null;
  primary_persona_id: number | null;
  /** The face currently worn (durable active_persona, else primary) — #981/#1043. */
  active_persona_id: number | null;
  /**
   * The shelf this entry sits on (a `RosterType` value, e.g. "Active", "NPC").
   * Lets callers split a GM's own Story NPCs out of the general list (#3426)
   * without a second query. Optional so the many pre-existing test mocks of
   * this type across the app don't all need updating for an unrelated field.
   */
  roster_type?: string;
}

/**
 * Response body of `POST /api/roster/entries/select/` (#3412) — mirrors
 * `GET /api/user/`'s `selected_entry_id`/`selected_entry` fields exactly, so
 * the mutation result can hydrate the same slice state the account query does.
 * `entry_id: null` clears the selection, in which case both fields come back null.
 *
 * Sourced from the generated schema (drf-spectacular introspects
 * `SelectedEntryResultSerializer`, unlike the hand-rolled `AccountData` in
 * `evennia_replacements/types.ts` — that endpoint is a plain `APIView` with no
 * `serializer_class`/`@extend_schema`, so it stays out of the schema entirely).
 */
export type SelectedEntryResult = components['schemas']['SelectedEntryResult'];

export interface CharacterGallery {
  name: string;
  url: string;
}

export interface RaceData {
  id: number;
  name: string;
  description: string;
}

export interface SubraceData {
  id: number;
  name: string;
  description: string;
  race: string;
}

export interface CharacterRaceInfo {
  race: RaceData | null;
  subrace: SubraceData | null;
}

export interface CharacterData {
  id: number;
  name: string;
  age?: number | null;
  /** Celebrated birthday, rendered "March 15" (#2756); waking day for Sleepers. */
  birthday?: string;
  gender?: Gender | null;
  race?: CharacterRaceInfo | null;
  char_class?: string | null;
  level?: number | null;
  concept?: string;
  family?: string;
  vocation?: string;
  social_rank?: number | null;
  background?: string;
  relationships?: string[];
  galleries: CharacterGallery[];
  /** Core-identity covenant: the active DURANCE-type covenant role, if any (#1446). */
  covenant?: { id: number; name: string; role: string } | null;
}

export type CreationProvenance = 'staff' | 'gm_table' | 'player';

export interface RosterEntryData {
  id: number;
  character: CharacterData;
  profile_picture: TenureMedia | null;
  tenures: RosterTenure[];
  can_apply: boolean;
  fullname: string;
  quote: string;
  description: string;
  // Who authored this character — a viewable quality/trust signal (#1506).
  creation_provenance: CreationProvenance;
  creation_provenance_display: string;
  created_for_table_name: string | null;
}

export interface RosterData {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  available_count: number;
}

export interface Artist {
  id: number;
  name: string;
  description: string;
  commission_notes: string;
  accepting_commissions: boolean;
}

export interface PlayerMedia {
  id: number;
  cloudinary_public_id: string;
  cloudinary_url: string;
  media_type: string;
  title: string;
  description: string;
  created_by: Artist | null;
  uploaded_date: string;
  updated_date: string;
}

export interface PlayerData {
  id: number;
  profile_picture: PlayerMedia | null;
  media: PlayerMedia[];
  max_storage: number;
  max_file_size: number;
}

export interface TenureMedia {
  id: number;
  media: PlayerMedia;
  sort_order: number;
  is_public: boolean;
}

export interface TenureGallery {
  id: number;
  tenure: number;
  name: string;
  is_public: boolean;
  allowed_viewers: number[];
}

export interface RosterTenure {
  id: number;
  player_number: number;
  start_date: string;
  end_date: string | null;
  applied_date: string;
  approved_date: string | null;
  approved_by: PlayerData['id'] | null;
  tenure_notes: string;
  photo_folder: string;
  media: TenureMedia[];
}
