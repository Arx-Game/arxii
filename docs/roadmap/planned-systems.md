# Planned Systems — designed/intended, not built on either surface

**Purpose:** a durable home for systems and capabilities we intend to build but that have **no code
yet** (no service, model, viewset, Action, or command). Much of this was previously *implied and never
recorded* — mentioned in passing and silently lost. This registry exists so that design intent stops
disappearing. It is **explicitly incomplete and is the capture surface going forward** — add to it
freely; an entry here is recorded intent, not a commitment to a date.

**Relationship to other docs.** Per house policy (*journeys are milestones; only journey-driven issues;
no speculative issues*), planned-but-unbuilt systems live **here**, not as kanban issues — a system
graduates to an issue/milestone only when it becomes next-up. The
[player-reachability audit](../audits/2026-06-25-player-reachability-coverage.md) links its
PLANNED-UNBUILT tier here. Where a planned system *does* already have an issue/milestone, it is cited.

**Status key:** `intent` = no code; `partial` = a piece exists (named here) but the core is unbuilt;
`unrecorded` = surfaced from design conversation, not previously in any doc/issue.

---

## Cross-cutting primitives (build once, reused widely)

- **Damage/condition immunity & vulnerability framework** — "people who can't drown," vampires harmed
  by sunlight, fire-immune species, etc. `partial` — **#1740/#1588** built the core unified seam
  (`resolve_damage_type_resistance`; combat/traps/DoT-tick net condition + gift-thread resistance
  against a `damage_type`, immunity = high resistance not boolean, ADR-0073) plus the first live
  trigger (Sunlight Exposure). Aquatic ("can't drown") is now built via **#1714**: vehicle
  hull-breach/living-mount-defeat ejection routes real participants' drowning/falling damage
  through `resolve_damage_type_resistance` against a `Drowning`/`Falling` `DamageType`
  (`ensure_drowning_damage_type`/`ensure_falling_damage_type`), so a species/gift with high
  resistance to that damage type is effectively immune; abstract `BattleUnit`s instead check a
  flat presence-only `flying`/`aquatic` `Property`. Other species-specific triggers beyond
  sunlight and the vehicle-hazard pair are still unbuilt. The companion mitigation layer (an
  ally or a location granting cover against a hazard) shipped as **#1744** (ADR-0069): Succor
  maneuver + location `DAMAGE_TYPE` cascade axis.
- **Perception-override / altered-reality scene mode** — "who perceives what is real." Reused by
  dreamstates, illusions, and disguise/guise. A scene variety over the `SceneRound` seam. `intent`.

## Scenes & RP

- **Frictionless / implicit scene start** — a directed interaction starts a scene with no staff staging
  (`ensure_scene_for_location` is built-not-wired; only explicit StartScene wires it). `partial` — #1309, ADR-0006.
- **Provisional, EPHEMERAL-by-default scenes + explicit keep-vs-discard agency** — never auto-persist
  RP; the player decides what is kept. Summary draft→agreed exists; scene-level keep/discard does not.
  `partial` — #1309, ADR-0006.
- **Auto-close an empty scene** on room-empty / logout / disconnect. `intent` — #1361.
- **Intimate / private relationship scene variety** — a distinct scene mode (and mechanics) for the
  scenes where relationships are tested and capstones created. `intent` — `unrecorded`-adjacent (rp-scenes.md mentions it).
- **GM-run-table as a live scene variety** — today `GMTable` is only a membership grouping, not a live
  scene mode a player-GM runs. `intent`.
