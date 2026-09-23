import type { HouseDocument, LadderRow } from '@/almanach/types';
import type { components } from '@/generated/api';

/**
 * Inferna realm fixtures (#3983 evidence harness) — the Almanach plates'
 * own worked example (`staff.html`/`founder.html`'s `.mock` sections):
 * House Piropa holds the crown of Inferna and the duchy Vampa outright;
 * House Solano holds the county Ardor beneath it; the duchy Fervor sits
 * unclaimed with its own bundled seat chain (Arsura -> Ascua) plus two
 * independently claimable rungs (Solfatara/Tizón and an undefined county);
 * Caldera and an undefined duchy round out the unclaimed root rungs. Every
 * name/count below is lifted from the plates so a reviewer comparing a
 * screenshot against `staff.html`/`founder.html` sees the same entities,
 * per the evidence-harness brief.
 *
 * `buildLadderRows(fervorHeld)` produces both the S-I/F-I ladder (Fervor
 * still unclaimed) and the F-I b ladder (Fervor+Arsura held by the
 * founder's own newly named house, `CANDELA_HOUSE_NAME`) from one shared
 * shape, since the two payloads differ only in Fervor's own chain — see the
 * module doc on `buildLadderRows` below.
 */

export const REALM_ID = 40;

export const PIROPA_HOUSE_ID = 500;
export const SOLANO_HOUSE_ID = 501;
/** The house name the founder journey (F-II onward) claims — matches
 * `founder.html`'s own worked example so the founder screenshots read as
 * the same story as the staff ones. Not pre-seeded as a house row; it only
 * exists once the founder names it in `FounderHouseChapter`. */
export const CANDELA_HOUSE_NAME = 'Candela';

// Vampa's own chain (held outright by Piropa).
const VAMPA = 300;
const INFERNA_COUNTY = 301;
const PERDITION = 302;
const BOCHORNO = 303;
const LUMBRE = 304;

// Ardor's own chain (held outright by Solano, Seawatch the one exception).
const ARDOR = 310;
const ESTIO = 311;
const SEAWATCH = 312;
const CANICULA = 313;

// Fervor's own unclaimed chain (claimed by the founder as "Candela").
export const FERVOR = 320;
const ARSURA = 321;
const ASCUA = 322;
const UNDEF_BARONY_IN_ARSURA = 323;
export const SOLFATARA = 330;
const TIZON = 331;
const UNDEF_BARONY_IN_SOLFATARA = 332;
const UNDEF_COUNTY_UNDER_FERVOR = 333;

const CALDERA = 340;
const UNDEF_DUCHY = 341;

export const REALM: components['schemas']['AlmanachRealm'] = {
  id: REALM_ID,
  name: 'Inferna',
  formal_name: 'Grand Principality of Inferna',
  default_tithe_pct: 10,
  unclaimed_by_tier: { empire: 0, kingdom: 0, duchy: 3, march: 0, county: 3, barony: 3 },
};

/** `/api/almanach/realms/{id}/charter/` (`RealmCharter`, `almanach/types.ts`)
 * — the realm's blank-floor particle/succession/quiddity-prompt trio the
 * staff record rail (S-I) and every founder chapter (F-I's aside, F-II's
 * name preview, F-V's capital) read. Matches `staff.html`'s own realm
 * charter box and `founder.html:f2`'s quiddity prompt paragraph verbatim. */
export const CHARTER = {
  succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: 12 },
  particle: { born: 'za', taken_in: 'zas' },
  quiddity_prompt:
    'What drives your house? A Quiddity is the thing an Infernal house is known for, the answer everyone else already has ready when your name comes up.',
  capital_name: 'Perdition',
};

export const LAND_SHAPES: components['schemas']['LandShape'][] = [
  { id: 1, name: 'coast', description: '', sort_order: 0 },
  { id: 2, name: 'reefs', description: '', sort_order: 1 },
  { id: 3, name: 'hills', description: '', sort_order: 2 },
  { id: 4, name: 'volcanic', description: '', sort_order: 3 },
];

