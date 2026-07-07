# Houses (#1884)

Noble/merchant/crime houses as first-class play. A house **is** an
`Organization` (`family` FK → `roster.Family`; ADR-0098) sitting on the kinship
graph (#2062): recognition and succession are derivations over public-record
parentage, fealty is an org→org tree, domains feed the existing
streams→treasury spine, and marriage pacts fire coded commitments. Lives in
`world/societies/houses/` (submodule of societies).

## Models (`world/societies/houses/models.py`)

- **`NobiliaryParticle`** — realm × family-type → particle ("du"); names render
  `First particle House`.
- **`HouseRecognitionRule`** — a realm's birth-recognition law
  (`MATRILINEAL_AUTO_WEDLOCK`, `MOTHER_OPTION_OUT_OF_WEDLOCK`,
  `CONSORT_CHILDREN_ENNOBLED`, `PATRILINEAL_AUTO_WEDLOCK`).
- **`FealtyEdge`** — vassal (OneToOne) → liege; the realm tree.
- **`SuccessionLaw`** — derivation (`PRIMOGENITURE_WEDLOCK`,
  `MATRILINEAL_RECOGNITION`, `FEMALE_LINE_CONSORTS_ENNOBLED`, `CHOSEN_HEIR`,
  `TANISTRY_ELECTION`) + ordering (`ELDEST`, `MOST_POWERFUL_GIFTED` — pluggable
  rater, PLACEHOLDER falls back to eldest) + `require_wedlock`/`enatic_tiebreak`.
  House default on `Organization.default_succession_law`; per-title override on
  `Title.succession_law` (Imperial Tanistry).
- **`Title`** — first-class: name, tier (crown/duchy/county/barony), realm,
  house, holder (→ `Kinsperson`), seat domain, `is_claimable` (Phase D slots).
- **`Domain`** — decorates a DOMAIN-level `Area` (OneToOne PK): owner org +
  PLACEHOLDER civ stats (population/prosperity/unrest). Abstract — no room
  grids yet.
- **`HoldingKind`** / **`DomainHolding`** — authored holding vocabulary; each
  holding materializes an `OrgIncomeStream` (OneToOne) so collection, graft,
  and settlement reuse the audited currency pipeline unchanged.
- **`DomainImprovementDetails`** — per-kind details for `DOMAIN_IMPROVEMENT`
  projects; **`DomainCrisis`** — opened when an improvement resolves badly.
- **`MarriagePact`** — OneToOne → `roster.Union`; senior/junior house;
  dissolved with reason (DEATH/ANNULMENT/BREACH). **`PactCommitment`** — coded
  kind (DOWRY/SUBSIDY/CRISIS_RESPONSE/RESIDENCY/CUSTOM), amount/percent,
  optional `OrgObligation`, `breached_at`.

## Services (`world/societies/houses/services.py`)

`full_display_name` (particle naming), `recognize_birth` (realm rules over
public-record edges; mother's-option returns None — `acknowledge_into_family`
is the explicit seam), `derive_succession_candidates` (omniscient public
record; tanistry returns the unordered eligible pool; empty list = succession
crisis, deliberately unresolved), `pass_title`, `swear_fealty` (cycle-refusing)
/ `vassals_of` / `liege_chain_of`, `sign_marriage_pact` (executes DOWRY
transfer, SUBSIDY → `OrgObligation`, RESIDENCY → `MARRIED_IN` membership),
`dissolve_pact`, `handle_death_for_pacts` (call seam for the death flow — the
CK2 instant-death rule), `breach_commitment` (stops machinery; scandal fires
through the normal Secrets → tidings channel, staff-authored),
`create_domain` / `add_holding`, `start_domain_improvement` /
`complete_domain_improvement` (projects framework; kind handler registered in
societies `apps.ready()`). `register_gifted_power_rater` is the
MOST_POWERFUL_GIFTED plug. `HousesServiceError.user_message` on refusals.

## Surfaces

- **REST:** `OrganizationSerializer.house` block (family, liege, vassals,
  titles, domains; null for non-family orgs) +
  `/api/societies/organizations/{id}/feed/` (house feed).
- **House feed:** `world/tidings/services.house_feed_for(org)` — member deeds +
  revealed scandals, query-and-merge, no feed model (replaces Arx 1 informs).
- **Web:** `/orgs/:id` renders the house block + House Tidings (extends the
  #1446 stub OrgPage).
- **Telnet:** `sheet/house` (house, particle name, fealty chain, titles,
  tidings).
- **Channel:** `sync_house_channel(org)` — Evennia channel `house_<pk>`
  (aliased to the house name); audience = accounts currently playing active
  members, vassal houses cascaded. Idempotent explicit call (no signals) —
  run it after membership or fealty changes.
- **Seeds:** cluster `houses` (rides `kinship`) — the demo house made a landed
  peer: org, particle, recognition rules, succession law, crown fealty, ducal
  title, domain + farmland holding.

## House creator (Phase D)

CG-only (Apostate ruling): a claim defines the house *retroactively* — the
character has always been its representative. Founding a brand-new house in
play (ennoblement, new lands) is a separate future loop.

- **`HouseTemplate`** — realm recipe: name-pattern regex (the realm's naming
  conventions as an automated gate), per-axis principle ranges, society,
  liege, succession law, holdings package, `starting_kin_slots`.
- **`HouseClaim`** — rides the `CharacterDraft` (dies with it); automated
  thematic gates run at `submit_house_claim` (claimable title, realm match,
  one live claim per title, name pattern + collision, backstory present,
  principle ranges); staff approve/reject in **Django admin**
  (`HouseClaimAdmin` actions).
- **Materialization at CG finalization** (`materialize_house_claim`, called
  from `_bind_house_claim` before the kinship bind): Family + org (+rank
  ladder, principle overrides) + fealty to the template liege + title seated
  on the founder (FOUNDING membership) + seat domain reassigned with the
  holdings package + a `KinSlotPool` for future kin app-ins + the house
  channel. Approval alone creates nothing — an abandoned application leaves
  no ghost house.
- **Surfaces:** `/api/character-creation/house-titles/` (claimable titles +
  templates), `GET/POST /api/character-creation/drafts/{id}/house-claim/`;
  the CG Lineage stage shows the "Define a House" panel to familyless
  drafts. Seeds: a set-aside claimable barony + charter template ride the
  `houses` cluster.

## Regional flavor: aspects + features (#2079)

Two deliberately distinct concepts give each realm's (and each noble-type's)
houses a unique creation experience (ADR-0101):

- **Aspect** — a required, normalized CHOICE. `HouseAspectDefinition` (name,
  player-facing prompt, `min_picks`/`max_picks`) attaches to templates via
  `HouseTemplate.aspect_definitions` (M2M — both Inferna templates can share
  "House Vice" while only the Cinderi template carries a diaspora choice);
  `HouseAspectOption` rows are its admin-editable catalog. **Catalog-only by
  design** — no free-text answer path (ADR-0101). `HouseClaimAspect` records
  the founder's picks; `_validate_aspect_picks` refuses submission unless
  every attached definition is answered within [min, max] with active options
  of that definition.
- **Feature** — a structural cultural FACT, no player input.
  `HouseFeature` (name, unique `slug` as the stable code anchor, player-facing
  description) attaches via `HouseTemplate.features`; at CG it orients the
  founder ("a house of this charter keeps a Black Ledger"), in play it is the
  anchor future systems key off (`org.features` has slug `black-ledger` — data
  row + slug, never a bespoke code path).
- **Shared stylings** — `Organization.words/colors/sigil_description`
  (org-level: gangs and guilds get them free), collected as required claim
  inputs alongside `lands_writeup`, which materializes onto the seat
  `Domain.description`.
- **Materialization** — claim picks become `OrganizationAspect` rows and
  template features stamp `OrganizationFeature` rows (both also directly
  authorable for staff-seeded houses); stylings copy onto the org.
- **Surfaces:** template payloads carry the definitions-with-options tree +
  features (CG panel renders option cards + a features orientation panel and
  gates submit on completeness); the org payload carries stylings + house-block
  `aspects`/`features`; `sheet/house` lists words, colors, facets, features;
  admin registers definitions (options inline), features, and a read-only
  picks inline on the claim review queue.
- **Content:** per-region catalogs (deities, vices, virtues, totems, geasa,
  traditions) arrive from later per-region brainstorms — targets: 2 aspects
  per region (3 only if genuinely fun), ≥1 advantageous RP-usable feature.
  Seeds ship one PLACEHOLDER exemplar of each on the Arx demo template.
