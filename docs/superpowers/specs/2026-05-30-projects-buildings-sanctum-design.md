# Projects, Buildings, and Sanctum — Design Spec

**Date:** 2026-05-30
**Status:** Design — awaiting senior dev review
**Scope:** Foundational `Projects` framework + `Buildings` system + `Sanctum` room feature (MVP surgical slice). Multiple supporting subsystems specced at design level, with implementation deferred to filed issues.

## Guiding Principles

These principles govern every implementation decision downstream. When a mechanic and the narrative texture conflict, narrative wins; we re-tune the math.

1. **Narrative feel is the primary lens; math serves the witchy texture.** Mechanics exist to make moments feel right (the Ritual of Homecoming should *feel* like consecrating a refuge; the 100:1 imbuing ratio matters because it makes each sacrifice weighty, not because the number itself is tuned). Balance matters, but getting the witchy feel exactly right is the most pressing concern.

2. **Immediate vs delayed is the framework boundary.** Projects (subsystem A) are for *delayed multi-tick investment with outcome rolls* — construction, feature progression, war funding, anything that should feel earned over time. NPC functionary interactions (subsystem B) are for *immediate menu-driven resolution* — bribery, permit issuance, negotiation, anything that should feel live and personal. Don't force one shape into the other's model. "Permit application is a Project" would be wrong because permits feel immediate; "the Builders Guild clerk gives you a Sanctum on the spot" would be wrong because Sanctum installation feels earned.

3. **Time scale is RL-months, not days.** Arx-time is fundamentally different from MMO-time (Arx 1 ran ~10 years). Project durations should target weeks-to-months for high-tier progression, not weekend grinds. Anti-inflation concerns that dominate MMO design largely don't apply — power growth is measured in real-world months, so steep exponential scaling on high tiers is *expected and welcomed*, not a balance problem.

## Scope Overview

| Subsystem | Status | Notes |
|---|---|---|
| **A. Project framework** | Built today (full) | Foundational for many gameplay loops |
| **B. NPC Interaction framework** | Built today (full) + 1 functionary role | Builders Guild Clerk only; other roles deferred |
| **C. Permits & site validation** | Built today (full) | Building permit only; other permit kinds deferred |
| **D. Buildings** | Built today (full framework) + 1 building kind | House only; Warship/Farm/etc. deferred |
| **E. Room Feature framework** | Built today (full framework) + 1 feature | Sanctum only; Library/Training Room/etc. deferred |
| **F. Sanctum (the MVP feature)** | Built today (full) | Resolves #511 |
| **G. Asset/Companion system** | Framework noted, mostly deferred | Hook stub fires; full impl filed as issues |
| **Critical Followup: Room Builder Tool** | Deferred to next phase after Sanctum | Required for full player experience |

## Anti-Reinvention Pass — Verification Results

Verified against actual code via parallel Explore agents on 2026-05-30. Findings here override docs and prior brainstorming assumptions.

### ✅ Confirmed (reuse directly)

1. **`Area` is already tiered.** `world.areas.constants.AreaLevel` is an `IntegerChoices` with `BUILDING=10`, `NEIGHBORHOOD=20`, `WARD=30`, `CITY=40`, `REGION=50`. **Buildings ARE already an Area level** — we build a `BuildingProfile`-style OneToOne extension (mirroring `RoomProfile` at the Room level), not a "thin wrapper."
2. **`RoomProfile.is_outdoor`** exists (`evennia_extensions/models.py:372-410`) — identifies outer-grid rooms.
3. **`AreaClosure`** is a materialized view (`world/areas/models.py:68-91`) — ward-of-room queries via closure walk.
4. **`world.locations.services` helpers** — all 9 exist with the signatures the spec assumes: `effective_owner`, `current_tenants`, `is_owner`, `is_tenant`, `transfer_ownership`, `grant_tenancy`, `end_tenancy`, `ownership_history_for`, `tenancy_history_for` (file `src/world/locations/services.py`).
5. **`LocationOwnership` + `LocationTenancy`** with Persona|Organization holder + Area|Room target — exact discriminator pattern the spec assumes.
6. **`DiscriminatorMixin`** at `src/core/mixins.py:12-98` with `_validate_discriminator()` API.
7. **Cron infrastructure** — custom registry via `world.game_clock.tasks.register_all_tasks()` + `register_task(CronDefinition(task_key=..., callable=..., interval=...))` pattern. NOT Celery/Django-Q. Evennia `GameTickScript` runs due tasks every 5 minutes.
8. **Decay/cleanup pattern** — `cleanup_decayed_modifiers` in `world/locations/services.py:915-943` wired via cron. Reusable shape for Sanctum/Building decay.
9. **`ActionPointPool.spend(amount)`** at `world/action_points/models.py:86-395` for AP contributions.
10. **`CurrencyBalance.gold`** at `world/items/models.py:541-562` for money contributions.
11. **`CharacterXP.spend_xp(amount)`** at `world/progression/models/character_xp.py:56-62` — threads already use this pattern (`world/magic/services/threads.py:220-229`).
12. **`Covenant`** at `world/covenants/models.py:25-65` exists with `level` field (Slice D placeholder).
13. **`CharacterCovenantRole`** at `world/covenants/models.py:216-301` is the membership model with `engaged: bool` flag, `left_at` timestamp. Active membership query: `CharacterCovenantRole.objects.filter(covenant=cov, character_sheet=sheet, left_at__isnull=True).exists()`.
14. **`Thread`** at `world/magic/models/threads.py:266-610` with per-PC active-thread constraints already enforced via partial unique constraints. `Thread.level` (0-30+ scale) represents strength. `TargetKind` discriminator already handles ROOM targeting via `target_object` FK.
15. **`Ritual`** at `world/magic/models/rituals.py:49-210` with `execution_kind` dispatch (SERVICE/FLOW/SCENE_ACTION) and `author_account` for player-authored rituals.
16. **`Resonance` model** (at `world/magic/models/affinity.py:53-106`) is a proper Django model with FK to `Affinity`, NOT TextChoices. Resonance types are queryable rows.
17. **`ResonanceGrant`** at `world/magic/models/grant.py:21-158` with rigid discriminator-FK pattern (CheckConstraints enforce exactly one typed source FK per row).
18. **`perform_check`** at `world/checks/services.py:28-100` supports trait modifiers, `extra_modifiers` injection (for contribution bonuses), and effort levels.
19. **`LegendEntry` + `LegendDeedStory`** at `world/societies/models.py:719-943` with the API the spec assumes.
20. **`Distinction`** at `world/distinctions/models.py` — exists, no asset-grant hook yet but extensible for subsystem G.
21. **`ItemTemplate` + `ItemInstance` + `OwnershipEvent` + consumable pattern** — all exist in `world/items/models.py`. Consumable items use `is_consumable=True` + `max_charges=N` + `charges` decrement (items persist with `charges=0` after exhaustion, not deleted).
22. **`MissionGiverStanding`** at `world/missions/models.py:1216-1268` is a perfect schema template for our `NPCStanding` — same shape (giver FK + character FK + affection int + cooldown). Generalize its scope for the new system; missions and our framework don't overlap on NPC interaction shape (missions are branching graphs; we're menu-driven immediate-resolution).

### ⚠️ Spec corrections required

1. **`Persona.path_level` does NOT exist.** Path level is on `CharacterClassLevel`, accessed via `get_character_path_level(character)` helper in `world/progression/services/skill_development.py:46-56`. **Ritual of Homecoming cap formula must use this helper**, traversing `persona → character_sheet → character`. Update Subsystem F service code accordingly.

2. **`Ritual` has NO role-gating field.** "Requires X to lead" must be handled at **service-level validation** inside `perform_homecoming_ritual` and `perform_purging_ritual`, NOT as a model field on the existing `Ritual` table. No `Ritual` model migration needed. This is cleaner — Ritual stays generic; ritual-specific access rules live with the ritual-specific service.

3. **`grant_resonance` signature is explicit-kwarg with typed source FKs**, not a generic source FK. Real signature in `world/magic/services/resonance.py:62-73`:
   ```python
   def grant_resonance(
       character_sheet: CharacterSheet,
       resonance: ResonanceModel,
       amount: int,
       *,
       source: str,
       pose_endorsement=None, scene_entry_endorsement=None,
       room_profile=None, staff_account=None, outfit_item_facet=None,
   ) -> CharacterResonance:
   ```
   Adding Sanctum support requires: (a) new `GainSource` enum values (`SANCTUM_WEAVING`, `SANCTUM_OWNER_BONUS`, `PROJECT_CONTRIBUTION`), (b) new typed FK fields on `ResonanceGrant` model (`source_sanctum_details`, `source_project`), (c) new `CheckConstraint` rows that enforce exactly-one-source per row, (d) new optional kwargs on `grant_resonance` to populate them. Real migration cost — not a no-op.

4. **`OutcomeTier` pattern divergence.** Codebase uses `CheckOutcome` model rows with `success_level: int` (-10 to +10) at `world/traits/models.py:467-505`, NOT a 5-tier TextChoices enum. For projects, **choose**: (i) reuse `CheckOutcome` rows (more consistent, more extensible — recommended); OR (ii) define a separate 5-tier enum and document why (cleaner per-tier code dispatch, less query overhead). Spec previously assumed (ii); recommend switching to (i) during implementation unless there's a strong reason otherwise.

5. **Achievements use `StatDefinition` + `StatTracker`**, NOT `FactStat`. API: `character_sheet.stats.increment(stat_def, 1)` (`world/achievements/models.py:21-89`). Project contribution aggregation creates a new `StatDefinition(key="projects.total_contributed")` row and increments via the existing handler. Spec previously called this `FactStat` — fix in implementation.

6. **Items extend via FK rows (`ItemFacet` pattern), not per-kind subclasses.** `BuildingPermitDetails` should be `OneToOneField(ItemInstance, on_delete=CASCADE)` — mirrors `ItemFacet`'s composition style at `world/items/models.py:564-608`. Permit-specific fields hang off `BuildingPermitDetails`, queryable by `permit.item_instance.permit_details`.

7. **`ItemInstance.owner` is FK to `AccountDB`** (not Persona) at `world/items/models.py:346-352`. "Who owns this permit" queries are Account-level. Permission gates that need persona-level identity must traverse `account → roster → active_persona` or similar — implementation pass figures out the cleanest pattern.

8. **No generic `use_item()` action exists.** Need to **build `ActivatePermitAction`** in `src/actions/definitions/items.py` (subclass `Action`, key `"activate_permit"`, `execute()` method dispatches to permit-activation service) + register in `actions/registry.py`. Reference existing pattern: `EquipAction` at `src/actions/definitions/items.py:20-64`. Add to Subsystem C's today's-scope deliverables.

9. **No item-as-permission pattern exists.** Need to **build `PermitRequired` prerequisite** in `src/actions/prerequisites.py` (or wire validation directly into the construction-wizard submission service — simpler). Add to Subsystem C's today's-scope deliverables.

10. **`Covenant.level` is placeholder for Slice D.** Cap formula for Covenant `base_resonance` cannot use `covenant.level` directly until Slice D ships. **Interim formula**: `cap = sum(get_character_path_level(member.character_sheet.character) for member in active_members) * 10`, OR a fixed-per-covenant-size formula. Lock in during implementation; the formula is a tunable knob in the spec.

11. **Item activation needs `OwnershipEventType` extension** — current enum values are `CREATED`/`GIVEN`/`STOLEN`/`TRANSFERRED`. Adding `ACTIVATED` and `CONSUMED` requires migration to `OwnershipEventType` choices (or use the `notes` field for activation metadata — less queryable but no migration).

### ❌ Confirmed must-build (no existing duplication)