export const GENDERS: components['schemas']['Gender'][] = [
  { id: 1, key: 'man', display_name: 'Man' },
  { id: 2, key: 'woman', display_name: 'Woman' },
];

/** `/api/almanach/houses/` (unscoped, `useAllHouses`) — every house on
 * record, `family_id` set so the "born into"/"swear a house" pickers have
 * something real to offer (`AddKinDialog`, `RealmLeaf`). */
export const ALL_HOUSES: components['schemas']['AlmanachHouseSummary'][] = [
  {
    id: PIROPA_HOUSE_ID,
    name: 'Piropa',
    house_state: 'standing',
    published_at: null,
    family_id: 5001,
  },
  {
    id: SOLANO_HOUSE_ID,
    name: 'Solano',
    house_state: 'standing',
    published_at: '2026-01-01T00:00:00Z',
    family_id: 5002,
  },
];

/**
 * The realm ladder (#3983 evidence harness), shared by the staff `?for=staff`
 * read (S-I/S-II) and the founder `?for=founder` read (F-I/F-I b) — the two
 * modes differ only in server-side permission, never in row shape. Pass
 * `fervorHeld: true` for the F-I b screen (plate `f1b`): Fervor and its
 * bundled seat county Arsura flip to `state: 'Held'`, `house_name:
 * 'Candela'`, `claimable: false`; every other row is unchanged.
 */
