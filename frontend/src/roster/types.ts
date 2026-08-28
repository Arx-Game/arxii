import type { Gender } from '@/world/character_sheets/types';
import type { components } from '@/generated/api';

/**
 * Sourced from the generated schema (drf-spectacular introspects
 * `MyRosterEntrySerializer`, used by `RosterEntryViewSet.mine`/`select` — same
 * serializer backs both `unread_narrative_count`'s annotated-list path and its
 * unannotated single-object fallback; see the field's own doc comment on the
 * generated type). This is pre-existing legacy hand-rolled duplication, not a
 * new-this-slice one — reconciled here (#3412 task 4, api-types regen) rather
 * than left drifting: `unread_narrative_count` (#3412) is the only field this
 * type gained since the schema already covered the rest, so keeping it a
 * second hand declaration would just be duplicate-of-generated per "generated
 * wins" (contrast `AccountData` in `evennia_replacements/types.ts`, which
 * stays genuinely hand-rolled because `CurrentUserAPIView` is a plain
 * `APIView` with no `serializer_class`/`@extend_schema` and never enters the
 * generated schema at all).
 */
export type MyRosterEntry = components['schemas']['MyRosterEntry'];

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
