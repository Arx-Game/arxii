# Standoffs

The moment before a fight: a party reads a band of creatures for what moves them, presses
them with social approaches, and names terms that settle them without a round of combat.
Source `src/world/standoffs/`; glossary `src/world/standoffs/AGENT_GLOSSARY.md`; decisions
ADR-4145-A (a standoff is round zero of the encounter, derived from OPEN groups) and
ADR-4145-B (one difficulty function for social checks on a character). Issue #4145,
umbrella #4121. Slice 1 shipped; later slices are listed at the end.

## Lifecycle

- A standoff is **derived**: `is_in_standoff(encounter)` (`services/state.py:17`) is true when
  `round_number == 0` and an OPEN `StandoffGroup` exists. There is no `is_standoff` column.
- Opened by a mission ENCOUNTER option with `opens_as_standoff` set
  (`world/missions/services/encounter_option.py:103`), which calls `open_standoff`
  (`state.py:24`): one OPEN group per creature template among the ACTIVE opponents, then
  `evaluate_causes`.
- Group membership and force use ACTIVE opponents only (`active_members`, `state.py:42`). An
  OPEN group with nobody left is SETTLED (`settle_empty_groups`, `state.py:51`).
- Ends three ways. The party fights (`standoff_fight`), a cause fires, or a caller starts
  round one: all go through `end_standoff_into_fight` (`state.py:60`), which locks the
  encounter row, rechecks, sets every OPEN group FIGHTING and calls
  `begin_declaration_phase`; a second simultaneous breaker returns False and writes nothing.
  `begin_round_or_break_standoff` (`state.py:83`) is what cast seeding
  (`combat/cast_seed.py:333`, PC side) and the GM begin-round view and action
  (`combat/views.py:497`, `actions/definitions/gm_combat.py:217`, `initiated_by_pc_side=None`)
  call, so attacking during a standoff starts the fight instead of raising.
- Or every group is SETTLED: `complete_standoff` (`services/routing.py:11`) grades the mission
  on the terms (`complete_standoff_for_option`, `missions/services/encounter_option.py:208`,
  tier = weakest settled outcome) and then completes the encounter as an ordinary VICTORY.

## Models (`world/standoffs/models.py`)

| Model | Purpose |
|---|---|
| `CreatureDrive` (:26) | A property a creature template wants, with `DriveStrength` (1 Minor, 2 Major, 3 Defining). Unique per template and property. |
| `RegardRule` (:60) | How a template regards particular characters: predicate `rule` (the one ratified JSON field, ADR-0007), `deed_archetype` FK, `difficulty_shift_bands`, `drive` + `drive_shift`, `suppresses_cause`, `spark_text`, `revealed_text`. |
| `StandoffApproach` (:133) | A press: `check_type`, `capability` (aims at drives through `Application`), `sway_target` modifier target, `damages_morale`, `archetypes`, `display_order`. |
| `StandoffTerms` (:181) | `effect` (`TermsEffect`: PASS, FLEE, TURN, TOLL), `required_drive`, `difficulty_shift_bands`, `archetypes`, `display_order`. |
| `StandoffConfig` (:222) | Singleton: `read_check_type`, `terms_check_type`, `pass_condition`, `turn_condition`, per-tier force weights, `botch_force_bands`, `band_force_percent`. `load()` returns it. |
| `StandoffGroup` (:296) | One band in one encounter: `creature_template`, `state` (OPEN, SETTLED, FIGHTING), `terms_ease`, `emboldened_bands`, `settled_outcome`. Unique per encounter and template. |
| `StandoffReveal` (:345) | A thing a read uncovered: `kind` (CAUSE, DRIVE, REGARD) plus the drive or rule. Group-wide, shared knowledge. |
| `StandoffSparkShare` (:398) | A character choosing to share a spark for a group. Unique per group, sheet and rule. |

Also added elsewhere: `CreatureTemplate.cause` (`CauseKind`: NONE, PREDATION) and
`cause_margin_percent` (`combat/models.py`, `combat/constants.py`); `CombatEncounter`'s
`initiated_by_pc_side` help text now says a cause stamps False;
`MissionOption.opens_as_standoff` (`missions/models.py:700`, ENCOUNTER options only).
Migration `0199_creaturetemplate_cause_and_more`. Admin: `world/standoffs/admin.py` with
drive and regard-rule inlines on the creature template.

## Services

- **One difficulty function**: `social_target_difficulty` (`world/checks/social_target.py:48`)
  returns `SocialDifficulty`. Combat's `_social_combat_difficulty`
  (`combat/services.py:7873`) and scenes' NPC passive resist
  (`scenes/action_services.py:650`, `_npc_passive_resist_increment`) feed it too. Parley now
  warms its target (`npc_services/social_disposition.py`).
- **Force and cause** (`services/force.py`): `party_force` (:22), `group_force` (:42, level
  times tier weight percent), `effective_party_force` (:50, less emboldening), `cause_fires`
  (:58), `evaluate_causes` (:69). Predation fires when the party does not outweigh the group
  by its margin, unless every active participant matches a suppressing regard rule
  (`regard.py:93`). A party far above the group never triggers it.
- **Regard** (`services/regard.py`): `regard_matches` (:57), `drive_strength_from` (:105,
  clamped 0..3), `band_shift_from` (:111). Deed knowledge counts only the persona the
  character presents (the primary when none), via common-knowledge `LegendEntry` rows, so an
  alt's deeds never leak the link (ADR-0033). Predicate leaves read only the acting
  character's own state, which is why deeds are a typed field and not a leaf.