export function buildLadderRows(fervorHeld: boolean): LadderRow[] {
  const fervorState = fervorHeld ? 'Held' : 'Unclaimed';
  const fervorHouseId = fervorHeld ? 9001 : null;
  const fervorHouseName = fervorHeld ? CANDELA_HOUSE_NAME : '';
  const fervorClaimable = !fervorHeld;

  const rows: LadderRow[] = [
    // Vampa's own chain — Piropa's demesne outright.
    {
      title_id: VAMPA,
      name: 'Vampa',
      is_defined: true,
      tier: 'duchy',
      level: 0,
      parent_title_id: null,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'Piropa (crown)',
      demesne: 4,
      vassals: 1,
      claimable: false,
      seat_domain_id: 1001,
      comes_with: '',
      chain_top_id: VAMPA,
      claimant_name: '',
    },
    {
      title_id: INFERNA_COUNTY,
      name: 'County of Inferna',
      is_defined: true,
      tier: 'county',
      level: 1,
      parent_title_id: VAMPA,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'Vampa',
      demesne: 3,
      vassals: 1,
      claimable: false,
      seat_domain_id: 1001,
      comes_with: '',
      chain_top_id: INFERNA_COUNTY,
      claimant_name: '',
    },
    {
      title_id: PERDITION,
      name: 'Perdition',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: INFERNA_COUNTY,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: 'Piropa',
      sworn_to: 'County of Inferna',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1001,
      comes_with: '',
      chain_top_id: PERDITION,
      claimant_name: '',
    },
    {
      title_id: BOCHORNO,
      name: 'Bochorno',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: INFERNA_COUNTY,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'County of Inferna',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1001,
      comes_with: '',
      chain_top_id: BOCHORNO,
      claimant_name: '',
    },
    {
      title_id: LUMBRE,
      name: 'Lumbre',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: INFERNA_COUNTY,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'County of Inferna',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1001,
      comes_with: '',
      chain_top_id: LUMBRE,
      claimant_name: '',
    },
    // Ardor's own chain — Solano's demesne (Seawatch stays Piropa's own).
    {
      title_id: ARDOR,
      name: 'Ardor',
      is_defined: true,
      tier: 'county',
      level: 1,
      parent_title_id: VAMPA,
      house_id: SOLANO_HOUSE_ID,
      house_name: 'Solano',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'Vampa',
      demesne: 2,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1002,
      comes_with: '',
      chain_top_id: ARDOR,
      claimant_name: '',
    },
    {
      title_id: ESTIO,
      name: 'Estío',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: ARDOR,
      house_id: SOLANO_HOUSE_ID,
      house_name: 'Solano',
      state: 'Held',
      is_seat_of: 'Solano',
      sworn_to: 'Ardor',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1002,
      comes_with: '',
      chain_top_id: ESTIO,
      claimant_name: '',
    },
    {
      title_id: SEAWATCH,
      name: 'Seawatch',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: ARDOR,
      house_id: PIROPA_HOUSE_ID,
      house_name: 'Piropa',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'Ardor',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1002,
      comes_with: '',
      chain_top_id: SEAWATCH,
      claimant_name: '',
    },
    {
      title_id: CANICULA,
      name: 'Canícula',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: ARDOR,
      house_id: SOLANO_HOUSE_ID,
      house_name: 'Solano',
      state: 'Held',
      is_seat_of: '',
      sworn_to: 'Ardor',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1002,
      comes_with: '',
      chain_top_id: CANICULA,
      claimant_name: '',
    },
    // Fervor's own chain — unclaimed (or held by Candela, `fervorHeld`).
    {
      title_id: FERVOR,
      name: 'Fervor',
      is_defined: true,
      tier: 'duchy',
      level: 0,
      parent_title_id: null,
      house_id: fervorHouseId,
      house_name: fervorHouseName,
      state: fervorState,
      is_seat_of: '',
      sworn_to: 'Piropa (crown)',
      demesne: 2,
      vassals: 2,
      claimable: fervorClaimable,
      seat_domain_id: 1010,
      comes_with: '',
      chain_top_id: FERVOR,
      claimant_name: '',
    },
    {
      title_id: ARSURA,
      name: 'Arsura',
      is_defined: true,
      tier: 'county',
      level: 1,
      parent_title_id: FERVOR,
      house_id: fervorHouseId,
      house_name: fervorHouseName,
      state: fervorState,
      is_seat_of: '',
      sworn_to: 'Fervor',
      demesne: 2,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1010,
      comes_with: 'Fervor',
      chain_top_id: FERVOR,
      claimant_name: '',
    },
    {
      title_id: ASCUA,
      name: 'Ascua',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: ARSURA,
      house_id: fervorHouseId,
      house_name: fervorHouseName,
      state: fervorState,
      is_seat_of: fervorHeld ? CANDELA_HOUSE_NAME : '',
      sworn_to: 'Arsura',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1010,
      comes_with: 'Fervor',
      chain_top_id: FERVOR,
      claimant_name: '',
    },
    {
      title_id: UNDEF_BARONY_IN_ARSURA,
      name: '',
      is_defined: false,
      tier: 'barony',
      level: 2,
      parent_title_id: ARSURA,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Arsura',
      demesne: 0,
      vassals: 0,
      claimable: true,
      seat_domain_id: 1010,
      comes_with: '',
      chain_top_id: UNDEF_BARONY_IN_ARSURA,
      claimant_name: '',
    },
    {
      title_id: SOLFATARA,
      name: 'Solfatara',
      is_defined: true,
      tier: 'county',
      level: 1,
      parent_title_id: FERVOR,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Fervor',
      demesne: 1,
      vassals: 1,
      claimable: true,
      seat_domain_id: 1011,
      comes_with: '',
      chain_top_id: SOLFATARA,
      claimant_name: '',
    },
    {
      title_id: TIZON,
      name: 'Tizón',
      is_defined: true,
      tier: 'barony',
      level: 2,
      parent_title_id: SOLFATARA,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Solfatara',
      demesne: 1,
      vassals: 0,
      claimable: false,
      seat_domain_id: 1011,
      comes_with: 'Solfatara',
      chain_top_id: SOLFATARA,
      claimant_name: '',
    },
    {
      title_id: UNDEF_BARONY_IN_SOLFATARA,
      name: '',
      is_defined: false,
      tier: 'barony',
      level: 2,
      parent_title_id: SOLFATARA,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Solfatara',
      demesne: 0,
      vassals: 0,
      claimable: true,
      seat_domain_id: 1011,
      comes_with: '',
      chain_top_id: UNDEF_BARONY_IN_SOLFATARA,
      claimant_name: '',
    },
    {
      title_id: UNDEF_COUNTY_UNDER_FERVOR,
      name: '',
      is_defined: false,
      tier: 'county',
      level: 1,
      parent_title_id: FERVOR,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Fervor',
      demesne: 1,
      vassals: 0,
      claimable: true,
      seat_domain_id: 1012,
      comes_with: '',
      chain_top_id: UNDEF_COUNTY_UNDER_FERVOR,
      claimant_name: '',
    },
    // Root rungs beside Fervor.
    {
      title_id: CALDERA,
      name: 'Caldera',
      is_defined: true,
      tier: 'duchy',
      level: 0,
      parent_title_id: null,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Piropa (crown)',
      demesne: 1,
      vassals: 1,
      claimable: true,
      seat_domain_id: 1020,
      comes_with: '',
      chain_top_id: CALDERA,
      claimant_name: '',
    },
    {
      title_id: UNDEF_DUCHY,
      name: '',
      is_defined: false,
      tier: 'duchy',
      level: 0,
      parent_title_id: null,
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      is_seat_of: '',
      sworn_to: 'Piropa (crown)',
      demesne: 1,
      vassals: 0,
      claimable: true,
      seat_domain_id: 1021,
      comes_with: '',
      chain_top_id: UNDEF_DUCHY,
      claimant_name: '',
    },
  ];

  return rows;
}

