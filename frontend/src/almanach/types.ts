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
export type AlmanachHouseFacet = components['schemas']['AlmanachHouseFacet'];
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
  /** The record's own facts (#4239): missing, and what it says of a death. */
  is_missing?: boolean;
  obituary?: string;
}

/** `document.family` — the house's kinship graph, viewer-gated like every
 * other kinship read (`_family_payload`, `almanach_reads.py`). */
export interface AlmanachFamily {
  /** The Family pk (#4239), what Create Kin needs; null for a house with no family row.
   * Optional so the founder's draft shape, which has no row yet, still fits. */
  family_id?: number | null;
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
  realm_theme: string /** #4239: the house's own top rung, for Add vacant seats from the house page. */;
  holds_title_id?: number | null;
  holds_tier?: string;
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
  /** #4239: the chapters every family page carries. `turf` is null for a
   * house that holds none. */
  books: AlmanachBooks;
  forces: AlmanachForceRow[];
  openings: AlmanachOpenings;
  turf: AlmanachTurf | null;
}

/** `books` (#4239, `almanach_pages.books_for`): coppers per cycle, what is
 * pooled uncollected, and the treasury. The full ledger is #4243. */
export interface AlmanachBooks {
  income_week: number;
  uncollected: number;
  treasury: number;
  streams: number;
}

/** One unit row (#4239, `almanach_pages.forces_for`). */
export interface AlmanachForceRow {
  unit_id: number;
  name: string;
  owner: string;
  quality: string;
  men: number;
  strength: number;
  morale: number;
  posted_here: boolean;
}

/** A person as the #4239 pages list them: kin rows, appable kin, search. */
export interface AlmanachPersonRow {
  id: number;
  name: string;
  relation: string;
  /** parent / child / spouse / sibling: what the row counts as; `relation` is the word. */
  link?: string;
  tier: string;
  tier_display: { number: number | null; label: string };
  status: 'alive' | 'rip' | 'missing';
  is_pc: boolean;
  sheet_id: number | null;
  is_appable: boolean;
  family_id: number | null;
}

export interface AlmanachOpenings {
  appable: AlmanachPersonRow[];
  posts: { vacancy_id: number; position: string }[];
  vacant_seats: AlmanachRealmRowSummary[];
}

export interface AlmanachTurf {
  tier: string;
  wards: { turf_id: number; area_id: number; name: string; grip: number; base_value?: number }[];
  gangs: {
    org_id: number;
    name: string;
    boss: string;
    neighborhood: string;
    crews: {
      crew_slot_id: number;
      name: string;
      rooms: number;
      claimed_by: string;
      is_open: boolean;
    }[];
  }[];
}

/** The #4239 documents, typed over the generated schema's dict sections. */
export type FrontRolls = components['schemas']['FrontRolls'];
export type SearchHit = components['schemas']['SearchHit'];
export type AlmanachFamilyKind = components['schemas']['AlmanachFamilyKind'];
export type AlmanachTemplate = components['schemas']['AlmanachTemplate'];
export type AlmanachUnionKind = components['schemas']['AlmanachUnionKind'];
export type AlmanachTitleSummary = components['schemas']['AlmanachTitleSummary'];
export type AlmanachHoldingKind = components['schemas']['AlmanachHoldingKind'];

export interface PersonDocument {
  person: {
    id: number;
    name: string;
    display_name: string;
    gender_id: number | null;
    gender: string;
    age: number | null;
    tier: string;
    tier_display: { number: number | null; label: string };
    status: 'alive' | 'rip' | 'missing';
    record_accurate: boolean;
    obituary: string;
    is_pc: boolean;
    description: string;
  };
  family: {
    id: number;
    name: string;
    kind: string;
    basis: string;
    organization_id: number | null;
  } | null;
  kin: AlmanachPersonRow[];
  house: {
    org_id: number;
    name: string;
    role: string;
    rank: number | null;
    household_post: string;
  } | null;
  titles: {
    title_id: number;
    name: string;
    tier: string;
    realm: string;
    held_by: string;
    seat?: string;
    vassals: number;
  }[];
  sheet: {
    sheet_id: number | null;
    is_appable: boolean;
    name_locked: boolean;
    age_min: number | null;
    age_max: number | null;
    allowed_gender_ids: number[];
  };
  memberships: { org_id: number; name: string; rank: string }[];
  record: {
    parents: number;
    children: number;
    siblings: number;
    unions: number;
    hidden_truths: number;
  };
}

export interface RungDocument {
  title: {
    title_id: number;
    name: string;
    tier: string;
    realm_id: number;
    realm: string;
    house_id: number | null;
    held_by: string;
    holder_id: number | null;
    holder: string;
    sworn_to: string;
    succession: string;
    seat: string;
    is_claimable: boolean;
    chain_top_id: number;
  };
  demesne: {
    domain_id: number;
    name: string;
    description: string;
    hall: string;
    population: number;
    prosperity: number;
    unrest: number;
    defenses: number;
  } | null;
  holdings: {
    holding_id: number;
    name: string;
    kind: string;
    site: string;
    standing: number;
    unsited: boolean;
  }[];
  books: AlmanachBooks;
  forces: AlmanachForceRow[];
  vassals: AlmanachRealmRowSummary[];
}

export interface FamilyDocument {
  family: {
    id: number;
    name: string;
    kind: string;
    realm_id: number | null;
    realm: string;
    is_playable: boolean;
    description: string;
  };
  organization_id: number | null;
  tree: AlmanachFamily;
  openings: AlmanachOpenings;
}

/** Registry keys of the ten staff Almanach actions (#3983 Task 6). */
export type AlmanachActionKey =
  | 'almanach_plant_rung'
  | 'almanach_batch_unclaimed'
  | 'almanach_name_rung'
  | 'almanach_assign_holder'
  | 'almanach_delete_rung'
  | 'almanach_move_rung'
  | 'almanach_edit_house'
  | 'almanach_swear'
  | 'almanach_describe_demesne'
  | 'almanach_add_holding'
  | 'almanach_plan_estate'
  | 'almanach_edit_kin'
  | 'almanach_publish'
  // #4239: every family, every person.
  | 'almanach_create_family'
  | 'almanach_found_organization'
  | 'almanach_create_kin'
  | 'almanach_link_kin'
  | 'almanach_correct_kin'
  | 'almanach_set_status'
  | 'almanach_promote_kin'
  | 'almanach_set_appable'
  | 'almanach_attach_sheet'
  | 'almanach_set_holder'
  | 'almanach_claim_ward'
  | 'almanach_add_gang'
  | 'almanach_open_crew_slot'
  | 'almanach_edit_person';
