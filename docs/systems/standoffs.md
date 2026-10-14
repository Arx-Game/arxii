# Standoffs

The moment before a fight: a party reads a band of creatures for what moves them, presses
them with social approaches, and names terms that settle them without a round of combat.
Source `src/world/standoffs/`; glossary `src/world/standoffs/AGENT_GLOSSARY.md`; decisions
ADR-4145-A (a standoff is round zero of the encounter, derived from OPEN groups) and
ADR-4145-B (one difficulty function for social checks on a character), and ADR-4354-A (a
standoff proposal is a GM decision prompt, and GM-run is derived). Issue #4145 (missions),
#4354 (GM-run scenes), umbrella #4121. Later slices are listed at the end.

## Lifecycle

- A standoff is **derived**: `is_in_standoff(encounter)` (`services/state.py:65`) is true when
  `round_number == 0` and a live (OPEN or PROPOSED) `StandoffGroup` exists. There is no
  `is_standoff` column.
- Opened by a mission ENCOUNTER option with `opens_as_standoff` set
  (`world/missions/services/encounter_option.py:103`), by a story beat any of whose opponent
  lines has `BeatOpponentLine.opens_as_standoff` set (`RunBeatAction._run_encounter_beat`,
  `actions/definitions/gm_story.py`), or by a scene GM on an encounter that has not begun
  round one (`gm_open_standoff`). Each calls `open_standoff` (`state.py:72`): one OPEN group
  per creature template among the ACTIVE opponents, then `evaluate_causes`.
- Group membership and force use ACTIVE opponents only (`active_members`, `state.py:90`). A
  live group with nobody left is SETTLED (`settle_empty_groups`, `state.py:99`).
- Ends three ways. The party fights (`standoff_fight`), a cause fires, or a caller starts
  round one: all go through `end_standoff_into_fight` (`state.py:115`), which locks the
  encounter row, rechecks, sets every live group FIGHTING (closing any pending proposal) and calls
  `begin_declaration_phase`; a second simultaneous breaker returns False and writes nothing.
  `begin_round_or_break_standoff` (`state.py:169`) is what cast seeding
  (`combat/cast_seed.py:333`, PC side) and the GM begin-round view and action
  (`combat/views.py:497`, `actions/definitions/gm_combat.py:217`, `initiated_by_pc_side=None`)
  call, so attacking during a standoff starts the fight instead of raising.
- Or every group is SETTLED: `complete_standoff` (`services/routing.py:29`) grades the mission
  on the terms (`complete_standoff_for_option`, `missions/services/encounter_option.py:208`,
  tier = `settled_tier`, the weakest settled outcome) and then completes the encounter as an
  ordinary VICTORY. A story beat's encounter is graded the same way: the ENCOUNTER_COMPLETED
  beat handler (`combat/beat_wiring.py`) uses `settled_tier` before the battle mapping.

## Models (`world/standoffs/models.py`)