1. **Project framework** (Subsystem A) — entirely new. Nothing in the codebase resembles "delayed multi-tick contribution-pooling endeavor with outcome rolls." Missions are different (authored branching content).
2. **Ward permit rules / `WardBuildingRule`** (Subsystem C) — no existing ward-flag mechanism. Building permits cannot extend an existing model; the ward-policy infrastructure is genuinely new.
3. **`Building` (as Area+Profile pattern)** (Subsystem D) — no `Building`/`Construction`/`Property`/`Estate`/`Manor`/`Holding` model exists. `Property` in `world/mechanics/models.py` is mechanical-modifier properties, NOT buildings.
4. **`FunctionaryRole` + `FunctionaryServiceOption`** (Subsystem B) — missions are branching graphs, not menu-driven immediate-resolution. The frameworks are distinct.
5. **`ActivatePermitAction` + `PermitRequired` prerequisite** (Subsystem C) — see corrections 8 + 9 above.

---

## Subsystem A — Project Framework

### Purpose

A reusable framework for *delayed multi-tick investment with outcome rolls*. Any gameplay loop where players collectively pour AP/money/items/checks into an endeavor and get a tiered result at completion uses this. Construction is one consumer; many future consumers (cleanup, war funding, gang turf, etc.) hang off the same engine.

### Data Layer

**`Project`** — the runtime model. Common fields:

- `kind` — TextChoices discriminator (`BUILDING_CONSTRUCTION`, `ROOM_FEATURE_PROGRESSION`, plus deferred kinds)
- `completion_mode` — TextChoices (`SINGLE_THRESHOLD`, `TIERED_PERIOD`)
- `status` — TextChoices (`PLANNING`, `ACTIVE`, `RESOLVING`, `COMPLETED`, `FAILED`, `CANCELLED`) — `CANCELLED` covers manual cancellation + Building-decay-mid-project per Coherence Pass Notes
- `owner_persona` FK (the persona who initiated and is the "weighted check" source at resolution; resolved from `account.active_persona` at creation if triggered from an account-level action like permit activation)
- `started_at`, `time_limit` (datetime — always set; both modes use it)
- `threshold_target` (int, nullable — only for `SINGLE_THRESHOLD`)
- `current_progress` (int, accumulates from contributions)
- `outcome_tier` (set at completion, nullable until then; representation per "Outcome Tier Model Choice" below)
- `resonance` FK (optional — references the `Resonance` model row; drives `ResonanceGrant` emission on contributions)
- `description` (text — staff-authored or template-derived narrative)

**Per-kind typed payload** via discriminator pattern (mirrors `LocationValueModifier`, `ConditionInstance`, `Consequence` from existing codebase). Each kind owns its own details model:

- `BuildingConstructionDetails` (built today) — target outer-grid room FK, building kind FK, scope tier, customization fields (name, description), builder persona FK, optional owner override
- `RoomFeatureProgressionDetails` (built today) — target `RoomProfile` FK, target `RoomFeatureKind` FK, target level (int), initial-customization payload, installer persona FK
- `InteriorDesignDetails`, `CleanupDetails`, `WarFundingDetails`, `GangTurfDetails`, `CityDefenseDetails` — deferred to issues

Adding a new kind = new details model + new enum value + new outcome handler + (optionally) new service strategy. No schema change to `Project` itself.

**`Contribution`** — single table with discriminator over `kind`:

- `project` FK
- `contributor_persona` FK
- `kind` — TextChoices (`AP`, `MONEY`, `ITEM`, `CHECK`)
- Kind-specific columns (typed, only one populated per row):
  - `ap_amount` (int, nullable)
  - `money_amount` (decimal, nullable)
  - `item_instance` FK (nullable)
  - `check_outcome` FK to `perform_check` result (nullable)
- `intent_text` (text — player's narrative for what they're attempting)
- `privacy_setting` — TextChoices (`PRIVATE`, `GROUP`)
- `occurred_at` (datetime)

Aggregations per `(project, contributor_persona)` enable achievement queries and contribution-summary UI.

### Lifecycle

Cron-driven. Each cron tick scans `Project` rows with `status=ACTIVE`. For each:

1. **Resolve pending check-contributions** since last tick (run the checks via `perform_check`, write outcomes, update `current_progress` — contributions almost always help; catastrophic-fail outcomes occasionally subtract). XP/legend implications per `perform_check` semantics.
2. **Accumulate non-check contributions** (AP, money, items already applied at submission time; sanity-sweep).
3. **Check completion conditions:**
   - `SINGLE_THRESHOLD`: `current_progress >= threshold_target` (success path) OR `now >= time_limit` (timeout path)
   - `TIERED_PERIOD`: `now >= time_limit` only
4. If completing, schedule resolution for the next tick (so completion is never instantaneous — minimum 1 cron from any state change). Set `status=RESOLVING`.

On the resolution tick:

- Owner's weighted check runs via `perform_check`, modified by cumulative contributions.
- Time-out + under-threshold dramatically biases toward failure tiers.
- Outcome tier set per the tier-mapping rules (see "Outcome Tier Shape" below).
- `status=COMPLETED` (any tier from `PARTIAL` up) or `FAILED` (`FAILED` or `CATASTROPHIC`).
- Per-kind outcome handler dispatches (creates Building, levels Sanctum, etc. — depending on kind).

### Outcome Tier Shape

Tiered (`CATASTROPHIC` / `FAILED` / `PARTIAL` / `SUCCESS` / `CRITICAL` — 5 tiers, universal across all Project kinds). Per-kind details model holds the tier→effect mapping.

For `SINGLE_THRESHOLD` mode:

- Below `threshold_target` by `time_limit` → biased toward `FAILED` / `CATASTROPHIC`
- At/above `threshold_target` before `time_limit` → biased toward `SUCCESS` / `CRITICAL`
- Owner's weighted check + contribution modifiers modulate within the bias range

For `TIERED_PERIOD` mode:

- Per-kind `tier_thresholds` on the details model (e.g., `{PARTIAL: 25, SUCCESS: 50, CRITICAL: 100}`)
- Tier reached at deadline = highest `tier_thresholds` entry whose progress was crossed
- Owner's weighted check + contribution modifiers can shift up or down one tier from the threshold-derived value

The exact authoring shape for per-tier effects (effect rows like `ConsequenceEffect`, vs service-dispatched handler, vs hybrid) is an open detail-level decision deferred to implementation. Both are viable and fit the discriminator pattern.

### Integration with Existing Systems

- `ResonanceGrant` (in `world.magic.services.resonance.grant_resonance`) — add `GainSource.PROJECT_CONTRIBUTION` enum value + new typed FK `source_project` on `ResonanceGrant` model + new `CheckConstraint` enforcing exactly-one-source + new optional kwarg on `grant_resonance`. Contributions to projects with a resonance set emit grants.
- `LegendEntry` + `LegendDeedStory` — same pattern as missions. Project completion with legend-worthy outcomes lets contributors author entries.
- **`StatDefinition` + `StatTracker`** (achievements, at `world/achievements/models.py:21-89`) — aggregate "total AP contributed to projects," "projects completed at CRITICAL," etc. become natural achievement stats via `character_sheet.stats.increment(stat_def, 1)`. Seed `StatDefinition` rows like `key="projects.total_contributed"`, `key="projects.completed_critical"`, etc. (Spec previously referenced "FactStat" — the actual model is `StatDefinition`/`StatTracker`.)
- `perform_check` — check contributions are stock `perform_check` calls. The owner's weighted resolution roll uses `extra_modifiers` to inject cumulative contribution bonuses.

### Outcome Tier Model Choice

Codebase uses `CheckOutcome` model rows with `success_level: int` (-10 to +10) at `world/traits/models.py:467-505`, NOT a 5-tier TextChoices enum. For Project outcomes:

- **Recommended (i):** Reuse `CheckOutcome` model rows — define new outcome rows like `CheckOutcome(name="Project Catastrophic", success_level=-2)` ... `CheckOutcome(name="Project Critical", success_level=2)`. More consistent with the codebase's open-ended pattern; per-kind tier mapping uses `success_level` for ordering.
- **Alternative (ii):** Define a separate `ProjectOutcomeTier` TextChoices enum with the 5-tier vocabulary (CATASTROPHIC/FAILED/PARTIAL/SUCCESS/CRITICAL). Cleaner per-tier dispatch, less query overhead, but diverges from the codebase pattern.

Implementation should default to **(i)** unless there's a strong reason otherwise — document the choice during implementation. Spec text below uses the 5-tier names as conceptual labels; the actual representation is the implementer's call.

### Today's Scope

Build the `Project` base model, the `Contribution` table, the cron lifecycle (supporting both `completion_mode`s from day one), the outcome-tier representation (per "Outcome Tier Model Choice" above), AND the `BuildingConstructionDetails` + `RoomFeatureProgressionDetails` per-kind models. Other kinds get filed as issues — each ships its own per-kind details model + service hook when implemented.

**Cron task registration:** Register the Project cron-tick scanner via `register_task(CronDefinition(task_key="projects.lifecycle_tick", callable=scan_active_projects, interval=...))` in `world.game_clock.tasks.register_all_tasks()`. Reuse the existing cron-registration pattern (no new scheduler infrastructure needed).

### Open Detail-Level Decisions

- Exact `tier_thresholds` field implementation on per-kind details models (related table vs structured field — JSONField is banned, lean toward related `ProjectTierThreshold` rows or per-tier columns on each details model)
- Per-tier outcome effect authoring (effect rows vs service-dispatched handler vs hybrid)
- Exact lifecycle state transitions if `BLOCKED` / `CANCELLED` states needed (lean toward keeping minimal until use case appears)

---

## Subsystem B — NPC Interaction Framework

### Purpose

A reusable framework for *immediate menu-driven atomic interactions* with NPCs. Any system where a player faces an NPC who has decisions to make (permits, purchases, info, favors, persuasion) uses this. Permits are today's wedge consumer; merchants, guards, mission NPCs, and any future NPC service surface compose on the same engine.

### Data Layer

**`FunctionaryRole`** — defines what kind of NPC role this is. Fields:

- `name`, `description`
- `default_description_template` (for nameless class-1 NPC rendering)
- `default_rapport_starting_value` (int)
- `faction_affiliation` FK (nullable — references existing org/faction model)

**`FunctionaryServiceOption`** — options registered against a `FunctionaryRole`. Fields:

- `role` FK
- `label` (UI display)
- `category` — TextChoices (`ISSUE`, `DISCOUNT`, `PERMISSION`, `INFORMATION`, `FAVOR`)
- `rapport_requirement` (int — min in-interaction rapport to see/use this option)
- `capability_requirements` — related rows (`OptionRequirement` with kind discriminator: trait threshold, skill threshold, currency, item ownership, etc.)
- `cost` — per-kind cost record (money amount, AP amount, item consumption, etc.)
- `effect_spec` — typed FK to per-effect-kind model (mirrors outcome-tier shape from subsystem A)
- `is_final` (bool — final actions resolve the interaction; non-final actions update rapport and re-render menu)
- `rapport_delta_success`, `rapport_delta_failure` (int — for non-final check-based actions)

**`NPCStanding`** — persistent per-PC-per-NPC disposition. **Only created for class 2/3/4 NPCs** (Assets, Public Named, Story). Fields:

- `persona` FK (the PC)
- `npc_persona` FK (the named/asset NPC)
- `standing_value` (int, can go negative)
- `last_changed_at` (datetime)
- `last_interaction_summary` (text — free-text summary of last meaningful interaction)

**Class-1 nameless functionaries have *no row here*** — every interaction starts fresh, nothing to remember.

**Schema template reuse:** `MissionGiverStanding` at `world/missions/models.py:1216-1268` is a near-identical schema (giver FK + character FK + affection int + cooldown). The implementation pass should use it as the structural template for `NPCStanding` — same shape, just generalized scope (not mission-specific). Missions' branching-graph interaction pattern doesn't overlap with our menu-driven framework, so the two systems are distinct *consumers* of a similar standing data shape.

**Interaction state** is ephemeral and session-scoped — kept in the player's session/UI state for the duration of one menu interaction. Not persisted. When the player picks a final action, that action resolves and any persistent effects are committed.

