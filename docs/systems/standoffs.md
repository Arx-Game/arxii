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
| `StandoffTerms` (:181) | `effect` (`TermsEffect`: PASS, FLEE, TURN, TOLL), `critical_effect` (applied instead on a critical), `required_drive`, `difficulty_shift_bands`, `archetypes`, `display_order`. |
| `StandoffConfig` (:222) | Singleton: `read_check_type`, `terms_check_type`, `pass_condition`, `turn_condition`, `botch_force_bands`, `band_force_percent`, `over_level_percent_per_tier`, `falter_force_percent`, `break_force_percent`. `load()` returns it. |
| `StandoffApproach.casts_technique` / `StandoffConfig.terms_ease_faltering`, `terms_ease_broken` | #4147: a casting approach (the display of power) and the bands terms ease by morale (see "Display of power and morale"). |
| `StandoffGroup` (:296) | One band in one encounter: `creature_template`, `state` (OPEN, SETTLED, FIGHTING), `terms_ease`, `emboldened_bands`, `settled_outcome`. Unique per encounter and template. Deleting its `creature_template` deletes the group (CASCADE). |
| `StandoffReveal` (:345) | A thing a read uncovered: `kind` (CAUSE, DRIVE, REGARD) plus the drive or rule. Group-wide, shared knowledge. |
| `StandoffSparkShare` (:398) | A character choosing to share a spark for a group. Unique per group, sheet and rule. |

Also added elsewhere: `CreatureTemplate.cause` (`CauseKind`: NONE, PREDATION) and
`cause_margin_percent` (must stay above -100) (`combat/models.py`, `combat/constants.py`); `OpponentTierTemplate.force_weight_percent` (how much one opponent of a tier counts in group force; default 100 for every tier, staff tune it per tier in admin); `CombatEncounter`'s
`initiated_by_pc_side` help text now says a cause stamps False;
`MissionOption.opens_as_standoff` (`missions/models.py:700`, ENCOUNTER options only).
Migration `0199_creaturetemplate_cause_and_more`. Admin: `world/standoffs/admin.py` with
drive and regard-rule inlines on the creature template.

## Services

- **One difficulty function**: `social_target_difficulty` (`world/checks/social_target.py:48`)
  returns `SocialDifficulty`. Four paths call it: the standoff verbs, combat's
  `_social_combat_difficulty` (`combat/services.py`), and both scene overrides
  (`_compute_difficulty_override_for_primary` / `_compute_target_difficulty_override` in
  `scenes/action_services.py`, through `_graded_scene_difficulty`). Scenes pass the
  defender's already-computed increment (a PC's declared effort, with its development award
  and fatigue, or an NPC's passive medium effort via `_npc_passive_resist_increment`).
  Relationship-gated Allure (`perceiver_sheet`) is applied by scenes at check-modifier time
  and is not yet applied in combat or standoffs (a later slice). Parley now warms its
  target (`npc_services/social_disposition.py`).
- **Force and cause** (`services/force.py`): force is relative to the content and reflects live
  state. `party_force` is the sum over ACTIVE participants of effective combat level times the
  character's current health fraction (`CharacterVitals`; no vitals row counts as whole),
  scaled by `over_level_factor`: for a mission standoff (`encounter.scenario_deed.instance.
  template`), each `LEVELS_PER_TIER` (`stories/services/stakes.py`) levels the party AVERAGE
  stands above `level_band_max` adds `StandoffConfig.over_level_percent_per_tier` percent, and
  each tier below `level_band_min` takes it off (never under 25% of base); no mission means no
  band and a factor of 1.0. `group_force` is the sum over ACTIVE members of level times the
  tier template's `force_weight_percent` times health fraction times a morale factor
  (`morale_state_for`: steady 100, falter `falter_force_percent`, break `break_force_percent`;
  a no-morale tier counts as steady). `effective_party_force` takes off `band_force_percent`
  per `emboldened_bands`. Predation (`cause_fires`) fires when the party does not outweigh the
  group by its margin, unless every active participant matches a suppressing regard rule
  (`regard.py`). Opponent level is the party average at spawn (scaling), so headcount and the
  mission band are what move the comparison; whittling, wounding or breaking the group stops
  it firing, wounded party members make it likelier.
