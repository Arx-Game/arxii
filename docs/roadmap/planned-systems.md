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
  by sunlight, fire-immune species, etc. A single immunity/vulnerability layer over conditions+vitals,
  reused by the aquatic, species, and combat systems below. `intent`.
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
- **Shapeshift (voluntary + rage) + combat profiles** — #1111 (spec:approved, unbuilt). Note: a
  `forms` shapeshift/appearance engine exists at the service layer but is NO-SURFACE (see audit).
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
- **Technique-designer consequence-pool catalog** — pick a pool from a curated set; all casts share one
  seeded pool today. #1320, `partial`.
- **Aspect-in-magic — DESIGN-CLARIFICATION, not an unbuilt system.** `Aspect`/`PathAspect`/
  `_calculate_aspect_bonus` are **built and live** as a *path-competence* check bonus
  (`world/classes/models.py:277,309`, `world/checks/services.py:161`). The open question (#1363): magic
  checks only seed a placeholder `Arcana` aspect, so path investment does ~nothing for magic — decide
  whether/how magic should use the aspect dimension, or drop it for magic. **Not** "build Aspects." Note:
  mapping resonance→aspect was *rejected* (closed #1357) as double-counting `power_terms`. `partial`.
- **Soulfray progression** (warp stage-advance / aftermath / treatment) — #712, `partial`.
- **Multi-target per-target consent state machine** — ADR-0045, `partial`.
- **ResonanceGrantReversal** — endorsements are currently irreversible. `intent` (named in code).

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
  drowning** and the immunity framework (who can't drown). `intent`, partly recorded.
- **Servant / retriever NPC entity**; **vault security / access lists / theft**;
  **building→neighborhood→domain progression** (#696); **room-feature systems** (Library/Lab/Training
  Room/Command Center/Granary/Cannon Deck — #675, only Sanctum real); **future Project kinds** (#673);
  **touchstone items + reagents + personal imbuments** (#707). `intent`.
- **Asset / Companion subsystem** — #672. Includes **animal companions**; we would almost certainly want
  **gifts around them, possibly paths built around companionship**. `intent`.

## Species & racial framework

- **Species/racial framework** — `world/species` is a near-empty stub. A thin racial-*language* notion
  exists (species racial language, `world/character_creation/models.py:257`), but **gifts, abilities,
  and progression are absent**. Needs: **racial gifts**, **growing stronger at racial abilities**
  (racial progression), and species **status vulnerabilities** (e.g. **vampires harmed by sunlight** —
  no vampire/sunlight code today) via the immunity/vulnerability primitive. `intent`, `unrecorded`.

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
- **Roster release / end-tenure**; **events RSVP-accept** (invitee response); **projects activation
  service** — small but real gaps where one half of a loop is unbuilt. `intent`.