| Model | Purpose |
|---|---|
| `CreatureDrive` (:28) | A property a creature template wants, with `DriveStrength` (1 Minor, 2 Major, 3 Defining). Unique per template and property. |
| `FactionRule` (:62, was `RegardRule`, renamed #4354) | How a template stands toward particular characters: predicate `rule` (the one ratified JSON field, ADR-0007), `deed_archetype` FK, `difficulty_shift_bands`, `drive` + `drive_shift`, `suppresses_cause`, `angle_text` (was `spark_text`), `revealed_text`. |
| `StandoffApproach` (:141) | A press: `check_type`, `capability` (aims at drives through `Application`), `sway_target` modifier target, `damages_morale`, `archetypes`, `display_order`. |
| `StandoffTerms` (:195) | `effect` (`TermsEffect`: PASS, FLEE, TURN, TOLL), `critical_effect` (applied instead on a critical), `required_drive`, `difficulty_shift_bands`, `archetypes`, `display_order`. |
| `StandoffConfig` (:257) | Singleton: `read_check_type`, `terms_check_type`, `pass_condition`, `turn_condition`, `botch_force_bands`, `band_force_percent`, `over_level_percent_per_tier`, `falter_force_percent`, `break_force_percent`. `load()` returns it. |
| `StandoffApproach.casts_technique` / `StandoffConfig.terms_ease_faltering`, `terms_ease_broken` | #4147: a casting approach (the display of power) and the bands terms ease by morale (see "Display of power and morale"). |
| `StandoffCauseGloss` (:338, #4354) | The one-line player-facing gloss under a revealed cause, one row per `CauseKind`, authored in admin (was a hardcoded dict). |
| `StandoffGroup` (:368) | One band in one encounter: `creature_template`, `state` (OPEN, PROPOSED, SETTLED, FIGHTING), `terms_ease`, `emboldened_bands`, `settled_outcome`, and (#4354) `proposal_reason`, `override_party_force`, `override_group_force`. Unique per encounter and template. Deleting its `creature_template` deletes the group (CASCADE). |
| `StandoffReveal` (:435) | A thing a read uncovered: `kind` (CAUSE, DRIVE, FACTION_RULE) plus the drive or `faction_rule`. Group-wide, shared knowledge. |
| `StandoffAngleShare` (:490, was `StandoffSparkShare`) | A character choosing to share an angle for a group. Unique per group, sheet and rule. |
| `StandoffMoraleRuling` (:586, #4354) | A GM moved a group one morale state: `direction` (SHAKE, STEADY), required `reason`, `ruled_by`. The GM's own record. |

Also added elsewhere: `CreatureTemplate.cause` (`CauseKind`: NONE, PREDATION, ORDERS) and
`cause_margin_percent` (must stay above -100) (`combat/models.py`, `combat/constants.py`); `OpponentTierTemplate.force_weight_percent` (how much one opponent of a tier counts in group force; default 100 for every tier, staff tune it per tier in admin); `CombatEncounter`'s
`initiated_by_pc_side` help text now says a cause stamps False;
`MissionOption.opens_as_standoff` (`missions/models.py:700`, ENCOUNTER options only).
Migration `0199_creaturetemplate_cause_and_more`. #4354 adds `BeatOpponentLine.opens_as_standoff`,
`GMPrompt.standoff_group` and `GMPrompt.resolution_note` (migrations `0223`-`0226`; the rename is
`RenameModel`/`RenameField`, the reveal kind moves in its own data-only migration). Admin: a
creature's cause, drives and faction rules are authored on the Standoff Profile Builder
(`web/admin/standoff_profile/`, below); approaches, terms, config and cause glosses are stock
admins in `world/standoffs/admin.py`.

## Services

- **One difficulty function**: `social_target_difficulty` (`world/checks/social_target.py:48`)
  returns `SocialDifficulty`. Four paths call it: the standoff verbs, combat's
  `_social_combat_difficulty` (`combat/services/`), and both scene overrides
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
  group by its margin, unless every active participant matches a suppressing faction rule
  (`faction_rules.py`). Orders (#4354) fires the same way and also on a provocation: a botched
  press or terms against that group, passed to `evaluate_causes` as `provoked`/`provocation` on
  that action only. `cause_fire_reason` (`force.py:165`) returns why (system text), or None. Opponent level is the party average at spawn (scaling), so headcount and the
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
- **Faction rules** (`services/faction_rules.py`, was `regard.py`): `faction_rule_matches` (:57),
  `drive_strength_from` (:105, clamped 0..3), `band_shift_from` (:111). Deed knowledge counts only the persona the
  character presents (the primary when none), via common-knowledge `LegendEntry` rows, so an
  alt's deeds never leak the link (ADR-0033). Predicate leaves read only the acting
  character's own state, which is why deeds are a typed field and not a leaf.
- **Verbs** (`services/verbs.py`): `standoff_read` (:224), `standoff_press` (:592),
  `standoff_terms` (:712), `standoff_fight` (:805), `standoff_share_angle` (:822). Each locks
  the encounter (and group) row and rechecks state; a verb after the standoff ended or the
  group settled is refused with a message and no roll. A PROPOSED group can still be acted on.
  Every verb ends by testing causes (#4354; a read or share used not to). `press_difficulty`
  (:403) and `terms_difficulty` (:423) are shared by the roll and the payload so a shown grade matches
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
- **Angles**: acting on an angle (press or terms by the matched character while that rule
  shifts their grade) auto-records the share.

## Actions, keys and surfaces

- Actions (`actions/definitions/standoff.py`, registered in `actions/registry.py:835`):
  `standoff_read`, `standoff_press`, `standoff_terms`, `standoff_fight`,
  `standoff_share_angle` (was `standoff_share_spark`). GM actions
  (`actions/definitions/gm_standoff.py`, account-authorized): `gm_standoff_confirm`,
  `gm_standoff_hold`, `gm_standoff_override`, `gm_standoff_morale`, `gm_open_standoff`.
- Telnet: `CmdStandoff` (`commands/standoff.py`, key `standoff`): bare summary, `read`,
  `press`, `terms`, `display`, `share`, `fight`. Thin dispatch only. The bare summary renders
  `build_standoff_view` as text (groups, hidden count, revealed cause and drives, visible
  faction rule detail, the viewer's angles and shared angles, approaches with grades and lever lines,
  terms with grades), so it carries exactly what the web payload does. A group awaiting a GM
  decision reads "Open, deciding". Outside the encounter, `standoff` shows a scene GM (or
  staff) the GM view and anyone else the public summary (#4354).
- Public lines: after a verb really happens (a refusal says nothing), the action layer sends
  one short line through `broadcast_action_outcome` (web and telnet), for example "Vess
  presses the Roadside Bandits with Threaten: success." It names the actor, verb, group and the
  same five-tier word the actor's message opens with, lower case; reveals stay in the reader's own message and the party payload.
- Web: `StandoffCard` (`frontend/src/combat/standoff/StandoffCard.tsx`), rendered by
  `CombatTurnPanel` from the encounter detail's `standoff` block
  (`combat/serializers.py:1378`, `build_standoff_view`). #4354: `gm_standoff` (:1397) feeds
  `GMStandoffPanel` in the combat GM tab, `standoff_summary` (:1414) feeds
  `StandoffSummaryCard` for an onlooker.
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
  technique, and a casting approach given none, one the actor neither knows
  (`CharacterTechnique` row) nor holds as this Audere's readied ultimate (compared by
  technique row, never by name), or one that fails `technique_performable` right now.
  A caster carrying Soulfray is refused with the stage's warning and spends nothing
  (`StandoffActionResult.soulfray_warning`) until the press is re-sent with
  `confirm_soulfray_risk=True`. A success eases terms exactly as any press does.
- **A cast that earns a display shakes the group.** `_display_morale_line` runs
  `classify_cast` on the technique, its runtime intensity and the success level. When it
  returns a kind (an ultimate, or a critical technique), `apply_spectacle` runs against
  the group's members and its credit and flavour lines are appended to the press result.
  An approach with `damages_morale` still lowers morale as before, but only when the cast
  earned no display, so one press never shakes twice.
- **Terms ease by morale.** `terms_difficulty` subtracts `_morale_terms_ease` from the
  extra bands: the group's worst member decides, `StandoffConfig.terms_ease_broken`
  (default 2) for a broken member, `terms_ease_faltering` (default 1) for a faltering one,
  none when steady. It stacks with the group's own `terms_ease` and the faction rule shifts.
- **View fields.** Each group in the payload carries `morale_state` (`steady`, `falter` or
  `break`, the worst among active members; the numbers stay GM-only). Each approach carries
  `casts_technique`. The view carries `display_techniques` (`technique_id`, `name`): the
  viewer's known techniques plus a readied ultimate that pass `performable_techniques`,
  computed only when some approach casts a technique (empty otherwise).
- **Surfaces.** The `standoff_press` action takes an optional `technique_id` and
  `confirm_soulfray_risk`; a Soulfray refusal returns the warning in the result's
  `data["soulfray_warning"]`. Telnet: `standoff display <technique> <group> [soulfray]` picks
  the first approach with `casts_technique=True` and presses with the named technique
  (`castable_technique_named` parses the typed name); a trailing `soulfray` accepts the risk,
  and a Soulfray refusal prints the command to accept it. The web `StandoffCard` shows a
  morale chip on each group and a technique picker for casting approaches; a Soulfray refusal
  shows the warning in the picker with an "Accept the risk" button that re-presses.

## Payload privacy (`services/view.py`, `services/describe.py`)

Everything is built for one viewer; the block is `None` for a non-participant or outside a
standoff.

- Unread cause, drives and rules appear only as `hidden_count`; a hidden drive still shapes
  every grade but is never named.
- A FACTION_RULE reveal's text shows to any character the rule matches, or once a
  `StandoffAngleShare` exists for that rule; everyone else sees only that someone's history
  matters.
- `angles` hold the viewer's own matched rules; `shared_angles` hold what others chose to
  share. A shared angle is not a read: levers show faction rule text only for a rule that was
  read.
- Approaches and terms are listed only for live groups with active members. A PROPOSED group
  shows its `state` as `proposed` (the card says "deciding"); what was proposed is never sent.
- `gm_standoff` (GM view) goes to the scene's GMs and staff only; `standoff_summary` (public
  facts: names, counts, morale, emboldened, settled or fighting; PROPOSED reads as open) goes
  only to a viewer who is neither a participant nor a GM.
- Approach and terms grades are the viewer's own. Terms with an unread required drive are
  omitted.
- There is no owner-only options field: mission owner-only option reasons ship through the
  mission option reasons (Story 6). Group mission ballots still show every
  participant's gated option labels to the whole group (the pre-existing shared vote,
  `missions/services/multiplayer.py`); only the "because" reason is owner-only.

## Config and Required content

Staff author in admin: drives, faction rules and cause on the Standoff Profile Builder;
approaches; terms; cause glosses; the `StandoffConfig` singleton. The tuning dashboard
(`web/admin/tuning/required_content.py`) carries three REQUIRED entries, `standoff-config`
(all four links set), `standoff-approaches` and `standoff-terms`; without them players can
only fight. TUNING entries: `standoff-reaction-lines` (the authored flavour lines) and
`standoff-cause-glosses` (a gloss for every cause but None). Player-facing prose (angle text,
names, glosses) is authored in admin.

## Deviations and rulings

1. No `is_standoff` column; derived (ADR-4145-A).
2. Drives and cause are read through `CombatOpponent.creature_template`, not stamped on
   opponents. Per-placement overrides are slice 2 of #4121.
3. Five-tier checks (no "strong success"); botch is -2 (see Read grading).
4. Predicate leaves read only the actor's own state, so deed knowledge is the typed
   `deed_archetype` on `FactionRule`; `has_species` and `has_upbringing` are leaves.
5. The `StandoffCard` omits the demo's per-group reaction line and level-band caption: no
   data source yet (a level band must be earned by a read, and reaction narration has no
   model).

## GM-run standoffs (#4354)

- **GM-run is derived** (ADR-4354-A): `standoff_is_gm_run(encounter)` (`services/proposals.py:47`)
  is true when `prompt_recipients(encounter.scene, STANDOFF_CAUSE)` is non-empty, that is the
  scene is active and has a GM who has not muted the `STANDOFF` prompt group. A mission a GM
  steps into (an existing `grant_scene_gm` or a present table GM) plays as GM-run from its next
  decision. Nothing is stored.
- **Proposal.** In `evaluate_causes` (`force.py:203`), a firing cause in a GM-run standoff calls
  `propose` (`proposals.py:54`): one `STANDOFF_CAUSE` `GMPrompt` per addressed GM through
  `route_narratable_event`, the group goes PROPOSED with `proposal_reason`. If no GM takes it the
  fight starts as in a mission. A PROPOSED group whose cause fires again only has its reason
  restated. Players keep acting; settling it or a fight closes its prompts.
- **Resolution** (`resolve_proposal`, `proposals.py:131`, under the encounter and group locks):
  Confirm starts the fight NPC-initiated (prompts CONFIRMED); Hold returns it to OPEN, and the
  next action tests the cause again; Override needs a reason, returns it to OPEN, records
  "Overridden: <reason>" in `GMPrompt.resolution_note` and snapshots the force on both sides, so
  the cause is not tested again until force moves or a botch lands (`clear_override`). A
  proposal the standoff already moved past closes with nothing done.
- **The prompt.** `STANDOFF_CAUSE` is a decision kind (`DECISION_PROMPT_KINDS`,
  `world/gm/constants.py`), addressed like a narration prompt but not narrated or dismissed;
  `ADDRESSED_PROMPT_KINDS` drives visibility. Web: `POST /api/gm/prompts/<id>/confirm/`
  (branches on kind), `.../hold/`, `.../override/` (`{reason}`), with `standoff_group_name`,
  `standoff_cause_label`, `standoff_reason` and `resolution_note` on the row. Telnet:
  `gm prompt confirm|hold <id>`, `gm prompt override <id> <reason>`; `gm prompts` lists the
  proposal summary. Scene end closes open decision prompts.
- **GM morale control** (`services/gm_morale.py`, `shift_group_morale`): SHAKE or STEADY moves
  every active member one morale state (to exactly the next threshold going down, one past it
  going up), records a `StandoffMoraleRuling`, clears any override, tests causes, and the room
  gets "<group> falters." / "breaks." / "steadies." (system strings). Refused without a reason,
  outside a standoff, or when no member's tier has morale. Web:
  `POST /api/combat/<id>/standoff-morale/`; telnet `gm standoff shake|steady <group> <reason>`.
- **GM view** (`services/gm_view.py`, `build_gm_standoff_view`): every group with cause and
  whether it fires now (read without lapsing an override), drives with strengths and whether
  read, faction rules with a staff-facing label (`faction_rule_label`), the participants each
  matches and whether read, force on both sides, every member's morale, the pending prompt.
  `build_standoff_summary` is the onlooker's public view.

## Standoff Profile Builder (#4354)

`web/admin/standoff_profile/` (`admin_standoff_profile`, `_standoff_profile/<template pk>/`,
superuser and contributor gated, reached from the creature template's change page): one page
writes `CreatureTemplate.cause` and `cause_margin_percent`, every `CreatureDrive` and every
template-owned `FactionRule` in one transaction and credits the template. The rail
(`live.py`): what each drive means and which approaches and terms reach it, a grade preview
for an example character of a chosen level against one member of that level (the shared
`social_target_difficulty` with no actor), a plain-text cause check for an example party,
and the beat and mission lines that place the creature. `FactionRule.rule` is still typed as
JSON here; the predicate widget arrives with organization and society rules (slice 2).

## Later slices

Plan from #4121 (the proposed slice cut there):

- **Slice 2, placement edits and inheritance:** per-line edits with a spawn snapshot (the
  override in deviation 2), organization and society faction rules with inheritance and
  suppression, the reputation and association predicate leaves, the Placement and Faction
  Rules admin pages, the predicate widget, and the beat dialog's placement fields.
- **Slice 3, named NPCs and language:** persona groups with `NpcRegard`, the verbal gate.
- **Slice 4:** Hunger, Hatred and Territory, `cause_effect`, and the cause re-test when a
  Charmed or Calm hold breaks.
- **Slice 5:** opt-in profiles for player characters.
- **Separately:** resonance from acts via archetype tags. `StandoffApproach.archetypes` and
  `StandoffTerms.archetypes` are stored for it and unread today.
- **Reaction narration** (deviation 5) has no slice yet.
