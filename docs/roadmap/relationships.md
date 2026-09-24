# Relationships & Bonds

**Status:** shipped (#3957, "Ties, redrawn") — extensions tracked below
**Depends on:** Journals (the capstone entry and the tie stream), Scenes, Progression (XP and
AP), Magic (threads/resonance), Consent

## Overview

Relationships are the heart of the game, and a relationship here is a **tie**: two people,
each side naming what the other is to them. A side holds any number of **labels** from a
staff-authored catalogue (Lover, Rival, Kin, Mentor…), each at one of three awareness stages
that only ever move forward — Private, Clandestine, Public — each with a since date and a
memory of what it replaced. Labels are never deleted. Both sides **add depth** by playing
together and by allocating weekly AP, and the tie's depth is the two sides' sum, so investment
by one person deepens the tie for both. Each side **claims its own tier** on one shared ladder
by marking a journal entry about the other as the capstone and spending XP — the moment is
written down, and the choice is the player's. **Affection** and **Conflict** are two unsigned
gauges on each side, moved only by play and never set by a hand on a dial. The sheet shows a
cast: one card per tie, with the other character's face, the labels, the depth, the tier and
the woven thread.

## Key Design Points

- **A tie is two directed sides.** Every piece of state — labels, tier, gauges, summary — is
  per side. Nothing is stored on the pair; mutuality is derived, and the pooled depth is a sum.
- **Labels carry awareness and history, never points.** Change ends one label and starts
  another that remembers it; End leaves a former label on the card. A known thing cannot be
  unsaid, so awareness never moves backward.
- **Depth grows from play.** The first scene in a game week that two characters both take
  part in credits each side (a say or a mechanical action counts, not only a pose); weekly
  AP converts to depth on the rollover. No decay, no weekly cap, one AP number per tie, and
  every award leaves an audit row.
- **A tier is claimed, not reached.** Pair depth opens the rung; a capstone journal entry and
  XP claim it. Bonuses ride the claimed tier.
- **Feeling is a record, not a dial.** Bumps, Flirt/Seduce shifts, boon drains, grievances and
  the NPC mirror move Affection and Conflict; nothing lets a player set them, and only the
  owner (and staff) ever sees them.
- **Conflicted feelings are still first-class.** A tie moved in both directions at once is
  what magic's fraught pull term rewards — love and hate on the same tie, with no netting.
- **Secrecy is playable.** A Clandestine label is visible to the other side and nobody else; a
  tie with no Public label does not exist for a stranger, and its page 404s rather than 403s,
  so absence and refusal are indistinguishable.
- **The declaration is the consent.** Mutual hostile labels open antagonism (consent's RIVALS
  mode) and the journals' Retort and Condemn — one predicate, `mutual_hostile`, read by both.
  A roster successor inherits the label and the history, but not the open antagonism.
- **Counterparts make paired roles mean the right thing.** Mentor pairs with Student, Ward
  with Guardian, Liege with Vassal; symmetric types pair with themselves.
- **Interface copy is bare** (Dan, 2026-09-21): a Public label carries no marker, no help text
  sits beside a control, numbers are bare, and nothing on a screen explains itself.
- **The game never writes prose for players.** The summary is the player's own paragraph, and
  the prose about a tie is journal entries about the other character — one prose channel.

## What Exists

- **Models** (`src/world/relationships/models.py`): `RelationshipType` (family, valence,
  counterpart, `fuels_escalation_spikes`; credited content), `RelationshipTier` (one ladder:
  `depth_threshold`, `combat_bonus`), `CharacterRelationship` (the side: `scene_depth`,
  `invested_depth`, `tier`, `affection`, `conflict`, `summary`, `is_active`, the soul-tether
  fields, `target` XOR `target_companion`), `RelationshipLabel` (awareness, the three
  timestamps, `replaced`, `declared_by_tenure`, `note`), `RelationshipAllocation`,
  `RelationshipDepthTransaction`, `RelationshipGrowthConfig`, `RelationshipCapstone` (the
  advance receipt, or a ritual capstone), `BondCombatConfig`, `GrievanceOption`,
  `RelationshipCondition` / `TemporaryRelationshipCondition`, `RelationshipBump`,
  `AffectionShift`.
- **Services** (`services.py`): `get_or_create_side`, `declare_label`, `shift_label`,
  `end_label`, `advance_awareness`, `set_summary`, `set_allocation`,
  `process_weekly_relationship_allocations` (idempotent per game week),
  `credit_scene_depth(scene)` (called from `Scene.finish_scene`), `advance_tier`,
  `move_gauges`, `register_grievance`, `apply_relationship_bump`, `apply_affection_shift`,
  `mirror_npc_regard_event`, `is_mutual`, `mutual_hostile` (+ the annotatable expression),
  `known_label_q`, `bond_combat_bonus` / `bond_bonus`, `get_relationship_tier`.
- **Per-audience reads** (`reads.py`): `build_tie_page` (the batched page read the API and the
  sheet cast share), `tie_audience`, `third_party_can_see`, `visible_labels`,
  `depth_breakdown`, `tie_stream`.
- **Actions** (`src/actions/definitions/relationships.py`): `declare_label`, `shift_label`,
  `end_label`, `advance_label_awareness`, `set_tie_allocation`, `advance_relationship_tier`,
  `set_tie_summary`, `relationship_bump`.
- **API:** `/api/relationships/relationships/` (list, retrieve, `{id}/stream/`, and POST
  declare / shift / end / awareness / allocation / advance / summary) and
  `/api/relationships/types/`; the sheet payload carries `ties` and `ties_ap_this_week`.
- **Telnet:** `relationship list | show | plus | neg | declare | shift | end | reveal | ap |
  advance | summary`.
- **Frontend:** the Ties section is the cast of cards; a card opens the tie page
  (`/characters/:id/ties/:tieId`) with the depth button and breakdown panel, labels, the
  summary, the thread line, the Labels-and-AP and Advance-Tier doors, and the merged stream.
- **Seeds:** twenty-three PLACEHOLDER types in five families (Heart 5, Company 4, Contest 4,
  Blood and oath 6, Teaching 4; Kin warm), the five asymmetric
  counterpart pairs, the four tier rungs at 25/100/500/2000, the growth config and the
  starter reaction emoji (`world/seeds/relationship_scale.py`).
- **Consumers wired:** consent's RIVALS mode and the scene picker sweep, journals'
  `can_retort` / `annotate_can_retort`, the combat bond bonus and the surge engine's
  grief/peril/hated-foe legs, magic thread anchors (`Thread.target_relationship`) with the
  tier-gated weave and the depth/gauge-keyed pull terms, social difficulty's affection bands,
  training's mentor multiplier (a mutual Mentor/Student tie, via `get_relationship_tier`),
  magic's fury provocation cap (the character's own side's claimed tier, any label),
  `RelationshipRequirement`, and the NPC regard mirror.
- **Harness:** `frontend/e2e/ties.spec.ts` mounts the real sheet and tie page against
  fixtures for the three audiences (the #3898 evidence lesson).
- **Decision record:** ADR-0308 (this shape and its rejected alternatives); ADR-0117 amended
  for the two-party read; ADR-0024 still governs "a declaration is not consent-gated".

## What's Needed

- **Relationship Prestige** — a share of the partner's renown added to yours by tier, and
  ranking boards for the most renowned marriages, rivalries, friendships and enemies. Its own
  feature and its own issue, filed after this merges (Decision 17). What this pass leaves it:
  a tier per side, mutual labels, and #761's ranking boards.
- **Companions in combat** — a companion tie earns **invested depth only** today (no scene
  credit, since `credit_scene_depth` pairs character sheets), has no reverse side, claims no
  tier (a capstone is a journal entry about the other party, so `advance_tier` refuses a
  companion target) and grants no combat bond. Companions fighting beside their owner is a
  later expansion, not a deferral of this spec (Decision 14).

Everything the previous roadmap listed as needed is superseded, not outstanding: consent
prompts and designation fallback (the label IS the declaration, and mutual labels are the
consent), the deceit check (Private labels replace the deceit display), inactivity freeze and
roster reset (`is_active` freezes a side; a successor inherits the history and re-declares
what they mean to keep open), the development roll and XP formula (depth comes from scenes and
AP; XP is spent, not awarded), the decay cron (no temporary points exist), hybrid-type
detection (several labels on one side carry the fact), and the achievement hooks that named
tracks (they would need rewriting against labels and tiers before they mean anything).