- **NPC-initiated fight is delivered live**: `end_standoff_into_fight(initiated_by_pc_side=
  False)` sends, after commit, a Narrator OUTCOME "The <group> attack!" through
  `broadcast_action_outcome(deliver_telnet=True)`, and the actor's result message ends "They
  attack!". Terms-wheel theater is emitted after commit too. A press with `damages_morale` that moves a
  member's morale state to a worse one (steady to falter, or to break) sends one more line after
  one more line, "<persona> shakes the <group>: they falter." (or "they break."), crediting the
  persona the actor presents; no line when no state changed. The verb returns it as
  `StandoffActionResult.morale_line` and the action layer sends it right after the press line,
  so the room reads the press before its consequence. A verb that raises flushes the
  encounter, its groups and its opponents from the identity map (`flush_cache_on_error`) so
  the cache matches the rolled-back database. `begin_round_or_break_standoff` returns whether
  a round began; the GM view answers 409 and the GM action says so when it did not.
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
- **Press**: each successful press adds exactly 1 to `terms_ease` (whatever its tier); a botch
  (-2) emboldens the group by `botch_force_bands`; morale damage when `damages_morale`. The
  eased difficulty is the sum of hit-drive strengths in bands; the sway modifier counts once
  plus once per eased band.
- **Terms**: a partial or better settles the group, stamps `settled_outcome`, applies the
  effect (PASS and TOLL the pass condition, TURN the turn condition, FLEE sets opponents
  FLED). A terms entry with a `required_drive` is refused until that drive is read. TOLL is
  PASS mechanics, authored with a required Greedy-type drive; any payout comes from the mission
  author's reward lines on the routed tier (`MissionOptionRouteReward`), no new reward model.