- **Dreamstate scene variety** — altered-reality scene. `intent`, `unrecorded`. Uses perception-override.
- **Illusionary scene variety** — false/perceived reality. `intent`, `unrecorded`. Uses perception-override.
- **Community pose-of-the-scene voting / award** — beyond the automatic scene XP. `intent`.
- **New-player onboarding tutorial** (#1035); **friend list / "looking for RP" finder**; rich-text
  composer / conversation threading. `intent`.

## Combat depth

- **Ranged / reach / archery** — `partial`, NOT greenfield. Technique targeting already has range
  bands (`SAME`=melee / `ADJACENT`=reach / `ANY`=ranged, `world/magic/models/techniques.py:295`), a
  `RANGED` weapon class (`world/items/constants.py:84`), and a `bow`→`archery` skill mapping. What's
  missing is the full ranged-combat mechanics: positioning/range enforcement, line-of-sight, distinct
  archery actions. `partial`, `unrecorded`.
- **Mounts** — mounted movement/combat. `intent`, `unrecorded`.
- **Verticality / flying / rooftops** — vertical space and an aerial layer player surface (a
  positioning `enter_aerial` path exists internally but no player surface). `intent`, `unrecorded`.
- **Knockback + trap-into-combat hazards** — #1317.
- **Out-of-combat reactive interpose / DANGER-round arming** — #1316.
- **Shapeshift (voluntary + rage) + combat profiles** — #1111, **DONE**: an "alternate self"
  mechanism — a bundle of optional facets (form + stats + abilities + persona + control-state)
  swapped together on assumption, reverted together. `assume_alternate_self` /
  `revert_alternate_self` services; `in_control` is a derived `@cached_property` (not stored —
  ADR-0014) that is False while any active condition's category is `alters_behavior` (rage/
  possession/charm). Assumption is NOT `in_control`-gated; revert IS (`RevertBlockedError`);
  clearing the condition re-derives `in_control=True` and unblocks a later self-revert (decoupled).
  Strictly-one-active (`AlternateSelfActiveError`); cross-sheet `form`/`persona` FKs rejected
  (`FormOwnershipError` / `ActivePersonaError`) — never an uncaught 500. Berserk's category was
  wired to `alters_behavior=True`, reusing the existing Fury lever (#567: Berserk +
  `RestoreSenseAction` calm-down) rather than building a parallel rage/calm-down. `ShiftFormAction`
  / `RevertFormAction` (REGISTRY `target_type=SELF`) wrap the services; telnet `CmdForm`
  (`form shift`/`form revert`) and the web `AlternateSelfViewSet` + `FormSwitcher` both dispatch
  via `dispatch_player_action` → `action.run()` (ADR-0001). `PersonaType.ALTERNATE` added.
- **Transformation cause-paths** — #1604, **DONE**: the at-will `form shift` command was
  the only path to `assume_alternate_self`; the technique-driven and involuntary-trigger
  cause-paths were never built. Added a single seam, `trigger_transformation(sheet, alt, *,
  cause, instance_value=1.0)` (`world/forms/services/transformation.py`), that both new paths
  call and that scales each granted `CharacterModifier.value` by the persistent per-character
  `AlternateSelf.tuning_value` baseline × the per-instance `instance_value` (÷ `SCALE=10`;
  neutral case short-circuits to identity). The **technique path**: an
  `EffectKind.ASSUME_ALTERNATE_SELF` pull effect (new) whose `ThreadPullEffect.target_form` FK
  names the form; at cast resolution the success band selects a `FormCombatProfile` by the new
  `depth` field (fail→lowest, mid→middle, crit→highest) and sets `instance_value` (1.0/1.5/2.0).
  The **involuntary-trigger path**: a reactive condition fires `CONDITION_APPLIED` → a flow
  `CALL_SERVICE_FUNCTION` step invokes the registered `flow_trigger_transformation` wrapper
  (`flows/service_functions/forms.py`), which resolves the alt by `(sheet, form__name)`; a
  resist-check branch authors the "fail a check to *not* change" journey. The at-will command is
  retained but gated behind a seeded `at_will_shifting` capability
  (`HoldsCapabilityPrerequisite`) — a niche escape hatch. Revert-blocked-while-raging (the
  #1111 invariant) is exercised end-to-end by the trigger test. Gift-level modulation of the
  resist check is deferred to #1578 (specialization engine).
- **Combo mechanics — fuller rules** — combos exist (upgrade/revert); the exact rules need design. `partial`, `unrecorded`.
- **Soulfray-risk accept + fury commit** — player-chosen combat risk decisions. #1454, **DONE**:
  party-combat casts carry the player's `confirm_soulfray_risk` + fury (`fury_commitment` tier +
  `fury_anchor`) on the `CombatRoundAction` declaration; `resolve_combat_technique` honors them
  (soulfray gate no longer hardcoded; fury via the shared `run_fury_for_action` consumer → control
  penalty + intensity bonus, Berserk on lost control, `Interaction.fury_committed` audit). Telnet
  `cast … fury=<tier> anchor=<name>` reaches the same dispatch seam the web uses; declining a risky
  cast is free re-declare.
