/**
 * Almanach de Catenys types (#3983 Task 7): thin aliases over the generated
 * schema (Task 5) for the shapes DRF documents explicitly, plus hand-written
 * interfaces for the house document's `family`/`household`/`realm`/`lands`/
 * `estate` sections. Those five ride `DictField`/`ListField(child=DictField())`
 * in the schema (`almanach_serializers.py`) because they're already plain
 * dicts in the read layer (`almanach_reads.py`) — the interfaces below mirror
 * that read layer's payload builders (`_family_payload`, `_household_payload`,
 * `_realm_payload`, `_lands_payload`, `_estate_payload`) field for field so
 * callers get real types instead of `unknown`.
 */
import type { components } from '@/generated/api';

export type AlmanachRealm = components['schemas']['AlmanachRealm'];
export type PaginatedAlmanachRealmList = components['schemas']['PaginatedAlmanachRealmList'];

export type LadderRow = components['schemas']['LadderRow'];
export type LadderPayload = components['schemas']['LadderPayload'];

/** `?for=` cut of the realm ladder (`AlmanachRealmViewSet.ladder`) — `staff`
 * stays `IsAdminUser`; `founder` is opened to any authenticated player
 * (Plan B Task 3) so `SeatPicker`/`FounderAlmanach` can read it directly. */
export type LadderMode = 'staff' | 'founder';

export type AlmanachHouseSummary = components['schemas']['AlmanachHouseSummary'];
export type PaginatedAlmanachHouseSummaryList =
  components['schemas']['PaginatedAlmanachHouseSummaryList'];

export type LandShape = components['schemas']['LandShape'];
export type PaginatedLandShapeList = components['schemas']['PaginatedLandShapeList'];

export type AlmanachHouseDocumentHouse = components['schemas']['AlmanachHouseDocumentHouse'];
export type AlmanachSuccessionLaw = components['schemas']['AlmanachSuccessionLaw'];
export type AlmanachHouseAspect = components['schemas']['AlmanachHouseAspect'];
export type AlmanachHouseFeature = components['schemas']['AlmanachHouseFeature'];
export type AlmanachHouseOffice = components['schemas']['AlmanachHouseOffice'];

/**
 * `GET /api/almanach/realms/{id}/charter/` (#3983 Plan B Task 3) — the
 * realm-level facts the founder Almanach's Seat/House chapters gloss (the
 * duchy's succession law, its founder-particle pair, the House chapter's
 * Quiddity prompt, and the realm's capital for the Estate step). Hand-typed
 * rather than a generated alias: Task 3 is landing the endpoint and schema
 * regen concurrently with this task, so `components['schemas']` doesn't
 * carry it yet. `succession_law` reuses the already-generated
 * `AlmanachSuccessionLaw` shape (`{name, codex_entry_id}`), just nullable.
 */
export interface RealmCharter {
  succession_law: AlmanachSuccessionLaw | null;
  particle: { born: string; taken_in: string };
  quiddity_prompt: string;
  capital_name: string;
}

/**
 * `document.family`'s node shape (`_family_payload`, `almanach_reads.py`):
 * a viewer-gated `family_tree_for` node (mirrors `KinspersonNode`,
 * `@/kinship/types`) with `believed_deceased` folded on — the one field the
 * almanach read adds that the roster kin-tree endpoint doesn't expose.
 */
export interface AlmanachFamilyNode {
  id: number;
  name: string;
  tier: string;
  family_id: number | null;
  is_deceased: boolean;
  is_appable: boolean;
  sheet_id: number | null;
  gender: string;
  age: number | null;
  description: string;
  believed_deceased: boolean;
}

/** `document.family` — the house's kinship graph, viewer-gated like every
 * other kinship read (`_family_payload`, `almanach_reads.py`). */
export interface AlmanachFamily {
  nodes: AlmanachFamilyNode[];
  parentage: components['schemas']['ParentageEdge'][];
  unions: components['schemas']['UnionEdge'][];
}

/** One `document.household` row — a RETAINER Vacancy at the Household rank
 * (`_household_payload`, `almanach_reads.py`), never a kin slot. */
export interface AlmanachHouseholdMember {
  vacancy_id: number;
  position: string;
  holder_id: number | null;
  holder_name: string;
  is_open: boolean;
  count_remaining: number;
  is_deceased: boolean;
  believed_deceased: boolean;
}

/** A ladder-row summary the way `document.realm.demesne`/`.vassals` list it
 * (`_row_summary`, `almanach_reads.py`). */
export interface AlmanachRealmRowSummary {
  title_id: number;
  name: string;
  held_by: string;
  demesne: number;
  vassals: number;
}

/** `document.realm` — the house's own standing in its realm's ladder
 * (`_realm_payload`, `almanach_reads.py`). `realm_id`/`default_tithe_pct`/
 * `realm_theme` (final review I11, deferred item 3) let the House Document
 * link back to the realm's own ladder page, prefill the swear dialog's
 * tithe, and gate the Gentry toggle — `realm_id` is `null` when the house's
 * title carries no realm (an orphaned/legacy house). */
export interface AlmanachDocumentRealm {
  sworn_to: string;
  obligation_pct: number | null;
  holds: string;
  demesne: AlmanachRealmRowSummary[];
  vassals: AlmanachRealmRowSummary[];
  realm_id: number | null;
  default_tithe_pct: number;
  realm_theme: string;
}

/** One `document.lands.baronies` entry (`_lands_payload`, `almanach_reads.py`). */
export interface AlmanachBarony {
  id: number;
  name: string;
  in: string;
  hall: string;
  is_seat: boolean;
  description: string;
  land_shapes: string[];
  population: number;
}

/** `document.lands` — the house's held baronies and what they produce
 * (`_lands_payload`, `almanach_reads.py`). */
export interface AlmanachDocumentLands {
  count: number;
  population: number;
  produces: string[];
  seat: string;
  baronies: AlmanachBarony[];
}

/** One `document.estate` entry — an owned building sitting under a city
 * (`_estate_payload`, `almanach_reads.py`). */
export interface AlmanachEstateEntry {
  id: number;
  name: string;
  district: string;
  description: string;
}

/**
 * The Almanach house document (`GET /api/almanach/houses/{id}/document/`,
 * mirrors `almanach_reads.HouseDocument`). `house` rides the schema's own
 * nested serializer (`HouseDocumentSerializer`, `almanach_serializers.py`
 * gives it one deliberately, #3983 Task 5 decision); the other five
 * sections are hand-typed above since the schema leaves them generic.
 */
export interface HouseDocument {
  house: AlmanachHouseDocumentHouse;
  family: AlmanachFamily;
  household: AlmanachHouseholdMember[];
  realm: AlmanachDocumentRealm;
  lands: AlmanachDocumentLands;
  estate: AlmanachEstateEntry[];
}

/** Registry keys of the ten staff Almanach actions (#3983 Task 6). */
export type AlmanachActionKey =
  | 'almanach_plant_rung'
  | 'almanach_batch_unclaimed'
  | 'almanach_name_rung'
  | 'almanach_edit_house'
  | 'almanach_swear'
  | 'almanach_describe_demesne'
  | 'almanach_add_holding'
  | 'almanach_plan_estate'
  | 'almanach_edit_kin'
  | 'almanach_publish';
