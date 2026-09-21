# Relationships App

Ties between characters (#3957, ADR-0308). A tie is **two directed sides**; each side names
the other with **labels** from a staff catalogue, **adds depth** through play, **claims a
tier** with a capstone journal entry and XP, and carries two play-moved gauges. Labels carry
awareness and history, never points. Terms: `AGENT_GLOSSARY.md` next to this file.

## Core Concepts

- **Side** (`CharacterRelationship`) — one character's row toward another sheet (`target`) or
  their own bonded `Companion` (`target_companion`); exactly one is set. Owns that
  character's labels, added depth, claimed tier, gauges and summary.
- **Label** (`RelationshipLabel`) — this side naming one `RelationshipType`, at one awareness,
  with `since`, `replaced`, `ended_at` and an optional `note`. Never deleted; at most one open
  label per type per side.
- **Awareness** — `LabelAwareness` PRIVATE → CLANDESTINE → PUBLIC, forward only. Default
  Private. `KNOWN_AWARENESS` (Clandestine or Public) is what the other side may read and the
  only stages that count toward mutual.
- **Depth** — each side *adds* depth (`scene_depth` from scenes together, `invested_depth`
  from weekly AP); `side.depth` is its own sum, `side.pair_depth()` is both sides'. No decay,
  no weekly cap, no per-label points. Every award has a `RelationshipDepthTransaction`.
- **Tier** — claimed, not reached. One `RelationshipTier` ladder for every tie
  (`depth_threshold`, `combat_bonus`; seeded 25/100/500/2000, PLACEHOLDER names). Each side
  claims its own against the **pair** depth.
- **Affection / Conflict** — two unsigned gauges on the side, moved only by play through
  `move_gauges` (positive adds Affection, negative adds Conflict). Owner-and-staff-only.
- **Mutual** — derived: both sides hold counterpart labels (`RelationshipType.counterpart`,
  null = itself) at Clandestine or Public, under still-open tenures, both sides active.

## Models

Catalogue and tuning (staff-authored / singleton):

- **`RelationshipType`** — the catalogue: `name`, `slug`, `family` (`TypeFamily`), `valence`
  (`TypeValence` WARM / HOSTILE / NEUTRAL), `counterpart` self-FK (null = symmetric),
  `fuels_escalation_spikes`, `display_order`. `CreditedContent` + `NaturalKeyMixin` (content
  repo owns it). Seeded as twenty-three PLACEHOLDER types in five families (Heart 5,
  Company 4, Contest 4, Blood and oath 6, Teaching 4) by
  `world/seeds/relationship_scale.py`; Kin is WARM (found family reads as warm).
- **`RelationshipTier`** — one ladder: `tier_number`, `name`, `depth_threshold`,
  `combat_bonus`. Also the source of the social-difficulty affection bands.
- **`RelationshipGrowthConfig`** (pk=1) — `scene_base_gain`, `depth_per_ap`, `xp_per_tier`,
  `thread_min_tier`. All PLACEHOLDER values.
- **`BondCombatConfig`** (pk=1) — `min_tier`, `soul_tether_multiplier`.
- **`GrievanceOption`** (#1429) — `label`, `conflict_points`.
- **`RelationshipCondition`** (#1696) — gates modifier targets (`gates_modifiers` M2M).

Per-tie rows:

- **`CharacterRelationship`** — the side. `source`, `target` XOR `target_companion`,
  `is_active`, `scene_depth`, `invested_depth`, `tier`, `affection`, `conflict`, `summary`,
  the soul-tether fields (`is_soul_tether`, `soul_tether_role`, `magical_flavor`), the
  `conditions` M2M. Properties: `depth`, `reverse` (the other side's row, always None toward
  a companion — a plain `@property`, deliberately NOT cached: nothing would invalidate a
  per-instance cache on an idmapper-shared model, so it would outlive the identity-map flush
  the depth and gauge writers do on the other side; page reads batch the reverse rows
  themselves in `reads.build_tie_page`), `pair_depth()`, `open_labels()`, `next_tier()`,
  `target_name` (read
  this, never `target.character`, anywhere a row may be about a companion). Constraints: the
  two partial uniques, `relationship_target_xor_companion`, `relationship_source_not_target`.
- **`RelationshipLabel`** — `relationship`, `type`, `awareness`, `declared_by_tenure`,
  `since` / `clandestine_at` / `public_at` / `ended_at`, `replaced` self-FK, `note`.
  `UniqueConstraint(relationship, type)` partial on `ended_at IS NULL`. `is_former` property.
  `declared_by_tenure` is read by **consent only** — a roster successor inherits the label but
  the RIVALS gate needs one declared under a tenure that is still open.
- **`RelationshipAllocation`** — one row per side (`OneToOne`), `ap_amount`, `game_week`.
  Mirrors `TrainingAllocation`.
- **`RelationshipDepthTransaction`** — the audit of one award: `amount`, `source`
  (`DepthSource` ALLOCATION / SCENE), `scene`, `game_week`. The side's columns are the
  running sums (the same trade `CharacterSkillValue` makes against `DevelopmentTransaction`).
- **`RelationshipCapstone`** — the receipt of one advance: `journal_entry` (O2O, PROTECT),
  `tier_claimed`, `xp_spent`, or `is_ritual_capstone` + `ritual` for a soul-tether formation
  (`capstone_has_entry_or_is_ritual` check). `title` reads the entry's title.
- **`RelationshipBump`** (#1699), **`AffectionShift`** (#1697 / #2540),
  **`TemporaryRelationshipCondition`** (#1697) — unchanged in shape; all now write the gauges.

## Lifecycle

**Declare → play and allocate → advance.**

1. **Declare.** `declare_label` names a type on the caller's side, Private unless told
   otherwise; the side row is get-or-created on first touch (`get_or_create_side`), so a first
   declaration creates the tie. Free, and never consent-gated (ADR-0024) — it describes the
   caller's own stance and compels nothing.
2. **Play.** `credit_scene_depth(scene)` runs at scene close (`Scene.finish_scene` in
   `world/scenes/models.py`): for every pair of sheets whose personas both **took part**, each
   side gets `scene_base_gain` once per game week — the read is over every `Interaction` in
   the scene, so a say or a mechanical action counts as surely as a pose does. Gauges move on
   their own through bumps,
   affection shifts, grievances and the NPC mirror.
3. **Allocate.** `set_allocation` sets this week's AP against one side. **Ties and training
   share ONE weekly budget** (`ActionPointConfig.get_weekly_regen()`): the check is this
   amount plus the character's other `RelationshipAllocation` rows plus their standing
   `TrainingAllocation` total, because all of them are paid out of the same
   `ActionPointPool` at the weekly turn, and training runs first
   (`world/game_clock/tasks.py` step 4 skills, step 6 ties) — an unbudgeted tie allocation
   would simply earn nothing, every week, in silence. Over-commitment raises
   `AllocationTooLargeError`, the pool's live balance is checked too, and a skip at the
   weekly turn is logged rather than swallowed. The tie page's `ap_pool` line reports that
   same budget and what is left of it. The weekly rollover calls
   `process_weekly_relationship_allocations()`, which spends the AP and converts it at
   `depth_per_ap`. Idempotent per game week — a side already credited with an ALLOCATION
   transaction for the current week is skipped, so a repeat call never double-spends.
4. **Shift / end / reveal.** `shift_label` ends the old row and creates the new one with
   `replaced` set; `end_label` stamps `ended_at` (the label shows as former and stops counting
   toward mutual); `advance_awareness` moves a label forward only.
5. **Advance.** `advance_tier` checks pair depth against the next rung, validates the capstone
   entry, spends `xp_per_tier × new tier`, writes the receipt and sets `tier`.
6. **Freeze.** `is_active=False` stops new credit and mutuality; the depth already earned
   stays and still counts toward the pair (`build_tie_page` deliberately does not filter the
   reverse side on `is_active`). It also drops the side from the sheet cast — `_build_ties`
   filters `is_active=True` — while the tie API's own `list` has no such filter and still
   returns it.

## Visibility — four audiences, decided server-side

`TieAudience` + `reads.tie_audience(side, viewer_sheet, is_staff)`. Never a client decision,
and never a Python-side filter over a wider payload: what an audience may not see is *absent*
from the read.

| Audience | Labels | Numbers |
|---|---|---|
| OWNER | all, including Private and former | pair depth, both tiers, breakdown, **Affection and Conflict**, `ap_this_week`, `ap_pool` |
| OTHER_SIDE | Clandestine + Public | pair depth, both tiers, breakdown; **no gauges**, **no `ap_pool`** |
| THIRD_PARTY | Public only | **none at all**; a side with no open Public label is absent from lists and **404s** on retrieve (never 403) |
| STAFF | everything | everything **except `ap_pool`** |

**`ap_pool` is the one field staff do not get on a foreign tie.** It rides `is_own_side`,
not `audience`, because it is not tie state at all: it is the owner's own weekly spend
control (their budget and what is left of it), so it is null for everyone but the
character's own player — a staffer reading someone else's tie included.

**The stream is gated on both halves.** `GET {id}/stream/` merges journal entries with the
scenes both sides took part in, and each half goes through its own app's visibility rule:
journals through `visible_entries_q`, scenes through `Scene.objects.viewable_by(account)`
(the scenes app's single source of truth), with the viewer's account threaded in from the
view. A PRIVATE or EPHEMERAL scene therefore reaches only a participant or staff, and each
row reports the scene's own privacy mode rather than a blanket `is_public=True`.

Every **tie API** payload (`TieSerializer`, set in `views._row_to_payload`) also carries
**`is_own_side`**: true when the viewer is looking at their own side. The sheet cast's
`TieCardEntry` has no such field -- every card there is the sheet owner's own side already. `list` passes it
unconditionally (its queryset is a tenure join on `source`), `retrieve` derives it from the
viewer sheet. It is the flag the frontend branches its owner-only doors on, so a client never
has to re-derive ownership from `audience`.

Corollaries in `reads.py`: `_replaced_type_name` only names a replaced type the audience could
have seen; `note` is owner/staff-only; `is_mutual` is computed with `public_only=True` for a
third party so a marker can never expose a Clandestine label; `TieStreamItem.is_capstone` is
unconditional but `capstone_tier` is null for a third party. Companion sides are owner/staff
only everywhere. Soul-tether rows keep their universal-read carve-out (ADR-0117, amended by
ADR-0308).

## Services (`services.py`)

Writes:

- `get_or_create_side(*, source, target=None, target_companion=None)` — exactly one target.
- `declare_label(*, side, type, awareness=PRIVATE, tenure=None)` → `LabelAlreadyDeclaredError`
  on a second open label of the same type.
- `shift_label(*, label, new_type, note="")` — creates the new row **first** so a constraint
  collision leaves no stale idmapper instance behind (ADR-0008 addendum).
- `end_label(*, label)`, `advance_awareness(*, label, to)` (`AwarenessBackwardError`).
- `set_summary(*, side, summary)`, `set_allocation(*, side, ap_amount)`
  (`AllocationTooLargeError`).
- `process_weekly_relationship_allocations() -> int`, `credit_scene_depth(scene) -> int`.
- `advance_tier(*, side, journal_entry) -> RelationshipCapstone` (`TierNotReachedError`,
  `CapstoneEntryInvalidError`).
- `move_gauges(*, side, amount)`, `apply_relationship_bump`, `apply_affection_shift`,
  `mirror_npc_regard_event(event)`, `register_grievance(*, source, target, option=None,
  custom_points=None)`, `add_relationship_condition`, `clear_very_attracted`.

Predicates and reads used by other apps:

- `is_mutual(side, type, *, public_only=False)`, `mutual_hostile(a_sheet, b_sheet)`,
  `mutual_hostile_expression(viewer_sheet_id, other_ref="author_id")` (the annotatable form),
  `known_label_q(source_id, target_ref=None, type_ref=None, *, awareness=KNOWN_AWARENESS)` —
  the one SQL spelling of "a label the other side may see, under a still-open tenure".
- `bond_combat_bonus(sheet, encounter)`, `bond_bonus(actor, protected)`,
  `soul_tether_active(a_sheet, b_sheet)`, `relationship_gated_contributions`,
  `get_growth_config()`, `get_bond_combat_config()`, `companion_target_error`.
- `helpers.get_relationship_tier(character_a, character_b)` — the lower claimed tier of a
  **mutual TEACHING-family** tie, else 0. Training's mentor multiplier (`(tier + 1)`) is its
  only consumer, and the mutual-Teaching narrowing is the point: it rewards a real
  mentorship. Anything wanting plain bond strength reads the side's own `tier` directly
  instead (magic's fury cap does — `world/magic/services/fury.py:_bond_tier`).

Per-audience reads live in `reads.py`, never in `services.py`: `tie_audience`,
`third_party_can_see` / `has_open_public_label`, `visible_labels`, `label_payload`,
`depth_breakdown`, `tie_stream`, `resolve_viewer_sheet`, `entry_id_for`, and
**`build_tie_page(sides, *, viewer_sheet, is_staff, force_audience=None,
include_allocation=True)`** — the batched entry point the tie API and the sheet's Ties cast
share (three extra queries total regardless of page size: reverse sides, open threads, the
tier ladder). Use it for a page; the per-side functions are for single rows.

Exceptions (`exceptions.py`, each with a `user_message` for a safe 400): `TieError` and
`LabelAlreadyDeclaredError`, `LabelEndedError`, `AwarenessBackwardError`,
`SameTypeShiftError`, `TierNotReachedError`, `CapstoneEntryInvalidError`,
`AllocationTooLargeError`, `NotYourTieError`; plus `RelationshipBumpError` /
`AlreadyAcknowledgedError` (#1699).

## Player Surface

Both surfaces converge on `actions/definitions/relationships.py` — `declare_label`,
`shift_label`, `end_label`, `advance_label_awareness`, `set_tie_allocation`,
`advance_relationship_tier`, `set_tie_summary`, `relationship_bump` — through `action.run()`.

- **Web.** `CharacterRelationshipViewSet` under `/api/relationships/relationships/`: `list`
  (the caller's own sides, always the OWNER shape), `retrieve` (any pk, audience computed,
  404 rules above), `GET {id}/stream/` (journal entries either side wrote about the other,
  visibility-filtered row by row, merged with the scenes both took part in that the viewer
  may see — `Scene.objects.viewable_by(account)`, so a PRIVATE or EPHEMERAL scene reaches
  only a participant or staff), and seven POST
  actions — `declare`, `shift`, `end`, `awareness`, `allocation`, `advance`, `summary`.
  `RelationshipTypeViewSet` (`/api/relationships/types/`) is the read-only catalogue for the
  picker; `RelationshipCapstoneViewSet` and `RelationshipConditionViewSet` are unchanged.
  The **sheet payload** carries `ties` (a `TieCardEntry` per visible side, built by
  `_build_ties` in `world/character_sheets/serializers.py`) and `ties_ap_this_week`
  (owner/staff only). The cast is the Ties section; a card opens the tie page at
  `/characters/:id/ties/:tieId`.
- **Telnet.** `CmdRelationship` (`relationship` / `relation` / `rel`), subverbs
  `list | show | plus | neg | declare | shift | end | reveal | ap | advance | summary`. Reads
  (`list`, `show`) are telnet-only; the tie page and its stream are web-only.
- **Admin.** Types (family, valence, counterpart), the tier ladder, both singleton configs,
  grievance options, conditions, `CharacterRelationship` with a `RelationshipLabel` inline,
  and allocations / depth transactions / capstones through `_AuditReadOnlyAdmin`, which
  refuses add, change and delete outright — a hand-written audit row would desync the side's
  running sums, or hand out a tier nobody paid XP for.

## Integration

- **Consent** (`world/consent/services.py`, `actions/player_interface.py`) —
  `ConsentMode.RIVALS` calls `mutual_hostile`; the scene-wide picker sweep intersects the same
  `known_label_q` sets. `scenes.Rivalry`, `RivalryViewSet`, `declare_rival` and `is_rival` are
  gone: the Rival label *is* the declaration. An inherited label opens nothing until the
  successor re-declares (the tenure test).
- **Journals** (`world/journals/services.py`) — `can_retort` calls `mutual_hostile` and
  `annotate_can_retort` uses `mutual_hostile_expression` (ADR-0307, narrowed here). The
  capstone is a `JournalEntry`; the tie page's stream reuses the journals' own visibility
  rule.
- **Combat** — `bond_combat_bonus` reads the side's **claimed tier** against
  `BondCombatConfig.min_tier` and the tier's authored `combat_bonus`, one-sided, doubled by a
  live tether. The surge engine (`world/combat/escalation.py`) reads an open label whose type
  has `fuels_escalation_spikes` (plus `TypeValence.HOSTILE` for the hated-foe leg) and the
  side's added depth against the curve's floor.
- **Magic** — `Thread.target_relationship` anchors a RELATIONSHIP_TRACK thread to the **side
  row**; weaving one requires the weaver's claimed tier to reach
  `RelationshipGrowthConfig.thread_min_tier` (`RelationshipTierTooLow`), and
  `ThreadWeavingUnlock.unlock_type` / the picker's `weavable_relationship_type_ids` gate which
  types may be woven. Soul-tether formation still weaves on a tier-0 tie — a magic-design call
  left as it stands. Pull modulation (`pull_modulation_relationship.py`, ADR-0092/0110) keys
  the base term on `pair_depth()`, fraught on `min(affection, conflict)`, devotion on pooled
  depth past its threshold.
- **Scenes** — `Scene.finish_scene` calls `credit_scene_depth`; `social_difficulty` reads the
  `RelationshipTier` ladder's `depth_threshold` rungs as its affection bands.
- **Training** (`world/skills/services.py`) — the mentor multiplier is
  `get_relationship_tier(character, mentor) + 1` (a mutual Mentor/Student tie).
- **Fury** (`world/magic/services/fury.py`) — `provocation_cap` reads the claimed `tier` on
  the character's OWN side toward the fury anchor (`_bond_tier`), any label and no
  reciprocity: a character can be provoked over someone who never declared anything back.
  Deliberately not `get_relationship_tier`, whose mutual-Teaching narrowing belongs to
  training.
- **Progression** — `RelationshipRequirement` counts the character's own **sides** that hold
  an open label (optionally of one `required_type`) and have claimed `tier >= minimum_tier`,
  against `minimum_count`. It is `.values("relationship_id").distinct()`, so two labels on
  one side count once: the gate is "N ties", never "N labels".
- **NPC regard** (#2039) — `mirror_npc_regard_event(event)` moves the PC's gauges toward the
  NPC. `NPCStanding` remains the separate NPC cousin.
- **Game clock** — the weekly rollover calls `process_weekly_relationship_allocations()`; the
  hourly `relationships.temp_condition_cleanup` task prunes expired temporary conditions.