/** `/api/almanach/houses/{id}/document/` for House Piropa (S-III to S-VIII).
 * `published` toggles `house.published_at` — pass `true` only for the
 * Publish leaf (S-VIII), which is the one screen the plate shows already
 * published; every other leaf's plate shows the `draft` chip. */
export function buildPiropaDocument(published: boolean): HouseDocument {
  return {
    house: {
      id: PIROPA_HOUSE_ID,
      name: 'Piropa',
      description: 'PLACEHOLDER',
      words: 'PLACEHOLDER',
      colors: 'PLACEHOLDER',
      sigil_description: 'PLACEHOLDER',
      house_state: 'standing',
      published_at: published ? '2026-09-20T00:00:00Z' : null,
      particle_example: 'Océane aza Piropa · Raffaele azas Piropa',
      default_succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: 12 },
      aspects: [
        {
          definition: 'Quiddity',
          option: 'Glamour',
          description:
            "Grandeur is the house's due, and a slight is answered before the ball has ended.",
        },
      ],
      features: [
        { name: 'Letter of Marque', slug: 'letter-of-marque', description: 'PLACEHOLDER' },
      ],
      offices: [
        { slug: 'steward-of-the-domains', title: 'Steward of the Domains', holder_name: '' },
        { slug: 'mistress-of-letters', title: 'Mistress of Letters', holder_name: '' },
      ],
    },
    family: {
      nodes: [
        {
          id: 1,
          name: 'Galerna aza Piropa',
          tier: 'pc',
          family_id: 5001,
          is_deceased: false,
          is_appable: true,
          sheet_id: 1,
          gender: 'Woman',
          age: 44,
          description: 'PLACEHOLDER',
          believed_deceased: false,
        },
        {
          id: 2,
          name: 'Raffaele azas Piropa',
          tier: 'pc',
          family_id: 5002,
          is_deceased: false,
          is_appable: true,
          sheet_id: 2,
          gender: 'Man',
          age: 46,
          description: 'PLACEHOLDER',
          believed_deceased: false,
        },
        {
          id: 3,
          name: 'Nerea aza Piropa',
          tier: 'sheeted',
          family_id: 5001,
          is_deceased: false,
          is_appable: false,
          sheet_id: 3,
          gender: 'Woman',
          age: 19,
          description: '',
          believed_deceased: false,
        },
        {
          id: 4,
          name: 'Océane aza Piropa',
          tier: 'pc',
          family_id: 5001,
          is_deceased: false,
          is_appable: true,
          sheet_id: 4,
          gender: 'Woman',
          age: 17,
          description: 'PLACEHOLDER',
          believed_deceased: false,
        },
      ],
      parentage: [
        { child_id: 3, parent_id: 1, kind: 'biological', is_true: true, via_secret: false },
        { child_id: 3, parent_id: 2, kind: 'biological', is_true: true, via_secret: false },
        { child_id: 4, parent_id: 1, kind: 'biological', is_true: true, via_secret: false },
        { child_id: 4, parent_id: 2, kind: 'biological', is_true: true, via_secret: false },
      ],
      unions: [{ id: 1, kind: 'marriage', member_ids: [1, 2], ended: false }],
    },
    household: [
      {
        vacancy_id: 1,
        position: 'ward',
        holder_id: 5,
        holder_name: 'Marisol',
        is_open: false,
        count_remaining: 0,
        is_deceased: false,
        believed_deceased: true,
      },
      {
        vacancy_id: 2,
        position: 'Master-at-arms',
        holder_id: null,
        holder_name: '',
        is_open: true,
        count_remaining: 1,
        is_deceased: false,
        believed_deceased: false,
      },
    ],
    realm: {
      sworn_to: '',
      obligation_pct: null,
      holds: 'the crown',
      demesne: [
        { title_id: PERDITION, name: 'Perdition', held_by: 'Piropa', demesne: 0, vassals: 0 },
        { title_id: BOCHORNO, name: 'Bochorno', held_by: 'Piropa', demesne: 0, vassals: 0 },
        { title_id: LUMBRE, name: 'Lumbre', held_by: 'Piropa', demesne: 0, vassals: 0 },
        { title_id: SEAWATCH, name: 'Seawatch', held_by: 'Piropa', demesne: 0, vassals: 0 },
      ],
      vassals: [
        { title_id: ARDOR, name: 'Ardor', held_by: 'Solano', demesne: 2, vassals: 0 },
        { title_id: FERVOR, name: 'Fervor', held_by: '', demesne: 2, vassals: 2 },
        { title_id: CALDERA, name: 'Caldera', held_by: '', demesne: 1, vassals: 1 },
        { title_id: UNDEF_DUCHY, name: '', held_by: '', demesne: 1, vassals: 0 },
      ],
      realm_id: REALM_ID,
      default_tithe_pct: 10,
      realm_theme: 'inferna',
    },
    lands: {
      count: 4,
      population: 4200,
      produces: ['salt', 'timber', 'a port'],
      seat: 'Perdition',
      baronies: [
        {
          id: PERDITION,
          name: 'Perdition',
          in: 'County of Inferna',
          hall: 'the Palazzo Ardente',
          is_seat: true,
          description:
            "Several hundred years ago, a Grand Princess of Inferna changed the name of the capital holding to Perdition following a crushing naval victory over Luxen. It remains the island kingdom's seat of royal power, cosmopolitan despite its fearsome reputation.",
          land_shapes: ['coast', 'reefs'],
          population: 4200,
        },
        {
          id: BOCHORNO,
          name: 'Bochorno',
          in: 'County of Inferna',
          hall: '',
          is_seat: false,
          description: '',
          land_shapes: [],
          population: 0,
        },
        {
          id: LUMBRE,
          name: 'Lumbre',
          in: 'County of Inferna',
          hall: '',
          is_seat: false,
          description: '',
          land_shapes: [],
          population: 0,
        },
        {
          id: SEAWATCH,
          name: 'Seawatch',
          in: 'Ardor',
          hall: '',
          is_seat: false,
          description: '',
          land_shapes: [],
          population: 0,
        },
      ],
    },
    estate: [
      {
        id: 1,
        name: 'Casa Piropa',
        district: 'Harborside',
        description: '',
      },
    ],
  };
}