- **Duels** — non-lethal PvP + lethal PC-vs-significant-NPC. Milestone #8; NPC-tier lethality gap M#10
  (ADR-0023/0038/0040). (The duel *Actions* exist and are web-dispatchable — see the audit's WEB-ONLY row.)

## Magic & progression

- **Spell system** — learnable, path-independent magic usable by quiescent characters. No `Spell`
  model. `intent` (character-progression.md, magic glossary).
- **Post-CG Gift acquisition** — gain a new Gift in play; today `CharacterGift` is created only at CG
  finalize, so magic freezes after creation. `intent`.
- **Trainer system** — find trainers, costs, tiers. `intent`.
- **Path discovery / research / switching** — beyond listing next options. `intent`.
- **Resonance→aspect mapping** so path investment rewards magic checks (placeholder `Arcana` today). #1363, `partial`.
- **Aspect-in-magic — DESIGN-CLARIFICATION, not an unbuilt system.** `Aspect`/`PathAspect`/
  `_calculate_aspect_bonus` are **built and live** as a *path-competence* check bonus
  (`world/classes/models.py:277,309`, `world/checks/services.py:161`). The open question (#1363): magic
  checks only seed a placeholder `Arcana` aspect, so path investment does ~nothing for magic — decide
  whether/how magic should use the aspect dimension, or drop it for magic. **Not** "build Aspects." Note:
  mapping resonance→aspect was *rejected* (closed #1357) as double-counting `power_terms`. `partial`.
- **Soulfray progression** (warp stage-advance / aftermath / treatment) — #712, `partial`.
- **Multi-target per-target consent state machine** — ADR-0045, `partial`.
- **ResonanceGrantReversal** — endorsements are currently irreversible. `intent` (named in code).

## Gift & resonance economy (ADR-0050–0057)

The 2026-06-27 design discussion produced a connected set of decisions (ADRs 0050–0057). The machinery
below is **designed (ADR)** — the Major/Minor taxonomy keystone has landed (#1577); the rest is unbuilt.
Build to the ADR; these are not open questions. See
[`player-capability-ledger.md`](player-capability-ledger.md) for tiers and sequencing.

- ✅ **Major/Minor gift taxonomy** — LANDED (#1577). `Gift.kind` column (`GiftKind`: `MAJOR` =
  CG-chosen, `MINOR` = shared/acquirable; default `MAJOR`, db_index). The keystone the rest of the
  economy hangs off. ADR-0050. Supersedes the bare "Post-CG Gift acquisition" intent above: acquirable
  powers + species abilities are Minor Gifts via the gift pipeline. (Acquisition machinery itself is
  still #1580/#1581 — this PR is the taxonomy column only.)
- **Species abilities as Minor Gifts** — khati/vampire/lycan/lineage powers delivered as species-granted
  Minor Gifts, no bespoke per-species system. ADR-0050. (See Species & racial framework below.)
- **GIFT thread anchor + per-target-kind cost** — add a `GIFT` `TargetKind` (+ `target_gift` FK +
  constraint quartet) and a per-kind cost axis (cost is tier/level/path only today); gift-threads are
  the costliest kind. ADR-0051. `intent`.
- **Gift resonance from the woven thread** — a gift's affinity is read from its gift-thread resonance
  instead of the fixed `Gift.resonances` M2M (moves `power_terms`/`resonance_environment`/`defilement`
  consumers). ADR-0052. `partial`.
- **The one specialization engine** — generalize `resolve_effective_role` (the only working
  axis-combination) into a shared `(entity × resonance [× thread level]) → customized capability`
  primitive over Gift/Path/Covenant-Role, derive-on-read. **`priority:now` keystone.** ADR-0055,
  ADR-0016. Consumes the dead `TechniqueStyle.allowed_paths` link.
- **XP-unlock contract** — XP buys unlocks that gate, never grant, across the economy (reuse
  `*Unlock`/`Character*Unlock` + `ExperiencePointsData`). ADR-0053. Mostly a contract + new unlock rows
  (acquire-gift, threadweaving-for-gift).
- **Signature technique-thread** — re-scope `TargetKind.TECHNIQUE` to a per-technique signature delta
  (own resonance, may diverge → discordant signature). ADR-0056. `partial`.
- **Fall / Redemption conversion service** — resonance-type conversion (Celestial→Abyssal gains;
  Abyssal→Primal/Celestial loses) without violating the monotonic `lifetime_earned` invariant. ADR-0054.
  `intent` (no conversion primitive today).
- **Covenant of the Court** — new `CovenantType.COURT` (leader + servants across ≥1 power-tier gulf),
  reusing the covenant substrate (CovenantRank + role-power + sub-role specialization). ADR-0057.
  `partial`.

## Relationships, covenants & collectives

- **Relationship mechanics made live** — the relationship-building loop is built but NO-SURFACE (see
  audit); separately, the *mechanical* payoffs are unbuilt: mechanical-bonus consumed in checks,
  teamwork/combo/coordination gating, RelationshipUpdate + decay/freeze cron, and the consent/deceit
  safety layer (privacy MVP-gating). `intent` / `partial`.
- **Adventuring-party model** — group formation, shared legend, coordination. `intent`.
- **NPC reputation model** — −1000..1000 standing for shops/factions. `intent`.
- **Org-level ritual-leadership permissions** — #708.
- **Society politics** — army/military, territory control, alliances/betrayal/warfare, leadership
  succession, world-event influence. `intent`, partly recorded (societies.md).
- **Battle / army / warfare system** — war covenants exist (banner-call rise, `battle_binding`) but have
  **nowhere to resolve into**: no Battle/Army/Regiment/skirmish model. The obvious missing partner to
  war covenants. `intent`, `unrecorded`.

## Crafting, economy, items, estates

- **Item-creation pipeline** — recipe → new `ItemInstance` with stats/facets; today the engine only
  *attaches* facets to existing items. #1125, `intent`.
- **Materials / resources + harvesting loop** — #1125, `intent`.
- **Recipe acquisition** (discover / learn / buy, skill-gated) — `intent`.
- **Crafting-station durability + repair economy** — #1234, `intent`.
- **Crafting Action + telnet command** — the currency/crafting service layers are deep but have zero
  Actions/commands (see audit NO-SURFACE). `intent`.
- **Store / shop / vendor + player↔player trade / barter / auction** — #923, `intent`.
- **Ship system** — vessels, crew, sea travel, mission integration. Connects to **boats / sea travel /
  drowning** and the immunity framework (who can't drown). `partial` — **#1714** built the first
  concrete slice: a battle-time-only `BattleVehicle` (ship/airship/dragon/kraken), reachable only
  inside a `Battle` and discarded with it. **#1832** shipped the persistent half: `ShipDetails`
  (a per-kind `Building` extension, ADR-0086) with commission/upgrade/repair Projects,
  ship-as-sanctum, and `materialize_ship_as_battle_vehicle` bridging into #1714's battle vehicle —
  see [ships.md](../systems/ships.md). Still `intent`: crew as named NPCs (today `crew_capacity`
  is a number), out-of-combat sea travel, cargo-as-tracked-goods, and mission integration.
- **Servant / retriever NPC entity**; **vault security / access lists / theft**;
  **building→neighborhood→domain progression** (#696); **room-feature systems** (Library/Lab/Training
  Room/Command Center/Granary/Cannon Deck — #675, only Sanctum real); **future Project kinds** (#673);
  **touchstone items + reagents + personal imbuments** (#707). `intent`.
- **Asset / Companion subsystem** — #672. Includes **animal companions**; we would almost certainly want
  **gifts around them, possibly paths built around companionship**. `intent`.

## Species & racial framework

- **Species/racial framework** — `world/species` has the species gift substrate
  (`SpeciesGiftGrant` + `provision_species_gifts`, #1580) and the environmental
  vulnerability framework (vampire↔sunlight as `ConditionDamageOverTime` riding the
  peril pipeline, #1740; see ADR-0073). Still **absent**: **racial gifts** (seeded
  species Minor Gift data), **growing stronger at racial abilities** (racial
  progression), and broader **status vulnerabilities** beyond sunlight. `intent`,
  `unrecorded`.

## GM tooling, missions, knowledge

- **Umpire check-modifier tooling** — GM applies ±difficulty/advantage in-flight. `intent`.
- **GM trust→risk leveling curve**; **live Situation/Encounter session resolvers** (beyond the GM-mark
  placeholder); **cross-table GM availability marketplace**. `intent`.
- **Mission player journey on `action.run()`** — mission play runs only through a ViewSet today
  (ADR-0001 gap); plus group invite/consent handshake (#887), categorical room binding (#888),
  player discovery board, mission→beat completion engine, instanced-room wiring (#886), real reward
  sinks (#932). `partial`.
- **Clue/investigation journal UI** (#1143); more clue trigger sources (resonance / past-life, #1160);
  secret/scandal clue kinds. `intent` / `partial`.
- **Collaborative research** (start/contribute project) and **codex teaching** (accept/cancel) — service
  layers exist, no player surface (see audit). `partial`.
- **Returning-player wrap-up of FORECLOSED threads** — #1188, ADR-0039. `intent`.
- **Achievement content + notification delivery** — the engine is built but unfed and silent. `intent`.

## Doors, traps & misc

- **Door lock/unlock** — `CmdLock`/`CmdUnlock` are stubs; `LockAction`/`UnlockAction` don't exist. `intent`.
- **Trap arming/placement** — only disarm exists; the GM side of the trap loop is unbuilt. `intent`.
- **Persona minting** (create/edit/delete an identity) — reserved for future IC flows. `intent`.
- **Tidings posting/reacting/commenting** — feed is read-only; no authoring model. `intent` — #1450.
- **Scandal reach & containment — BUILT (#1464, ADR-0082):** acts fork at deed birth into
  contained Secrets or society awareness (archetype-dot scandal judgment, containment check,
  fame-scaled spread). **Civic-hub reader BUILT (#1450, closes the epic):** Notice Board / Town
  Crier RoomFeatureKinds gate a local tidings slice (`hub_feed_for_room`: room → area →
  `societies_for_area`) surfaced as arrival echo, `tidings local`, and a web room-panel block;
  crier install places a Functionary. **Witness handling BUILT (#1824):** the declared
  capability list (`WITNESS_APPROACHES` + `witness_approaches_for`) replaces the containment
  auto-pick when an approach is declared (bribery attempt tags its own CrimeKind); act-time
  Stealth witness-reduction is wired end-to-end via the mission approach fan (a Stealth
  `ChallengeApproach` → `concealed` deed). Still open: an async prompted-choice containment
  UX at fork time (service param is live; needs its own design); venue vitality (PC-owned
  RP hubs) is its own future umbrella.
- **Roster release / end-tenure**; **events RSVP-accept** (invitee response); **projects activation
  service** — small but real gaps where one half of a loop is unbuilt. `intent`.
