# Relationships & Bonds

**Status:** in-progress
**Depends on:** Magic (threads/resonance), Scenes, Progression, Achievements

## Overview
Relationships are the heart of the game. A track-based system lets characters develop feelings across multiple dimensions simultaneously — friendship, romance, rivalry, enmity, family, mentorship, and alliances. The absolute value of a relationship (total intensity regardless of direction) drives mechanical bonuses, meaning a bitter rival and a devoted lover are equally powerful. The system rewards all forms of intense RP while providing safety mechanics so drama stays fun and never feels like obligation.

## Key Design Points
- **Track-based progression:** Characters allocate points across feeling tracks (Friendship, Romance, Enemies, Rivals, Family, Mentor, Allies), each with tiered intensity levels
- **Absolute value = mechanical power:** A character with 500 love and 500 hate has 1000 absolute value — massive bonuses regardless of emotional direction
- **Conflicted feelings are first-class:** Characters can simultaneously love and hate someone. The system supports "enemies to lovers" and "beloved enemy" arcs naturally
- **Mutual consent at every step:** Intense relationship types (Rivals, Romance, Enemies) only activate with both players' agreement. Easy de-escalation at any time
- **Deceit mechanic:** Characters with Deceitful distinctions can display a fake relationship type, with an OOC warning flag so the other player is never truly blindsided
- **Weekly updates with diminishing returns:** Relationship growth is gated by scene-based or private reflection rolls, with decreasing returns per update per week
- **Hybrid types:** Staff-defined combinations (Frenemy, Beloved Enemy, Friends With Benefits) emerge when multiple tracks are active simultaneously
- **OOC safety:** Player-level agree/disagree on designations. Any player can make a relationship inactive at any time
- **Thread integration:** Magic threads amplify and solidify existing relationships, scaling power off the relationship's absolute value
- **Achievement integration:** Relationship milestones fire achievement stats (first relationship, enemies-to-lovers, etc.)