- **Critical upgrade**: `StandoffTerms.critical_effect` (blank = none, `clean()` rejects a value
  equal to `effect`) is applied instead of `effect` on a critical (success level 2); the settled
  outcome is still the critical `CheckOutcome`, so the mission routes the critical tier and its
  reward lines pay any toll. Payload and telnet terms rows carry it as `critical_label` ("on a
  critical: Turn") so a player knows a spectacular roll can do more.
- **Reaction lines** (`StandoffReactionLine`, `services/reactions.py`): staff-authored room text
  on a press approach or a terms row, banded by success level on the -2..2 scale. The highest
  `min_success_level` at or below the roll wins; at an equal floor a line tied to the group's
  `creature_template` beats a generic one. `<actor>` is the presented persona name, `<group>` the
  creature kind. The line REPLACES the plain "presses ... : success." room line (one line per
  action; no line authored keeps the plain one), and is sent by the action layer through
  `broadcast_action_outcome(deliver_telnet=True)`. Refusals announce nothing. Admin inlines sit
  on the approach and terms pages. Distinct from `NPCReactionLine` (NPC role, banded on a
  character metric).
- **Sparks**: acting on a spark (press or terms by the matched character while that rule
  shifts their grade) auto-records the share.

## Actions, keys and surfaces

- Actions (`actions/definitions/standoff.py`, registered in `actions/registry.py:809`):
  `standoff_read`, `standoff_press`, `standoff_terms`, `standoff_fight`,
  `standoff_share_spark`.
- Telnet: `CmdStandoff` (`commands/standoff.py`, key `standoff`): bare summary, `read`,
  `press`, `terms`, `display`, `share`, `fight`. Thin dispatch only. The bare summary renders
  `build_standoff_view` as text (groups, hidden count, revealed cause and drives, visible
  regard, the viewer's sparks and shared sparks, approaches with grades and lever lines,
  terms with grades), so it carries exactly what the web payload does.
- Public lines: after a verb really happens (a refusal says nothing), the action layer sends
  one short line through `broadcast_action_outcome` (web and telnet), for example "Vess
  presses the Roadside Bandits with Threaten: success." It names the actor, verb, group and the
  same five-tier word the actor's message opens with, lower case; reveals stay in the reader's own message and the party payload.
- Web: `StandoffCard` (`frontend/src/combat/standoff/StandoffCard.tsx`), rendered by
  `CombatTurnPanel` from the encounter detail's `standoff` block
  (`combat/serializers.py:1366`, `build_standoff_view`).
- Mission options gated by a visibility rule show the owner a "because" line
  (`missions/services/resolution.py:293`, built from `matched_leaves` and `describe_leaf`)
  in the BeatCard; `OptionPage` carries the `opens_as_standoff` control. Predicate additions:
  `matched_leaves` (`predicates/predicates.py:104`), leaves `has_species` (by id) and
  `has_upbringing` (by origin template id), `predicates/describe.py`.

## Display of power and morale (#4147)

- **Display of power press.** A `StandoffApproach` with `casts_technique=True` has the
  player pick one of their own techniques, and that cast is the check (`_press_check` in
  `services/verbs.py`, through `use_technique` with `lethal=False`, so nobody is harmed and
  anima is spent as for any cast). The roll runs through `floor_ultimate_check`, so an
  ultimate never fails. `_technique_refusal` refuses a non-casting approach given a
  technique, and a casting approach given none or one the actor cannot cast. If the cast
  never resolves (the soulfray gate declines) the press is refused with "The display
  falters before it begins." A success eases terms exactly as any press does.
- **A cast that earns a display shakes the group.** `_display_morale_line` runs
  `classify_cast` on the technique, its runtime intensity and the success level. When it
  returns a kind (an ultimate, or a critical technique), `apply_spectacle` runs against
  the group's members and its credit and flavour lines are appended to the press result.
  An approach with `damages_morale` still lowers morale as before, but only when the cast
  earned no display, so one press never shakes twice.
- **Terms ease by morale.** `terms_difficulty` subtracts `_morale_terms_ease` from the
  extra bands: the group's worst member decides, `StandoffConfig.terms_ease_broken`
  (default 2) for a broken member, `terms_ease_faltering` (default 1) for a faltering one,
  none when steady. It stacks with the group's own `terms_ease` and the regard shifts.
- **View fields.** Each group in the payload carries `morale_state` (`steady`, `falter` or
  `break`, the worst among active members; the numbers stay GM-only). Each approach carries
  `casts_technique`. The view carries `display_techniques` (`technique_id`, `name`): the
  viewer's known techniques plus a readied ultimate that pass `technique_performable`.
- **Surfaces.** The `standoff_press` action takes an optional `technique_id`. Telnet:
  `standoff display <technique> <group>` picks the first approach with
  `casts_technique=True` and presses with the named technique (`castable_technique_named`).
  The web `StandoffCard` shows a morale chip on each group and a technique picker for
  casting approaches.

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
- There is no owner-only options field: mission owner-only option reasons ship through the
  mission option reasons (Story 6). Group mission ballots still show every
  participant's gated option labels to the whole group (the pre-existing shared vote,
  `missions/services/multiplayer.py`); only the "because" reason is owner-only.

## Config and Required content

Staff author in admin: drives, regard rules and cause on creature templates; approaches;
terms; the `StandoffConfig` singleton. The tuning dashboard
(`web/admin/tuning/required_content.py`) carries three REQUIRED entries, `standoff-config`
(all four links set), `standoff-approaches` and `standoff-terms`; without them players can
only fight. A TUNING entry, `standoff-reaction-lines`, notes the authored flavour lines. Player-facing prose (spark text, names) is authored in admin.

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
