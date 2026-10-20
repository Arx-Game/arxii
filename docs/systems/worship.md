# Worship & Ceremonies

Gods as authorable data with worship economies (#2355), and ceremonies as
lightly-structured freeform RP bookended by commands (#2289). Specs live in the
issue bodies; the model decision is ADR-0132.

## Worship foundation (`world/worship`, #2355)

**Models**

- `WorshipTradition` — lookup: name, description, `rites_specialization` FK →
  `skills.Specialization`. Bridges a being to the Rites specialization its
  ceremonies roll with. Seeded (PLACEHOLDER names): Church Liturgy,
  Spiritcalling, Druidry, Occultism.
- `WorshippedBeing` — the primitive (ADR-0132): name, PLACEHOLDER description,
  `domains` (#3776: plain free-text spheres, e.g. "Carnage, wanton bloodshed,
  feral battle, ferocity" — deliberately no lookup table; overlap across gods
  is expected and fine, and no mechanical matching need was confirmed), tradition
  FK, `resonance_pool` (BigInteger, spent by miracles and visions, #2360/#3779),
  `lifetime_worship` (monotonic audit), nullable OneToOne `avatar_sheet` →
  CharacterSheet (rare played gods), `is_active`, `tarot_cards` (#3776 Task 9:
  M2M → `tarot.TarotCard`, `related_name="represented_beings"`, blank, no cap —
  cards people believe represent this being; pure association, read by
  `is_birth_favored_by` below; since #4198 `through="arxii.BeingTarotCard"`, the link
  row carrying `is_reversed` - the through model adopted the auto M2M table in place,
  so `being.tarot_cards` and `.add()` still answer, and a reversed representation still
  counts as the card for birth favor), nullable `codex_entry` FK (#3776 Task 11:
  `codex.CodexEntry`, `on_delete=PROTECT`, `related_name="worshipped_beings"` —
  mirrors `Gift.codex_entry`/`Technique.codex_entry`/`HouseAspectOption.codex_entry`;
  visibility (Public/Obscure/Secret) is read entirely through the linked entry's
  `is_public` tier, no separate visibility field on `WorshippedBeing` itself; #3780
  spells the three tiers out as `BeingVisibility` in `editor_services.visibility_of`:
  PUBLIC when the entry is public, OBSCURE when an `OrganizationCodexGrant` names the
  organization whose membership knows it, SECRET otherwise or when no entry exists).
  `gm_notes` (#3780): staff-only prose (continuity, who the being was in Arx 1), never
  shown to players.
  Reuses `CodexEntry.quote` (#3776 Task 10, `codex/models.py`) for free: an optional
  italic intro line shown atop any entry's Codex page (blank hides it) — added as a
  general `CodexEntry` field (benefits every entry type, not worship-specific) so a
  being's page could open on an attributed quote without a worship-only field. Not
  yet exposed by `CodexEntryListSerializer`/`CodexEntryDetailSerializer` — reading it
  today means going through the model or admin, not the API.
- `BeingFacet` (#3776) — a being's favored aesthetic Facets: `being` FK,
  `facet` FK → the shared `magic.Facet` pool (same pool Motif draws from),
  unique per (being, facet). The deity page picks through the shared `FacetPicker`
  (#4197): search, "Did you mean" near-matches, and a staff-only **Create** for a
  spelling that resolves to nothing, so the vocabulary grows from the page that needs it.
- `BeingNickname` (#3776) — an alternate name a being's worshippers use:
  `being` FK (`related_name="nicknames"`), `name`, unique per (being, name).
  No reverent/irreverent field — tone is prose, not data. Reached
  transitively by `Organization.patron_nickname` (see societies.md) so
  different orgs can name the same god differently in their own records.
- `BeingResonance` (#3776) — a resonance a being favors or is merely
  associated with: `being` FK (`related_name="resonances"`), `resonance` FK →
  `magic.Resonance` (PROTECT, `related_name="favored_by_beings"`), `tier`
  (`BeingResonanceTier`: FAVORED/ASSOCIATED), unique per (being, resonance). No
  cap on how many a being holds — models "different kinds of worshippers" for
  the same being. Read by issue #3777's `WorshipRite` reward calculation
  (FAVORED pays double, ASSOCIATED the ordinary rate) and by #3776 Task 9's
  tarot/feast-day mechanic.
- `BeingTarotCard` (#4198) — the link row behind `WorshippedBeing.tarot_cards`:
  `being` FK (`db_column="worshippedbeing_id"`, `related_name="card_links"`), `card` FK
  (`db_column="tarotcard_id"`, `related_name="being_links"`), `is_reversed`
  (`db_default=False`). `db_table` is the auto M2M's own
  (`arxii_worshippedbeing_tarot_cards`), adopted in state by migration 0210 so the rows
  entered before the orientation existed carry over as uprights. One row per
  (being, card); reversal is a flag on the link, as `TarotCard.get_surname(is_reversed)`
  already treats it, not a second card. The Codex rail reads "The Tower reversed".
- `BeingRelationship` (#3776) — a public relationship fact between two gods:
  `being_a`/`being_b` FKs (`related_name`s `relationships_as_a`/`relationships_as_b`),
  `valence` (`BeingRelationshipValence`: ALLY/RIVAL/FEUD/UNKNOWN), `story_from_a` /
  `story_from_b` (#4198: freeform prose, one per side - each god's own telling of it;
  `story_from(being_id)` / `set_story_from(being_id, story)` pick the side, and
  `_normalize_order` swaps the stories with their beings). Two public prose fields and
  deliberately NO hidden-truth field on
  this model: a real hidden truth (why two beings actually feud) lives entirely as a
  separately-authored, separately-gated `CodexEntry` reached through a `Clue`, never a
  maybe-secret field here, because even a hidden/blank field on a public row would leak
  presence/absence of a mystery. ALLY/RIVAL/FEUD/UNKNOWN all read as undirected facts,
  so `being_a`/`being_b` carry no meaning of their own — `save()`/`clean()` sort the
  pair into pk-ascending order (mirrors `scenes.PersonaDiscovery` and
  `positioning.PositionEdge`), and `being_relationship_canonical_order` enforces it at
  the DB level too, so a caller can never record the same pair twice under swapped
  argument order. Unique per (being_a, being_b) post-normalization;
  `being_relationship_not_self` blocks a being from relating to itself.
- `WorshipFeastDay` (#3776 Task 9) — a being's annual feast day: `being` FK
  (`related_name="feast_days"`), `ic_month`/`ic_day` (no year — recurs every
  IC year, mirrors `weather.FeastDay`'s shape), `name`, `lore`. Worship gets
  its own model rather than reusing weather's — a religious concept shouldn't
  be owned by the weather app. Unique per (being, ic_month, ic_day). Feeds a
  universal worship-rite reward multiplier for anyone worshipping the being on
  that date (wired in #3777) — distinct from `is_birth_favored_by` below,
  which is per-character (tarot match + personal birthday), not per-date.
- `RiteKind` (#3777) — the pantheon-wide catalog of rite kinds: `name`, `description`,
  `tier` (`RiteTier`: 1 Devotional, 2 Demanding, 3 Perilous). Many kinds share a tier
  and the tier is the only mechanical fact a kind carries (AP cost = 1 per tier;
  tier 3 is a Ceremony). Seeded: Vigil, Sermon, Canticle, Blessing (1), Pilgrimage
  (2), Ordeal (3), all PLACEHOLDER.
- `WorshipRite` (#3777) — a being's own instantiation of a kind: `being` FK
  (`related_name="rites"`), `kind` FK, `name`/`description` (the being's flavor,
  unique per being+name), `check_type` FK, `resonance` FK → one of the being's own
  `BeingResonance` rows (`clean()` refuses another being's), `is_active`. No
  difficulty, cost or reward field: all read from the kind's tier. Authored per
  being (the Deity Editor, #3780); nothing seeds one.
- `WorshipRiteTierAward` (#3777) — the payout per (`tier`, `outcome_tier` FK →
  `traits.CheckOutcome`): `resonance_amount`, `favor_amount`; unique per pair. The
  `AnimaRitualBudgetAward` shape keyed additionally by tier, so three tiers tune once
  for every god; NOT an `OutcomeTierAward` subclass (that base's OneToOne allows one
  row per outcome). Every (tier, outcome) pair must be seeded; a missing row raises
  `RiteAwardMissing` rather than paying 0. Seeded 3 × 5 PLACEHOLDER rows.
- `WorshipRitePerformance` (#3777) — one performance: `character_sheet`, `rite`,
  `game_week` FK, nullable `scene`, nullable OneToOne `ceremony` (set for a tier 3
  rite), `outcome_tier`, `resonance_granted`, `favor_granted`, `performed_at`. The
  audit row, the `ResonanceGrant` source (`GainSource.WORSHIP_RITE`,
  `source_worship_rite_performance`) and the weekly devotion cap in one table.
- `Relic` (#3777) — a specific sacred item of a being: `being` FK
  (`related_name="relics"`), OneToOne `item_instance` → `items.ItemInstance`, `lore`.
  A particular named instance, never an archetype; distinct from the offering facet
  bonus below. Surfaced on the being's dashboard (#3780).
- `ShrineDetails` (#3778) — the room-level site: OneToOne `feature_instance` →
  `room_features.RoomFeatureInstance` (`related_name="shrine_details"`, a kind whose
  `service_strategy` is `SHRINE`), `being` FK (`related_name="shrines"`),
  `founder_character_sheet`, `consecration_points` (a plain counter), `created_at`.
  Reuses Sanctum's machinery exactly: one feature per room, soft-deleted through
  `RoomFeatureInstance.dissolved_at`; a dissolved shrine gives the room's slot back.
- `TempleDedication` (#3778) — the building-level site: `building` FK →
  `buildings.Building` (`related_name="temple_dedications"`), `being` FK
  (`related_name="temples"`), `founder_character_sheet`, one shared
  `consecration_points` for the whole building, `dedicated_at`, `dissolved_at`
  (partial unique: one active dedication per building). Every room whose area sits
  under the building's BUILDING-level `Area` node counts as sanctified, with no
  per-room duplication.
- `ConsecrationTier` (#3778) — the authored ladder per `scope` (SHRINE / TEMPLE):
  `name`, `min_points`, `bonus_percent` (unique per scope+min_points). Seeded
  PLACEHOLDER: shrine Humble 0 → 5%, Tended 25 → 10%, Hallowed 100 → 20%; temple
  Founded 0 → 10%, Consecrated 100 → 25%, Great 500 → 50%.
- `Prayer` (#3779) — a character's freeform words to a being: `character_sheet`,
  `being` FK (`related_name="prayers"`), `text`, `room_profile` (where it was made),
  `game_week`, `devotion_granted` (the weekly holy-site prayer's favor, else 0),
  `dire_straits` (`DireStraitsKind`: SOULFRAY / NEAR_DEATH / blank), OneToOne
  `intervention` → `MiraclePerformance` (the miracle that answered it, when one did),
  `prayed_at`. A plain log with no effect of its own: one of the few freeform channels
  a player has straight to staff.
- `Vision` (#3779) — a GM-sent vision, first-class and standalone: `recipient` sheet
  (`related_name="visions"`), `being` FK (the true sender), `sent_by` account, `body`,
  `reveal_source` (whether the recipient is told the being; the twisted-rite leak
  shape), optional `prayer` FK (the prayer it answers), optional `clue` FK → `clues.Clue`
  (a CODEX or SECRET clue the vision hands over; PROTECT), optional `episode` FK →
  `stories.Episode` (a personal beat of a story the recipient is in), optional `answer` FK →
  `Answer` (the written-ahead answer a closing rite released, #4333 slice 3; SET_NULL),
  OneToOne `message` → `narrative.NarrativeMessage` (the VISIONS-category delivery),
  `resonance_spent`, `sent_at`. Rarity is not enforced: a person writes each one, live or
  ahead of time (ADR-4333-B).
- `WorshipGrant` — audit ledger (being, amount, granted_by sheet, reason).
- `DevotionStanding` — one-way PC→god favor, unique (character_sheet, being).
  Chosen patronage fields (#2550): `valence` (nullable PatronageValence:
  DEVOTIONAL/ANTAGONISTIC/PACT — null = ordinary worship), `established_at`
  (when the patronage was established), `released_at` (set when the patron
  released the Chosen — null = active). Favor is the single favor number for
  both ordinary worship and patronage; `bump_devotion` accrues it regardless.
- `WorshipDeclaration` — OneToOne sheet: `public_being` + `secret_being`
  (both optional) + the minted `secret` FK. Secret worship mints a `Secret`
  (`worship/secrets.py: mint_worship_secret`, mirrors the secret-distinction
  pattern). Set at CG (`CharacterDraft.public_worship`/`secret_worship`,
  created in `_create_worship_declaration` at finalization). `public_is_sincere`
  (BooleanField, default True, #2361) — the heart-vs-lip-service inward truth:
  whether the character genuinely believes the public declaration or it's
  performative only. PRIVATE — the sheet identity serializer only shows it to
  the owner/staff (`worship_sincere` in `IdentitySection`, same leak-table
  pattern as `current_mood`); the public record (`worship`) shows the being to
  everyone regardless.
- `ChosenFavorConfig` — singleton (pk=1, lazy-created via
  `get_chosen_favor_config()`). Staff-tunable favor thresholds for Chosen
  benefits (#2550): `anima_recovery_threshold`/`anima_recovery_bonus` (wired —
  the Chosen's anima ritual adds the bonus to recovery budget when favor meets
  the threshold), `ceremony_edge_threshold`/`ceremony_edge_bonus` (deferred —
  defined for shape stability but inert until a future issue wires them).
- `PatronageValence` — TextChoice (DEVOTIONAL/ANTAGONISTIC/PACT). Null on
  DevotionStanding.valence means ordinary worship.

**Services** (`worship/services.py`)

- `grant_worship(being, amount, *, granted_by, reason)` → pool + lifetime +
  ledger row.
- `bump_devotion(sheet, being, amount, *, source=None)` → `DevotionBump(standing, credited,
  pledge_credit, earning_rate_percent)`:
  standing upsert + the God's Favorite check: reaching or tying the being's top
  favor grants the gender-matched achievement (God's Favorite Princess / Prince /
  Chosen; leapfroggers earn it too, prior holders keep theirs; text never names
  the being). Since #4333 a positive amount is scaled by the **earning rate**
  (`favor_services.earning_rate`: 100% + `ChosenFavorConfig.earn_bonus_percent`
  for an active patronage of the being + the character's favor earning modifiers),
  rounded down; `credited` is what landed, and the rite and prayer callers record
  it (`WorshipRitePerformance.favor_granted`, `Prayer.devotion_granted`). A Chosen
  bonus of 0 and no favor earning modifiers restore the old rates. Since #4333 slice 2
  a positive credit also goes to the character's open pledge to the being, when there
  is one (`pledge_services.record_pledge_credit`); `source` (`FavorSource`) names what
  the favor was for, so the pledge card can show it.
- `gods_favorite_achievement_for(sheet)` — gender-variant row resolution.
- `get_chosen_favor_config()` — lazy-create the singleton (pk=1).
- `active_patronage_for(sheet)` → active patronages (valence set, released_at
  null), ordered by favor descending. Empty list for non-Chosen or a Chosen
  who lost all patrons.
- `best_patronage_favor(sheet)` → the highest-favor active patronage's favor,
  or 0. Read by `apply_anima_ritual_outcome` to gate the anima recovery bonus.
- `establish_patronage(sheet, being, *, valence)` → get-or-create a
  DevotionStanding and mark it as patronage (sets valence/established_at;
  idempotent; preserves existing favor). Called at CG when Path of the Chosen.
- `release_patronage(standing)` → sets `released_at` (graceful degradation —
  the Chosen keeps the Path but this patron's favor no longer gates benefits).
- `convert_public_worship(sheet, new_being, *, is_sincere=True)` → WorshipDeclaration
  (#2361) — the single write path for a post-CG public conversion. Get-or-creates the
  declaration (a first post-CG public declaration is the same code path as a
  conversion), repoints `public_being`, stores the heart-vs-lip-service choice on
  `public_is_sincere`. Never touches `DevotionStanding` (old favor history for either
  being survives untouched) or the secret side (`secret_being`/`secret` — an old
  secret faith's `Secret` row is left standing as history, still discoverable).
  Called from `world.ceremonies.services.finish_ceremony`'s CONVERSION branch.
- `is_birth_favored_by(character_sheet, being, *, today=None)` → bool (#3776
  Task 9) — pure query, no side effects: True only when the character's own
  tarot card (`character_sheet.tarot_card`, a forwarding property onto
  `character_sheets.Profile.tarot_card` via `true_profile` — there is no
  separate `character_sheet.profile` accessor) matches one of `being`'s
  `tarot_cards` AND `today` falls on the character's
  `birthday_month`/`birthday_day`. `today` defaults to the current IC date
  (`world.game_clock.services.get_ic_now()`), matching how
  `world.tidings.services._birthday_items` already reads the same two fields
  — never the real wall clock; returns False (never raises) with no active
  `GameClock`. Read by issue #3777's worship-rite reward calculation to double
  the being-scoped payout; grants nothing itself.

**Rite services** (`worship/rite_services.py`, #3777) — mechanics serve RP: a rite
is a dramatic in-scene act with a real cost and an outcome-tiered payout, the
anima-recovery ritual's shape.

- `perform_worship_rite(character_sheet, rite, *, scene)` → `RiteOutcome`. Tier 1
  and 2 only (a tier 3 rite raises `RiteIsCeremony`); needs an active scene the
  performer has entered (`RiteScenePrerequisiteFailed`); charges `rite_ap_cost`
  (1 AP per tier, `RiteActionPointsInsufficient` when short) plus
  `RITE_SOCIAL_FATIGUE_COST` social fatigue before the roll (a botch still cost the
  effort); rolls the rite's `check_type` with the being's tradition specialization
  (the same modifier the ceremony Rites roll applies); then `apply_rite_award`.
- `apply_rite_award(character_sheet, rite, outcome, *, scene=None, ceremony=None)`
  — the shared payout: reads the (tier, outcome) award, applies
  `reward_multiplier_percent` (FAVORED being resonance ×2, `is_feast_day_today`
  ×2, `is_birth_favored_by` ×2, stacking; all PLACEHOLDER constants in
  `worship/constants.py`), writes the `WorshipRitePerformance`, grants resonance
  through `grant_resonance` (source `WORSHIP_RITE`) and bumps devotion unless
  `favor_capped_this_week`: favor from a given rite lands at most once per
  `GameWeek` per character; resonance is never capped, so repeating a rite stays
  fine for RP. Called by `finish_ceremony` for a RITE ceremony.
- Action: `PerformWorshipRiteAction` (registry key `worship_rite`, `category`
  "worship"): `rite` or `rite_name` (+ `being_name`) kwargs, resolves the scene from
  the actor's room, maps every `WorshipRiteError` to a soft failure.

**Prayer services** (`worship/prayer_services.py`, #3779) — a prayer is a message,
not a mechanic; three independent, stackable conditions make one count.

- `pray(character_sheet, being, text)` → `PrayerOutcome(prayer, at_holy_site,
  devotion_granted, dire_straits, intervention)`. Writes the `Prayer` first (it stands
  on its own; `PrayerEmpty` / `PrayerTooLong` / `PrayerBeingInactive` refuse before
  any write). Then: the **weekly holy-site prayer**: when the character's room holds a
  shrine or sits under a temple of the being (`consecration_services.sites_of`) and
  `site_prayer_capped_this_week` is False, `bump_devotion` pays
  `PRAYER_SITE_DEVOTION_AMOUNT` (once per being per `GameWeek`, below a tier 1 rite);
  and **dire straits**: `dire_straits_for(sheet)` reads Soulfray through
  `magic.services.soulfray.get_soulfray_warning` (a read on TehomCD's domain, not a
  redesign) and near death as `CharacterVitals.health_percentage <=
  KNOCKOUT_HEALTH_THRESHOLD` while alive; when either holds, `fire_divine_intervention`
  runs on the `NEAR_DEATH` trigger narrowed to the being prayed to, outside the
  prayer's transaction (a miracle is its own committed act). The performance's
  `trigger_event` is `prayer_soulfray` / `prayer_near_death` and the prayer records it.
- `send_vision(*, recipient, being, body, sent_by=None, reveal_source=False,
  prayer=None, clue=None, episode=None)` → `Vision`. Validates the attachments
  (`VisionPrayerMismatch`, `VisionClueNotCodex`, `VisionEpisodeNotShared`,
  `VisionRecipientUnrostered`), then in one transaction spends
  `VISION_RESONANCE_POOL_COST` from the being's pool through `spend_worship_pool`
  (`VisionPoolInsufficient`), records the `Vision` and hands a clue over through
  `clues.services.find_clue` (held, then `grant_clue_target` when the clue is AUTOMATIC;
  #4327, #4331; a RESEARCH clue is only held); only after that commit does it deliver the prose as a
  VISIONS `NarrativeMessage` (`send_narrative_message`: live push when online, login
  catch-up otherwise; `related_story` from the episode) and link it on the row, so a
  push never precedes a record that could roll back. A revealed source appends
  "You know whose vision this is: <being>." to the delivered prose; the stored `body`
  stays the GM's words.
- Actions (`actions/definitions/worship.py`): `PrayAction` (`pray`: `being` /
  `being_name`, `text`), `SendVisionAction` (`vision_send`, staff only: `recipient` /
  `recipient_name`, `being` / `being_name`, `body`, `reveal_source`, `prayer`, `clue`,
  `episode` ids). Telnet (`commands/worship.py`): `pray <being>=<words>`,
  `vision[/reveal] <character>/<being>=<prose>`, `vision/prayer <id> ...` (Admin).
- Delivery presentation: a VISIONS message is the one narrative category with its own
  tag and colour, `|G[VISION]|n` on telnet (Arx 1's green), and the frame carries
  `category` so the web feed files it as its own `vision` kind; see the narrative doc.

**Deity Editor** (`worship/editor_services.py`, `staff_serializers.py`, `staff_views.py`,
`filters.py`; #3780) — the staff tool that authors everything above. One long edit page,
saved live (no draft gate pre-launch); blank fields simply do not render on the Codex.

- `BeingPage` (dataclass) is the page: identity (`name`, `description`, `domains`,
  `tradition_id`, `is_active`), the Codex `quote`, `nicknames`, `resonances`
  (`ResonanceLine`), `facet_ids`, `feast_days` (`FeastDayLine`), `tarot_cards`
  (`TarotLine`: `card_id`, `is_reversed`; #4198), `relationships` (`RelationshipLine`:
  `other_being_id`, `valence`, `story` - this being's own side; the other god's side is
  never written from this page, #4198), `visibility`,
  `organization_id`, `gm_notes`. `save_being(page, *, being=None)` writes it in one
  transaction: the being, then its Codex page (`ensure_codex_entry` creates one under
  the seeded "The World" / "The Pantheon" subject when a public or obscure tier needs
  it; a secret being keeps whatever it has), the quote and `is_public`, the Obscure
  grant (`OrganizationCodexGrant`, handed to current members through
  `codex.services.grant_organization_entry_to_members`), and every satellite set
  replaced wholesale (the page is the truth; relationships are stored once per pair in
  canonical id order, so this being's page owns every pair it is part of and writes only
  its own side's story).
- `visibility_of(being)` / `obscure_organization_of(being)`: the read side.
- **The Codex reads it all (#4198, ADR-4198):** `worship/companion.py`
  `being_companion(entry, reader)` is the deity's Codex companion provider, registered
  from `worship/apps.py` `ready()` through `codex.companions.register_companion`. The
  rail, in order and each group left out when empty: Domains, Also called (nicknames),
  Feast day(s) (`format_ic_month_day`, "The Reaping Festival · Masquing 18 (10/18)",
  anchored to its section when the day has lore), Cards ("The Tower reversed"; a card has
  no entry of its own, so never a link), Favored, Associated, Facets, then one group per
  valence (Ally, Rival, Feud, Unclear) naming the other god as a link to its entry -
  drawn only when the reader may open that entry (`CompanionReader.may_see`), so a feud
  with a god the reader cannot see is not drawn at all - and last **Sworn houses**
  (#4205): the published organisations whose `patron_nickname.being` is this god, each
  a site-path link to its house page (`CompanionItem.href`, `/orgs/<id>`), left out when
  there is nobody. Sections under the Lore: one per
  feast day with lore (calendar order), one per visible relationship whose story from
  this god's side is non-blank. Before #4198 nothing read these rows.
- API (`/api/worship/admin/beings/`, staff only, `StaffBeingViewSet`): list = tiles
  (`StaffBeingListSerializer`: name, first nickname as an annotation, domain chips,
  pool, lifetime worship, visibility, organization; sorted by pool; `search` on name
  and nicknames; `StaffBeingFilterSet` `visibility` / `tradition` / `is_active`),
  retrieve / create / update = the page (`StaffBeingPageSerializer`; no PATCH at all,
  a 405, since a partial write would empty the lists it omits; a taken being name or a
  same-named page already under The Pantheon is a 400, never adopted), `options`
  (every picker's choices), and the dashboard actions `overview` (pool, lifetime, most
  devoted, site count, a merged recent-activity feed of grants, rite performances,
  prayers and visions), `worship` (contributors, offerings, most devoted on one tab),
  `sites`, `prayers`, `visions`, `relics`, `codex` (the being's page, its prerequisite
  chain, entries its visions' clues open; per entry the tier, the organizations that
  know it and the clues that target it). Web: `frontend/src/pantheon/` at
  `/staff/pantheon`.

**Consecration services** (`worship/consecration_services.py`, #3778) — shrines and
temples are places, not fees: a site of the rite's own being boosts the award, and
the rite consecrates the site in turn.

- `shrine_at(room_profile)` → the room's active `ShrineDetails` or None;
  `building_over(room_profile)` walks `Area.parent` up from the room's area to the
  BUILDING-level node (self first, cycle-safe) and returns its `Building`;
  `temple_over(room_profile)` → that building's active `TempleDedication` or None.
- `sites_of(room_profile, being)` → `ConsecrationSites(shrine, temple)`, each only
  when the site belongs to `being`; `ConsecrationSites.bonus_percent()` adds the shrine
  bonus and the temple bonus, each read through `tier_bonus_percent(scope, points)`
  (the highest `ConsecrationTier` whose `min_points` the site has reached). Stacking
  is additive: a cathedral's own inner altar is a shrine inside a temple.
  `consecration_bonus_percent(room_profile, being)` is the one-call form.
- `apply_rite_award` resolves the room from the scene (or the ceremony's scene),
  resolves the sites once, multiplies the tier award by `100 + bonus` after the
  FAVORED/feast/birth multipliers, and calls `grow_consecration(sites, rite)` in the
  same transaction: every site gains `rite.tier` × `CONSECRATION_POINTS_PER_RITE_TIER`
  points through an `F()` update (race-safe across the game server and web requests),
  and the held row is set from a `values_list` read, since `refresh_from_db` is a
  no-op on an identity-mapped row. `RiteOutcome.consecration_bonus_percent` reports
  what applied. A site of another being neither boosts nor grows.
- Founding gates on holding the place, never on payment: `found_shrine(room_profile,
  being, founder)` requires the founder's persona to be the room's
  `effective_owner` (`SiteNotHeld`), refuses a room whose one feature slot is taken
  by an active feature or a dissolved feature of another kind (`SiteAlreadyTaken`;
  Sanctum keeps its dissolved rows as history), and creates the `RoomFeatureInstance`
  through `ensure_shrine_kind()`; `dissolve_shrine(shrine, persona)` soft-deletes it.
  `dedicate_temple(building, being, founder)` requires the persona to hold the
  building: its credited `owner_persona`, the holder of the building's area through
  `effective_owner_for_area`, or a leader of the holding org (`is_org_leader`); one
  active dedication per building; `revoke_temple(dedication, persona)` closes it.
  Holding one room inside the building is not holding the building.
- Actions (`actions/definitions/worship.py`): `FoundShrineAction` (`shrine_found`),
  `DissolveShrineAction` (`shrine_dissolve`), `DedicateTempleAction`
  (`temple_dedicate`), `RevokeTempleAction` (`temple_revoke`); each resolves the
  actor's active persona and current room (`being` or `being_name` kwarg) and maps
  every `ConsecrationError` to a soft failure.
- The SHRINE `RoomFeatureServiceStrategy` is registered by `world.worship.apps.ready`
  (called from `world/apps.py`); its progression handler refuses the generic
  ROOM_FEATURE_PROGRESSION project path, since a shrine is founded by its holder,
  never built as a project.

### Favor with beings: invoking favor (#4333, slice 1) [BUILT & WIRED]

Spec and demo: issue #4333 (slice 1 is #4353). Decision: ADR-4333-A (favor is
invoked through a check and never spent). Favor (`DevotionStanding.favor`) is a
character's standing with one being; it is never spent.

**Models**

- `DevotionConfig` — singleton (`invocation_services.get_devotion_config()`):
  `invocation_check_type` (default; nullable, invoking is refused until set or the
  being has its own), `base_difficulty` (`DifficultyChoice`, default Daunting),
  `favor_ease_low_threshold`/`_points` (30/15) and `favor_ease_high_threshold`/`_points`
  (60/30), `invocations_per_week` (3). Example tuning throughout.
- `FavorOutcomeAward` — `config` FK, `kind` (`FavorAwardKind`: INVOCATION = check points
  added to the check; CLOSING = base favor a pledge's closing rite pays, read from slice 2),
  `outcome_tier` FK `CheckOutcome`, `amount`; unique per (config, kind, tier). Not an
  `OutcomeTierAward` (its one-to-one allows one row per tier). A missing INVOCATION row is
  no bonus.
- `FavorInvocation` — one rolled invocation: the weekly counter and the log
  (`character_sheet`, `being`, `game_week`, `outcome_tier`, `bonus`, `player_line`, nullable
  `scene` / `mission_instance`, OneToOne `scene_action_request`). The only stored player
  text is `player_line`.
- `WorshippedBeing.invocation_check_type` — optional per-being override (ruling 13).
- `ChosenFavorConfig.earn_bonus_percent` (100) and `.invocation_ease_points` (30).
- `MissionGroupBallot.invoke_being`/`invoke_line` and `SceneActionRequest.invoke_being`/
  `invoke_line` — a declared invocation held until its check rolls.

**Favor modifiers** (`worship/favor_services.py`). Two `ModifierCategory` rows,
`favor_invocation` (difficulty points eased) and `favor_earning` (percentage points added
to the earning rate). `ModifierTarget.target_being` scopes a target to one being; null in
those categories means any being. Uniqueness: (category, target_being) when the being is
set; `ModifierTarget.clean()` holds the single "any being" target per category and refuses a being outside the two favor categories.
`ensure_being_modifier_targets(being)` get-or-creates the being's two targets and the two
"any being" targets; called by the Deity Editor's `save_being`, the seeds, and the backfill
migration `0224_being_favor_targets`. `favor_modifier_total(sheet, being, category)` is the
one reader: over the category's targets for the being and for any being, it sums
`get_modifier_total` (distinctions and other `CharacterModifier` rows, crafted items, the
equipment walk) and `get_condition_modifier_total` (conditions). Both favor categories are
in `EQUIPMENT_RELEVANT_CATEGORIES`, and for them the walk counts a covenant role once
(`covenant_role_base_total`). Facet, mantle and motif bonuses reach targets only through a
resonance, so they add nothing here (slice 8 covers favored facets).
`earning_rate(sheet, being)` feeds `bump_devotion`, which applies it and returns the rate on
`DevotionBump.earning_rate_percent`.

**Invocation** (`worship/invocation_services.py`)

- `invocation_difficulty(sheet, being)` → `InvocationDifficulty`: base points minus the
  Chosen ease (active patronage of the being), the favor ease (by threshold), and the
  favor invocation total; never below Trivial (15). Each ease is labelled for the picker.
- `invocation_refusal(sheet, being)` / `check_can_invoke` — favor above zero, a use left
  this week (every invocation counts, failures too), a check type configured.
- `invoke_favor(sheet, being, *, actor_name, player_line, scene, mission_instance,
  scene_action_request)` → `InvocationOutcome`: rolls `perform_check_with_modifiers` with
  the being's (or the default) check type and the tradition's Rites specialization at that
  difficulty, writes the `FavorInvocation`, and returns the FAVOR `ModifierContribution`
  ("<being>'s favor (invocation: <outcome>)") and the lines. Favor is unchanged.
- Lines (design 1): "<name> calls on <being>: <line>" (or "<name> calls on <being>."),
  then "<name>'s invocation: <outcome>.". For a secret faith (the declaration's
  `secret_being`) the public call line is "<name> calls on something." with no line; the
  actor still gets their own. The bonus is never in a room line.
- `invocation_options(sheet)` / `invocation_bonus_table()` — the picker's data; also
  served at `GET /api/worship/beings/invocation-options/` (`entry_id` names the character).

**Where the bonus lands**

- Missions: `resolve_beat_option(..., invoke=InvocationChoice)` and `submit_group_pick`
  (stored on the ballot; it rolls at node resolution, only for a pick whose check rolls).
  `resolve_option(..., invocation=)` rolls first and adds the bonus to `extra_modifiers`;
  lines go to every participant's mission log (`missions/services/invocation.py`). The solo
  result carries `BeatInvocation` (lines, points before and after, ranks; never the roll).
- Scene self-checks and answered check calls (`invoke_being_id`/`invoke_line` kwargs on
  `scene_self_check` / `answer_check_call`): roll at once; lines are OUTCOME interactions.
- Scene actions: `create_action_request(..., invoke=)` stores the choice; at accept time
  `scenes/favor_invocation.declared_invocation_contribution` rolls it once per request and
  the contribution joins the check (`extra_contributions` on the plain path).
- Telnet: `invoke` lists beings, difficulty and uses; a trailing
  `/invoke <being>[=<line>]` works on `check`, `check answer`, `mission resolve`,
  `mission pick` and the social actions (`commands/utils/invocation.py`).

**Admin**: Devotion config (singleton change form, the awards inline, a read-only
difficulty table and last week's invocations), Chosen favor config (the two new terms,
Chosen per being), the being's check type override, the Distinction Builder's favor-target
help line. Required-content sentinels: `favor-invocation-check-type`,
`favor-invocation-awards`.

### Favor with beings: pledges and sacrifices (#4333, slice 2) [BUILT & WIRED]

Spec and demo: issue #4333 (slice 2 is #4362; walkthrough A steps 1 and 2). Decision:
ADR-4362 (pledge credits explain a pledge's favor and never count it). Favor is the only
pledge progress (Ruling 9).

**Models**

- `Pledge` (`CreditedContent`) — a pledge type: `being`, `name`, `description`,
  `favor_target`, `span_weeks`, `closing_rite` (FK `WorshipRite`; `clean()` requires one of
  the being's own tier 1 or 2 rites, since a tier 3 rite is a ceremony), `is_active`; unique
  (being, name).
- `PledgeDetails` — the PLEDGE project's sidecar: O2O `project`, `character_sheet`,
  `pledge`, nullable `prayer` (the `Prayer` pledged with; the text lives there),
  O2O `closing_performance` (the `WorshipRitePerformance` that resolved it; empty for an
  open or lapsed pledge), `close_attempts`.
- `PledgeCredit` — one favor credit with its calculation: `pledge_details`, `source`
  (`PledgeCreditSource`: DEED, SACRIFICE, RITE, PRAYER, CEREMONY_OFFERING, CEREMONY, CLOSING,
  LAPSE, OTHER), `base`, `earning_rate_percent`, `credited`, `game_week`, and the typed
  source (`resonance_grant` O2O, `offering` O2O, `rite_performance`).
- `DevotionConfig` gains `favored_deed_percent` (100), `associated_deed_percent` (50) and
  `weekly_deed_favor_cap` (8, base favor). `FavorOutcomeAward` CLOSING rows are the closing
  awards (seeded 8 / 5 / 3 / 2 / 0). Its `sacrifice_value_per_favor` was removed in #4500
  (see "Sacrifices count by meaning" below).
- `CeremonyOffering` (ceremonies) gains nullable `being`, `pledge_details` and `facet`;
  `ceremony` is nullable; a CHECK requires exactly one of ceremony or being (migration 0234,
  its own migration after the columns in 0233).
- `ProjectKind.PLEDGE`, registered expiry-only (`projects.services.register_expiry_only_kind`).

**Services** (`worship/pledge_services.py`)

- `take_pledge(sheet, pledge, *, prayer_text="")` — one open pledge per character (the sheet
  row is locked while checking); opens a SINGLE_THRESHOLD PLEDGE project (threshold = favor
  target, time limit = span x 7 days) and the sidecar; a prayer goes through `pray`, after
  the pledge opens, so a holy-site prayer's devotion already counts.
- `record_pledge_credit(...)` — called by `bump_devotion` for every positive write: the open
  pledge to that being gains the credited favor on `current_progress` and a `PledgeCredit`.
  CLOSING and LAPSE credits name their pledge and add no progress.
- `credit_pledge_deed(grant)` — called by `grant_resonance` after it writes the ledger row.
  With an open pledge whose being holds the grant's resonance as FAVORED or ASSOCIATED: base
  = amount x the percent, rounded down, at least 1, held to what is left of the week's cap.
  WORSHIP_RITE grants are skipped (the rite pays favor itself). So are the passive sources in
  `PASSIVE_DEED_SOURCES` (`worship/constants.py`): the residence and outfit trickles, distinction
  grants and staff grants. Favor comes only from a character's actions (ruling 2026-10-16).
- `close_pledge(sheet, *, scene)` — needs the target met and the span not over; runs
  `perform_worship_rite(..., pay_award=False)` (the roll and the performance row are kept,
  the rite's own award is not paid, `record_unpaid_performance`). A first Failure or
  Critical Failure only counts the attempt (Ruling 17). Otherwise, in one atomic block, the
  project goes to RESOLVING, the performance is recorded and `resolve_project` runs; a
  failure restores the identity-mapped project and sidecar.
- `resolve_pledge_project(project, outcome_tier)` — the PLEDGE handler. With a closing
  performance it pays the CLOSING award for the rite's tier; without one it is a lapse (the
  tick resolved it at the time limit): half the target or more pays the Partial Success
  CLOSING award, less pays nothing (Ruling 18). Awards go through `bump_devotion` at the
  earning rate; earned favor is never taken back. The closing answer (slice 3) is delivered
  by `close_pledge` after this resolution commits, never from inside it.
- `service_terms(sheet, being)`, `pledge_card(details)`, `holy_sites_here(sheet)`,
  `open_pledge_for` / `latest_pledge_for`, `broadcast_room_line`.
- Sacrifices (#4500, ADR-4462): see "Sacrifices count by meaning" below.

**Sacrifices count by meaning** (`ceremonies.services.sacrifice_items(sheet, items, *,
being=None)`, `worship/sacrifice_services.py`) [BUILT & WIRED]

No favor, pool grant or prestige reads an item's price, a fee or a material cost. A
sacrifice (at a shrine in the room or a temple over it) is a check eased by what each item
means to the one giving it up:

- Each item is read once (`ceremonies.services.read_item`): `item_meaning` returns its
  signals (carried, gift, heirloom, own work, made by a tie, and since #4512 designed by you,
  made for, made from and shown; see `docs/systems/items.md`),
  and a carried facet the being favors multiplies the points by
  `CeremonyConfig.offering_favored_facet_multiplier_percent`.
- An item with 0 points is given up with no roll, no favor, no pool grant and no use of the
  weekly limit. An item with points rolls the being's invocation check type (else the
  devotion config's) at the `invocation_difficulty` (Chosen ease, favor ease and favor
  invocation modifiers keep applying) eased by points x
  `DevotionConfig.sacrifice_ease_per_point`, never below Trivial. A piece's design and
  dedication survive its being given up (#4512): examine still credits its maker, designer
  and facet workers, marked "Gone: given up to <being>". With no check type
  configured the sacrifice is refused before anything is given up.
- The outcome tier selects the `FavorOutcomeAward` of kind SACRIFICE (seeded 6 / 4 / 2 / 0 /
  0 by `ensure_favor_terms`; a missing row pays nothing). That is the base favor;
  `bump_devotion` applies the earning rate and credits an open pledge, as before.
- At most `DevotionConfig.sacrifices_per_week` items with points count per being, per
  character, per game week, shrines and ceremonies together (`sacrifice_slots_left`); items
  past it are given up for nothing, and a Critical Failure closes the being's hand to that
  character until the next week.
- Every counted item grants `effective points x CeremonyConfig.offering_pool_per_point` to
  the being's pool whatever the roll (`give_up_item`).
- The item is soft-destroyed with `preserve=True` (design kept, #4461); the
  `CeremonyOffering` records the roll (`outcome_tier`), the week (`game_week`), whether it
  `counted`, and one `OfferingSignal` per signal (kind, points, detail), since the item and
  its holder are gone. The GM's steward panel lists each sacrificed item with its signals and
  roll (`answer_services.sacrifice_detail`); the pledge card credit and the being's
  dashboard row read the same signals. One room line, "<name> sacrifices <item> at
  <being>'s shrine.", is unchanged.
- `record_offering` (ceremonies) uses the same reading: the officiant's devotion is
  `effective points x CeremonyConfig.devotion_per_offering_point` and is not rolled (the
  rite's own roll is the check); it shares the weekly limit. `finish_ceremony` prestige drops
  the offering-value term (`offering_prestige_per_value` was removed) and keeps the
  deed-legend term.

**Surfaces**

- Actions: `pledge_take` (`TakePledgeAction`; pledge pk, or names), `pledge_close`
  (`ClosePledgeAction`; starts or joins the room's scene through `StartSceneAction`; the room
  sees "<name> performs <rite>." and nothing of the result), `sacrifice` (`SacrificeAction`;
  item pks from the web, names from telnet). `PerformWorshipRiteAction` writes the same rite
  line. Being kwargs accept a pk (the web) or a name.
- API: `GET /api/worship/pledges/?being=`, `GET /api/worship/pledge-cards/?character_sheet=`
  (own characters, staff all), `GET /api/worship/beings/{id}/service-terms/` (`character_sheet`
  the requester plays, or `entry_id`), `GET /api/worship/beings/holy-site/`.
- Web: the sheet's Worship section (Pray, Sacrifice, Pledge yourself; the pledge card in three
  labelled parts with each credit's calculation and Close once ready); the room panel's
  holy-site line (`HolySiteBlock`).
- Telnet: `pledge`, `pledge <being>`, `pledge <being>/<pledge>[=<prayer>]`, `pledge/close`,
  `sacrifice <item>[,<item>...][=<being>]`.
- Admin: the **Being Service builder** (`/admin/_being_service/<being>/`,
  `web/admin/being_service/`): favored resonances (with deed favor and the last 30 days'
  grants to the being's worshippers by source), favored facets, every pledge type (with how
  long its target takes from deeds alone at the cap), the favor modifiers authored against
  the being's targets, a rail of worship numbers, checks and credit with Mark reviewed. It
  creates the being's favor targets when it opens. `PledgeAdmin` and `PledgeDetailsAdmin`
  are read-only. Devotion config shows the four earning fields. Required-content sentinel:
  `favor-closing-awards`.

### Favor with beings: answers at the close (#4333, slice 3) [BUILT & WIRED]

Spec and demo: issue #4333 (slice 3 is #4374; walkthrough A steps 3 and 4). Decision:
ADR-4333-B (a vision written ahead may be released by a closing rite). Stewards are slice 4
(below); answering live is slice 5 (below).

**Models**

- `Answer` (`CreditedContent`) — text staff wrote ahead for a being at one outcome tier:
  `being`, nullable `pledge` (empty = the being's general answers), `outcome_tier`,
  `delay_text`, `answer_text`, `fact_text`, nullable `fact_clue` (CODEX or SECRET),
  `cost_text`, nullable `cost_pool` (`ConsequencePool`), `follow_up_text`, nullable
  `follow_up_clue`, `onlooker_line`, `conceals_source`, `weight`, `is_active`; index on
  (being, pledge, outcome_tier). `clean()` applies `answer_part_errors`: fact text and fact
  clue on Success and Critical Success only, the follow-up clue on Partial Success and above.
- `AnswerSacrificeLine` — (answer, facet, text), unique per answer and facet.
- `PendingAnswer` — (character_sheet, answer PROTECT, O2O pledge_details, created_at): an
  answer whose being's pool could not yet pay for the vision.
- `Vision.answer` (above). Migration 0235 is schema only.

**Services** (`worship/answer_services.py`)

- `draw_answer(details, outcome_tier)` — the pledge type's active rows at the closing tier,
  then the being's rows with no pledge type, then the same two steps one tier lower, down to
  the lowest; each step is a weighted choice (`select_weighted`) that leaves out answers the
  character already drew (delivered or held). None means no vision; the award still lands.
- `answer_body(answer, offerings)` — delay; answer text then one sacrifice line per distinct
  facet recorded on the pledge's sacrifices (`CeremonyOffering.pledge_details`), other items
  listed by name ("Also sacrificed: ..."); fact text (Success and above only); cost; follow-up.
- `deliver_answer(details, answer)` — `send_vision(sent_by=None, reveal_source=not
  conceals_source, prayer=details.prayer, clue=<fact clue at Success and above>,
  answer=answer)`, then the follow-up clue through `find_clue` (Partial Success and above;
  the same AUTOMATIC/RESEARCH rule a vision's clue follows, #4331), then the cost pool through
  `apply_pool_for_tier` at the answer's own tier. A short pool holds it as a `PendingAnswer`.
  `send_vision`'s clue guard now accepts SECRET as well as CODEX (`VisionClueNotFact`).
- `deliver_pledge_answer(details, outcome_tier)` — called by `close_pledge` after the
  resolution block commits (a vision is pushed to the player the moment it is written, so it
  must never be written inside a transaction that can still roll back). `ClosingOutcome`
  carries the `AnswerDelivery` (answer, vision, held).
- `deliver_held_answers()` — the daily tick `worship.held_answers`
  (`world/worship/tasks.py`): oldest first, each whose being's pool can pay; one refused
  attachment is logged and kept.
- `cost_condition_names(answer)` — the vision's condition footnote.

**Surfaces**

- Room: after the rite line, the answer's `onlooker_line` when the vision went out at the
  rite (`ClosePledgeAction`); a held answer sends no room line later. Nothing player-written
  reaches the room, so a secret faith's close carries no player line.
- Web: the sheet's `VisionCard` footnotes the fact clue, the follow-up and the cost's
  condition (`VisionSerializer.clue_name`, `follow_up_footnote` - "A mission came with it"
  for a mission clue - and `condition_names`); `answer_footnotes` ends the `[VISION]`
  narrative message with the same lines for telnet. The
  Deity Editor dashboard's Overview counts pledge types, answers and held answers and links
  both builders; its Visions tab lists held answers
  (`GET /api/worship/admin/beings/{id}/held-answers/`).
- Telnet: the vision arrives as a `|G[VISION]|n` narrative message, as every vision does,
  ending with the footnotes. It is pushed while the close runs, so it prints before the
  closing-award line.
- Admin: the **Answer builder** (`/admin/_being_answers/<being>/?pledge=&tier=&answer=`,
  `web/admin/answer_builder/`): a coverage grid (no pledge type and each pledge type, by
  tier), one answer's form with its sacrifice lines, what each linked clue and pool is, a
  vision preview, the being's worship, checks (tier rules, a public codex entry, missing
  tiers and what they fall back to) and credit with Mark reviewed. Reached from the being's
  change form, the Being Service builder (per pledge type "N of 5 outcome tiers written")
  and the Deity Editor. `AnswerAdmin` and `PendingAnswerAdmin` are read-only.

### Favor with beings: stewards (#4333, slice 4) [BUILT & WIRED]

Spec and demo: issue #4333 (slice 4 is #4416; walkthrough C). Decision: ADR-4333-C (free text
only from a being's steward). Answering live in a GM-run scene and `GMLevelCap.may_adapt_answers`
are slice 5 (below).

**Models**

- `BeingSteward` — (O2O being CASCADE, table FK `GMTable` PROTECT, assigned_at): the GM table that
  answers for a being. `clean()` raises `steward_refusals`. Staff assign it on the being's admin
  change form (`BeingStewardInline`, `OneRowPerFormSet`, at most one), which shows the table GM's
  level, its active members, the other beings it stewards and the god signs checked.
- `DevotionConfig.steward_answer_days` (default 3, example tuning): the window the table GM has.
- `GMPrompt.pledge` (FK `PledgeDetails`, SET_NULL) and `GMPromptKind.BEING_ANSWER` /
  `GMPromptGroup.BEING_ANSWER` ("Being answers"); BEING_ANSWER is a decision kind
  (`DECISION_PROMPT_KINDS`): addressed to one GM, resolved by their own action, no default lines.
  Migration 0243 is schema only.

**Services** (`worship/steward_services.py`)

- `god_signs(being, table)` — there is no god flag, so: a public codex entry
  (`codex_entry.is_public`); any `WorshipDeclaration.public_being`; a Chosen (valence set, not
  released) who is not an active member of `table`; an active `TempleDedication`. A secret faith
  is not a sign. `steward_refusals(being, table)` adds a GM below `GMLevel.SENIOR` and an archived
  table (Ruling 5).
- `stewarded_refusal(sheet, being)` — "<being> answers only to the members of one GM table." for
  anyone not seated at the steward table (an active `GMTableMembership` whose persona is the
  sheet's). Asked by `take_pledge` (`StewardedBeingClosed`), `pray` (`PrayerError`),
  `invocation_refusal` and the sacrifice site; a member's sacrifice to a named stewarded being needs
  no shrine (`_sacrifice_site` returns site "", room line "<name> sacrifices <item> to <being>.").
  `PledgeViewSet` lists a stewarded being's pledge types only to its members, its GM and staff.
- `route_to_steward(details)` — called by `close_pledge` in place of the draw once the resolution
  commits: a scene-less `BEING_ANSWER` prompt through `route_narratable_event` with the table GM as
  the only candidate. A GM who muted the group, or who plays the closing character, is not prompted
  and the answer is drawn as for any being. `AnswerDelivery.awaiting_steward`; the close message
  adds "<being>'s answer will come later."
- `answer_options(details)` — the being's active answers (this pledge type's and its general ones)
  at or below the closing tier. `may_write_free_text(details)` — Success and Critical Success only.
  `catalogue_clues(being)` — the clues its answers already link (fact or follow-up); staff create
  clues.
- `send_steward_answer(prompt, *, resolver, answer=None, text="", clue=None)` — one authored
  option (delivered by `deliver_answer`, held while the pool is short) or the GM's own text
  (`send_vision(sent_by=<GM>, reveal_source=True, prayer=...)`; a CODEX or SECRET clue rides the
  vision's clue slot, any other is handed over by `find_clue`). Free text needs the pool to pay
  now. The prompt is resolved (CONFIRMED) under a row lock before anything is sent.
- `dismiss_being_answer(prompt, *, resolver)` — DISMISSED, then `deliver_pledge_answer` draws an
  authored answer: never dropped. `dismiss_gm_prompt` routes the kind here, so the web queue's
  Dismiss and telnet `gm prompt dismiss` both use it.
- `expire_steward_prompts()` — the hourly tick `worship.steward_answer_timeout`: a prompt older
  than `steward_answer_days` is closed the same way, with "No answer within N days: an authored
  answer was drawn."

**Surfaces**

- Table page (`/tables/:id`, Beings tab, GM and staff; `?tab=beings` opens it): GM prompts with
  Open and Dismiss, the answer panel (pledge, tier, sacrificed items, prayer, the answers at the
  tier and below, Write free text, the catalogue clue picker, Send as <being>, time left in the
  window); one card per stewarded being (what it favors, pledge types with favor target and span,
  "N of 5 outcome tiers written"); Edit opens the pledge type form and the answer form by tier
  with the coverage grid and the catalogue. API under `/api/worship/`: `stewarded-beings/`,
  `steward-pledges/`, `steward-answers/`, `steward-sacrifice-lines/`, `steward-prompts/` (+
  `answer/`, `dismiss/`), all scoped by `stewarded_beings_for(account)`; answers keep the tier
  limits and take clues only from the catalogue; the GM's `PlayerData.contributor` is credited.
- Scene GM queue: a being answer row (`GMPromptSerializer.being_answer_summary`,
  `being_answer_table`) with Open (the table's Beings tab) and Dismiss.
- Telnet: `gm prompts` lists it; `gm prompt answer <id>` lists the options, `answer=<id>` sends
  one, `text=<words> [clue=<id>]` sends the GM's own; `gm prompt dismiss <id>`.
- Admin: the Answer builder's rail names the steward ("None (staff-owned)").

### Favor with beings: answering live (#4333, slice 5; completes #3298) [BUILT & WIRED]

Spec and demo: issue #4333 (slice 5 is #4442; walkthrough D, design 6). A GM running a scene
answers a rite performed there from the same catalogue the pledge route draws from: the live
route. Migration 0248 is schema only.

**Models**

- `GMPrompt.rite_performance` (FK `WorshipRitePerformance`, SET_NULL): set on a `BEING_ANSWER`
  prompt raised by a rite in a scene (a stewarded close sets `pledge` instead). The prompt is
  scene-bound and addressed to each scene GM who has not muted the Being answers group, never
  the performer's own player. Every GM's copy shares an `event_group`.
- `GMLevelCap.may_adapt_answers` (default False; staff tune it on the level's admin form): a GM
  at the level may edit an answer's main text before sending it live.
- No limit table: a confirmed live prompt is the record of each live answer or miracle.

**Services** (`worship/live_services.py`)

- `route_live_answer(performance, scene)` - called by `PerformWorshipRiteAction` after the rite
  paid, so a prompt never gates the award. A pledge's closing rite goes through
  `ClosePledgeAction` and never calls it. No prompt when the being is at its limit, or has no
  general answer at the roll and no miracle.
- `live_limit_reason(being, sheet)` / `live_answers_this_week` - a being answers a given
  character live at most once per game week, answers and miracles counted together, per being
  and character (confirmed live prompts whose rite was performed this game week).
- `live_panel(prompt, account=)` -> `LivePanel` (types.py): the being's active **general**
  answers (no pledge type; a pledge type's answers belong to its pledge) at or below the rolled
  tier with how often each was sent, the being's active miracles each with its ineligibility
  reason (empty when it may be performed), `may_adapt` for the viewing GM's level and
  `limit_reason`.
- `send_live_answer(prompt, resolver=, answer= | miracle=, text=)` - exactly one choice.
  An answer is delivered by `answer_services.deliver_live_answer` (a vision from the GM
  account; fact clue, follow-up clue and cost exactly as written; never held - a short pool
  refuses the send and the prompt stays open). `text` replaces the answer's main text only
  and only for a level with `may_adapt_answers`; nobody edits clue, cost or follow-up. A
  miracle is checked by `services.miracle_ineligibility` and performed through
  `perform_divine_intervention` (`trigger_event="live_rite"`; its normal miracle narration
  prompt follows). The prompt and every sibling copy are locked first: the first answer
  confirms its prompt and dismisses the others, and the limit is asked under the same lock.
- `dismiss_live_prompt` - dismissing sends nothing (`dismiss_being_answer` routes a prompt
  with a `rite_performance` here); the scene ending closes a still-pending prompt the same way.
  The hourly steward timeout leaves live prompts alone.
- `services.miracle_ineligibility(sheet, miracle, favor=, on_cooldown=, cfg=)` - the check
  extracted from `fire_divine_intervention`: cooldown condition clear, favor at least both the
  config threshold and the miracle's, pool at least the larger of the cost and the config
  minimum. It does not ask the miracle's trigger. `intervention_cooldown_active(character)`.

**Surfaces**

- Scene GM queue: the being answer row reads "<name>'s <rite> to <being> (<tier>)." with Open,
  which expands the answer panel under the row (`LiveAnswerPanel`): answers at or below the
  roll with their use count and onlooker line, an Edit the text control only when `may_adapt`,
  each miracle (greyed with the reason), Send nothing and Send this answer / Perform this
  miracle. `GMPromptSerializer.being_answer_live` marks the row.
- API: `/api/worship/live-answers/` (list, retrieve = the panel) with `answer/` (`{answer} |
  {miracle}`, `text` with an answer) and `dismiss/`; scoped to the requester's own pending
  prompts (staff: any). Both dispatch `gm_being_answer` (`AnswerBeingPromptAction`, which
  branches on `rite_performance`) and `DismissGMPromptAction`.
- Room: the sent answer's `onlooker_line` reaches the room the rite was performed in.
- Telnet: `gm prompts` names the rite; `gm prompt answer <id>` lists the answers (with use
  counts), the miracles (with the reason a greyed one is refused) and whether `text=` editing
  is allowed; `answer=<id> [text=<words>]` or `miracle=<id>` sends; `gm prompt dismiss <id>`
  sends nothing.
- Not wired: a live miracle does not start the divine intervention cooldown (the weekly limit
  already bounds it); the automatic intervention does.

### Miracles & Divine Intervention (#2360)

Gods spend their accumulated `resonance_pool` on miracles — authored effects that
fire automatically when a high-devotion PC is in danger, and faith-colored Audere
Majora crossings.

**Models** (`worship/models.py`)

- `Miracle` — authored catalog entry: `name`, `being` FK (PROTECT),
  `resonance_pool_cost`, `intervention_trigger` (MiracleTrigger: INCAPACITATED,
  NEAR_DEATH), `favor_threshold`, `narrative_text`, `is_active`, `sort_order`.
  Unique per `(being, name)`.
- `MiracleAppliedCondition` / `MiracleDamageProfile` —
  payload child rows inheriting `Abstract*` bases from `magic/models/techniques.py`.
  (The capability-grant sibling was stripped per ADR-0248 — capability-flavored miracle
  effects are authored as applied conditions.) `MiracleAppliedCondition` rows are
  the MVP mechanical effect surface. `MiracleDamageProfile` inherits
  `execute_missing_health_multiplier` from `AbstractDamageProfile` (#2643, see
  `docs/systems/magic.md`'s "The Damage Identity" section) — default 0, no wiring
  change needed here since it rides the shared column.
- `MiraclePerformance` — immutable audit row (miracle, being, target_character,
  scene, resonance_spent, trigger_event, created_at).
- `DivineInterventionConfig` — singleton (pk=1): `favor_threshold` (default 50),
  `cooldown_hours` (default 24), `min_pool_for_intervention` (default 100).
- `MiracleTrigger` (TextChoices in `constants.py`): INCAPACITATED, NEAR_DEATH.

**Services** (`worship/services.py`)

- `spend_worship_pool(being, amount, *, reason)` → bool — the spend counterpart to
  `grant_worship`. Deducts from `resonance_pool` (floor at 0); returns False if
  insufficient. Does NOT create an audit row — the caller creates `MiraclePerformance`.
- `perform_divine_intervention(sheet, being, miracle, *, scene)` → MiraclePerformance —
  the commit seam: spends pool, applies `MiracleAppliedCondition` rows via
  `apply_condition`, creates audit row, broadcasts narrative EMIT.
- `fire_divine_intervention(sheet, *, trigger, trigger_event, scene=None, being=None)`
  (#3779) — the shared check: cooldown, then every `DevotionStanding` at or above the
  config threshold (narrowed to `being` when given), each of its miracles on
  `trigger` whose own threshold and pool cost are met, highest priority first;
  performs it with `trigger_event` on the audit row and applies the cooldown
  condition. Returns the `MiraclePerformance` or None.
- `maybe_fire_divine_intervention(character, payload)` — trigger handler: called by
  the `divine_intervention_on_incapacitated` TriggerDefinition's flow step when
  `CHARACTER_INCAPACITATED` fires; resolves the sheet and scene and calls
  `fire_divine_intervention` on the INCAPACITATED trigger. The NEAR_DEATH trigger is
  the dire-straits prayer's (#3779, `prayer_services.pray`).
- `install_divine_intervention_trigger(sheet, being)` / `remove_divine_intervention_trigger(sheet, being)` —
  installs/removes the `Trigger` row on the character's ObjectDB. Called from
  `bump_devotion` when favor crosses the config threshold. Mirrors Soul Tether's
  trigger installation pattern.

**Trigger lifecycle**: `bump_devotion` calls `install_divine_intervention_trigger`
when `standing.favor >= DivineInterventionConfig.favor_threshold`. The trigger
subscribes to `CHARACTER_INCAPACITATED` (priority 60, above combat escalation's 50).
When the event fires, the flow's `CALL_SERVICE_FUNCTION` step calls
`maybe_fire_divine_intervention`. Per-character cooldown via a timed
`ConditionInstance` ("Divine Intervention Cooldown").

**Seed content** (`worship/factories.py: wire_miracle_content()`): TriggerDefinition +
FlowDefinition, DivineInterventionConfig singleton, "Divine Intervention Cooldown"
ConditionTemplate, example Miracle rows per seeded being. Called from
`seed_worship_content()`.

**Admin**: `MiracleAdmin` (with payload inlines), `MiraclePerformanceAdmin` (read-only
audit), `DivineInterventionConfigAdmin` (singleton).

**API**: `GET /api/worship/miracles/` — staff-facing catalog browser
(`IsAdminUser`). No player-facing API — intervention is automatic.

**GM narration (#4101):** `perform_divine_intervention` calls `_route_miracle` instead of
broadcasting `miracle.narrative_text` directly: `route_narratable_event(NarratableEvent(
kind=GMPromptKind.MIRACLE, scene=..., character_sheet=..., room_text=miracle
.narrative_text))` prompts every opted-in GM present with a `GMPrompt` to narrate
(`GMPromptGroup.MIRACLE`); with no GM opted in, the authored `narrative_text` broadcasts
unprompted exactly as before #4101. Full model/queue reference: `docs/systems/magic.md`'s
"GM Prompt Queue" section and `docs/systems/scenes.md`'s "GM narration of mechanical
events" section.

### Audere Majora Faith Coupling (#2360)

When a faithful character crosses Audere Majora, the ceremony gets faith-specific
vision/manifestation text override + a mechanical bonus. Pool is spent at crossing
time (not offer creation), so a declined offer costs nothing.

**Models** (`magic/audere_majora.py`)

- `AudereMajoraFaithVariant` — per-being ceremony override: `threshold` FK (CASCADE),
  `being` FK → `worship.WorshippedBeing` (PROTECT), `vision_text` (spoiler-private),
  `manifestation_text`, `resonance_pool_cost`, `favor_threshold`, `is_active`.
  Unique per `(threshold, being)`.
- `AudereMajoraFaithVariantAppliedCondition` — the payload child row, applied live at
  crossing. (The capability-grant sibling was stripped per ADR-0248.)
  `AudereMajoraFaithVariantAppliedCondition` rows are the MVP bonus surface.
- `PendingAudereMajoraOffer.faith_variant` — nullable FK (SET_NULL), persisted at
  offer creation when a variant qualifies.

**Services** (`magic/audere_majora.py`)

- `maybe_apply_audere_faith_coupling(sheet, threshold, offer)` → variant | None —
  called from `maybe_create_audere_majora_offer` after offer creation. Checks
  DevotionStanding + pool sufficiency; if a variant qualifies, persists it on the
  offer FK and broadcasts the variant's `manifestation_text` (replacing the generic
  threshold text). Does NOT spend the pool — deferred to crossing time.
- `cross_threshold` extended with `offer=` kwarg: after the existing crossing logic,
  if `offer.faith_variant` is set, applies the variant's `AppliedCondition` rows via
  `apply_condition` and spends the pool via `spend_worship_pool` inside the same
  `transaction.atomic()`. Re-checks pool sufficiency (staleness guard); skips bonus
  but completes the crossing if pool is now insufficient.

**Serializer**: `PendingAudereMajoraOfferSerializer.vision_text` — SerializerMethodField;
returns `faith_variant.vision_text` when set, else `threshold.vision_text`.
`AudereMajoraCrossingResultSerializer` adds `faith_coupling_applied` + `faith_being_name`.

**Skill & seeds** (`seeds/worship_content.py`, cluster `worship`)

- Rites skill (Trait-backed, open to all paths) + the four tradition
  specializations; "Ceremony Rites" CheckType (presence + Rites); Devotion
  `Aspect` with `PathAspect(Path of the Chosen)` + `CheckTypeAspect` weights —
  the Chosen's ceremony edge rides the existing aspect formula, no new
  mechanism. The `secret-investigation` consent category seeds with the
  antagonism tree (`seeds/consent.py`, parented under All Antagonism).

**API**: `/api/worship/beings/` — read-only reference catalog (id, name,
tradition name only; pools/avatars never serialized). Sheet identity section
exposes the **public** worship name only. `/api/worship/prayers/` and
`/api/worship/visions/` (#3779) — a character's prayers and visions: the account that
plays the sheet reads its own, staff read anyone's (filter `character_sheet` /
`recipient`), and staff `POST /api/worship/visions/` sends one (`VisionCreate`). A
vision's `being_name` is null unless `reveal_source` or the reader is staff. Web: the
sheet's Worship card (`frontend/src/worship/`). `/api/worship/rites/` (#3777) — the
rites of active beings (`WorshipRiteSerializer`: name, description, kind name,
tier, check type name, resonance name; filter `being`, `kind__tier`; search
`name`).

## Ceremonies (`world/ceremonies`, #2289)

A ceremony bookends freeform RP: open → offerings/speeches (freeform poses
carry the scene) → finish (or abandon). No Scene/Event required — nullable FKs
to both; normally it runs inside them.

**Models**: `CeremonyType` (data rows: Funeral full handler; Blessing/Sermon
renown-only; Seance the third ghost-window handler, #2393; Wedding marries the
honorees on finish gated on WeddingConsentOffers, with or without a Betrothal,
#2358/#2999/#4232;
Conversion repoints public worship on finish, #2361; Coronation solemnizes an
already-held title, #2358; Rite holds a tier 3 worship rite as a ceremony,
#3777), `Ceremony` (officiant
Persona, TRUE `being` vs `presented_being` — see leak rule, location
RoomProfile, status OPEN/COMPLETED/ABANDONED, one-OPEN-per-location
constraint, quality_level, nullable `title` FK — CORONATION only, nullable
`worship_rite` FK — RITE only, the TRUE being's tier 3 rite),
`CeremonyHonoree`, `CeremonyOffering` (item
snapshot; the item is destroyed; `item_legend_value` snapshots the offered
item's legend at sacrifice time — #2359), `CeremonySpeech`, `CeremonyConfig`
singleton (all magnitudes PLACEHOLDER; `offering_favored_facet_multiplier_percent`,
#3777, scales an offering that carries a facet the TRUE being favors), `SeanceManifestationOffer` (#2393,
consent gate for a Seance honoree's manifestation), `WorshipConversionOffer`
(#2361, consent gate for a PC-officiated Conversion honoree — see below).

**Rites as ceremonies (#3777)**: a RITE ceremony carries exactly one tier 3
`WorshipRite` of the TRUE being (`_validate_rite_for_type`: other types carry none,
a tier 1 or 2 rite is refused as a scene act); at finish the officiant's Rites roll
outcome pays the rite's tier award through `worship.rite_services.apply_rite_award`
(`_pay_rite_award`; skipped when no Rites check type is seeded, so there was no
roll), on top of the ceremony's own honors and `devotion_officiant`. Participants
earn resonance through `DramaticMomentType`/`DramaticMomentTag` as before; the
event's own contest resolution stays out of scope (#3770). Telnet: `ceremony/rite
<rite>[,<honoree>…][=<being>]`; the open action takes `rite_name`.
**Favored offerings (#3777)**: `record_offering` resolves, in one query before any
item is destroyed, which offered items carry an `ItemFacet` matching one of the TRUE
being's `BeingFacet` rows; those are credited at the config multiplier on both the
pool grant and the offerer's devotion bump (the god likes it more, so favor follows).

**Services** (`ceremonies/services.py`): `open_ceremony` (Decision-10
being/presented mapping: default = officiant's public declaration; explicit
override naming their `secret_being` = twisted rite presenting the public
front; any other override = open rite; validates honoree counts/liveness per
type — FUNERAL/SEANCE need every honoree dead, CONVERSION needs exactly one
honoree, the convert), `record_offering` (soft-destroys items via
`destroy_consumed_item_instance` inside `give_up_item`, so the design and any resonance
history outlive the offering, #4461; snapshots `item.legend_value` before destruction
as `CeremonyOffering.item_legend_value` — #2359; pool always to the TRUE
being; devotion follows belief — Decision 11), `record_speech` (Performance/Oratory roll),
`finish_ceremony` (one Rites + tradition-spec quality roll → multiplier;
honoree deeds via the legend engine's `create_solo_deed`; offering legend
total added to honoree prestige base — #2359; officiant lesser
cut; funeral handler calls the `execute_will` **no-op seam** for #1985; WEDDING
handler marries the honorees (`solemnize_wedding` when an active Betrothal stands
between them, else `record_marriage`, #4232); CONVERSION handler calls
`convert_public_worship` per confirmed honoree — see below),
`abandon_ceremony` (awards nothing), `open_funeral_for` (the ghost-container
lookup).

**Public conversion** (#2361, `CeremonyTypeKey.CONVERSION`): two routes reuse
the same generic ceremony action set (Open/Offering/Speech/Finish/Abandon), no
new Action classes for opening/finishing. (a) **PC-officiated**: clergy opens
the rite naming the convert as the sole honoree; `open_ceremony` mints a
`WorshipConversionOffer` (PENDING) since the officiant differs from the
honoree — the convert must accept it (`respond_to_conversion_offer`, the one
new Action: `conversion_offer_respond`) before `finish_ceremony` will convert
them; declining or leaving it unanswered means the rite concludes but honors
nothing for them (no deed, no worship repoint — mirrors a declined Seance
offer). The offer's own delivery surfaces mirror the Seance offer's byte for
byte: REST `/api/ceremonies/conversion-offers/` (`ConversionOfferViewSet`,
list + `accept`/`decline`, accept body takes optional `sincere`), telnet
`conversion` command (`commands/conversion.py`, offers/accept/decline — telnet
accept is always sincere, since there's no syntax slot for the choice there),
and the web `ConversionOfferBanner`/`ConversionOfferDialog`
(`frontend/src/ceremonies/`, mounted in `Layout.tsx` next to
`SeanceOfferBanner`; the dialog's Switch carries the heart-vs-lip-service
choice). (b) **Self-officiated solo** (the temple/no-officiant route): the
convert opens their own rite naming themself as both officiant and honoree —
`open_ceremony` skips the offer entirely (nobody consents to their own
choice); `finish_ceremony`'s optional `sincere` kwarg carries their
heart-vs-lip-service choice directly (defaults True). Both routes converge on
`world.worship.services.convert_public_worship`, called once per confirmed
honoree from `finish_ceremony`'s CONVERSION branch. The minted deed
(`_mint_ceremony_deed`, extended with optional `archetypes`/`scene` kwargs
passed straight through to `create_solo_deed`) carries the existing
"Treacherous Scandal" `PhilosophicalArchetype` (#1464's vocabulary — no new
archetype rows minted) when converting AWAY from an already-declared public
faith, so the ordinary scandal fork (`route_deed_reach`) judges it per
society; a first public declaration (no prior faith to betray) carries no
archetype tag and skips the scandal fork. **No temple/shrine location model
exists in this codebase** (verified by grep — worship has no location
substrate at all), so the solo route is NOT location-gated; it is simply the
self-officiated shape. **No location gate for the temple route** is a known
gap — flag for a future issue if a temple/shrine location primitive is ever
built. `DevotionStanding` rows and the old faith's `Secret` row (if any) are
never touched by a conversion — they stand as history (Decision 3/Ratified
amendment #3 of #2361; the secret-faith retarget/shed services proposed in the
draft spec were explicitly NOT built in this pass — only proven as a no-op).

**Ghost window**: an OPEN funeral honoring a dead character at their location
is the third recognized container in `GhostWindowPrerequisite`
(`actions/prerequisites.py`) alongside the death scene and IC death-day
(ADR-0131; seance #2290 is the remaining hook).

**Twisted-rite leak** (`ceremonies/leak.py`): when the rite secretly serves
the officiant's hidden god, each witness passing the consent gate
(`secret-investigation` category, mirrors `accusation_permitted`) rolls a
hidden Search check; success mints a `Clue` → `CharacterClue` against the
officiant's worship Secret. Failures silent.

**Corpse gear**: `_dead_owner_trusts` in
`flows/service_functions/inventory.py` — a dead owner's items still require
`steal`, unless the dead player's tenure friended the taker (friends-list
trusted handler; direction matters — trust flows from the dead).

**Wedding & Coronation (#2358, #4232).** WEDDING marries the honorees. A
betrothal is optional for everyone (ADR-4232): when an active `Betrothal`
stands between the honorees' nodes the rite lands everything it negotiated
(`world/societies/houses/pact_services.solemnize_wedding`: union, marriage pact,
tier prestige, `wed_at`); otherwise `world.roster.services.kinship.record_marriage`
records the union under the realm's wedlock `UnionKind` and nothing else, so two
commoners, or a noble and a commoner, marry as surely as two houses. An honoree
with no `Kinsperson` node gets one first (`ensure_node_for_sheet`); a pair who
already share an open wedlock union get no second one; a world with no
wedlock-conferring kind refuses the rite ("No law of marriage exists to wed
under.", a `CeremonyError`). Consent is gated at the CEREMONY, not the proposal:
`open_ceremony` mints a `WeddingConsentOffer` per spouse honoree at START (mirrors
`SeanceManifestationOffer`'s shape, shares `SeanceOfferStatus`);
`finish_ceremony`'s WEDDING branch refuses to marry until every offer is
ACCEPTED, and a DECLINE (`respond_to_wedding_consent_offer`, account-scoped)
aborts the whole ceremony via `abandon_ceremony`. CORONATION solemnizes an ALREADY-HELD
`Title` — no title-passing mechanics: `open_ceremony`'s precondition
requires exactly one honoree who holds `title` (or staff/GM fiat — a
non-holder without fiat is the contested-claim case, rejected rather than
auto-resolved), and `finish_ceremony` mints the permanent `Coronation`
record (`honoree_sheet`, `title`, unique together — one-off per title, not
per person: a later coronation for a DIFFERENT title still works). Neither
type adds flat ceremony prestige beyond the shared honoree-renown pass every
ceremony type gets — the event grandeur/prestige-influx pipeline (#2357) is
what drives the real payoff, reading the same ceremony deed this pass
mints. Divorce and the marriage-tier/pact mechanics themselves live in
`docs/systems/houses.md`'s "Org pacts, betrothal & the dossier" section.

**Bounded abandonment**: `ceremonies.auto_abandon` cron
(`game_clock/tasks.py: abandon_stale_ceremonies`, hourly) abandons OPEN
ceremonies whose scene finished, whose event completed/cancelled, or a real
day after opening.

**Actions** (`actions/definitions/ceremonies.py`; registry keys
`ceremony_open` / `ceremony_offering` / `ceremony_speech` / `ceremony_finish` /
`ceremony_abandon` / `seance_offer_respond` / `conversion_offer_respond` /
`wedding_consent_respond`):
anyone may officiate — skill shapes the outcome, not
permission; offering/speech/finish are officiant-only, abandon is
officiant-or-staff. `conversion_offer_respond` (#2361) and
`wedding_consent_respond` (#2358) are account-authorized (mirror
`seance_offer_respond`) — kwargs `offer_id`, `account`, `accept`, plus
`sincere` (bool, conversion-accept only). `ceremony_open` takes `title_name`
for CORONATION (resolved by name; `is_staff_fiat` derives from
`is_staff_observer(actor)`). Telnet: `ceremony` family
(`commands/ceremonies.py`, switch or space subverbs —
`ceremony/wedding <a>,<b>[=<being>]`, `ceremony/coronation <honoree>=<title>`,
`ceremony/conversion <convert>[=<being>]` since #3657 tranche 16);
`wedding` family (`commands/wedding.py`, mirrors `commands/seance.py`'s
`offers`/`accept`/`decline` shape) answers a pending `WeddingConsentOffer`;
`conversion` family (`commands/conversion.py`, same shape) answers a pending
`WorshipConversionOffer`. Web: read API `/api/ceremonies/ceremonies/`
(filter `location__objectdb` for the game-view room card,
`frontend/src/ceremonies/CeremonyRoomCard.tsx`); verbs ride the generic
action dispatch.

**LEAK RULE**: player-facing surfaces (serializers, command output, card)
render `presented_being` ONLY. The true `being` of a twisted rite never
leaves the model layer except via the clue path.

## Manifested by a technique (#4118) [BUILT & WIRED]

A `WorshippedBeing` can be an option on a manifesting technique
(`TechniqueManifestOption.being`, `world.magic`), sized by the option's `tier`. A
character's `CharacterManifestation` for that option holds while
`active_patronage_for(character)` includes the being. `manifest_bound_entity` moves the
being's `avatar_sheet` character into the caster's room and adds it to the encounter as an
ALLY `CombatOpponent`, on a successful, unbounced cast only. It manifests nothing for a
caster with no location, a failed roll, an avatar that is not in the caster's room after
the move, or an avatar still in another running fight. A being with no avatar sheet
manifests nothing (probe `manifest-being-avatars`); a tier with no `OpponentTierTemplate`
makes the cast raise and the whole round roll back (probe `manifest-tier-templates`). This is separate from `WorshippedBeing.ultimate_techniques`
(an ultimate a devotee may be shown at Audere). See `docs/systems/magic.md`'s "Manifesting a
bound entity".

## Deferred (filed)

Coronation type (Wedding **shipped** — #2358/#2999, marries the honorees on
finish; a `Betrothal` adds its `MarriagePact`, #4232), event
grandeur/prestige investment (#2357), item legend value at offerings (#2359,
**shipped** — `ItemInstance.legend_deeds` M2M + `CeremonyOffering.item_legend_value`
+ finish-tally wiring), miracles +
audere coupling (#2360, **shipped**), post-CG public conversion (#2361,
**shipped** — see "Public conversion" above; secret-faith retarget/shed was
explicitly scoped OUT of the #2361 pass, proven a no-op rather than built),
getinline queue (#2356);
wills remain #1985 (the `execute_will` seam).