## What Exists
- **Models:** RelationshipTrack, RelationshipTier, HybridRelationshipType + HybridRequirement, CharacterRelationship (with track progress, deceit fields, consent mechanics), RelationshipTrackProgress (capacity + developed_points), RelationshipUpdate (temporary + capacity), RelationshipDevelopment (permanent up to capacity), RelationshipCapstone (permanent + capacity), RelationshipChange, RelationshipCondition (modifier gating), GrievanceOption (#1429)
- **Writeup feedback (#1537):** WriteupKudos (subject's non-revocable commendation; awards kudos to the author via the existing `award_kudos` path; one per account+writeup), WriteupComplaint (bad-faith-RP flag for staff triage; `resolved` bool; no player signal)
- **Services:** create_first_impression (with reciprocal activation), redistribute_points (atomic point movement between tracks), create_development (permanent points up to capacity), create_capstone (permanent + capacity), give_writeup_kudos (#1537), file_writeup_complaint (#1537)
- **Writeup feedback player surface (#1537):** GiveWriteupKudosAction (key `give_writeup_kudos`) + FileWriteupComplaintAction (key `file_writeup_complaint`) wired to both web (`RelationshipUpdateViewSet` POST `kudos`/`complaint`) and telnet (`relationship kudos <ref>` / `relationship complain <ref>=<reason>`). Read serializers expose `kudos_count` + `viewer_has_kudosed`. Admin: WriteupComplaint registered for staff triage.
- **Magnitude scale + ambient bumps (#1699, SHIPPED):** RelationshipBump (permanent ±1
  anchored to an Interaction; unique per relationship+interaction = the whole anti-spam
  cap), the Regard/Friction system tracks (`RelationshipTrack.system_key`), the seeded
  25/100/500/2000 `RelationshipTier` bands (PLACEHOLDER names, `relationship_scale` seed
  cluster), `apply_relationship_bump` + `RelationshipBumpAction` (key `relationship_bump`),
  telnet `relationship plus|neg <name>` (`rel/plus`, `rel/neg`) with backfill anchoring,
  and web valenced `ReactionEmoji` reactions (catalog endpoint `/api/reaction-emoji/`,
  catalog-driven scene footer). Shift sizes for Flirt/Seduce land with #1697.
- **Automatic affection shifts + tier difficulty ladder (#1697, SHIPPED):**
  `AffectionShift` + `apply_affection_shift` + the `SHIFT_AFFECTION` effect (Flirt +5 /
  Seduce +50 PLACEHOLDER, first-per-scene-per-pair dedup — the generic valence-signed
  family future offensive actions reuse with negative amounts); the affection-derived
  social difficulty now reads its bands from the #1699 system-track tiers (one tier per
  band, neutral = Normal); Smitten's teeth (`exploitable_tiers=2` easing checks against
  the bearer, Melee Defense −10 `ConditionCheckModifier`, Force +100%
  `ConditionDamageInteraction` riding #2018 — all PLACEHOLDER); the Attractive
  distinction's allure grant (+2/rank PLACEHOLDER, `social_relationships` seed).
  Surprise-attack semantics deliberately not built (combat design, TehomCD).
- **Magic threads (new Thread model, Spec A):** Single `Thread` table with a discriminator
  and typed FKs per anchor kind. For relationships the two kinds are `RELATIONSHIP_TRACK`
  (anchored to a specific CharacterRelationship + track) and `RELATIONSHIP_CAPSTONE`
  (soul-tether thread; requires `CharacterRelationship.is_soul_tether=True`). Threads are
  persistent currency consumers that players spend Resonance on via pulls, not 0-100 axis
  trackers. Supporting tables: `ThreadPullCost`, `ThreadXPLockedLevel`, `ThreadLevelUnlock`,
  `ThreadPullEffect`, `ThreadWeavingUnlock`, `CharacterThreadWeavingUnlock`. See
  `docs/systems/magic.md` for the full model lineup.
- **Fraught + devotion pull differentials (#2034, ADR-0110, SHIPPED):** the "conflicted
  feelings are first-class" and "beloved enemy"/devoted-lover design points above now have
  a mechanical payoff on `RELATIONSHIP_TRACK` thread pulls, not just the sign-blind base
  bonus — a bond invested heavily in BOTH positive and negative tracks at once earns an
  additive **fraught** bonus (`CharacterRelationship.developed_signed_sums`, keyed on the
  smaller of the two signed sub-sums), and a bond deep enough to clear a threshold past the
  base curve's own half-saturation point earns an additive **devotion** bonus (depth alone,
  no ritual gate). See `world/magic/services/pull_modulation_relationship.py`.
- **APIs:** Full viewsets and serializers for tracks, tiers, hybrids, conditions, and relationships
- **Admin:** Admin classes for all models with inlines
- **Tests:** Model tests, service tests, and view tests

## What's Needed for MVP

### Magic Integration
- **Thread anchor wiring** — The new `Thread` model (Spec A) supports `RELATIONSHIP_TRACK`
  and `RELATIONSHIP_CAPSTONE` anchor kinds. Per-track threads anchor to a specific
  CharacterRelationship + track; soul-tether (capstone) threads require
  `CharacterRelationship.is_soul_tether=True`. Authoring paths, UI for creating/levelling
  these threads, and service wiring for scaling thread power off relationship absolute
  value are still pending.
- **Soul tethers (capstone threads)** — DONE in Spec B (branch `spec-b-soul-tether-design`).
  `CharacterRelationship.is_soul_tether`, `soul_tether_role` (Sinner/Sineater), and the
  `RELATIONSHIP_CAPSTONE` Thread anchor kind all shipped in Spec A. Spec B activated the
  mechanic: formation ritual (`accept_soul_tether`), the Hollow buffer (`Thread.hollow_current`),
  the Sineating loop, the `CORRUPTION_ACCRUING` redirect handler, stage-advance dramatic prompts,
  and the stage-3+ rescue ritual. `RelationshipCapstone.is_ritual_capstone` +
  `RelationshipCapstone.ritual` FK also added for capstone-gated ritual dispatch.
  See `docs/architecture/soul-tether.md`.
- **Pull integration** — Players should be able to spend Resonance on pulls against
  relationship threads during actions where the other party is engaged (§5 of Spec A).
  The underlying pull machinery (`ThreadPullCost`, `ThreadPullEffect`, `CombatPull`)
  exists; the relationship-action surface that consumes it is not yet wired.
- **Aura farming tie-in** — Dramatic relationship moments in scenes should feed into
  resonance/aura (depends on scenes + magic integration)

### Mechanical Bonuses & Formulas
- **Cube root bonus in checks** — `mechanical_bonus` property exists on CharacterRelationship (cube root of developed absolute value) but nothing in the check/attempt pipeline consumes it
- **Track-specific bonus types** — Different tracks should give different bonus types (Romance → protective actions, Rivals → competitive performance, Found Family → resilience). No formulas defined, depends on combat system
- **Teamwork check bonuses** — Bonus when characters act together, scaled by developed absolute value. Not integrated into check resolution
- **Combat coordination bonuses** — Party members with strong relationships get coordination bonuses. Depends on combat system
- **Combo attack gating** — Effectiveness gated by relationship strength + thread resonances. Depends on combat system
- **Minimum-of-both rule** — Each player sets track designations independently; shared mechanical bonuses should use the lower of the two. No service function implements this

### Relationship Advancement Mechanics
- **Relationship tier calculation for training** — Training system mentor bonus uses `(relationship_tier + 1)` as multiplier. Need to define tier breakpoints from affection/impression values and expose via `get_relationship_tier(character_a, character_b)` helper. Currently stubbed at 0. See `docs/plans/2026-03-10-training-system-design.md`
- **Development roll formula** — What stat/skill is used for the social roll in development updates, and how roll result maps to points earned. Currently create_development just takes points directly
- **Tier point thresholds** — DONE for the system tracks (#1699): Regard/Friction seeded at 25/100/500/2000 via the `relationship_scale` cluster (PLACEHOLDER names, magnitudes tunable in data). Authored tracks (Friendship, Romance, …) still need their own tier rows
- **XP reward formula** — How much XP a development update awards. xp_awarded field exists on RelationshipDevelopment but no formula calculates it
- **Temporary point decay cron** — RelationshipUpdate.current_temporary_value() calculates decay on read, but there's no cron job to clean up fully-decayed updates or update cached totals
- **RelationshipUpdate creation service** — No service function for creating relationship updates (only first impressions have a service). Need validation, achievement stat firing, capacity updates

### Consent & Safety
- **Player agreement flow** — OOC prompt when a player picks a designation ("Are you comfortable RPing this?"). No UI or backend for this consent exchange
- **Designation fallback logic** — When consent is denied, positive tracks fall to Acquaintance, negative to Unfriendly Acquaintance. No implementation
- **Deceit skill check** — What check is required for non-distinction characters to maintain a deceptive displayed relationship. No formula or integration with check system
- **Consent withdrawal** — Either player can withdraw consent at any time. No endpoint or UI for this
- **Inactivity/freezing** — Players can make relationships inactive (points freeze, bonuses stop). Frozen model referenced in design but not implemented
- **Roster transition reset** — When a new player takes over a character, both players can mutually agree to reset. No implementation

### Frontend UI
- **Relationship management page — DONE (#2159).** `RelationshipsSection`'s "Ties" subsection
  now renders `RelationshipPanel`, branching on own vs. foreign sheet (own:
  `OwnRelationshipsList`; foreign: `ForeignRelationshipTimeline`) instead of the old
  free-text `string[]` "TBD" stub.
- **First impression / development / capstone / redistribute creation UI — DONE (#2159).**
  One `RelationshipWriteupDialog` covers all four positive write actions (mode is a fixed
  prop per call site), with track picker(s), points, title, writeup, visibility, and
  `coloring` (impression-only). Reachable from `OwnRelationshipsList` action buttons and
  from a card-drawer quick action (impression-vs-development chosen automatically by
  whether a relationship already exists).
- **Relationship timeline view — DONE (#2159).** `GET .../relationship-updates/timeline/`
  merges Update/Development/Capstone history into one type-tagged, `-created_at`-ordered
  feed; consumed by `OwnRelationshipsList`'s per-relationship expandable history and by
  `ForeignRelationshipTimeline` in full.
- **Track progress visualization — partially DONE (#2159).** `OwnRelationshipsList` shows
  points/tiers per track via the relationship detail read (`track_progress`); no dedicated
  capacity vs. developed vs. temporary chart yet.
- **Visibility controls — partially DONE (#2159).** Private/Shared/Gossip/Public is a field
  on `RelationshipWriteupDialog`'s create form and is enforced read-side (privacy-scoped
  timeline/list queries, ADR-0117); a standalone "appropriate filtering" browse UI beyond
  the panel's own scoped queries is not built.
- **Deceit indicator** — Red question mark OOC warning when a character's displayed feelings may differ from real
- **Asymmetric view rendering** — Each player sees their own real designations + the other's displayed designation
- **Consent prompt UI** — OOC agree/disagree modal for track designations
- **Hybrid type display** — Showing when a relationship qualifies as a hybrid type (Frenemy, Beloved Enemy, etc.)

### Achievement Integration
- **Achievement stat hooks** — Only reciprocation fires `relationships.total_established`. Missing stats for:
  - Relationships per track (number of Friends, Rivals, etc.)
  - Highest tier reached per track
  - Track transitions (Enemies → Romance = "enemies to lovers" trigger)
  - Total points in each track type
  - Number of relationship updates written
  - Total absolute value across all relationships
  - Pure positive relationships (no negative tracks)
  - Pure negative relationships (no positive tracks)
  - Time spent in relationship (weeks active)
  - Monogamous relationship milestones
  - Capstone events written
  - Development updates completed
- **Relationship achievement definitions** — Example achievements designed but not created as fixture data: First Impression, Social Butterfly, It's Complicated, Enemies to Lovers, Lone Wolf, Serial Monogamist, Heart of Gold, Enemies With Benefits, Irresistible
- **Hybrid type detection service** — No service function to check if a relationship's active tracks match hybrid type requirements (needed for achievement triggers)

### Content Authoring
- **Family track tier definitions** — Tier names and mechanics TBD
- **Mentor track tier definitions** — Tier names and mechanics TBD
- **Allies track tier definitions** — Tier names and mechanics TBD
- **Hybrid type definitions** — Frenemy, Friends With Benefits, Beloved Enemy designed; need fixture data and potentially more types
- **Relationship condition definitions** — RelationshipCondition model exists with M2M to ModifierTarget, but no service to apply conditions during checks

### Cross-System Integration
- **Progression requirements** — `RelationshipRequirement` (progression app) implemented (#2116):
  counts the character's own `RelationshipTrackProgress` rows at/above an authored
  `minimum_tier`, optionally narrowed to one `required_track_kind`, gated on `minimum_count`.
- **Gossip system** — Gossip-visible updates should be discoverable by other players. No gossip system exists yet
- **Scene linking** — linked_scene FK exists on updates/developments/capstones but no UI to link scenes during creation
- **Adventuring party model** — Group formation, shared legend, coordination bonuses. No models exist
- **NPC reputation model** — Simpler -1000 to 1000 reputation for system NPCs (shopkeepers, faction contacts). No models exist

## Notes

See `docs/plans/2026-03-08-relationships-achievements-design.md` for the full design document.