### Interaction Flow

1. Player opens interaction with NPC (walks into the Guild, uses `interact` on a Tavernkeeper, etc.).
2. System looks up the `FunctionaryRole` attached to this NPC. Computes initial rapport: for class-1, default role value; for class-2/3/4, role default + persistent `NPCStanding.standing_value`.
3. Available options computed: filter `FunctionaryServiceOption` rows for this role by `rapport_requirement` and `capability_requirements` (player's traits/skills/currency/items). Visible options rendered as menu.
4. Player selects an option. Two paths:
   - **Non-final action** (e.g., "Charm the clerk" — uses Allure roll). Runs the check, applies rapport delta based on outcome, re-renders the menu (more options may now meet `rapport_requirement` thresholds). Loops.
   - **Final action** (e.g., "Pay 5000 gold for permit"). Pays the cost, applies the effect (creates permit `ItemInstance`, extends ward access, grants information, etc.), updates persistent `NPCStanding` if applicable, ends the interaction.
5. Post-interaction: for class-1 NPCs, state is discarded. For class-2/3/4, `NPCStanding` reflects the new value. For class-1 NPCs *whose final rapport crossed a threshold AND the NPC is still viable*, a deferred-system hook (subsystem G — Assets) offers a "Cultivate as asset" follow-up action.

### NPC Class Handling (4-tier Taxonomy)

| Class | Identity | Standing model | Visibility |
|---|---|---|---|
| **1. Nameless** | None (just `FunctionaryRole`) | None | Per-visit, may not be same NPC next time |
| **2. Asset** | Persona, created at promotion | Per-PC standing, private to promoter | Promoter only |
| **3. Public Named** | Persona, stable identity | Per-PC standing | Everyone |
| **4. Story NPC** | Persona + CharacterSheet | Per-PC standing | Everyone, full grid interaction |

The framework handles all four — the only switches are "does an `NPCStanding` row exist" and "does the post-interaction asset-promotion hook fire (only for class-1 with viable rapport)."

### Integration with Existing Systems

- `Persona` (already in `world.roster`) — used for class-2/3/4 NPC identity. Promotion (class-1 → 2) creates a new `Persona` row scoped to the promoter (subsystem G).
- `perform_check` — non-final actions inside an interaction use stock `perform_check`.
- `ResonanceGrant` — option `effect_spec` can include a resonance grant.
- `Trait`, `Skill`, `Currency`, `ItemInstance` — capability requirements pull from existing models.
- `LegendEntry` — meaningful final actions can emit Legend.

### Today's Scope

Build the `FunctionaryRole` + `FunctionaryServiceOption` models, the `OptionRequirement` related-table for capability gates, the option-category enum, the interaction state-machine, the option-resolution machinery, and the **Builders Guild Clerk** role with permit-issuance options:

- `ISSUE permit for ward X for Y gold` (default — no rapport requirement, capability requirement is gold)
- `DISCOUNT cost via Persuasion check` (rapport requirement 30+, capability Persuasion)
- `PERMISSION extend approved wards via Allure+Seduction check` (rapport requirement 60+, capability Allure+Seduction)
- `Bribe to allow palatial scope` (capability requirement: substantial gold; affects functionary disposition)
- `Charm the clerk` (non-final, Allure check; updates rapport)

`NPCStanding` model is built but only exercised for class-3/4 NPCs in other systems. Subsystem G's asset-promotion hook is a stub that no-ops on fire today.

### Filed Issues (Deferred)

- Subsystem G (Asset/Companion system) — entire post-promotion gameplay loop
- Town Guard `FunctionaryRole`
- Tavernkeeper `FunctionaryRole`
- Caravan Quartermaster `FunctionaryRole`
- Mission NPC `FunctionaryRole` — anti-reinvention pass should figure out whether existing missions NPC infrastructure absorbs into B or composes with it
- Persistent `NPCStanding` UI surfaces (player view of "who I have standing with and where")
- Voluntary asset-sharing
- Asset compromise / loss lifecycle events

### Open Detail-Level Decisions

- Exact `effect_spec` discriminator shape (echoes Project outcome-tier authoring shape — should match for consistency)
- Whether `capability_requirements` is a related table or structured field (lean toward related table — `OptionRequirement` rows with kind discriminator)
- Actual rapport-delta values for typical check outcomes — tunable per `FunctionaryServiceOption`

---

## Subsystem C — Permits & Site Validation

### Purpose

Gate building construction by ward-level permits issued through NPC functionary interactions. Permits are *immediate-resolution items* (not Projects), produced by subsystem B's interaction flow, consumed at construction-start time to validate the site.

### Data Layer

**Ward-level permit flags** added to the existing ward/neighborhood models in `world.locations` (anti-reinvention pass identifies the exact host model — likely `Area` or a related config table). Per-ward fields:

- `permit_eligibility` — TextChoices (`OPEN`, `REPUTATION_GATED`, `NPC_CONTROLLED`, `CLOSED`)
- `reputation_gate` (nullable — references the reputation stat + threshold for `REPUTATION_GATED` wards)
- `cost_multiplier` (decimal, default 1.0)
- `allowed_building_kinds` m2m to `BuildingKind`

**`BuildingPermit` `ItemTemplate`** — a new `ItemKind` in the existing items system (`world.items`). The permit is an `ItemInstance` of this template.

**`BuildingPermitDetails`** (instance-level data, related to the `ItemInstance`):

- `approved_wards` m2m to ward/area rows — snapshot at issuance
- `max_scope` (IntegerChoices, nullable — null means no scope cap)
- `cost_modifier` (decimal — captures any discount the functionary granted)
- `issued_by_role` FK to the `FunctionaryRole` that issued it
- `issued_at` (datetime)
- `notes_text` (free text for in-character flavor of how the permit was negotiated)
- `consumed_at` (datetime nullable — set when activated; soft retention for audit/history)

### Site Validation Service

`validate_permit_site(permit_instance, outer_grid_room) → ValidationResult` — a service function on the building/permit module. Checks:

- The room's ward is in `permit.approved_wards`
- The room is an outer-grid room (per existing locations metadata — `is_outdoor` or equivalent on `RoomProfile`)
- The permit hasn't been used yet (`consumed_at IS NULL`)
- The PC activating the permit is the permit's owner (per `OwnershipEvent`)

Returns OK or a structured error explaining why the site is invalid + which wards would be valid as feedback.

### Lifecycle

1. Player interacts with Builders Guild Clerk (subsystem B functionary). Functionary's options include "Apply for permit."
2. Final action creates a `BuildingPermit` `ItemInstance` in the PC's inventory with `approved_wards` populated based on what the player qualified for + negotiated.
3. Player walks to a desired outer grid room.
4. Player activates the permit item. `validate_permit_site` runs; on OK, opens the Construction wizard (subsystem D). On error, displays which wards the permit IS valid in.
5. Construction wizard collects building details, submits a `BUILDING_CONSTRUCTION` Project. The permit is consumed at this point (`consumed_at` set + soft retention).
6. Permits in inventory remain valid indefinitely until consumed. No expiration today.

### Cleanup (Decay)

Tied to broader player-inactivity rules. Sanctum has no bespoke decay, and Buildings inherit whatever the global "owner went inactive" cleanup eventually does. **No new decay machinery for permits or buildings in this spec.** Implementation hook: when the global inactivity cleanup determines a building should decay, the building enters a `decayed` state that hides it from the grid but preserves data; recovery on owner return is automatic.

Filed as issue if the global inactivity-rules system needs updates to feed this cleanly.

### Integration with Existing Systems

- `ItemTemplate` / `ItemInstance` / `OwnershipEvent` (already in `world.items`) — the permit is a new `ItemTemplate` row + a per-permit-instance details model (`BuildingPermitDetails` with `OneToOneField(ItemInstance)` — mirrors `ItemFacet` composition pattern at `world/items/models.py:564-608`, NOT per-kind subclasses).
- Consumable pattern: permit's `ItemTemplate` sets `is_consumable=True`, `max_charges=1`; activation decrements `charges` to 0 (item persists, not deleted).
- `ItemInstance.owner` is FK to `AccountDB`, not Persona — "who owns this permit" queries are Account-level. When checking persona-level identity for activation, traverse `account → active_persona` (implementation determines cleanest path).
- `OwnershipEvent` — adding `ACTIVATED` and `CONSUMED` to `OwnershipEventType` choices requires a migration. Alternative: use the existing `notes` field for activation metadata. Implementation choice; lean toward extending the enum for queryability.
- `world.locations.services` — site validation uses `effective_owner(room)` and ward-cascade helpers (via `AreaClosure`) to determine the ward of the activation point.
- Subsystem B's `FunctionaryServiceOption.effect_spec` — the "issue permit" effect calls a service that creates the `ItemInstance` with negotiated parameters.

### Today's Scope

- Add ward-level permit flags to the existing area/ward model (new `WardBuildingRule` 1:1 to `Area` or fields directly on `Area` — implementation decides)
- Build `BuildingPermit` `ItemTemplate` (single row) + `BuildingPermitDetails` model (`OneToOneField(ItemInstance)`)
- Implement `validate_permit_site` service function
- **Build `ActivatePermitAction`** in `src/actions/definitions/items.py` (subclass `Action`, key `"activate_permit"`, dispatches to permit-activation service) + register in `actions/registry.py`. Reference existing pattern: `EquipAction` at `src/actions/definitions/items.py:20-64`.
- **Build `PermitRequired` prerequisite** in `src/actions/prerequisites.py` OR wire validation directly into the construction-wizard submission service (latter is simpler; lean toward it unless the permission check needs to surface in multiple action contexts)
- Builders Guild Clerk's permit-issuance options live in subsystem B; per-option effect specs that create permit `ItemInstance`s are wired here
- Extend `OwnershipEventType` enum with `ACTIVATED`, `CONSUMED` values (migration)
- **Seed at least one ward in an existing test/dev city with each permit-eligibility flag** so the slice is testable end-to-end

### Filed Issues (Deferred)

- Other permit kinds (commercial, industrial, ritual-site, military)
- Permit transferability mechanics (gifting, selling, inheriting permits — works via stock item transfers today but may want bespoke rules later)
- Permit expiration (timed permits)
- NPC-controlled wards full mechanics (composes with subsystem G's asset/disposition mechanics)
- Special-event permits (staff-issued)

### Open Detail-Level Decisions

- Exact host model for ward permit flags (extend `Area` directly vs new `AreaPermitConfig` 1:1 model)
- Permit cost negotiation: is `cost_modifier` applied to base cost or composed multiplicatively with `ward.cost_multiplier`?
- UI surfacing: separate permit item vs "permits available" tab in construction UI

---

## Subsystem D — Buildings

### Purpose

Spawn and manage Buildings as the persistent grid result of completed `BUILDING_CONSTRUCTION` Projects. Buildings host Rooms, Rooms host Features (subsystem E). Ownership and per-room occupancy reuse existing `world.locations` infrastructure wholesale.

### Data Layer

**`Building` is implemented as a `BuildingProfile` model with `OneToOneField(Area)`** — mirroring how `RoomProfile` extends the room-level `ObjectDB`. The locations hierarchy already defines `AreaLevel.BUILDING = 10` (verified at `world/areas/constants.py:4-13`), so Buildings ARE already an Area level — no new tier definition needed. `BuildingProfile` carries the building-specific metadata that's not part of generic `Area`. Fields:

- `area` OneToOneField (the underlying `Area` row with `level=AreaLevel.BUILDING`)
- `kind` FK to `BuildingKind`
- `scope` (IntegerChoices 1-5)
- `linked_outer_grid_room` FK (the outer-grid room from which entry exits lead in — must have `is_outdoor=True` on its `RoomProfile`)
- `constructed_at` (datetime)
- `decayed_state` — TextChoices (`ACTIVE`, `DECAYED`, `HIDDEN`)

Building-as-Area + BuildingProfile-extension pattern means: `LocationOwnership` rows naturally point at the Building's `Area` (no special-casing); `AreaClosure` naturally cascades from rooms-inside-building up through ward/city; `locations.services` helpers (`is_owner`, `current_tenants`, etc.) work without modification.

**`BuildingKind`** — hybrid declarative + service-hook. Fields:

- `name`, `description`
- `allowed_room_features` m2m to `RoomFeatureKind`
- `ward_eligibility_rules` (flag-matching against `Area.permit_eligibility` / `allowed_building_kinds`)
- `service_strategy` — TextChoices (default `GENERIC`; names a registered service function for kinds needing custom completion logic; `GENERIC` uses stock room generation)

**`BuildingKindScopeConfig`** — 1:m to `BuildingKind`. One row per (kind, scope_tier). Fields:

- `kind` FK
- `scope_tier` (IntegerChoices 1-5)
- `scope_label` (string — kind-specific display label; e.g., House scope 5 = "Estate", Warship scope 5 = "Man-of-War")
- `default_room_count` (int)
- `cost_multiplier` (decimal)

**`BuildingManager`** — m2m through-model between `BuildingProfile` and `Persona`. Multiple managers per building allowed (permission tier). Fields:

- `building_profile` FK
- `persona` FK
- `granted_by_persona` FK (audit)
- `granted_at` (datetime)
- `notes_text` (free text)

**Ownership** uses existing `LocationOwnership` rows pointing at the Building's `Area`. Persona-OR-Organization polymorphism, cascade, audit trail, history all reuse the existing infrastructure. **No `owner_persona` / `owner_organization` fields on `Building` itself.**

**Per-room assignment** uses existing `LocationTenancy` rows pointing at the room's `RoomProfile`. Multiple concurrent tenancies handle shared bedrooms; `ends_at` handles eviction. **No `assigned_persona` field on `Room` / `RoomProfile`.**

### Construction Wizard Flow

1. Triggered by permit activation (subsystem C).
2. Player picks `BuildingKind` (filtered by ward-eligibility + permit `max_scope`).
3. Player picks `scope` tier (1-5, filtered by permit + kind's allowed scopes).
4. Player provides customization: building name, exterior description, optional starting funds (money applied as initial contribution to the construction Project).
5. Wizard submits a `Project` with `kind=BUILDING_CONSTRUCTION`, `completion_mode=SINGLE_THRESHOLD`, time/threshold values computed from `BuildingKindScopeConfig` + ward's `cost_multiplier`, and a `BuildingConstructionDetails` payload row.
6. Project runs per subsystem A's cron lifecycle.

### Room Generation at Completion

On the Project's resolution tick (`SUCCESS` or higher tier):

1. Materialize the new `Building` row + its underlying `Area` row (linked into the locations hierarchy).
2. Spawn `default_room_count` `Room` objects + their `RoomProfile` rows. **Default generation strategy:** linear chain — Entry Hall → Hall 2 → ... → Hall N, with stock placeholder names. Each Room's `RoomProfile.area` FK points at the new Building's `Area`.
3. Spawn entry exit from `linked_outer_grid_room` to the Entry Hall, labeled per the building name.
4. Create `LocationOwnership` row: holder = builder's Persona (or builder's specified Organization), parent = Building's Area, `acquired_at = now`.
5. Create `BuildingManager` row: persona = builder, granted_by_persona = builder (self-grant at construction), granted_at = now.

**Per-tier outcome modifiers:**

- `CRITICAL`: Building gets bonus stats (slight increase to default room count, building flagged as "quality construction")
- `SUCCESS`: Standard outcome
- `PARTIAL`: Building created but with degraded stats (fewer rooms, lower base prestige, flagged as "shoddy construction")
- `FAILED`: No building created; refund a fraction of contributions
- `CATASTROPHIC`: No building created; minimal refund; emit `LegendDeedStory`-adjacent entry about the failed project

### Critical Followup — Room Builder Tool

**Required near-term, NOT in Sanctum MVP slice.** The default room generation at construction completion is explicitly a stopgap. It exists so that the construction → Sanctum-install end-to-end can be exercised today, but it is *not the player-facing room creation experience*. Players need a real Room Builder Tool to:

- **Rename** rooms (cosmetic, immediate)
- **Redescribe** rooms (cosmetic, immediate)
- **Drop** rooms they don't want (structural — needs to handle tenants, features, contents, in-flight contributions)
- **Restructure** exits / layout (structural)
- **Add** rooms beyond the default count (`INTERIOR_DESIGN` or `BUILDING_EXTENSION` Project kind)
- **Set ambient / atmospheric data** (lighting, sound, smell, weather — cosmetic, immediate)
- **Set / raise room polish stats** (Opulence, Elegance — via `INTERIOR_DESIGN` Project)
- **Set room-level permissions** (UI over stock `LocationTenancy` mechanics)

**Two operation classes:** cosmetic edits (immediate, no resource cost) and structural changes (Project-driven). **The cosmetic-vs-structural split is flagged for senior dev review before implementation.**

The Sanctum MVP can ship without Room Builder Tool because Sanctum installation does not care about room names. But the *full feature playable experience* requires Room Builder Tool. **It is the very next piece of work after Sanctum ships.** Filed as a top-priority follow-up issue, NOT buried in the generic "filed as issues" list.

### Building Kinds Shipping Today vs Deferred

| Kind | Today | Service strategy |
|---|---|---|
| **House** | Yes (Bob's slice) | `GENERIC` |
| Warship | No, filed | `NEEDS_BESPOKE` |
| Farm | No, filed | `NEEDS_BESPOKE` |
| Fortress | No, filed | `NEEDS_BESPOKE` |
| Plaza (open-air) | No, filed | `NEEDS_BESPOKE` |
| Tower, Cottage, Townhouse, Manor (House variants) | No, filed | Likely `GENERIC` |

### Integration with Existing Systems

- `Area`, `RoomProfile`, `AreaClosure`, `LocationOwnership`, `LocationTenancy`, `world.locations.services` — all reused. Substantial infrastructure exists per the Explore agent's report; building system is essentially a consumer + thin extensions.
- `DiscriminatorMixin` (`core.mixins`) — used for any new polymorphic FKs.
- Evennia room/exit creation — use `evennia_extensions` factories.

### Today's Scope

- `BuildingProfile`, `BuildingKind`, `BuildingKindScopeConfig`, `BuildingManager` models
- House `BuildingKind` row with scope configs for tiers 1-5 (labels, room counts, cost multipliers)
- `BuildingConstructionDetails` Project payload model with `BUILDING_CONSTRUCTION` kind enum value
- Construction wizard UI (React)
- Room-generation service function (`GENERIC` strategy)
- Construction completion handler that materializes Area (with `level=AreaLevel.BUILDING`) + BuildingProfile + Rooms + `LocationOwnership` + `BuildingManager` + entry exit
- `decayed_state` field on `BuildingProfile` but **no decay machinery built today** — when broader inactivity-cleanup work happens, hook into the existing `register_task(CronDefinition(...))` pattern in `world.game_clock.tasks` (mirrors `cleanup_decayed_modifiers` at `world/locations/services.py:915-943`)

### Filed Issues (Deferred)

- All non-House `BuildingKind` rows
- Building demolition mechanics (owner-initiated destruction)
- Building modification post-completion beyond Room Builder Tool's add-rooms
- Building stat aggregation for future Prestige system (Opulence/Elegance)
- Building inheritance / transfer mechanics beyond stock `LocationOwnership.transfer_ownership`
- Broader player-inactivity cleanup system updates if needed

### Open Detail-Level Decisions

- Whether `Building` is a separate model or just metadata on an `Area` row tagged with `building_kind` — lean toward separate model for clarity
- Exact tier-to-outcome mapping for construction projects
- Builder persona vs builder PC for default manager assignment — lean toward initiator, not largest contributor

---

## Subsystem E — Room Feature Framework

### Purpose

A reusable framework for installing one specialized feature per room (Sanctum, Library, Training Room, Lab, Command Center, Granary, Cannon Deck, etc.). Each feature provides distinct mechanical hooks (resonance generation, XP discounts, ritual sites, combat modifiers — kind-specific). Install and upgrade both go through subsystem A as `ROOM_FEATURE_PROGRESSION` Projects.

### Data Layer

**`RoomFeatureKind`** — the catalog model. Fields:

- `name`, `description`
- `max_level` (int — per-kind bounded levels)
- `service_strategy` — TextChoices (names the registered service function that handles install/upgrade completion and ongoing mechanics)
- `required_building_owner_types` — structured field (list of allowed owner types: `[PERSONA]`, `[PERSONA, COVENANT]`, `[ANY]`) — implementation likely a related `RoomFeatureKindOwnerType` table, NOT a JSONField
- `allowed_building_kinds` m2m (empty m2m = any kind)

Sanctum's row: `max_level=5`, `service_strategy=SANCTUM`, `required_building_owner_types=[PERSONA, COVENANT]`, `allowed_building_kinds=` (empty, any kind).

**`RoomFeatureInstance`** — the installed feature. Fields:

- `room_profile` OneToOneField (enforces one-feature-per-room at the schema level)
- `feature_kind` FK to `RoomFeatureKind`
- `level` (int, default 1, bounded by `feature_kind.max_level`)
- `installed_at`, `last_upgraded_at` (datetime)

**Per-kind details model** — mirrors subsystem A's per-kind project payload pattern. `SanctumDetails` (built today), `LibraryDetails` (deferred), etc. Each holds kind-specific state with OneToOne back to `RoomFeatureInstance`. Direction: details → instance (so adding new kinds doesn't require migrating `RoomFeatureInstance`).

### Install / Upgrade Flow

1. Player initiates feature install or upgrade via a UI on a Room they have permission to modify.
2. **Permission gate:** `is_tenant(persona, room) OR persona in building.managers OR is_owner(persona, room)`. Uses existing `world.locations.services` helpers.
3. UI shows available `RoomFeatureKind` rows (filtered by `allowed_building_kinds` against the room's building's kind, AND `required_building_owner_types` against the building's owner type). Room must have no existing `RoomFeatureInstance` for install; existing instance with `level < max_level` for upgrade.
4. Player picks kind + target level + initial customization (any kind-specific parameters; for Sanctum at install time: which resonance type the room is consecrated to).
5. Wizard submits a `Project` with `kind=ROOM_FEATURE_PROGRESSION`, `completion_mode=SINGLE_THRESHOLD`, threshold/time scaled per `RoomFeatureKind` config + target level, and a `RoomFeatureProgressionDetails` payload.
6. Project runs per subsystem A cron lifecycle. Other contributors can pitch in (tenants/managers/owners have contribution capacity; non-permitted players cannot contribute).
7. **On resolution:** per-kind service function (`service_strategy`) runs with the project outcome tier as input. Per-tier outcome modifiers per kind.

### Permissions and Per-Room State During Install

- Installation-in-progress flagged on `RoomProfile` (likely a computed property from active Project queries, or an explicit `under_construction: bool` field — implementation choice).
- Rooms with installs-in-progress get a description suffix (per kind-specific flavor — Sanctum: "Workers and ritualists labor in the corner; the air smells of incense and fresh-paint.") so passers-by see the work.
- Other PCs visiting the room during install see *that something's being built* but not necessarily *what* (depends on the kind's flavor).

### Service Strategy Registry

`RoomFeatureKind.service_strategy` is a TextChoices enum. A registry maps each value to a service function:

```
SANCTUM       → world.magic.sanctum.services.handle_progression
LIBRARY       → (deferred — service stub raises NotImplementedError)
TRAINING_ROOM → (deferred — service stub raises NotImplementedError)
...
```

Service function signature: `handle_progression(project: Project, target_level: int, outcome_tier: OutcomeTier) → None`. Owns creating/updating the per-kind details model, the `RoomFeatureInstance`, and any ongoing-mechanic registration.

### Integration with Existing Systems

- `RoomProfile` (already in `evennia_extensions/models.py`) — the OneToOne anchor for `RoomFeatureInstance`. The model's own comment says "Future game systems (resonances, ownership, defenses) get their own models" — Sanctum is the first system to use that hook.
- Subsystem A (Projects) — install/upgrade is a Project kind, all lifecycle reused
- `LocationOwnership` / `LocationTenancy` / `BuildingManager` — permission gate
- `world.magic.services` — Sanctum service strategy calls into existing resonance / ritual infrastructure
- `Ritual` model (existing magic system) — Sanctum's rituals are authored as `Ritual` rows

### Today's Scope

- `RoomFeatureKind` model + catalog seeding (one row: Sanctum)
- `RoomFeatureInstance` model with OneToOne to `RoomProfile`
- `RoomFeatureProgressionDetails` Project payload model with `ROOM_FEATURE_PROGRESSION` kind enum value
- Install / upgrade wizard UI (React)
- Permission-gate service function
- Service strategy registry with one entry (`SANCTUM`); other entries stub-raise `NotImplementedError`
- Sanctum-specific `SanctumDetails` model + service strategy implementation (covered in Subsystem F)

### Filed Issues (Deferred)

- All non-Sanctum `RoomFeatureKind` rows + per-kind details models + service strategies (Library, Training Room, Lab, Command Center, Granary, Cannon Deck, etc.)
- Feature removal / uninstall mechanics (today: once installed, the feature stays until building demolished)
- Feature downgrade (level N → N-1)
- Cross-room feature interactions (Library adjacent to Lab grants research bonuses)
- UI: feature summary view

### Open Detail-Level Decisions

- Whether typed-FK-to-details direction is `RoomFeatureInstance → details` or `details → RoomFeatureInstance`. Lean toward latter.
- Cost / time scaling formula per level — sharp exponential per principle 1.3. Per-kind tunable.
- Customization-payload implementation — JSONField banned, so per-kind details-model fields set at install time OR related `RoomFeatureProgressionParam` table with kind-specific rows.

---

## Subsystem F — Sanctum (the Surgical Slice)

### Purpose

Ship the first `RoomFeatureKind` end-to-end: a magical home (Personal) or sacred ground (Covenant) installed in a room, generating passive resonance income for woven threads via a two-layer mechanic (discrete Level via Projects + continuous Base Resonance via Ritual of Homecoming). Resolves the deferred `Spec D` ROOM thread anchor cap question (the formula IS Sanctum level).

### Data Layer

**`SanctumDetails`** — the per-kind details model for the Sanctum `RoomFeatureKind`. OneToOne back to `RoomFeatureInstance`. Fields:

- `base_resonance` (decimal, default 0) — the imbued value, grown via Ritual of Homecoming, capped per owner Path level (Personal) or via the covenant's aggregate Path levels (Covenant — anti-reinvention pass identifies exact formula)
- `resonance_type` FK (references existing magic resonance-type model; identifies whether this is a Primal / Celestial / Abyssal / etc. Sanctum)
- `owner_mode` — TextChoices (`PERSONAL`, `COVENANT`) — denormalized from the building's ownership for fast queries; updated by service if building ownership transfers
- `last_homecoming_ritual_at` (datetime nullable) — soft cooldown enforcement + UI display
- `last_purging_ritual_at` (datetime nullable)
- `pending_sacrifice_overflow` (decimal, default 0) — personal resonance sacrificed beyond current cap, held in escrow until cap rises

**`SanctumThread`** — the woven-thread record. A new model OR an extension of existing thread-weaving infrastructure (anti-reinvention pass identifies whether existing thread models can carry the FK to `SanctumDetails` or if a new join model is cleaner). Fields:

- `sanctum_details` FK
- `weaver_persona` FK
- `thread_strength` (decimal or int — pulled from existing thread system)
- `woven_at` (datetime)
- `slot_kind` — TextChoices (`PERSONAL_OWN`, `COVENANT`, `HELPER`) — enforces the per-PC slot rules

### Personal vs Covenant Sanctum Divergences (Single Model, Mode-Driven)

| | Personal | Covenant |
|---|---|---|
| `owner_mode` | `PERSONAL` | `COVENANT` |
| Building owner | Persona | Covenant (specific org type) |
| Max threads | Sanctum level (1-5) | No level cap — gated by active covenant membership |
| Who may weave | Owner + permitted helpers | Active covenant members only |
| Bonus recipients | Manager-weavers | Covenant-member-weavers |
| Slot consumed | `PERSONAL_OWN` (owner) or `HELPER` (invited allies) | `COVENANT` |

**Sanctum ownership is narrower than Building ownership in general.** A Building can be owned by Persona OR any Organization. But to install a Sanctum into one of its rooms, the building's owner must be **Persona OR Covenant specifically** — not any other org type. This constraint lives on the Sanctum `RoomFeatureKind` row as `required_building_owner_types=[PERSONA, COVENANT]`.

**Architectural decision — Organization gets a `kind` discriminator + per-kind details models.** Verified during coherence pass: `Covenant` (at `world/covenants/models.py:25`) and `societies.Organization` are currently separate models with no relationship. `LocationOwnership.holder_organization` is FK to `societies.Organization` only.

**Decision (senior dev, 2026-05-31):** There will be many kinds of organizations (Noble Houses, Trade Guilds, Criminal Gangs, Covenants, etc.) all sharing a common membership/governance/audit/location-ownership surface but with kind-specific fields. Model this with the **discriminator + per-kind details** pattern (same shape as Projects, Buildings, Room Features) — `Organization` is the base with a `kind` enum, and each kind's specific data lives in a OneToOne details model.

**Model shape:**

```python
class OrganizationKind(models.TextChoices):
    NOBLE = "NOBLE", "Noble"            # houses, councils — landed/titled groups
    TRADE = "TRADE", "Trade"            # merchants AND crafters (one kind)
    CRIMINAL = "CRIMINAL", "Criminal"   # gangs, syndicates, cartels
    COVENANT = "COVENANT", "Covenant"   # magical oath groups
    DEVOTIONAL = "DEVOTIONAL", "Devotional"  # religious orders + militant holy orders (one kind)

class Organization(SharedMemoryModel):
    name = ...
    kind = CharField(max_length=20, choices=OrganizationKind.choices)
    founded_at, dissolved_at, description, ...
    # Common surface: membership (via OrganizationMembership), governance,
    # audit history, location ownership — all work for every kind

class Covenant(SharedMemoryModel):
    """Per-kind details for kind=COVENANT — magical oath group."""
    organization = OneToOneField(Organization, primary_key=True, ...)
    covenant_type = ...      # DURANCE / BATTLE / ...
    sworn_objective = ...
    level = ...              # Slice D progression placeholder
    # ...etc per existing covenants/models.py Covenant fields

# Future per-kind details models (filed as separate work, not built today):
# class NobleHouse(SharedMemoryModel): organization OneToOne, heraldry, head_persona, ...
# class TradeGuild(SharedMemoryModel): organization OneToOne, monopoly_resource, dues, ...
# class CriminalGang(SharedMemoryModel): organization OneToOne, territory, heat_level, ...
# class DevotionalOrder(SharedMemoryModel): organization OneToOne, faith_focus,
#     order_kind (RELIGIOUS / MILITANT), holy_relic_facet, ...
```

The 5 kinds are intentionally exhaustive — the senior dev's call. Devotional is a catch-all covering both religious orders (monks, priests, disciples) and militant holy orders (templars, paladins) under one kind; Trade is a catch-all covering both merchants and crafters. No `OTHER` fallback — every org commits to one of the five.

**What this gives:**

- One `LocationOwnership.holder_organization` FK serves all org types
- `OrganizationMembership` works for every kind (Noble House nobles, Guild members, Gang crew, Covenant oathbound — all the same membership API)
- Adding new org types = new `OrganizationKind` enum value + new per-kind details model + zero changes to `Organization`, `OrganizationMembership`, `LocationOwnership`, or `is_owner` cascade
- The "is this owner a Covenant?" check becomes `org.kind == OrganizationKind.COVENANT` (or `org.covenant` access for covenant-specific fields)
- Same pattern as Projects (`Project.kind` + per-kind details), Buildings (`BuildingKind` + per-kind details), Room Features (`RoomFeatureKind` + per-kind details) — single discoverable convention for the whole codebase

**Migration cost (small since Organization infrastructure is currently empty):**

- Add `Organization.kind` column with `OrganizationKind` TextChoices enum (`NOBLE`, `TRADE`, `CRIMINAL`, `COVENANT`, `DEVOTIONAL`)
- Migrate existing `Covenant` model: add `organization = OneToOneField(Organization, primary_key=True, ...)` + auto-create backing Org in `Covenant.save()` (set `kind=COVENANT`)
- Data migration: backfill existing Covenant rows with backing Organization rows
- Other per-kind details models (`NobleHouse`, `TradeGuild`, `CriminalGang`, `DevotionalOrder`) ship as their concrete consumers materialize — out of scope for the Sanctum slice, filed as future work

**Implementation path:** Explicit OneToOne composition (preferred over Django multi-table inheritance for SharedMemoryModel safety — verify MTI compatibility with idmapper if the implementer wants to use it, but lean toward OneToOne by default).

**For Sanctum specifically:**

- `required_building_owner_types = [PERSONA, OrganizationKind.COVENANT]` — narrows by kind, not by separate model
- Future room features could specify other org-kind requirements (a "Heraldic Hall" requires `NOBLE_HOUSE`; a "Smuggler's Hideout" requires `CRIMINAL_GANG`; etc.) using the same constraint mechanism
- `BuildingProfile.owning_covenant` helper:

```python
def get_owning_covenant(building_profile) -> Covenant | None:
    """Return the Covenant that owns this building, or None."""
    owner = effective_owner(building_profile.linked_outer_grid_room)
    if owner is None or owner.holder_type != HolderType.ORGANIZATION:
        return None
    org = owner.holder_organization
    if org.kind != OrganizationKind.COVENANT:
        return None
    return org.covenant  # OneToOne reverse access
```

### Per-PC Weaving Slots

- **1 personal Sanctum slot** — your own home (if you own a Sanctum, this is dedicated to it; consumed when you weave into your own Sanctum as `PERSONAL_OWN`)
- **1 covenant Sanctum slot** — committing to one covenant's sacred ground (must be a covenant you're an active member of; consumed when you weave as `COVENANT`)
- **Unlimited helper slots** — woven into other personal Sanctums as an ally (`HELPER`)
- XP cost per weaving (per existing thread-weaving cost rules)

Org Sanctums are members-only (no non-member helper weavings).

### Service: Sanctum Progression Handler

`world.magic.sanctum.services.handle_progression(project, target_level, outcome_tier)` — called by subsystem E on Project resolution.

**On install (target_level=1):**

- Creates `SanctumDetails` row with `base_resonance=0`
- Sets `resonance_type` from install params
- Sets `owner_mode` from building's owner type at install time
- Links to `RoomFeatureInstance`

**On upgrade (target_level=N+1):**

- Updates `RoomFeatureInstance.level` and `last_upgraded_at`
- No `SanctumDetails` field changes (level lives on the instance, not the details)

**Per-tier outcome modifiers:**

- `CRITICAL`: grants `+5%` of cap as bonus initial `base_resonance` (small "consecration boost")
- `PARTIAL`: reduces the next upgrade's threshold by some penalty (the install was rushed)
- `FAILED`: cancels the install — Project resources mostly refunded, no Sanctum created
- `CATASTROPHIC`: cancels install + minimal refund + Legend entry of the failure

### Service: Ritual of Homecoming

`world.magic.sanctum.services.perform_homecoming_ritual(sanctum, leader_persona, resonance_sacrificed, narrative_text)`:

1. **Validate leader is a manager (Personal) or designated covenant manager (Covenant)** — this gate lives in service-level validation, NOT as a `Ritual` model field. The Ritual model has no role-gating field today (verified); adding one would require a migration to a generic model used by many systems. Service-level validation is cleaner.
2. Validate `resonance_sacrificed` doesn't exceed leader's personal resonance pool.
3. Compute `base_resonance_gained = resonance_sacrificed / 100` (100:1 efficiency).
4. Compute current cap:
   - **Personal:** `cap = get_character_path_level(owner_persona.character_sheet.character) * 10` — uses the existing helper at `world/progression/services/skill_development.py:46-56`. `Persona.path_level` does NOT exist; the value lives on `CharacterClassLevel` and is retrieved via this traversal.
   - **Covenant:** interim formula `cap = sum(get_character_path_level(member.character_sheet.character) for member in active_members) * 10`, where `active_members` are `CharacterCovenantRole` rows with `left_at IS NULL`. (Final formula likely shifts to use `Covenant.level` once Slice D's Covenant level-up work ships — `Covenant.level` is a placeholder today per the model's own docstring.)
5. Apply gain up to cap; any overflow goes to `pending_sacrifice_overflow` (held in escrow until cap rises).
6. Deduct `resonance_sacrificed` from leader's personal pool.
7. Update `last_homecoming_ritual_at`.
8. Emit a `LegendDeedStory`-style entry capturing the `narrative_text` the player wrote (use `world.societies.LegendEntry` + `LegendDeedStory` per `world/societies/models.py:719-943`).
9. Periodic check (on next cron tick or owner level-up event): if `pending_sacrifice_overflow > 0` AND current cap > current `base_resonance + overflow_to_absorb`, absorb overflow up to new cap. Surfaces as a notification.

### Service: Purging Ritual

`world.magic.sanctum.services.perform_purging_ritual(sanctum, leader_persona, new_resonance_type, resonance_sacrificed)`:

1. **Service-level validation:** leader is a manager (Personal) or designated covenant manager (Covenant). Same pattern as Homecoming — no `Ritual` model field for role-gating.
2. Validate this is a *different* `Resonance` row from current (no-op purges rejected).
3. Cost is steep — `resonance_sacrificed >= sanctum.base_resonance * some_multiplier` (initial value 1×, tunable). Purging requires re-consecrating the entire imbued resonance.
4. Validate cost is paid (from leader's personal pool).
5. Atomically: change `resonance_type` FK to `new_resonance_type` (a `Resonance` model row, not an enum); **all `SanctumThread` rows attached to this Sanctum have their effective resonance type recomputed** (the thread adopts the room's new type — implementation either denormalizes or always reads from `sanctum.resonance_type` lazily).
6. Drain some fraction of `base_resonance` (purging is destructive — initial value: 50% retained, tunable).
7. Update `last_purging_ritual_at`.
8. Emit `LegendEntry` rows for the leader AND all woven thread holders.
9. Broadcast a system notification to all woven thread holders ("Your thread in [Sanctum] has been re-consecrated to [new type]").

### Resonance Generation Cron Tick

A scheduled task registered via `register_task(CronDefinition(task_key="sanctum.resonance_generation_tick", callable=..., interval=...))` in `world.game_clock.tasks.register_all_tasks()`. Frequency tunable — likely per-IC-day or every few hours. Iterates `RoomFeatureInstance` rows where `feature_kind=SANCTUM`:

```python
LEVEL_MULTIPLIERS = [1.0, 1.5, 2.0, 3.0, 6.0]  # index = level - 1

for sanctum in active_sanctums:
    if sanctum.base_resonance == 0:
        continue
    level_multiplier = LEVEL_MULTIPLIERS[sanctum.level - 1]
    pool_per_thread = sanctum.base_resonance * level_multiplier * K  # K is a tuning constant
    threads = SanctumThread.for_sanctum(sanctum)
    if not threads:
        continue  # no income paid if no one woven

    # Independent draw per weaver — grant_resonance is explicit-kwarg
    for thread in threads:
        income = thread.thread_strength * pool_per_thread
        grant_resonance(
            character_sheet=thread.weaver_persona.character_sheet,
            resonance=sanctum.resonance_type,  # actual Resonance row, not enum
            amount=int(income),
            source=GainSource.SANCTUM_WEAVING,
            source_sanctum_details=sanctum,  # new typed FK on ResonanceGrant
        )

    # Owner bonus
    if sanctum.owner_mode == PERSONAL:
        manager_personas = {bm.persona_id for bm in sanctum.building_profile.managers.all()}
        bonus_recipients = [
            t.weaver_persona for t in threads
            if t.weaver_persona_id in manager_personas
        ]
    else:  # COVENANT
        covenant = sanctum.building_profile.owning_covenant  # resolved from LocationOwnership
        active_member_ids = set(
            CharacterCovenantRole.objects.filter(
                covenant=covenant, left_at__isnull=True
            ).values_list("character_sheet__persona__id", flat=True)
        )
        bonus_recipients = [
            t.weaver_persona for t in threads
            if t.weaver_persona_id in active_member_ids
        ]

    other_threads_count = len(threads) - 1
    for recipient in bonus_recipients:
        # +1 per other thread (not counting their own)
        grant_resonance(
            character_sheet=recipient.character_sheet,
            resonance=sanctum.resonance_type,
            amount=other_threads_count,
            source=GainSource.SANCTUM_OWNER_BONUS,
            source_sanctum_details=sanctum,
        )
```

Level multipliers and `K` are tunable. The shape is locked.

**Required schema changes to `ResonanceGrant` (in `world/magic/models/grant.py`) to make the above work:**

- Add `source_sanctum_details = ForeignKey(SanctumDetails, null=True, blank=True, ...)`
- Add `source_project = ForeignKey(Project, null=True, blank=True, ...)`
- Add new `CheckConstraint` rows enforcing exactly-one-source per row (mirrors existing constraints at `grant.py:88-154`)
- Add `GainSource` enum values: `SANCTUM_WEAVING`, `SANCTUM_OWNER_BONUS`, `PROJECT_CONTRIBUTION` (in `world/magic/constants.py:130-138`)
- Add corresponding optional kwargs (`source_sanctum_details=None`, `source_project=None`) to `grant_resonance` at `world/magic/services/resonance.py:62-73`

### Thread Weaving and Slot Enforcement

`world.magic.sanctum.services.weave_thread(sanctum, weaver_persona, slot_kind)`:

1. Validate weaver has the required permission to weave (Personal: invited by manager; Covenant: active covenant member).
2. Validate slot rules:
   - `PERSONAL_OWN`: weaver must own this Sanctum AND have no existing `PERSONAL_OWN` thread elsewhere
   - `COVENANT`: weaver must be active member of the owning covenant AND have no existing `COVENANT` thread elsewhere
   - `HELPER`: weaver does not own this Sanctum AND this Sanctum must be Personal (no helper slots in Covenant Sanctums)
3. Validate XP cost (existing thread-weaving cost rules); deduct.
4. Validate weaver has not exceeded their broader thread cap (per existing thread-weaving infrastructure).
5. Validate Personal Sanctum's level allows another thread (current threads < level); Covenant Sanctums skip this check.
6. Create `SanctumThread` row; thread's effective resonance is the Sanctum's current `resonance_type`.

`world.magic.sanctum.services.sever_thread(sanctum, thread, requester_persona)`:

- Requester is the thread's weaver (voluntary withdrawal) OR a manager (snip).
- Delete the `SanctumThread` row.
- No resonance refund — thread was an investment.
- Notification to weaver if snipped.

### Resolves #511 Explicitly

The deferred `Spec D` ROOM thread anchor cap: **ROOM thread anchor cap = Sanctum level (for Personal) or unlimited subject to covenant membership (for Covenant); 0 if no Sanctum installed.** Rooms without a Sanctum simply aren't thread-anchorable. #511 closes when this spec ships — the formula IS Sanctum-the-feature.

### Integration with Existing Systems (Verified)

- **`Covenant`** at `world/covenants/models.py:25-65` — exists with `level` field (currently a Slice D placeholder). Active membership via `CharacterCovenantRole` (`covenants/models.py:216-301`) — query: `CharacterCovenantRole.objects.filter(covenant=cov, character_sheet=sheet, left_at__isnull=True).exists()`. The `engaged` boolean flag marks the "fulfilling" role.
- **`Thread`** at `world/magic/models/threads.py:266-610` — `Thread.level` represents strength; `target_kind` discriminator handles ROOM via `target_object` FK; per-PC active-thread uniqueness already enforced via partial unique constraints. Decide during implementation whether `SanctumThread` extends `Thread` (with a new `target_kind=SANCTUM` value + new `target_sanctum_details` FK) or is a separate join table — lean toward extending `Thread` for consistency with existing thread targeting.
- **`Ritual`** at `world/magic/models/rituals.py:49-210` — Ritual of Homecoming + Purging Ritual ship as `Ritual` rows with `execution_kind=SERVICE` and `service_function_path` pointing at the Sanctum service functions. No model migration needed; **role-gating is service-level validation**, not a Ritual field.
- **`ResonanceGrant`** + `grant_resonance` — see "Required schema changes to ResonanceGrant" block above. Adding `source_sanctum_details` + `source_project` typed FKs + new `GainSource` enum values + new `CheckConstraint` rows + new kwargs.
- **Path level access** via `get_character_path_level(character)` helper at `world/progression/services/skill_development.py:46-56`. `Persona.path_level` does NOT exist; traverse `persona → character_sheet → character` and call the helper.
- **`LegendEntry` / `LegendDeedStory`** at `world/societies/models.py:719-943` — used as the spec assumed.
- **`Resonance` + `Affinity`** model rows at `world/magic/models/affinity.py:53-106` — `SanctumDetails.resonance_type` is FK to `Resonance`, not a TextChoices enum. UI populates the resonance picker from `Resonance.objects.all()` (possibly filtered by what's narratively appropriate).

### Today's Scope (the Sanctum MVP)

- `SanctumDetails` model + service module
- `SanctumThread` model (or extension of existing thread infrastructure)
- Sanctum `RoomFeatureKind` row + service strategy registration
- Ritual of Homecoming and Purging Ritual authored as `Ritual` rows + their service implementations
- Cron tick for resonance generation
- Thread weave / sever services with slot enforcement
- UI: install Sanctum wizard, perform Ritual of Homecoming flow, weave thread, view my Sanctums, view bonus accrual
- Integration with `grant_resonance` (new `GainSource` enum values + `source_sanctum` typed FK)
- Resolves #511

### Filed Issues (Deferred)

- Item-consuming Ritual of Homecoming variant (sacrifice resonance-bearing items of great meaning)
- Sanctum decay machinery (deferred to broader inactivity-cleanup system)
- Sanctum stat aggregation for Prestige system (Opulence-of-Sanctum)
- Voluntary thread sharing between weavers
- Cross-Sanctum interactions (matching resonance type owned by linked PCs resonate together)
- "Visit other PCs' Sanctums" discoverability UI

### Open Detail-Level Decisions

- Cron tick frequency (hourly vs per-IC-day vs other) — balance question
- Tuning constant `K` and exact level multipliers — initial values `[1.0, 1.5, 2.0, 3.0, 6.0]` but tunable
- Covenant `base_resonance` cap formula — depends on what the covenant model exposes; pick during spec writing once Covenant is verified
- Purging Ritual cost multiplier and `base_resonance` retention fraction — initial values 1× current base + 50% retained, but tunable
- Whether snipped threads notify the weaver in-character or with system text

---

## Subsystem G — Asset / Companion System (Framework Noted; Mostly Deferred)

### Purpose

Persistent minor-NPC bonds owned by a PC. Sources: post-interaction cultivation (uses subsystem B) OR distinction-granted at CG (extends existing distinctions) OR earned via missions/play. Drives its own gameplay loops — recurring intel feeds, money streams, "send asset to do X" task submissions, guards / fans / hangers-on variants.

### Scope

**Mostly deferred to issues.** For today's spec:

- Asset taxonomy documented (4 NPC classes — see Subsystem B)
- Asset model sketched: `(promoter_persona, asset_persona, role context, standing, status)`
- Promotion mechanic described: post-interaction cultivation check against persistent NPC standing
- Distinction-granted-asset hook noted as an extension point
- Subsystem B fires a post-interaction stub hook for class-1 NPCs that crossed rapport threshold; today the hook no-ops

### Filed Issues (All Deferred)

- Asset model implementation
- Promotion mechanic (post-interaction cultivation check)
- Asset tasking system (PC submits actions for asset to perform — recurring intel feed, money streams, one-off investigation requests)
- Distinction-granted starting assets (extend existing distinction system)
- Guard / fan / minor-ally variants of asset type
- Asset compromise / loss lifecycle events
- Voluntary asset sharing
- CG asset designer UI

---

## Filed Issues Summary

When this spec is approved, the following get filed as GitHub issues. Organized by priority and subsystem.

### Critical Followup (Next Build Phase After Sanctum MVP)

- **Room Builder Tool** (per Subsystem D) — cosmetic edits + structural changes via `INTERIOR_DESIGN` Project kind. **Cosmetic-vs-structural split flagged for senior dev review.**
- **Inactivity-detection system** (per Coherence Pass Notes) — Sanctum/Building decay machinery is parked because there's no comprehensive "player went inactive" detection today. Designing this system is its own initiative; until it ships, decay is a hook-without-a-trigger.

### Subsystem A — Additional Project Kinds

- `INTERIOR_DESIGN` Project kind (used by Room Builder Tool)
- `CLEANUP` Project kind
- `WAR_FUNDING` Project kind (`TIERED_PERIOD`)
- `GANG_TURF` / `GANG_MENACING` Project kind (`TIERED_PERIOD`)
- `CITY_DEFENSE` Project kind (`TIERED_PERIOD`; staff-bespoke flavor)
- `BUILDING_EXTENSION` Project kind (add rooms to existing building)
- Outcome-tier authoring shape final decision

### Subsystem B — Additional NPC Functionaries

- Town Guard `FunctionaryRole`
- Tavernkeeper `FunctionaryRole`
- Caravan Quartermaster `FunctionaryRole`
- Mission NPC `FunctionaryRole` (with anti-reinvention pass on `world.missions`)
- Persistent `NPCStanding` UI surfaces

### Subsystem C — Additional Permit Kinds and Ward Mechanics

- Commercial / industrial / ritual-site / military permit kinds
- Permit expiration mechanics
- NPC-controlled ward full mechanics (composes with G)
- Staff-issued special-event permits

### Subsystem D — Additional Building Kinds and Lifecycle

- Warship / Farm / Fortress / Plaza `BuildingKind`s (`NEEDS_BESPOKE` strategies)
- Tower / Cottage / Townhouse / Manor (House variants, `GENERIC`)
- Building demolition mechanics
- Building inheritance / transfer beyond stock `LocationOwnership.transfer_ownership`
- Broader player-inactivity cleanup system updates if needed
- Building stat aggregation hooks for future Prestige

### Subsystem E — Additional Room Features

- Library / Training Room / Lab / Command Center `RoomFeatureKind`s
- Granary / Stables / Field (for Farm buildings)
- Cannon Deck / Brig / Captain's Quarters (for Warship buildings)
- Feature removal / uninstall mechanics
- Cross-room feature interactions
- Feature summary view UI

### Subsystem F — Sanctum Extensions

- Item-consuming Ritual of Homecoming variant
- Cross-Sanctum interactions
- Discoverability UI
- Prestige system hooks

### Subsystem G — Asset / Companion System (Entire Subsystem)

- See subsystem G section above

### Other Systems Hinted but Not Designed

- **Prestige system** — characters competing for fame and glamour, fed by Building/Room Opulence/Elegance stats, feeds society reputation. Needs its own brainstorming session.
- **Opulence/Elegance room stats** — fields on `RoomProfile` (or related model), raised via `INTERIOR_DESIGN` Project kind, aggregate to Building level.

---

## Implementation Slice for Today (Bob's Journey End-to-End)

### Bob's Journey (the Wedge / Acceptance Test)

1. Bob walks into the Builders Guild grid room. Interacts with the Builders Guild Clerk NPC.
2. Bob negotiates a permit through the functionary menu (Pay 5000 gold, OR Persuasion check for discount, OR Allure+Seduction to extend approved wards). Walks out with a `BuildingPermit` `ItemInstance` in his inventory naming the wards he's approved for.
3. Bob walks to an outer-grid room in an approved ward. Activates the permit. Construction wizard opens.
4. Bob picks `BuildingKind=House`, `scope=2` (a "Cottage" sized house), provides building name + exterior description, optionally adds money as initial contribution.
5. Wizard creates a `BUILDING_CONSTRUCTION` Project. Bob (and any friends he recruits) contribute over the next several cron ticks (AP, money, items, checks).
6. Project completes. House Building materializes — new `Area` row, 4 placeholder rooms (Entry Hall, Hall 2, Hall 3, Hall 4), entry exit from the outer-grid room, `LocationOwnership` row giving Bob ownership, `BuildingManager` row making Bob the manager.
7. Bob enters his new house. Goes into one of the placeholder rooms.
8. Bob installs Sanctum: picks `RoomFeatureKind=Sanctum` from the install wizard, selects which resonance type to consecrate the room to. Wizard creates a `ROOM_FEATURE_PROGRESSION` Project at `target_level=1`.
9. Install Project completes. `RoomFeatureInstance` + `SanctumDetails` created. Sanctum exists at level 1 with `base_resonance=0`.
10. Bob performs the Ritual of Homecoming — sacrifices 1000 personal resonance, writes the personalization narrative, gains 10 base resonance (capped to his current Path level × 10).
11. Bob weaves his thread into the Sanctum (`PERSONAL_OWN` slot consumed, XP cost paid).
12. Next cron tick: Bob's thread draws resonance income from the Sanctum (his only thread, no owner bonus yet since no other threads).
13. Bob invites his friend Alice to weave in. Alice spends XP, weaves a `HELPER` thread. Next cron tick: Alice gets her own thread income; Bob gets HIS thread income + 1 bonus (for Alice's thread).
14. Over coming weeks/months, Bob accumulates more base resonance through repeated Ritual of Homecoming, upgrades Sanctum to higher levels via more `ROOM_FEATURE_PROGRESSION` Projects, invites more allies.

### Deliverables

**Models / migrations:**

- `Project` + `Contribution` + `ProjectKind` enum (subsystem A)
- `BuildingConstructionDetails`, `RoomFeatureProgressionDetails` (subsystem A per-kind payloads)
- Outcome-tier representation per "Outcome Tier Model Choice" in Subsystem A — likely new `CheckOutcome` rows or a new `ProjectOutcomeTier` enum (implementation chooses)
- `BuildingKind` + `BuildingKindScopeConfig` + House row (subsystem D)
- `BuildingProfile` (OneToOneField to `Area` with `level=AreaLevel.BUILDING`) + `BuildingManager` through-model (subsystem D)
- Ward-level permit flags (new `WardBuildingRule` 1:1 to `Area`, or fields directly on `Area` — implementation decides) (subsystem C)
- `BuildingPermit` `ItemTemplate` row (single row, not a kind subclass) + `BuildingPermitDetails` (`OneToOneField(ItemInstance)`) (subsystem C)
- Extend `OwnershipEventType` enum with `ACTIVATED`, `CONSUMED` values (subsystem C migration)
- `FunctionaryRole` + `FunctionaryServiceOption` + `OptionRequirement` + `NPCStanding` (subsystem B; `NPCStanding` schema mirrors `MissionGiverStanding` at `world/missions/models.py:1216-1268`)
- Builders Guild Clerk `FunctionaryRole` row + permit-issuance option rows (B + C wiring)
- `RoomFeatureKind` + `RoomFeatureInstance` (subsystem E)
- Sanctum `RoomFeatureKind` row (E + F wiring)
- `SanctumDetails` + `SanctumThread` (subsystem F; consider extending existing `Thread` model with new `target_kind=SANCTUM` + `target_sanctum_details` FK)
- Ritual of Homecoming + Purging Ritual `Ritual` rows (subsystem F; `execution_kind=SERVICE` + `service_function_path` pointing at the Sanctum services)
- **`ResonanceGrant` extensions:** add `source_sanctum_details` + `source_project` typed FKs, add `GainSource` enum values `SANCTUM_WEAVING` / `SANCTUM_OWNER_BONUS` / `PROJECT_CONTRIBUTION`, add `CheckConstraint` rows enforcing exactly-one-source (cross-cut)
- **`StatDefinition` seed rows:** `projects.total_contributed`, `projects.completed_critical`, `sanctums.owned`, `sanctums.helper_threads_woven` (and others as desired) — uses `world/achievements/models.py` infrastructure

**Service functions:**

- Project cron-tick scanner + lifecycle resolver (subsystem A) — **registered via `register_task(CronDefinition(task_key="projects.lifecycle_tick", ...))` in `world.game_clock.tasks.register_all_tasks()`**
- Per-kind outcome handlers for `BUILDING_CONSTRUCTION` and `ROOM_FEATURE_PROGRESSION`
- `validate_permit_site` (subsystem C)
- Construction wizard submission service (subsystem D)
- Room generation service (`GENERIC` strategy — linear chain placeholder)
- Sanctum progression handler (`world.magic.sanctum.services.handle_progression`)
- Ritual of Homecoming service (`perform_homecoming_ritual`) — uses `get_character_path_level(persona.character_sheet.character)` for cap
- Purging Ritual service (`perform_purging_ritual`)
- Sanctum resonance generation cron tick — **registered via `register_task(CronDefinition(task_key="sanctum.resonance_generation_tick", ...))`** alongside the Project tick
- Thread weave / sever services with slot enforcement
- Extended `grant_resonance` with new optional kwargs (`source_sanctum_details=None`, `source_project=None`)
- Stubs for all other Project kinds, FunctionaryRoles, RoomFeatureKinds (raise `NotImplementedError` so dispatcher exists but doesn't accidentally succeed)

**Actions / prerequisites:**

- **`ActivatePermitAction`** in `src/actions/definitions/items.py` (subclass `Action`, key `"activate_permit"`, `execute()` dispatches to permit-activation service) — registered in `actions/registry.py`. Reference: `EquipAction` at `src/actions/definitions/items.py:20-64`.
- Permit-required validation in construction-wizard submission service (simpler than a generic `PermitRequired` prerequisite; can be promoted to a prerequisite later if other actions need permit-gating)

**UI (React, frontend):**

- Functionary interaction menu (generic — works for any FunctionaryRole)
- Construction wizard
- Permit-activation flow + site picker
- Room feature install wizard
- Ritual of Homecoming flow (with personalization-narrative text field)
- Thread weaving / sever UI
- "My Sanctums" view (personal + covenant + helper)
- Building manager actions (add/remove manager, snip threads — minimal surface)

**Tests:**

- Project lifecycle (cron tick + resolution + outcome tiers; both `SINGLE_THRESHOLD` and `TIERED_PERIOD` paths exercised)
- Permit issuance + activation + site validation
- Construction completion → Building materialization
- Sanctum install → Ritual of Homecoming → thread weaving → resonance generation
- Slot enforcement (cannot exceed 1 personal + 1 covenant; helper slots correctly tracked against broader thread cap)
- Permission gates (non-manager cannot install feature, non-member cannot weave into covenant Sanctum, etc.)
- Personal vs Covenant divergences (thread cap behavior, bonus distribution)
- #511 closes: ROOM thread anchor cap = Sanctum level

**Data seeding / dev environment:**

- House `BuildingKind` + scope configs
- Sanctum `RoomFeatureKind` + Ritual of Homecoming + Purging Ritual `Ritual` rows
- Builders Guild Clerk `FunctionaryRole` + option rows
- At least one ward with `permit_eligibility=OPEN` in the dev city
- At least one ward with `permit_eligibility=REPUTATION_GATED` for testing the negotiation path

### Out of Scope for Today

- Room Builder Tool (critical followup, NEXT phase)
- Any non-Sanctum room feature
- Any non-House building kind
- Subsystem G (Asset / Companion system — only the stub hook fires)
- Decay machinery
- Prestige / Opulence / Elegance stats
- Interior Design Project kind

---

## Spec Open Questions Flagged for Senior Dev Review

These were called out during brainstorming as worth revisiting:

1. **Cosmetic-vs-structural split in Room Builder Tool** (Section: Subsystem D, Critical Followup) — revisit when designing Room Builder Tool, not now.
2. **Covenant `base_resonance` cap formula** — interim formula provided (sum of active members' Path levels × 10); revisit once `Covenant.level` work in Slice D ships and the proper Covenant-level expression is available.
3. **Tuning numbers** (level multipliers, `K` constant, Purging Ritual cost multiplier, retention fraction, cron tick frequency) — initial values provided; balance pass during implementation.
4. **`OutcomeTier` representation choice** — reuse `CheckOutcome` model rows (more consistent with codebase) vs separate `ProjectOutcomeTier` TextChoices enum (cleaner per-tier dispatch). Recommendation: `CheckOutcome` rows. Implementation pass picks final.
5. **`SanctumThread` model strategy** — extend existing `Thread` with new `TargetKind.SANCTUM` + new typed FK, OR create a separate join model. Recommendation: extend `Thread` for consistency. Implementation pass picks final.

---

## Verification Findings (Post-Brainstorm Anti-Reinvention Audit)

This spec was revised after the brainstorming session via parallel Explore-agent verification against the actual codebase. The "Anti-Reinvention Pass — Verification Results" section near the top reflects those findings in detail. Summary of changes from the initial draft:

**Reuse confirmed (no spec changes needed beyond explicit references):**

- `Area`/`AreaLevel.BUILDING`, `RoomProfile.is_outdoor`, `AreaClosure`, all 9 `locations.services` helpers, `DiscriminatorMixin`, cron infrastructure (`world.game_clock.tasks`), decay pattern, `ActionPointPool`, `CurrencyBalance`, `CharacterXP.spend_xp`, `Covenant` + `CharacterCovenantRole`, `Thread`, `Ritual` (with `execution_kind` dispatch), `Resonance` + `Affinity` (model rows, not enums), `ResonanceGrant` (with rigid discriminator pattern), `perform_check`, `LegendEntry`/`LegendDeedStory`, `Distinction`, `ItemTemplate`/`ItemInstance`/`OwnershipEvent`/consumable pattern (`is_consumable`+`max_charges`+`charges`), `MissionGiverStanding` (schema template for `NPCStanding`).

**Corrections folded into the spec:**

1. `Persona.path_level` doesn't exist → use `get_character_path_level(character)` helper, traversing `persona → character_sheet → character`
2. `Ritual` has no role-gating field → handle Sanctum-owner gating at service-level validation, not as a Ritual model field
3. `grant_resonance` is explicit-kwarg signature → adding Sanctum support requires new typed FKs on `ResonanceGrant`, new `GainSource` enum values, new `CheckConstraint` rows, new optional kwargs
4. Codebase uses `CheckOutcome` model rows (open-ended `success_level: int`) instead of fixed-tier enums → spec offers two paths; recommendation is to reuse `CheckOutcome` rows
5. Achievements use `StatDefinition` + `StatTracker` (not `FactStat`) → reference corrected throughout
6. `BuildingPermitDetails` is `OneToOneField(ItemInstance)` mirroring `ItemFacet` composition, NOT a per-kind subclass
7. `ItemInstance.owner` is FK to `AccountDB` (not Persona) → permission gates traverse `account → active_persona` for persona-level identity
8. `Building` IS already an `Area` level (`AreaLevel.BUILDING = 10`) → spec uses `BuildingProfile` OneToOne extension, mirroring `RoomProfile`, NOT a "thin wrapper" model
9. No generic `use_item()` action exists → add `ActivatePermitAction` to Subsystem C deliverables
10. No item-as-permission prerequisite pattern exists → wire validation directly into construction-wizard submission service (simpler than building generic `PermitRequired` prerequisite)
11. `OwnershipEventType` enum needs `ACTIVATED` + `CONSUMED` values for permit activation auditability
12. `Covenant.level` is Slice D placeholder → use interim cap formula (sum of active members' Path levels × 10) until Slice D ships

**No-existing-duplication confirmed (clear to build new):**

- Project framework (entirely new)
- Ward permit rules (`WardBuildingRule` or equivalent — entirely new)
- `BuildingProfile` model (no existing Building/Construction/Property/Estate model)
- `FunctionaryRole` + `FunctionaryServiceOption` (missions use branching graphs, not menu-driven immediate-resolution)
- `ActivatePermitAction` + permit-activation service
- New ResonanceGrant `source_*` typed FKs (cross-cut migration)

---

## Coherence Pass Notes (Second Audit)

A second pass through the spec surfaced these clarifications and gaps. Each lands in the appropriate subsystem at implementation time; documented here as a checklist so they aren't lost.

### Covenant ownership of Buildings — RESOLVED

Senior dev decision (2026-05-31): **`Organization` gets a `kind` discriminator + per-kind details models** — the same pattern used by Projects, Buildings, Room Features. Covenant is one of those kinds (`kind=COVENANT`); Noble Houses, Trade Guilds, Criminal Gangs are future kinds following the same pattern. `LocationOwnership.holder_organization` works for all org types unchanged. Full details inline in Subsystem F — Data Layer.

Migration: add `Organization.kind` enum, migrate existing `Covenant` model to have `OneToOneField(Organization)` + auto-create backing Org on save, data migration backfills existing Covenant rows. Low risk since Organization infrastructure is currently empty and Covenant work is Slice A.

### `is_owner` cascades through org membership already (good news)

Per `world/locations/CLAUDE.md`: `is_owner(persona, room)` already returns True when the cascade-resolved owner is "an Organization this persona is a current member of (any rank)." This means our Subsystem E feature-install permission gate simplifies:

- **Originally specced:** `is_tenant(persona, room) OR persona in building.managers OR is_owner(persona, room)`
- **What's actually needed:** the three-way OR is still correct, because `is_owner` cascade covers (a) direct persona ownership and (b) org-membership-of-owning-org, but it does NOT cover the manager-tier role (managers are a building-level concept, not in LocationOwnership). So all three checks are independent and all three are needed.
- **For Covenant Sanctums specifically**, "active covenant member" via `CharacterCovenantRole.left_at IS NULL` is checked separately for the bonus-distribution rule, but the basic permission-to-weave gate is "the building is owned by a covenant you're a member of" — which `is_owner` handles for free once Covenant ownership works (per the architectural gap above).

### Account-level permits vs Persona-level Projects (resolution rule)

`ItemInstance.owner` is FK to `AccountDB`. `Project.owner_persona` is FK to `Persona`. When Bob activates a permit, we need to determine which Persona is initiating the construction Project. **Implementation rule: resolve via `account.active_persona` (or equivalent — verify the actual accessor during implementation)** at the moment of activation. The Project's `owner_persona` snapshots that resolution at creation. If the player switches personas mid-project, the Project's owner_persona stays bound to the original persona (they initiated; they own the project for outcome-roll purposes). For Building ownership at completion: same rule — the Project's owner_persona becomes the Building's owner via `LocationOwnership` (unless the wizard captured an explicit "owned by org X" override).

### Construction Project contributor permissions (default rule)

Spec was fuzzy on who can contribute to a `BUILDING_CONSTRUCTION` Project. **Default rule:** the Project's owner_persona, all `BuildingManager`-equivalents (during construction there's no Building yet, so this means whoever the owner explicitly invited in via a "co-builder" allowlist on `BuildingConstructionDetails`), and anyone with explicit invitation. For Sanctum's `ROOM_FEATURE_PROGRESSION` projects, contributors are scoped per Subsystem E (tenants/managers/owners of the target room). Add `co_contributor_personas` m2m to the per-kind details models when finer-grained invitation control is needed.

### Decay-in-progress Project handling

What happens to a `ROOM_FEATURE_PROGRESSION` Project on a room whose Building decays mid-progress? **Rule:** Building decay (entering `DECAYED` or `HIDDEN` state) cancels all active Projects targeting rooms in the building. Cancellation refunds partial contributions per the same per-tier outcome rules as a `FAILED` outcome (most-but-not-all returned). Same for active rituals (no Sanctum decay-mid-ritual edge cases since rituals are atomic, but document for sanity).

### No comprehensive "broader inactivity-cleanup" system exists today

Spec deferred Building decay timing to "broader player-inactivity rules." Verification found only narrow decay tasks (`cleanup_decayed_modifiers`, condition decay, form expiration) — there's **no comprehensive player-inactivity-detection system** yet. **Honest restatement:** Sanctum and Building decay are *parked* — the `decayed_state` field exists, the cron task scaffolding can be registered, but the *trigger* for "owner went inactive" is undefined until someone designs the inactivity system. Spec should NOT promise decay-on-inactive behavior in the MVP; the field exists as a hook for future work. **Update Section 5 Critical Followup list to add "inactivity-detection system design"** as a separate follow-up (alongside Room Builder Tool).

### `Persona.character_sheet` reverse-relation access pattern

Spec code samples reference `persona.character_sheet` traversal. Verify this is the actual accessor (probably FK from `Persona` to `CharacterSheet` with this name, but the implementer should confirm — could be `persona.sheet`, `persona.character_sheet`, `persona.character`, etc.). Pattern is sound; the attribute name needs verification at implementation time.

### Cron task `task_key` namespace

New cron tasks register with task_keys: `projects.lifecycle_tick`, `sanctum.resonance_generation_tick`. Verify no existing tasks use these keys. Lean toward dotted namespace per app (`projects.*`, `sanctum.*`) for clarity — matches existing patterns like `ap.daily_regen`, `locations.cleanup_decayed_modifiers`.

### Permit consumed item lifecycle

Spec uses the existing consumable pattern (`is_consumable=True`, `max_charges=1`, decrement to 0). After consumption, the permit item persists with `charges=0`. **Decision needed:** does the spent permit clutter the player's inventory forever, or is it auto-removed after activation? Lean toward auto-removal (`game_object.delete()` after `OwnershipEvent` of type `CONSUMED` is recorded — the OwnershipEvent ledger preserves the audit trail). Confirm with senior dev.

### "Pause" status for Projects

Project lifecycle currently has `PLANNING`, `ACTIVE`, `RESOLVING`, `COMPLETED`, `FAILED`. Decay-in-progress + manual pause scenarios suggest adding `CANCELLED` (and possibly `PAUSED`) status values. Adding `CANCELLED` is straightforward; `PAUSED` can be deferred until use case appears.

### Distinct `WardBuildingRule` model vs fields on `Area`

Subsystem C deferred this implementation choice. Reading existing `world/locations/CLAUDE.md` and seeing that `LocationValueModifier` is the established pattern for "this ward has property X" data, **probable best path:** model ward permit eligibility as `LocationValueModifier` rows with new `StatKey` values (`PERMIT_ELIGIBILITY`, `BUILD_COST_MULTIPLIER`) rather than a new dedicated model. This composes with the existing cascade resolver and reuses the existing `effective_value` read path. Implementer should evaluate vs a dedicated `WardBuildingRule` model and pick based on whether the data shape fits the cascade-modifier idiom.

### Building decay does NOT cascade-delete owned items / rooms

When a Building enters `DECAYED` or `HIDDEN` state, its rooms, owned items, occupant tenancies, etc. must NOT cascade-delete. The decay state is reversible. Implementation must use `decayed_state` as a read-side filter (decayed buildings hidden from default listings, exits hidden from grid) without touching the underlying data. Important to document in the spec to prevent over-zealous cleanup logic.
