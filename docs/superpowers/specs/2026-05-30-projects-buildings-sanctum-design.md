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

## Anti-Reinvention Pass (REQUIRED during implementation)

Per the project's `verify-against-code` skill — these MUST be verified against actual code before the implementation commits to a path. Docs (including this spec) are hints; existing code is the source of truth.

1. **`Covenant` model** — verify it exists, find its membership cap, find its active-member predicate, find how Path levels aggregate
2. **Existing thread-weaving infrastructure** — verify how threads are currently modeled and what the per-PC thread cap mechanism is; determine whether `SanctumThread` extends an existing model or creates a new one
3. **`Ritual` model** — verify how rituals are currently authored and how "requires sanctum owner" can be expressed (maybe via a ritual-meta extension, maybe via the existing `execution_kind` framework)
4. **`Persona.path_level`** (or equivalent) — verify this field exists and represents what we think (the PC's level in their Path); the homecoming cap depends on it
5. **`LocationOwnership` + `LocationTenancy` service helpers** — verify these cover the Sanctum permission gate cleanly (per the Explore agent's report, they should)
6. **`RoomProfile.is_outdoor`** (or equivalent) — verify the outer-grid-room flag for site validation
7. **`Area` extensibility** — verify whether ward-level permit flags can be added directly to `Area` or whether an extension model (`AreaPermitConfig` 1:1) is cleaner
8. **`world.missions/` NPC interaction overlap** — figure out whether mission NPC interactions become a *consumer* of subsystem B or whether B *absorbs* what missions has
9. **`ItemTemplate` / `ItemInstance`** patterns for the `BuildingPermit` kind
10. **`ResonanceGrant` + `GainSource`** enum — add new enum values cleanly, add `source_sanctum` / `source_project` typed FKs without breaking existing grants

---

## Subsystem A — Project Framework

### Purpose

A reusable framework for *delayed multi-tick investment with outcome rolls*. Any gameplay loop where players collectively pour AP/money/items/checks into an endeavor and get a tiered result at completion uses this. Construction is one consumer; many future consumers (cleanup, war funding, gang turf, etc.) hang off the same engine.

### Data Layer

**`Project`** — the runtime model. Common fields:

- `kind` — TextChoices discriminator (`BUILDING_CONSTRUCTION`, `ROOM_FEATURE_PROGRESSION`, plus deferred kinds)
- `completion_mode` — TextChoices (`SINGLE_THRESHOLD`, `TIERED_PERIOD`)
- `status` — TextChoices (`PLANNING`, `ACTIVE`, `RESOLVING`, `COMPLETED`, `FAILED`)
- `owner_persona` FK (the persona who initiated and is the "weighted check" source at resolution)
- `started_at`, `time_limit` (datetime — always set; both modes use it)
- `threshold_target` (int, nullable — only for `SINGLE_THRESHOLD`)
- `current_progress` (int, accumulates from contributions)
- `outcome_tier` (set at completion, nullable until then; `OutcomeTier` TextChoices: `CATASTROPHIC`, `FAILED`, `PARTIAL`, `SUCCESS`, `CRITICAL`)
- `resonance` FK (optional — references existing resonance type model; drives `ResonanceGrant` emission on contributions)
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

- `ResonanceGrant` (already in `magic.services.gain`) — add `GainSource.PROJECT_CONTRIBUTION` enum value + typed FK to source `Project`. Contributions to projects with a resonance set emit grants.
- `LegendEntry` + `LegendDeedStory` — same pattern as missions. Project completion with legend-worthy outcomes lets contributors author entries.
- `FactStat` (achievements) — aggregate "total AP contributed to projects," "projects completed at CRITICAL," etc. become natural achievement stats.
- `perform_check` — check contributions are stock perform_check calls.

### Today's Scope

Build the `Project` base model, the `Contribution` table, the cron lifecycle (supporting both `completion_mode`s from day one), the outcome-tier discriminator, AND the `BuildingConstructionDetails` + `RoomFeatureProgressionDetails` per-kind models. Other kinds get filed as issues — each ships its own per-kind details model + service hook when implemented.

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

- `ItemTemplate` / `ItemInstance` / `OwnershipEvent` (already in `world.items`) — the permit is just a new `ItemKind`. Inventory, ownership transfer, audit trail all reuse existing item infrastructure.
- `world.locations.services` — site validation uses `effective_owner(room)` and ward-cascade helpers to determine the ward of the activation point.
- Subsystem B's `FunctionaryServiceOption.effect_spec` — the "issue permit" effect calls a service that creates the `ItemInstance` with negotiated parameters.

### Today's Scope

- Add ward-level permit flags to the existing area/ward model
- Build `BuildingPermit` `ItemTemplate` + `BuildingPermitDetails`
- Implement `validate_permit_site` service function
- Implement permit-activation flow (use item → site validation → opens construction wizard)
- Builders Guild Clerk's permit-issuance options live in subsystem B; per-option effect specs that create permit `ItemInstance`s are wired here
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

**`Building`** lives as a thin wrapper around an existing `Area` (the locations hierarchy already has `Room → Building → Neighborhood → Ward → City → Region`; "Building" is an Area-tier in that hierarchy, not a brand-new model). Fields:

- `area` OneToOne to the underlying `Area` row
- `kind` FK to `BuildingKind`
- `scope` (IntegerChoices 1-5)
- `linked_outer_grid_room` FK (the outer-grid room from which entry exits lead in)
- `constructed_at` (datetime)
- `decayed_state` — TextChoices (`ACTIVE`, `DECAYED`, `HIDDEN`)

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

**`BuildingManager`** — m2m through-model between `Building` and `Persona`. Multiple managers per building allowed (permission tier). Fields:

- `building` FK
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

- `Building`, `BuildingKind`, `BuildingKindScopeConfig`, `BuildingManager` models
- House `BuildingKind` row with scope configs for tiers 1-5 (labels, room counts, cost multipliers)
- `BuildingConstructionDetails` Project payload model with `BUILDING_CONSTRUCTION` kind enum value
- Construction wizard UI (React)
- Room-generation service function (`GENERIC` strategy)
- Construction completion handler that materializes Building + Rooms + `LocationOwnership` + `BuildingManager` + entry exit
- `decayed_state` field on Building but **no decay machinery built** — that hooks into the broader inactivity system when it exists

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

1. Validate leader is a manager (Personal) or designated covenant manager (Covenant).
2. Validate `resonance_sacrificed` doesn't exceed leader's personal resonance pool.
3. Compute `base_resonance_gained = resonance_sacrificed / 100` (100:1 efficiency).
4. Compute current cap:
   - **Personal:** `cap = owner_persona.path_level * 10`
   - **Covenant:** anti-reinvention pass identifies the appropriate aggregate (likely something like `sum(member.path_level for member in active_members) * 10` or a covenant-level Path equivalent — deferred to spec writing once covenant model is verified)
5. Apply gain up to cap; any overflow goes to `pending_sacrifice_overflow` (held in escrow until cap rises).
6. Deduct `resonance_sacrificed` from leader's personal pool.
7. Update `last_homecoming_ritual_at`.
8. Emit a `LegendDeedStory`-style entry capturing the `narrative_text` the player wrote.
9. Periodic check (on next cron tick or owner level-up event): if `pending_sacrifice_overflow > 0` AND current cap > current `base_resonance + overflow_to_absorb`, absorb overflow up to new cap. Surfaces as a notification.

### Service: Purging Ritual

`world.magic.sanctum.services.perform_purging_ritual(sanctum, leader_persona, new_resonance_type, resonance_sacrificed)`:

1. Validate leader is a manager (Personal) or designated covenant manager (Covenant).
2. Validate this is a *different* resonance type from current (no-op purges rejected).
3. Cost is steep — `resonance_sacrificed >= sanctum.base_resonance * some_multiplier` (initial value 1×, tunable). Purging requires re-consecrating the entire imbued resonance.
4. Validate cost is paid (from leader's personal pool).
5. Atomically: change `resonance_type` to `new_resonance_type`; **all `SanctumThread` rows attached to this Sanctum have their effective resonance type recomputed** (the thread adopts the room's new type).
6. Drain some fraction of `base_resonance` (purging is destructive — initial value: 50% retained, tunable).
7. Update `last_purging_ritual_at`.
8. Emit Legend entries for the leader AND all woven thread holders.
9. Broadcast a system notification to all woven thread holders ("Your thread in [Sanctum] has been re-consecrated to [new type]").

### Resonance Generation Cron Tick

A scheduled task per cron tick (frequency tunable — likely hourly or per-IC-day) iterates `RoomFeatureInstance` rows where `feature_kind=SANCTUM`:

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

    # Independent draw per weaver
    for thread in threads:
        income = thread.thread_strength * pool_per_thread
        grant_resonance(
            target=thread.weaver_persona,
            amount=income,
            resonance_type=sanctum.resonance_type,
            source=GainSource.SANCTUM_WEAVING,
            source_sanctum=sanctum,
        )

    # Owner bonus
    if sanctum.owner_mode == PERSONAL:
        bonus_recipients = [
            t.weaver_persona for t in threads
            if t.weaver_persona in sanctum.building.managers
        ]
    else:  # COVENANT
        bonus_recipients = [
            t.weaver_persona for t in threads
            if covenant.is_active_member(t.weaver_persona)
        ]

    other_threads_count = len(threads) - 1
    for recipient in bonus_recipients:
        # +1 per other thread (not counting their own)
        grant_resonance(
            target=recipient,
            amount=other_threads_count,
            resonance_type=sanctum.resonance_type,
            source=GainSource.SANCTUM_OWNER_BONUS,
            source_sanctum=sanctum,
        )
```

Level multipliers and `K` are tunable. The shape is locked.

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

### Integration with Existing Systems (REQUIRES Anti-Reinvention Pass)

- **`Covenant` model** — verify it exists, find its membership cap, find its active-member predicate, find how Path levels aggregate
- **Existing thread-weaving infrastructure** — verify how threads are currently modeled and what the per-PC thread cap mechanism is
- **`Ritual` model** — verify how rituals are currently authored and how "requires sanctum owner" can be expressed
- **`ResonanceGrant`** + `magic.services.gain.grant_resonance` — add `GainSource.SANCTUM_WEAVING` and `SANCTUM_OWNER_BONUS` enum values; add `source_sanctum` typed FK
- **`Persona.path_level`** (or equivalent) — verify this field exists and represents the PC's level in their Path
- **`LegendEntry` / `LegendDeedStory`** — used for the homecoming personalization narratives and purging notifications

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
- `BuildingKind` + `BuildingKindScopeConfig` + House row (subsystem D)
- `Building` (thin wrapper over `Area`) + `BuildingManager` through-model (subsystem D)
- Ward-level permit flags added to existing `Area` / area-extension model (subsystem C)
- `BuildingPermit` `ItemTemplate` kind + `BuildingPermitDetails` (subsystem C)
- `FunctionaryRole` + `FunctionaryServiceOption` + `OptionRequirement` + `NPCStanding` (subsystem B)
- Builders Guild Clerk `FunctionaryRole` row + permit-issuance option rows (B + C wiring)
- `RoomFeatureKind` + `RoomFeatureInstance` (subsystem E)
- Sanctum `RoomFeatureKind` row (E + F wiring)
- `SanctumDetails` + `SanctumThread` (subsystem F)
- Ritual of Homecoming + Purging Ritual `Ritual` rows (subsystem F)
- `GainSource.SANCTUM_WEAVING`, `GainSource.SANCTUM_OWNER_BONUS`, `GainSource.PROJECT_CONTRIBUTION` enum values + `source_sanctum` / `source_project` typed FKs added to `ResonanceGrant` (cross-cut)

**Service functions:**

- Project cron-tick scanner + lifecycle resolver (subsystem A)
- Per-kind outcome handlers for `BUILDING_CONSTRUCTION` and `ROOM_FEATURE_PROGRESSION`
- `validate_permit_site` (subsystem C)
- Construction wizard submission service (subsystem D)
- Room generation service (`GENERIC` strategy — linear chain placeholder)
- Sanctum progression handler (`world.magic.sanctum.services.handle_progression`)
- Ritual of Homecoming service (`perform_homecoming_ritual`)
- Purging Ritual service (`perform_purging_ritual`)
- Sanctum resonance generation cron tick
- Thread weave / sever services with slot enforcement
- Stubs for all other Project kinds, FunctionaryRoles, RoomFeatureKinds (raise `NotImplementedError` so dispatcher exists but doesn't accidentally succeed)

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
2. **Covenant `base_resonance` cap formula** — pick exact formula once `Covenant` model is verified during anti-reinvention pass.
3. **Tuning numbers** (level multipliers, `K` constant, Purging Ritual cost multiplier, retention fraction, cron tick frequency) — initial values provided; balance pass during implementation.