- **Verbs** (`services/verbs.py`): `standoff_read` (:185), `standoff_press` (:396),
  `standoff_terms` (:466), `standoff_fight` (:514), `standoff_share_spark` (:530). Each locks
  the encounter (and group) row and rechecks state; a verb after the standoff ended or the
  group settled is refused with a message and no roll. `press_difficulty` (:341) and
  `terms_difficulty` (:351) are shared by the roll and the payload so a shown grade matches
  the roll.
- **Read grading**: checks have five tiers (-2 to 2). Failure reveals nothing; a partial
  reveals one hidden thing at random; a success the thing the reader chose (else the first);
  a critical everything. A drive focus with no id reveals the strongest hidden drive.
- **Press**: a success adds its tier to `terms_ease` (once per successful press); a botch
  (-2) emboldens the group by `botch_force_bands`; morale damage when `damages_morale`. The
  eased difficulty is the sum of hit-drive strengths in bands; the sway modifier counts once
  plus once per eased band.
- **Terms**: a partial or better settles the group, stamps `settled_outcome`, applies the
  effect (PASS and TOLL the pass condition, TURN the turn condition, FLEE sets opponents
  FLED). A terms entry with a `required_drive` is refused until that drive is read. TOLL is
  PASS mechanics, authored with a required Greedy-type drive; any payout comes from the mission
  author's reward lines on the routed tier (`MissionOptionRouteReward`), no new reward model.
- **Sparks**: acting on a spark (press or terms by the matched character while that rule
  shifts their grade) auto-records the share.

## Actions, keys and surfaces

- Actions (`actions/definitions/standoff.py`, registered in `actions/registry.py:809`):
  `standoff_read`, `standoff_press`, `standoff_terms`, `standoff_fight`,
  `standoff_share_spark`.
- Telnet: `CmdStandoff` (`commands/standoff.py`, key `standoff`): bare summary, `read`,
  `press`, `terms`, `share`, `fight`. Thin dispatch only.
- Web: `StandoffCard` (`frontend/src/combat/standoff/StandoffCard.tsx`), rendered by
  `CombatTurnPanel` from the encounter detail's `standoff` block
  (`combat/serializers.py:1366`, `build_standoff_view`).
- Mission options gated by a visibility rule show the owner a "because" line
  (`missions/services/resolution.py:293`, built from `matched_leaves` and `describe_leaf`)
  in the BeatCard; `OptionPage` carries the `opens_as_standoff` control. Predicate additions:
  `matched_leaves` (`predicates/predicates.py:104`), leaves `has_species` (by id) and
  `has_upbringing` (by origin template id), `predicates/describe.py`.

## Payload privacy (`services/view.py`, `services/describe.py`)

Everything is built for one viewer; the block is `None` for a non-participant or outside a
standoff.

- Unread cause, drives and rules appear only as `hidden_count`; a hidden drive still shapes
  every grade but is never named.
- A REGARD reveal's text shows to any character the rule matches, or once a `StandoffSparkShare`
  exists for that rule; everyone else sees only that someone's history matters.
- `sparks` hold the viewer's own matched rules; `shared_sparks` hold what others chose to
  share. A shared spark is not a read: levers show regard text only for a rule that was read.
- Approaches and terms are listed only for OPEN groups with active members.
- Approach and terms grades are the viewer's own. Terms with an unread required drive are
  omitted.
- `owner_options` is reserved and always empty. Group mission ballots still show every
  participant's gated option labels to the whole group (the pre-existing shared vote,
  `missions/services/multiplayer.py`); only the "because" reason is owner-only.

## Config and Required content

Staff author in admin: drives, regard rules and cause on creature templates; approaches;
terms; the `StandoffConfig` singleton. The tuning dashboard
(`web/admin/tuning/required_content.py`) carries three REQUIRED entries, `standoff-config`
(all four links set), `standoff-approaches` and `standoff-terms`; without them players can
only fight. Player-facing prose (spark text, names) is authored in admin.

## Deviations and rulings

1. No `is_standoff` column; derived (ADR-4145-A).
2. Drives and cause are read through `CombatOpponent.creature_template`, not stamped on
   opponents. Per-placement overrides are for a later slice.
3. Five-tier checks (no "strong success"); botch is -2 (see Read grading).
4. Predicate leaves read only the actor's own state, so deed knowledge is the typed
   `deed_archetype` on `RegardRule`; `has_species` and `has_upbringing` are leaves.
5. The `StandoffCard` omits the demo's per-group reaction line and level-band caption: no
   data source yet (a level band must be earned by a read, and reaction narration has no
   model).

## Later slices

Plan from #4121:

- **Slice 2, GM-run stories:** a GM rail with a "they attack" confirm, opponent lines on
  beats, per-placement profile edits (the override in deviation 2), and organization and
  society regard rules with inheritance.
- **Slice 3, more causes:** Orders, Hunger, Hatred and Territory, plus a cause re-test when
  a Charmed or Calm hold breaks.
- **Slice 4:** language barriers (a verbal flag on approaches) and persona NPCs as standoff
  targets.
- **Slice 5:** opt-in profiles for player characters.
- **Separately:** resonance from acts via archetype tags. `StandoffApproach.archetypes` and
  `StandoffTerms.archetypes` are stored for it and unread today.
- **Reaction narration** (deviation 5) has no slice yet.
