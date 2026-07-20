# Relationships App

Track-based character relationship system with temporary/permanent point progression,
mutual consent, deceit mechanics, and achievement integration.

## Core Concepts

- **Absolute Value**: Total magnitude of all track points (developed + temporary). Always positive.
- **Developed Absolute Value**: Sum of permanent points only. Drives mechanical bonuses (cube root).
- **Capacity**: Maximum developed points allowed per track. Increased by updates and capstones.
- **Affection**: Signed sum — positive tracks add, negative tracks subtract.
- **Developed Signed Sums** (`developed_signed_sums`, #2034): `(positive_sum, negative_sum)` —
  Developed Absolute Value split by track sign instead of netted; `pos + neg ==
  developed_absolute_value`. Consumed by `world.magic`'s fraught/devotion pull terms
  (ADR-0110) — a mixed-valence bond (invested in both signs at once) and an
  overwhelmingly deep bond (past a threshold) each earn an extra thread-pull bonus.
  This app has no concept of "fraughtness" or "devotion" itself — it just exposes the
  split; the math lives in `world/magic/services/pull_modulation_relationship.py`.
- **Tracks**: Categories of feeling (Friendship, Romance, Enemies, etc.) with positive or negative sign.
- **Tiers**: Intensity levels within tracks, unlocked by developed point thresholds.
- **Hybrid Types**: Staff-defined combinations (Frenemy = Friendship + Enemies).

## Progression System

Four ways to add points:

1. **Relationship Updates** (unlimited) — Add temporary points + capacity to a track.
   Temporary points decay linearly: 10% of original per day, zero after 10 days.
   Capacity increase is permanent.

2. **Development Updates** (7/week) — Add permanent (developed) points up to capacity.
   Social roll determines points. Awards XP.

3. **Capstone Events** (unlimited) — Add both permanent points AND capacity.
   Represent monumental moments. Never gated. Real mechanical power comes from
   magical tethers (future PR) built around capstones.

4. **Ambient Bumps** (#1699) — Permanent ±`BUMP_POINTS` (1) onto the generic
   Regard/Friction **system tracks** (`RelationshipTrack.system_key`), using the
   capstone write-shape (capacity + developed together). Anchored to the specific
   Interaction that prompted them; `UniqueConstraint(relationship, interaction)` on
   `RelationshipBump` is the entire anti-spam cap (the per-scene budget — no more
   bumps than the target posed — emerges from it). Doors: telnet
   `relationship plus|neg <name>` (`rel/plus`/`rel/neg`; backfill-anchors to the
   target's newest unacknowledged visible pose) and valenced `ReactionEmoji` web
   reactions at the pose's author. All via `RelationshipBumpAction`
   (key `relationship_bump`). Not consent-gated (ADR-0024); the target is never
   notified. Seeds: `relationship_scale` cluster (tracks + 25/100/500/2000 tier
   bands + starter emoji catalog, PLACEHOLDER names).

5. **Automatic Affection Shifts** (#1697, boon mode #2540) — A social action's
   success moves its TARGET's regard toward the actor: `apply_affection_shift`
   writes the signed amount onto the system tracks (capstone write-shape),
   recorded as an `AffectionShift` row. Two provenance modes, exactly one per row
   (`affection_shift_has_provenance` CheckConstraint): **effect-keyed** rows keep
   the `UniqueConstraint(relationship, scene, effect)` diminishing-returns rule
   (first success per scene per pair shifts; repeats no-op while conditions still
   refresh) — driven by the `SHIFT_AFFECTION` `ConsequenceEffect`
   (`affection_amount`, handler in `world/mechanics/effect_handlers.py`); Flirt +5
   / Seduce +50 (PLACEHOLDER, seeded in `world/seeds/social_actions.py`).
   **Boon-keyed** rows (#2540 — a granted Boon's negative drain, charged by the
   `boon` resolver in `world/scenes/boon_services.py`) dedup on the Boon OneToOne
   itself, so serial granted boons stack even within one scene. Shifted points
   never decay; a drain persists until rebuilt through play. The generic
   valence-signed family: consent-gated offensive actions reuse it with negative
   amounts — affection falls while absolute value grows.

## Models

### Lookup Tables (SharedMemoryModel)
- **RelationshipCondition** — Gates modifier application (Attracted To, Fears, Trusts)
- **RelationshipTrack** — Feeling categories with sign (positive/negative)
- **RelationshipTier** — Intensity levels per track with point thresholds
- **HybridRelationshipType** — Combination types with HybridRequirement entries
- **GrievanceOption** (#1429) — Staff-authored preset swings a wronged character may register
  against whoever harmed them (label + negative `track` + `points`). Used by the secret-victim
  flow: the victim picks one (or a custom value) and `register_grievance` applies it. `clean`
  enforces a NEGATIVE-sign track.

### Character Data
- **CharacterRelationship** — Core relationship between two CharacterSheets. Tracks
  active/pending status, deceit state, weekly development/change counters.
- **RelationshipTrackProgress** — Capacity and developed_points per track per relationship.
  Temporary points derived from active updates. current_tier uses developed_points.
- **RelationshipUpdate** — Adds temporary points + capacity. Has title, writeup, track,
  points, visibility, optional scene link. `current_temporary_value()` computes decay.
- **RelationshipDevelopment** — Adds permanent points up to capacity. Has xp_awarded.
- **RelationshipCapstone** — Adds both permanent points and capacity. Monumental moments.
- **RelationshipChange** — Redistributes existing developed points between tracks.

### Writeup Feedback (#1537)
Abstract base and two concrete models; FK direction follows ADR-0010 (specific→general) and
ADR-0015 (no polymorphism).

- **WriteupFeedbackBase** (abstract) — Links feedback to exactly one of
  `RelationshipUpdate` / `RelationshipDevelopment` / `RelationshipCapstone` via nullable FKs
  with a DB `CheckConstraint` ensuring exactly one is set. Derived props `writeup`,
  `author_sheet`, `subject_sheet`.
- **WriteupKudos** [BUILT & WIRED] — The subject's one-way, non-revocable commendation of a
  writeup about them. `account` FK (the commender). Awards `WRITEUP_KUDOS_AMOUNT` kudos to
  the *author* via the existing `award_kudos` path. One commendation per (account, writeup),
  enforced by conditional `UniqueConstraint`s. Awards only fire when the
  `KudosSourceCategory(name="relationship_writeup")` row exists — seeded by
  `world.progression.seeds.seed_relationship_writeup_kudos_category`, part of the
  "kudos" seed cluster (#2026).
- **WriteupComplaint** [BUILT & WIRED] — A bad-faith-RP flag filed by any viewer who can see
  a SHARED/PUBLIC writeup. `complainant` FK + `reason` TextField + `resolved` bool. Staff-triage
  only; zero player-facing signal.

## Lifecycle
1. **First Impression** — Unilateral, creates pending relationship with update + capacity
2. **Reciprocation** — Other player's first impression activates both sides
3. **Updates** — Unlimited, adds temporary + capacity (emotional spikes)
4. **Development** — 7/week, solidifies temporary into permanent (up to capacity)
5. **Capstones** — Unlimited, monumental moments add permanent + capacity
6. **Changes** — Redistribute developed points between tracks
7. **Inactivity** — Freeze relationship, reactivate later

## Safety
- Minimum-of-both rule for displayed relationship tier
- Player agree/disagree on designations (OOC consent layer)
- Deceit mechanic: displayed vs real designation with OOC warning flag
- Easy de-escalation to inactive at any time

## Services
- **`register_grievance(*, source, target, option=None, custom_points=None, custom_track=None, …)`**
  (#1429) — a wronged character's **one-sided** grievance: resolves a `GrievanceOption` (or a
  custom points+track) and applies it as a `create_capstone` on the (source→target) relationship.
  Unilateral — never needs the target's consent; the relationship stays `is_pending` until/unless
  reciprocated. Track must be NEGATIVE-sign. The secret-victim prompt is the caller (web slice).
- **`create_first_impression` / `create_development` / `create_capstone` / `redistribute_points`**
  (`services.py`) — the four positive relationship-building verbs. Each is wrapped by a
  corresponding Action in `actions/definitions/relationships.py` and reachable from both surfaces
  below.
- **`give_writeup_kudos(*, giver_account, writeup) -> WriteupKudos`** (#1537) — the subject
  commends a writeup about them; raises `WriteupFeedbackError` subclasses (`WriteupNotSharedError`,
  `NotWriteupSubjectError`, `CannotCommendOwnWriteupError`, `AlreadyCommendedError`) each with a
  `user_message`. Awards `WRITEUP_KUDOS_AMOUNT` kudos to the author when the
  `"relationship_writeup"` `KudosSourceCategory` exists (seeded by the "kudos" cluster,
  #2026); logs a warning and still records the row when it is absent.
- **`file_writeup_complaint(*, complainant_account, writeup, reason) -> WriteupComplaint`**
  (#1537) — any viewer of a SHARED/PUBLIC writeup files a bad-faith-RP complaint for staff
  triage. Raises `WriteupNotVisibleError` when the complainant cannot see the writeup.

## Player Surface (#1485, #1537)

The positive relationship-building loop is reachable from both web and telnet:

- **Web** — `RelationshipUpdateViewSet` exposes four POST endpoints (`first_impression` /
  `develop` / `capstone` / `redistribute`) that dispatch the Actions via `action.run()`.
  Relationship state list/detail reads live on `CharacterRelationshipViewSet` (read-only),
  **privacy-scoped** (#2159, ADR-0117): numeric state is author-private, so `get_queryset`
  filters to rows whose `source` is one of the caller's own tenure-owned characters (same
  tenure join as `RelationshipUpdateViewSet`, never Evennia's live-puppet `db_account`), OR
  `is_soul_tether=True` (a ratified carve-out — the tether panel on a foreign character's
  sheet depends on reading that row).
  The same `RelationshipUpdateViewSet` also mixes in `ListModelMixin` for a narrow `GET`
  list route (#2031) — **not** a general writeup browser: scoped to `RelationshipUpdate`
  rows where the requesting user's account has a **current RosterTenure** (mirroring
  `world.roster.selectors.get_account_for_character`) over the parent relationship's
  `target` (the writeup's commendable subject, matching `give_writeup_kudos`'s subject
  rule) and visibility is SHARED or PUBLIC (PRIVATE/GOSSIP never appear here regardless
  of subject). Deliberately tenure-based rather than Evennia's live-puppet `db_account`
  field — a subject browsing while not currently puppeting the character must still see
  writeups they can legally commend. Supports `?relationship=`/`?track=` filters, plus
  `?subject_character=<CharacterSheet pk>` (#2031 fix wave) to narrow the (possibly
  multi-character) tenure-scoped set down to one owned sheet — it can only narrow, never
  widen, past the requester's own tenure-owned characters. Feeds the commend button on
  the frontend's own-sheet Relationships tab, which passes the viewed character's pk as
  `subject_character` so a multi-character account's Writeups subsection never mislabels
  a sibling character's writeups as the viewed character's. Read serializers expose
  `kudos_count` and `viewer_has_kudosed` on every writeup row (annotated via
  `Count`/`Exists` to avoid N+1). Complaints never appear in any player-facing serializer.
  The same viewset also exposes a `GET timeline` action (#2159) — a merged, type-tagged
  (`kind`: update/development/capstone) feed across all three writeup models, ordered
  `-created_at`. Two mutually exclusive query modes (both or neither → 400):
  `?about_character=<CharacterSheet pk>` returns every non-PRIVATE writeup about that
  character from any author, plus PRIVATE writeups where the caller's account is the
  author's or the subject's — the queryset-level generalization of
  `services._can_view_writeup` (all scoping happens in the DB query, never Python-side
  row filtering); `?relationship=<CharacterRelationship pk>` returns one relationship's
  full history including PRIVATE, restricted to callers who are its tenure-owned source
  (404 if the relationship doesn't exist, 403 if the caller isn't its source). The three
  per-model querysets are projected to a shared column shape and combined with
  `.union()` (each branch's default `Meta.ordering` cleared via a bare `.order_by()` —
  SQLite rejects `ORDER BY` inside a union branch), then paginated via the viewset's own
  `pagination_class`. Both timeline arms are consumed by `RelationshipPanel` (#2159,
  `frontend/src/relationships/components/`) — the `?relationship=` arm backs each row's
  expandable history on the caller's own-sheet `OwnRelationshipsList` (alongside a detail
  fetch for `track_progress`, since the list serializer omits it); the `?about_character=`
  arm is the entirety of `ForeignRelationshipTimeline` on a foreign sheet — deliberately no
  numeric relationship state there, matching the author-private scoping below.
- **Telnet** — `CmdRelationship` (`relationship <subverb>`) runs the same Actions; it adds
  telnet-only `relationship list` and `relationship show <name|#>` read surfaces (the web provides
  these implicitly).

`linked_scene` defaults to the caller's active scene in the current room when the target is
co-located. **No consent gate** — these describe the caller's regard for another character; they do
not compel or provoke the target's behavior (ADR-0024).

### Writeup feedback (#1537) [BUILT & WIRED]
- **Web** — `RelationshipUpdateViewSet` POST `kudos` endpoint dispatches
  `GiveWriteupKudosAction`; POST `complaint` endpoint dispatches `FileWriteupComplaintAction`.
  Both run through `action.run()` (ADR-0001). A "Report" button beside Commend on the
  Writeups subsection (#2159, `WriteupComplaintDialog`) POSTs `{writeup_type, writeup_id,
  reason}` to `.../complaint/` — the filing surface, not a resolution one: the complainant
  gets a toast confirming it was filed and nothing else (`WriteupComplaint` still never
  appears in any player-facing serializer, so there's no outcome to show).
- **Telnet** — `CmdRelationship` adds `relationship kudos <ref>` and
  `relationship complain <ref>=<reason>`, where `<ref>` is `u<pk>` / `d<pk>` / `c<pk>` as shown
  by `relationship show`.
- **Admin** — `WriteupComplaint` is registered in Django admin (django-unfold style) for staff
  triage.
- **FK direction** — feedback models live in `relationships`; the kudos primitive (`KudosPointsData`
  etc.) is not polluted with FK back-pointers (ADR-0010). No denormalized kudos count column —
  derived at read time (ADR-0014).

## Integration
- Achievement stats fired via `world.achievements.services.increment_stat()`
- **Mechanical bonus (WIRED #2021):** cube root of developed absolute value — now
  consumed by `bond_combat_bonus(sheet, encounter)` as the co-combat passive
  magnitude. Returns `ModifierContribution(RELATIONSHIP)` entries (one per
  qualifying bonded ACTIVE co-combatant). Config: `BondCombatConfig` singleton
  (`min_developed_absolute_value`, `soul_tether_multiplier`). Directed (one-sided):
  only the character who invested gets the bonus. ADR-0109.
- Magical tethers (future PR): XP-gated power built around capstones
- **Conditions gate modifier application in checks** — `relationship_gated_contributions(*,
  perceiver, perceived)` (#1696) reads the directed `CharacterRelationship(source=perceiver,
  target=perceived)` and, for each active `RelationshipCondition.gates_modifiers` target, folds the
  **perceived's** `get_modifier_total` of that target in as a `RELATIONSHIP` `ModifierContribution`
  — **once per gating condition**, so two allure-gating conditions ("Attracted To" + "Very
  Attracted") count allure twice (the directed "double"). Consumed at social resolution via
  `world.scenes.action_services._resolve_action_against_persona`'s `extra_contributions` seam.
  **Permanent** conditions ("Attracted To") live on the `conditions` M2M; **temporary** ones ("Very
  Attracted") live on `TemporaryRelationshipCondition` (relationship + condition + `expires_at`) and
  the reader unions only the unexpired ones — a live Very Attracted is the second, self-lapsing
  allure application (#1697). Expired rows are pruned hourly by the
  `relationships.temp_condition_cleanup` game_clock task.
- **Setting attraction (#1697)** — `add_relationship_condition(*, source, target, condition,
  duration=None)` get-or-creates the directed relationship and adds the condition (null duration =
  permanent M2M; a `timedelta` = an expiring `TemporaryRelationshipCondition`, refreshed in place on
  re-up). Driven structurally by the `SET_RELATIONSHIP_CONDITION` `ConsequenceEffect` (a
  `world.checks.EffectType`; handler in `world.mechanics.effect_handlers`): on a successful social
  action the effect's TARGET becomes attracted to the actor (`source=target, target=actor`). The
  allure target + Attracted To / Very Attracted rows are seeded by the `social_relationships` cluster
  (`world/seeds/social_relationships.py`). Flirt/Seduce success-effect content wiring is a follow-up.
- **Secret reputation consequences (#1429):** a secret's persona-victim, on learning who wronged
  them, registers a grievance via `register_grievance` (the relationship effect they *decide*).
- **NpcRegard mirror-bridge (#2039):** `mirror_npc_regard_event_to_track(event)` reuses
  `apply_affection_shift`'s track-selection (`TrackSystemKey.REGARD`/`FRICTION` by sign) and
  capstone write-shape, but dedups on the `NpcRegardEvent` row itself rather than a
  `Scene`+`ConsequenceEffect` — called automatically by `world.npc_services.regard
  .record_npc_regard_event` for every nemesis/toxic-bond buildup event. Always writes
  `source=<PC's own CharacterSheet>, target=<NPC's CharacterSheet>` regardless of which side
  of the underlying `NpcRegardEvent` caused it, matching #2013's hated-foe surge read direction
  (`world.combat.escalation`) — lets that already-shipped surge pick up nemesis buildup with
  zero changes to its own code.
