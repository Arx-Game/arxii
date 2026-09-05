# Houses (#1884)

Noble/merchant/crime houses as first-class play. A house **is** an
`Organization` (`family` FK → `roster.Family`; ADR-0098) sitting on the kinship
graph (#2062): recognition and succession are derivations over public-record
parentage, fealty is an org→org tree, domains feed the existing
streams→treasury spine, and marriage pacts fire coded commitments. Lives in
`world/societies/houses/` (submodule of societies).

## Models (`world/societies/houses/models.py`)

- **`NobiliaryParticle`**: realm x `kind` (FK `roster.FamilyKind`, #3617) x tier-band, to born/taken-in
  particle pair (#3261, canon vocabulary ratified 2026-08-17 and seeded by realm
  theme in `world/seeds/houses.py`). `tier_floor` (blank = default band) bands a
  realm's particles by the house's highest held title — Luxen wears `du` at
  duchy+ and attached `D'` below (apostrophe-terminal particles join unspaced:
  "Sybel D'Regente"); `taken_in_particle` is worn by every non-born member
  (married/adopted/legitimized/granted; born + founding wear the born form).
  Arx has no rows by canon — bare names are its signature. Full formal names
  carry the continental née segment `ne <BirthFamilyName>` (bare — it REPLACES
  the birth particle): "Sharlotte ne Regente dau Vaelmont". Degrees of address
  (`NameDegree`: familiar/common/styled/full-formal) and the orthogonal title
  suffix (`TitleSuffixMode`: none/primary/all) are per-`Persona` preferences;
  `Title` rows carry authorable holder styles (King/Queen/Monarch, tier-default
  PLACEHOLDER via `DEFAULT_TIER_STYLES`).
- **`HouseRecognitionRule`** — a realm's birth-recognition law
  (`MATRILINEAL_AUTO_WEDLOCK`, `MOTHER_OPTION_OUT_OF_WEDLOCK`,
  `CONSORT_CHILDREN_ENNOBLED`, `PATRILINEAL_AUTO_WEDLOCK`).
- **`FealtyEdge`** — vassal (OneToOne) → liege; the realm tree.
- **`SuccessionLaw`** — derivation (`PRIMOGENITURE_WEDLOCK`,
  `MATRILINEAL_RECOGNITION`, `FEMALE_LINE_CONSORTS_ENNOBLED`, `CHOSEN_HEIR`,
  `TANISTRY_ELECTION`) + ordering (`ELDEST`, `MOST_POWERFUL_GIFTED` — pluggable
  rater, PLACEHOLDER falls back to eldest) + `require_wedlock`/`enatic_tiebreak`.
  House default on `Organization.default_succession_law`; per-title override on
  `Title.succession_law` (Imperial Tanistry). **Authored content (#2875):**
  carries `NaturalKeyMixin` (`name`) + `CreditedContent` and is registered in
  `CONTENT_MODELS`; the lore repo owns the realm succession vocabulary.
- **`Title`** — first-class: name, tier (`TitleTier`:
  empire/kingdom/duchy/march/county/barony — #3091's six-step ladder), realm,
  house, holder (→ `Kinsperson`), seat domain, `is_claimable` (Phase D slots),
  authorable holder styles (`holder_style_male/female/neutral`, #3261).
- **`Domain`** — decorates an `Area` (seeds use `AreaLevel.REGION`; no DOMAIN
  level exists) (OneToOne PK): owner org + PLACEHOLDER civ stats
  (population/prosperity/unrest). Abstract — no room grids yet.
- **`HoldingKind`** / **`DomainHolding`** — authored holding vocabulary; each
  holding materializes an `OrgIncomeStream` (OneToOne) so collection, graft,
  and settlement reuse the audited currency pipeline unchanged. `HoldingKind`
  carries `NaturalKeyMixin` (`name`) + `CreditedContent` and is registered in
  `CONTENT_MODELS` (#2875); `DomainHolding` (the per-domain instance row)
  stays play state, not content.
- **`DomainImprovementDetails`** — per-kind details for `DOMAIN_IMPROVEMENT`
  projects.
- **`DomainCrisisType`** / **`DomainCrisisTypeOption`** (#2238) — the authored
  crisis catalog: resolution is per-type (PAY / MISSION / WAIT option rows, no
  JSON); `automated` types feed the system spawners with `spawn_weight`.
- **`DomainCrisis`** (#2238) — opened by improvement failure, unrest boil-over,
  or staff (`origin`). While open it holds the domain in a damaged-but-stable
  state (`income_factor` scales `Domain.income_multiplier` by severity — never
  compounds). The administrator's judgment call (`choose_crisis_option`,
  gated by `can_administer_domain`) pays it off (treasury debit), commits to a
  mission, or consciously rides it out — only a *chosen* WAIT ever rolls
  weekly self-resolve/worsen (`crisis_wait_tick`; AFK-safe by design). An
  AUTOMATED-origin crisis whose type has exactly one MISSION option pre-commits
  at creation. Mission completion resolves the source crisis
  (`resolve_crisis_for_mission`, wired into missions' terminal seam). Open
  crises surface on the house feed (`kind="crisis"`) and the org page's house
  block (`open_crises` with computed option costs). Lifecycle services live in
  `world/societies/houses/crisis_services.py`.
- **`MarriagePact`** — OneToOne → `roster.Union`; senior/junior house;
  dissolved with reason (DEATH/ANNULMENT/BREACH). **`PactCommitment`** — coded
  kind (DOWRY/SUBSIDY/CRISIS_RESPONSE/RESIDENCY/CUSTOM), amount/percent,
  optional `OrgObligation`, `breached_at`.

## Services (`world/societies/houses/services.py`)

`full_display_name(person, degree=, title_suffix=)` (the universal name
renderer, #3261 — canon grammar `[style] First [ne Birth] [particle Family][,
titles]`; particle band via `resolve_particle` + `house_tier_rank`),
`name_alias_forms` / `sync_name_aliases` (derived-name Evennia aliases under
the `derived_name` category so every degree form matches in telnet — called
explicitly from `add_membership`/`end_membership` primary writes and CG
finalize, never signals), `recognize_birth` (realm rules over
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
  peer: org, recognition rules, succession law, crown fealty, ducal title,
  domain + farmland holding; plus `seed_nobiliary_particles()` upserting the
  canon particle table onto every authored realm by theme (#3261 — Arx
  deliberately gets none).
- **Persona/web (#3261):** `PersonaSerializer.display_name` renders the
  particled name at the persona's preferred degree (non-primary faces stay
  bare — a mask never leaks the née segment); `POST
  /api/scenes/personas/{id}/set-name-display/` writes the degree/title-suffix
  preferences; `FamilySerializer` ships `born_particle`/`taken_in_particle`
  for the CG live preview (`FamilyNamePreview` in `LineageStage`).

## House creator (Phase D)

CG-only (Apostate ruling): a claim defines the house *retroactively* — the
character has always been its representative. Founding a brand-new house in
play (ennoblement, new lands) is a separate future loop.

`SuccessionLaw`, `HoldingKind`, `HouseTemplate` and `HouseFeature` all joined
`CONTENT_MODELS` in #2875 (same shape as `HouseAspectDefinition`/
`HouseAspectOption` below). `world/seeds/houses.py`'s `seed_houses_demo()` and
`_seed_house_creator()` look all four up via `authored_or_sample()` rather
than inventing them with `get_or_create()` (#2875 Task 2), mirroring the
#2868 aspect-catalog migration referenced above: a real content universe's
rows win and the PLACEHOLDER rows only appear under
`ARXII_SEED_SAMPLE_CONTENT`. The Crown organization and its Society (plain
seeder-owned config, neither in `CONTENT_MODELS`) moved to
`world.seeds.config_prerequisites._house_charter_anchors`
(`world.seeds.houses._ensure_house_charter_anchors`), run before the content
load so a content-repo `HouseTemplate`/`SuccessionLaw` row can FK them by
name (ADR-0171); `seed_houses_demo()` calls the same helper again once
"Arx" is available, the self-healing gameplay-call-site pattern ADR-0171
describes.

- **`HouseTemplate`**: realm recipe, name-pattern regex (the realm's naming
  conventions as an automated gate), `kind` (FK `roster.FamilyKind`, #3617; the
  kind the founded family gets), per-axis principle ranges, society, liege,
  succession law, holdings package, `starting_kin_slots`. **Authored content
  (#2875):** carries `NaturalKeyMixin` (`name`) + `CreditedContent` and is
  registered in `CONTENT_MODELS`; a realm's charter recipe is the lore repo's
  to write.
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
- **`build_family_org` is the shared builder (#3648).** `materialize_house_claim`
  no longer assembles Family + org + rank ladder + aspects + features + fealty
  itself; it calls `world.societies.houses.creator.build_family_org(template, name,
  *, description, aspect_picks, served_house, created_by, origin_realm, influence)`
  for that package, then does what only the title path needs: seat the title
  (FOUNDING membership), reassign the seat domain and materialize the holdings
  package, and sync the house channel. The CG name path (below, and
  `character_creation.services._materialize_named_family`) calls the same
  builder with `influence=0` and no title, domain, channel or review; see
  ADR-0272.
- **Surfaces:** `/api/character-creation/house-titles/` (claimable titles +
  templates), `GET/POST /api/character-creation/drafts/{id}/house-claim/`;
  the CG Lineage stage shows the "Define a House" panel to familyless
  drafts. Seeds: a set-aside claimable barony + charter template ride the
  `houses` cluster.

## Authoring a realm's charter (#2875, #3648)

A **charter** is a realm's recipe for the houses CG can define on its claimable
titles: one **Family Template** row (model class stays `HouseTemplate`, #3648,
generalized past nobles) plus the four catalogs it draws on.

- **What a charter holds:** the Family Template itself (name, name-pattern regex,
  principle ranges, `starting_kin_slots`, required `org_type`), its
  `default_succession_law` (a `SuccessionLaw` row, now nullable: only a title-path
  template needs one), its `holdings` (a set of `HoldingKind` rows materialized on
  the seat domain at founding, title path only), its `features` (a set of
  `HouseFeature` rows stamping structural cultural facts on every house of this
  template, no player input), and its `aspect_definitions` (a set of
  `HouseAspectDefinition` rows, each with its own `HouseAspectOption` catalog,
  the required choices a founder answers at CG).
- **`org_type`** (FK `OrganizationType`, required, #3648): the organization type a
  family of this template gets. Exports by the type's natural key and resolves on
  load against the prerequisite anchors, which now include `commoner_family`
  alongside `noble_family` (below): a Caretaker-style template resolves on a fresh
  database the same way a noble one does.
- **`served_house_choices`** (M2M `Organization`, blank, #3648): the staff houses a
  family on this template may declare it served (blank = the question is not
  offered). Names installation-specific orgs, so unlike the rest of the charter it
  is installation state, not corpus: it is listed in
  `EXPORT_FIELD_EXCLUSIONS["societies.housetemplate"]` and never reaches the
  content repo, the same shape as `npcrole.faction_affiliation`.
- **Where it is authored:** all five models carry `NaturalKeyMixin` and
  `CreditedContent` and sit in `CONTENT_MODELS`, so a charter is written the
  same way as every other piece of authored content post-ADR-0238: in the
  database, through Django admin or the Authoring Workbench
  (`web/admin/authoring`), never through content-repo branches and PRs. There
  is no fixture to hand-edit and no load path to run against a populated
  database. `SuccessionLaw.description` is the writer's field on the
  succession row (how the law shapes inheritance, in prose) - all five
  models now have a registered `ModelAdmin`, so the Workbench's change link
  and backlog queue reach every one of them.
- **Code prerequisites, not authored rows:** a Family Template FKs a `society` and,
  when a title path needs one, a `liege` organization (nullable since #3648, a
  Caretaker-style template sets neither), and neither is something the charter
  author creates. Both are seeded ahead of any content load by
  `world.seeds.config_prerequisites._house_charter_anchors`
  (`world.seeds.houses._ensure_house_charter_anchors`), named by
  `CROWN_ORG_NAME`/`SOCIETY_NAME` in `world/seeds/houses.py`. A charter
  author picks the realm's existing Crown organization and Society by name;
  they do not author new ones as part of the charter.
- **Founding copies the charter, it does not reference it live:** CG
  finalization's `materialize_house_claim` reads the approved `HouseClaim`'s
  template and stamps a one-time copy into play state: a `Family`, an
  `Organization` sworn to the template's `liege`, `OrganizationFeature` rows
  for each template feature, `OrganizationAspect` rows for the founder's
  picks, and the template's `holdings` package materialized on the title's
  seat `Domain`. Editing the `HouseTemplate` after a house has founded off it
  never changes that house; it only changes what the next founder sees.
- **Vacancies (#3648, ADR-0272):** `societies.Vacancy` is an opening on an already-
  materialized family's org, not part of the charter itself: it belongs to one
  staff-minted family, not to the Family Template every family of that type shares.
  Fields: `organization` (the family's org), `name`, `description`, `importance` /
  `presumed_importance` (the two authored axes), `cg_point_cost` /
  `cost_per_influence` (priced via `cost_for(influence)`, ADR-0269 extended by
  ADR-0272), `rank` (nullable; blank = the org's base rank), `kin_pool` / `kin_node`
  (at most one; set = a **kin** Vacancy, `basis == "kin"`; neither set = a
  **retainer** Vacancy), `count_remaining` (blank = a standing vacancy, always open,
  never decremented), `trust_required`, `allowed_upbringings` (blank = any
  Upbringing that can reach the org), `is_active`. Authored on the Organization
  admin page (inline) or standalone via Admin > Societies > Vacancies. It carries
  `NaturalKeyMixin` and `CreditedContent` (so it appears in the Authoring Workbench
  and can be credited) but is **not** in `CONTENT_MODELS` and never reaches the
  corpus export, the same installation-state reasoning as `served_house_choices`.

## Regional flavor: aspects + features (#2079)

Two deliberately distinct concepts give each realm's (and each noble-type's)
houses a unique creation experience (ADR-0101). Staff authoring a culture-specific
family fact off the CG claim path (a quiddity, a Letter of Marque) follows the same
two shapes; see Recipe 7 in `docs/systems/family-authoring-recipes.md`.

- **Aspect** — a required, normalized CHOICE. `HouseAspectDefinition` (name,
  player-facing prompt, `min_picks`/`max_picks`) attaches to templates via
  `HouseTemplate.aspect_definitions` (M2M — both Inferna templates can share
  "House Vice" while only the Cinderi template carries a diaspora choice);
  `HouseAspectOption` rows are its catalog. **Catalog-only by
  design** — no free-text answer path (ADR-0101). `HouseClaimAspect` records
  the founder's picks; `_validate_aspect_picks` refuses submission unless
  every attached definition is answered within [min, max] with active options
  of that definition.
  - **The catalog is lore-repo content (#2868).** Both models carry
    `NaturalKeyMixin` (definition keys on `name`; option on `definition` +
    `name`) and are registered in `CONTENT_MODELS`, so the rows are authored in
    the content repo and imported — the seeder may no longer invent them
    (`_seed_house_creator` uses `authored_or_sample`, #2698/ADR-0168). Its
    `PLACEHOLDER` catalog only appears under `ARXII_SEED_SAMPLE_CONTENT`.
  - **`HouseAspectOption.codex_entry` (#2868)** binds an option to the
    `CodexEntry` carrying its write-up — Inferna's seven House Quiddities each
    have one. Same shape as `Species.codex_entry` (PROTECT, nullable); exposed
    to CG as `codex_entry_id` on `HouseAspectOptionSerializer` so the option
    card can link its lore. This is a *property of the catalog row*, NOT a
    grant: picking a Quiddity does not award the entry to a character, which is
    what the `*CodexGrant` models do. `HouseAspectDefinition` has no such FK —
    the definition is the question the founder answers, not a lore subject.
- **Feature** — a structural cultural FACT, no player input.
  `HouseFeature` (name, unique `slug` as the stable code anchor, player-facing
  description) attaches via `HouseTemplate.features`; at CG it orients the
  founder ("a house of this charter keeps a Black Ledger"), in play it is the
  anchor future systems key off (`org.features` has slug `black-ledger` — data
  row + slug, never a bespoke code path). **Authored content (#2875):**
  carries `NaturalKeyMixin` (`name`) + `CreditedContent` and is registered in
  `CONTENT_MODELS`, the same shape as `HouseAspectDefinition`/
  `HouseAspectOption` below.
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

## House Stature (#3091, ADR-0209/0210)

Perceived-vs-true deterrence for landed orgs. Models
(`world/societies/houses/models.py`): `StatureBand` (authored percentile
tiers; `threat_multiplier` scales ambient predation; `headline_template` is
the org page's qualitative headline), `HouseStature` (per-org components:
renown/military/economic/allied, `crisis_penalty`, `true_total`,
`perceived_total`, band + previous band, `prestige_rank`, stored
`realm_rank`/`realm_cohort_size`), `StatureShift` (the "why it moved" ledger;
feeds tidings), `PrestigeRankBand` (rank-relative benefits; prosperity bonus),
`OrgPrestigeRank` (rank storage for unlanded orgs).

Services (`stature_services.py`): `compute_components` /
`recompute_stature` (channels: active members, the head's COURT covenant
members, living family kin — sheetless kin weigh `Kinsperson.gifted_rating` —
and union partners: marriage counts both spouses fully to both houses;
consort kinds count half to the senior's house only, gated on a landed Title,
capped per `UnionKind.max_concurrent`; paramour kinds weigh zero),
`converge_perceived`, `apply_death_shock` (vitals death seam),
`apply_pact_shift` (sign/dissolve seams), `crisis_stature_shift`
(open/resolve seams; covert threats hit perceived only after surfacing),
`apply_whisper` (spy campaigns, bounded below true), `assign_bands`
(percentile within org-category cohorts), `assign_realm_ranks`,
`recompute_org_prestige_ranks` (ALL orgs, one contextual ladder),
`apply_prestige_prosperity_drift` (high band + zero open threats → weekly
prosperity bonus; the ~3x income ceiling emerges from prosperity's 0-100
clamp), `weekly_stature_tick` (game_clock processor, before crisis
generation so predation reads fresh bands), `gifted_power_rating` (the first
live `register_gifted_power_rater` — `MOST_POWERFUL_GIFTED` succession now
orders by best class level / gifted_rating), `award_marriage_tier_prestige`
(flat permanent prestige by house tier gap; fires at formation in phase 3).

Surfaces: org API house block `stature` panel (headline/band/trend/components/
ranks; prefetched, zero extra queries), `domain stature` telnet subverb, house
feed + public tidings (`FeedItemKind.STATURE`), spy payouts
(`_stature_lines` on org/military reports; `whisper_stature_delta` route).
Seeds: `world/seeds/stature.py` (bands, rank bands, consort/paramour union
kinds — Luxen's non-recognition is the absence of a row). `TitleTier` is the
six-step noun ladder empire/kingdom/duchy/march/county/barony.


## Org pacts, betrothal & the dossier (#2999, ADR-0212)

`PactKind` (authored levers: `allied_share_pct`, `income_share_pct`,
`non_aggression`, `mutual_defense`) + `OrgPact` (party_a/b, proposed_by,
ratified/dissolved, `BETRAYAL` reason) — the signed-paper sibling of
`MarriagePact` (which stays the embodied instrument). Services
(`pact_services.py`): `propose_org_pact`/`ratify_org_pact` (leadership-gated;
tithe mints an `OrgObligation`), `dissolve_org_pact` (betrayal = permanent
prestige penalty), `flag_betrayal_between` (called from offensive spy-task
resolution), `standing_org_pacts` (stature's allied slot reads these at
their authored share alongside marriage pacts). `Betrothal` + `BetrothalTerm`
(negotiated CommitmentSpec drafts; 25% stature preview both ways;
`break_betrothal` costs standing) and `solemnize_wedding` — the WEDDING
`CeremonyTypeKey` resolves the honorees' active betrothal at
`finish_ceremony` and lands union + marriage pact + tier prestige in one
rite (first in-play caller of `record_union`). **Consent lives at the
ceremony, not the proposal** (#2358 ratified 2026-08-15): the officiant's
`open_ceremony` call mints a `WeddingConsentOffer` per spouse honoree at
ceremony START; `finish_ceremony`'s WEDDING branch refuses to solemnize until
every offer is ACCEPTED (`respond_to_wedding_consent_offer`, account-scoped —
telnet `wedding`, mirrors `CmdSeance`), and a DECLINE aborts the whole
ceremony. `propose_betrothal` itself stays an unconsented house-leader
proposal artifact. The **match dossier**
(`societies/dossier_services.py` + `GET /api/societies/organizations/{id}/dossier/`
+ `/orgs/:id/dossier`) is readable by ANY authenticated player: band/
perceived/ranks, standing instruments, betrothals, known troubles (covert
crises only via the viewer org's `CrisisIntel`), recent shifts, consort
capacity. Telnet: `CmdPact` (`pact propose/ratify/dissolve/betroth/breakvow/
divorce`). Seeds: cluster `pacts`. Union membership in stature reads the m2m
THROUGH table — never `prefetch_related("members")` (idmapper corrupts
prefetch grouping; see `_union_membership`).

**Divorce & coronation (#2358).** `initiate_divorce(initiator_sheet, union)`
(`pact_services.py`) — either spouse ends a living `Union` unilaterally:
`end_union` (`roster.services.kinship`, the first writer of `Union.ended_at`
since #2062) sets `ended_at`, `dissolve_pact` fires under
`PactDissolutionReason.DIVORCE` (the existing house-level `apply_pact_shift`
alliance reprice — non-punitive, fires for every dissolution reason), then
BOTH spouses take a personal deed-prestige hit via `award_deed_prestige`
(the same channel `award_marriage_tier_prestige` uses) — the initiator's
steeper (`DIVORCE_INITIATOR_PRESTIGE_PENALTY`/
`DIVORCE_OTHER_SPOUSE_PRESTIGE_PENALTY`, PLACEHOLDER magnitudes).
`ANNULMENT` stays the zero-penalty void path. Action `initiate_divorce`;
telnet `pact divorce <union-id>`.
`CeremonyTypeKey.CORONATION` solemnizes an ALREADY-HELD `Title` — no
title-passing mechanics; see `docs/systems/worship.md`'s Ceremony section
for the model/service detail (`Coronation`, `Ceremony.title`).
