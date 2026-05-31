# Covenants Slice A — Entity & Membership

**Date:** 2026-05-09
**Status:** Draft (post-brainstorm; awaiting spec review)
**Branch:** TBD (e.g. `covenants-slice-a-entity`)
**Related:**
- `docs/roadmap/covenants.md` — domain roadmap; this spec implements the foundational missing skeleton
- `docs/superpowers/specs/2026-04-26-items-fashion-mantles-spec-d-design.md` — Spec D, which shipped the role/gear/Thread integration this spec builds on
- `src/world/covenants/models.py` — `CovenantRole`, `GearArchetypeCompatibility`, `CharacterCovenantRole` (existing)
- `src/world/magic/services/threads.py:97-141` — `compute_anchor_cap` (the COVENANT_ROLE arm we're un-placeholdering)
- `src/world/magic/models/threads.py:266-541` — `Thread` + COVENANT_ROLE constraints (the existing role-mastery axis; not modified)

---

## Goal

Land the foundational Covenant entity and bind existing per-character role assignments to it. The role mechanics that shipped with Spec D (gear compatibility, COVENANT_ROLE Thread anchor, combat speed) currently work against a phantom: characters hold roles in isolation, with no covenant containing them. Slice A creates the entity, attaches every active and historical role assignment to a covenant, and replaces the placeholder Thread anchor cap formula that has been waiting for this work to land.

This is the first slice of a multi-slice Covenants buildout. Subsequent slices (formation ritual, sworn objective progression, Battle covenant stacking, group abilities, use-based weave gating) build on top of A.

## Background

### What exists today

- **`CovenantRole`** (lookup, SharedMemoryModel) — staff-authored, scoped by `covenant_type`, includes `archetype` and `speed_rank`. Combat reads `speed_rank` directly. (`src/world/covenants/models.py:16-61`)
- **`GearArchetypeCompatibility`** (existence-only join) — `CovenantRole × GearArchetype`. Drives gear-bonus stacking math (Spec D §4.4). (`src/world/covenants/models.py:64-90`)
- **`CharacterCovenantRole`** (per-character assignment) — `character_sheet`, `covenant_role`, `joined_at`, `left_at`. Partial unique constraint: at most one active assignment per `(character_sheet, covenant_role)`. Consumed by combat (resolution speed), magic (`has_ever_held` weave gate, anchor cap formula), modifier pipeline. (`src/world/covenants/models.py:93-124`)
- **`Thread` with `target_kind=COVENANT_ROLE`** (`src/world/magic/models/threads.py:266-541`) — the existing role-mastery axis. Has `level`, `developed_points`, `ThreadLevelUnlock` per-boundary XP receipts, `ThreadPullEffect` rows that can grant capabilities (`effect_kind=CAPABILITY_GRANT`) at level thresholds, partial unique constraint enforcing one active Thread per `(owner, covenant_role)`.
- **Anchor cap formula** (`src/world/magic/services/threads.py:136-137`):

  ```python
  case TargetKind.COVENANT_ROLE:
      return thread.owner.current_level * 10
  ```

  Today it reads the character's authored level — a placeholder explicitly flagged in `docs/roadmap/covenants.md` ("`current_level` is a placeholder until the Covenant entity ships with its own progression").

### What's missing

The `Covenant` entity itself. There is no model for "the social/magical structure that contains members and a sworn objective." Every consumer of role assignments today implicitly treats the role as floating. The roadmap calls out ~11 sub-areas of work needed to deliver covenants as a full system; this spec lands the foundational subset.

### Slice decomposition (this spec is Slice A)

The full Covenants buildout breaks into independent slices. Each gets its own design+plan+implementation cycle. **This spec covers Slice A only**; the rest are listed for context so future-me knows where related work belongs.

| Slice | Scope | Status |
|---|---|---|
| **A** | **Covenant entity + membership FK + engagement context + anchor cap un-placeholder + COVENANT_ROLE pull gating + bundled bug fixes** | **This spec** |
| B | Formation ritual + member lifecycle (invite/accept/leave/kick) + dissolution paths + scene/mission engagement triggers + UI for engage/disengage | Future |
| C | Sworn Objective model + Stories/Missions integration | Future |
| D | Covenant-level XP/progression, group-ability unlocks, sub-role unlocks | Future |
| E | Battle Covenants + Durance × Battle stacking rules | Future |
| F | Group Abilities (techniques/rituals gated by ≥N members present) | Future |
| G | Use-based weave gate & anchor cap for COVENANT_ROLE Threads | Future (see §3.5) |
| H | Thread situational gating for non-COVENANT_ROLE kinds (Relationship/Facet "in action" tightening) | Future (see §3.6 — broader principle, project-wide) |

Note: an earlier slice "D2: Role Mastery Progression" was considered and **dropped** during brainstorming. The existing `Thread` machinery (level + level-gated unlocks + per-resonance pull effects + `CAPABILITY_GRANT` effect kind) is the role-mastery axis. No new `CharacterCovenantRoleProgression` model is needed; Slice F (and any deeper authoring work) supplies the content.

---

## Architecture decisions

These are the design points fixed during the Slice A brainstorm. They affect Slice A directly but also constrain later slices, so they are stated here as durable design intent.

### 3.1 Covenant memberships are non-exclusive

**A character can be an active member of multiple covenants simultaneously, including multiple Durance covenants.** This is a deliberate design call to make the social structure resilient to varying player activity levels — active players naturally support multiple groups as "primary" members in some, "supporting" members in others.

Implications:
- The active-membership uniqueness constraint is `(character, covenant) WHERE left_at IS NULL` — at most one active role per character per covenant. **Not** `(character, covenant_type)`. **Not** `(character, role)`.
- "Primary covenant" is a **future** player-declared designation (a boolean on membership with a partial unique, or an FK on CharacterSheet). Not in this slice. Do not conflate "primary covenant" with membership uniqueness.
- The roadmap (`docs/roadmap/covenants.md`) currently implies one foundational Durance covenant per character ("Long-lived, deeply personal, built around relationship bonds"). The roadmap update accompanying this spec must surface non-exclusive membership explicitly.

### 3.2 `CharacterCovenantRole` is the membership table

Adding a new `CovenantMembership` model alongside `CharacterCovenantRole` was considered and rejected: it would create two tables that must stay in sync (creating membership writes both rows) — the kind of denormalization CLAUDE.md explicitly warns against. The existing model is already shaped like a membership row: it has start/end times, a role attached, a partial-active constraint. Adding a `covenant` FK extends it to "which covenant did the character hold which role in, when?"

Replacing `CharacterCovenantRole` with a renamed `CovenantMembership` was also considered and rejected: the rename is rename-for-rename's-sake and forces every consumer (combat speed lookup, Thread weave gate, modifier pipeline) to update. The semantic doesn't change — just the schema gains a covenant FK.

### 3.3 Active-uniqueness constraint shifts from role to covenant

Today: `UniqueConstraint(fields=["character_sheet", "covenant_role"], condition=Q(left_at__isnull=True))`.

Slice A: `UniqueConstraint(fields=["character_sheet", "covenant"], condition=Q(left_at__isnull=True))`.

The new constraint correctly enforces "one active role per character per covenant" while permitting the same role to be active across multiple covenants (Vanguard of Covenant Alpha + Vanguard of Covenant Beta is fine — they're different memberships).

`has_ever_held(role)` continues to work — it queries all-time rows for `(character, role)` regardless of covenant, so its semantics are unchanged.

### 3.4 Role-mastery is `Thread`, not a new progression axis

`Thread` with `target_kind=COVENANT_ROLE` already provides:

- `level` (multiples of 10) — what "level up the role" means
- `developed_points` filled via the Imbuing ritual (which spends Resonance) — primary growth currency
- `ThreadLevelUnlock` per-boundary XP receipts — XP cost at level boundaries (mirrors skill XP locks)
- `ThreadPullEffect` keyed by `(target_kind, resonance, tier, min_thread_level)` — graduated bonuses at level thresholds
- `effect_kind=CAPABILITY_GRANT` with FK to `CapabilityType` — Threads literally grant capabilities at level
- One active Thread per `(owner, covenant_role)` — character-level (not covenant-level) progression

**Per-Resonance specialization is the intended authoring approach.** Two characters who hold the same `CovenantRole` but anchor their Threads with different Resonances will unlock different capabilities as their Threads grow. This is emergent specialization driven by the magical-identity layer, not a new dimension of authored content. Slice F (Group Abilities) and any future "covenant role authoring" content task will produce rich `ThreadPullEffect` catalogs keyed per `(role, resonance)`.

This decision means **Slice A does not introduce a new role-progression model**. The "level up the covenant role" mechanic is the existing Thread on COVENANT_ROLE. Authoring content (which capability unlocks at which Thread level, per resonance) is content work, not Slice A schema.

**COVENANT_ROLE Threads are situational** (per §3.6) — pull effects fire only when the character is engaged with a covenant where they hold the anchored role. The persistent character power (Thread level, developed_points, anchor cap) survives engagement changes; the runtime payoff (pull effects) is gated by engagement. This gating is implemented in Slice A (§4.7).

### 3.5 Anchor cap formula change is the minimal un-placeholder

Today the COVENANT_ROLE anchor cap reads `thread.owner.current_level * 10` — explicitly a placeholder per the roadmap. Slice A replaces it with a formula that reads from covenant level via the membership table.

With non-exclusive memberships, a character may hold the role in multiple covenants. The Slice A formula uses **the maximum covenant level among any of the character's `CharacterCovenantRole` rows for this role** (active or historical). This:

- Is a strict improvement over the placeholder
- Naturally scales when Slice D adds covenant XP
- Doesn't punish characters for leaving covenants (Threads don't lose their cap when the character ends a membership — historical association still counts)

Use-based gating (Tehom's "force people to actually use the role before they could weave threads into it") and use-based capping (legend earned in role / time held in role / etc.) are **explicitly future work**. They form Slice G in the decomposition. Slice A only does the placeholder removal; Slice G layers richer signal on top.

### 3.6 Role bonuses gate on engaged covenant context

**A character's role bonuses apply only when the character is "engaged with" the covenant where they hold the role.** Solo activity, or activity with a *different* covenant of the same type, does not grant role bonuses. Tehom's framing: *"You'd only be doing things with one covenant at a time, even if you have roles with other covenants."* — qualified by *"you can be engaged both with a single normal covenant -and- a battle covenant: those sorts of roles stack."*

This is a runtime context concept distinct from membership, and it is **scoped per covenant type**:

- **Membership** (`CharacterCovenantRole` row): persistent, non-exclusive — a character can hold roles in many covenants simultaneously, including multiple of the same type.
- **Engagement** (`CharacterCovenantRole.engaged` boolean): runtime, **at most one engaged active row per (character, covenant_type)**. The flag lives on the membership row, not on `CharacterSheet`. Today's two types (`DURANCE`, `BATTLE`) mean a character can have at most one engaged Durance membership AND at most one engaged Battle membership **simultaneously**. Default: `False`. New covenant types automatically inherit this shape — no schema migration needed when a third type lands.
- **Stacking is additive.** When a character has engaged memberships in both a Durance and a Battle covenant, both roles' bonuses apply additively to the modifier pipeline. Both roles' Threads can be pulled (per §4.7). Combat speed_rank is NOT subject to additive stacking — speed is a single number per encounter, set explicitly via `CombatParticipant.covenant_role` at combat setup; Slice E (Battle Covenants + stacking rules) decides combat-side precedence (likely Battle takes precedence in war contexts per the roadmap).
- **Schema rationale.** An earlier draft put two FKs on `CharacterSheet` (`engaged_durance_covenant`, `engaged_battle_covenant`); rejected because it spreads engagement state across N fields and forces a schema change for every new covenant type. A through-model with denormalized `covenant_type` was also rejected because the denormalization is exactly the "cached copy of a related field" pattern CLAUDE.md warns against. Boolean-on-membership consolidates engagement into the row that already has all the relevant context (membership existence, role, covenant, joined/left timestamps).
- **Constraint enforcement is service-side + `clean()`-side.** The "at most one engaged active row per (character, covenant_type)" invariant cannot be enforced via a partial unique constraint at the DB level — Postgres partial indexes can't reference joined-table columns (`covenant.covenant_type` lives on the related Covenant row). Slice A enforces the invariant via two layers:
  - **Service layer:** `set_engaged_membership` atomically un-engages any same-type row before engaging the new one. This is the only legitimate mutation path.
  - **`clean()` validation on `CharacterCovenantRole`:** rejects a row with `engaged=True AND left_at IS NOT NULL`; rejects a row with `engaged=True` if another engaged active row of the same covenant_type exists for the same character.

  No DB-level CHECK or partial unique. The service is the contracted single source of truth; `clean()` is the safety net for non-service mutation paths (admin forms, ad-hoc serializer use, etc.).

#### Surfaces affected by engagement

| Surface | Slice A change | Engagement check |
|---|---|---|
| Modifier pipeline (`covenant_role_bonus` in `world/mechanics/services.py:310`) | Refactored to iterate `currently_engaged_roles()` and SUM bonuses across engaged roles (additive stacking) | Iterates engaged-flagged rows |
| Gear compatibility (`is_gear_compatible(role, archetype)`) | Function signature unchanged; callers iterate engaged roles when they need stacking | Caller-driven |
| Combat speed_rank | Already encounter-scoped via `CombatParticipant.covenant_role` (set when joining combat); no change needed. Slice E decides combat-side precedence between Durance and Battle for war contexts | Already explicit |
| Thread pull eligibility (`_anchor_in_action` in `world/magic/services/resonance.py:282`) | Remove COVENANT_ROLE from `_ALWAYS_IN_ACTION_KINDS`; add explicit engagement check arm — pull allowed if **any** engaged membership row matches the Thread's anchored role | Explicit (new arm; ANY-match) |
| Thread anchor cap (`compute_anchor_cap` COVENANT_ROLE arm) | **No change** — Thread caps are persistent character properties, not active bonuses; max-across-covenants per §3.5 | None |
| Thread weave gate (`has_ever_held(role)`) | **No change** — weave gate is eligibility/permission (have you ever held the role), not a runtime bonus | None |
| Tier 0 passive Thread effects on COVENANT_ROLE | Out of scope for Slice A — implementation site for passive effect application requires investigation; gating wires up in whichever slice formalizes the application surface | TBD |

#### General principle: Threads are situational

Tehom's framing extends to all Threads: *"Threads are intended to be situational. A thread to a skill only works when you're using the skill, and this is a thread to your covenant role. If you're not fulfilling the role, you don't use it."* Today the pull pipeline implements this for `TRAIT`, `TECHNIQUE`, and `ROOM` Threads via `ctx.involved_*` tuples; for `RELATIONSHIP_TRACK` / `RELATIONSHIP_CAPSTONE` / `FACET` / `COVENANT_ROLE` it currently bypasses the check by classifying them as always-in-action.

**Slice A only fixes COVENANT_ROLE.** Bringing the other "always in-action" kinds into a stricter situational model is project-wide design work that belongs in its own slice (post-Covenants). The general principle is captured here so it doesn't get lost; the implementation expands when that slice lands.

#### Engagement lifecycle

- **Set:** `set_engaged_membership(membership)` — atomic side-effect on a pre-validated membership row. Un-engages any other engaged active membership of the same `covenant_type` for the character that owns this row; sets `membership.engaged = True`. Same-type stacking constraint is naturally enforced by the `covenant_type` filter on the un-engage step. Cross-type engagements are independent (engaging a Battle membership does NOT touch the Durance engagement and vice versa). Pre-conditions (membership not ended, covenant not dissolved, caller owns the character) are the serializer's responsibility — see §4.4 serializer-responsibilities table.
- **Clear:** `clear_engaged_membership(membership)` — sets `membership.engaged = False`. Idempotent.
- **Clear by type:** `clear_engaged_for_type(character_sheet, covenant_type)` — convenience for "stand down from all Durance engagements" or all Battle engagements; un-engages every engaged active row of the specified type for that character.
- **Auto-clear in Slice A:**
  - `dissolve_covenant(covenant)` un-engages every membership in that covenant (sets `engaged=False`) before/along with setting their `left_at`.
  - `end_covenant_role(membership)` un-engages the row before/along with setting `left_at`. The "if character has no other active membership in that covenant" check is no longer relevant — engagement is per-row, not per-covenant.
- **Auto-set / scene-context detection / mission-driven engagement / UI:** out of scope for Slice A — Slice B and beyond.

The default for every membership row is `engaged=False`. The migration adding the field initializes every existing row to `False`. Characters opt in via explicit `set_engaged_membership` calls (or get opted in by Slice B's lifecycle services) when those exist.

### 3.7 Bundled scope: two unrelated bug fixes

Per `feedback_expand_scope_when_diff_is_tiny.md` (updated with project-specific context that Tehom self-reviews and there is no second reviewer), two unrelated deferred bug fixes ride along in this PR. Both are small, both have memory entries describing the deferral, and both are independent of covenant work but cheap to land alongside it:

- **TreatmentAttempt unique constraint** — tighten via denormalized `once_per_scene_guard` boolean. (§4.10)
- **`perform_anima_ritual` budget overspend** — tighten loop guard from `budget > 0` to `budget >= cost_per_point`. (§4.11)

Bundling unrelated work is acceptable in this project specifically because Tehom is the de-facto reviewer and there is no second-reviewer overhead to amortize. This bundling exception is captured in `feedback_expand_scope_when_diff_is_tiny.md`.

---

## In scope

### 4.1 New `Covenant` model

Lives in `src/world/covenants/models.py`. Inherits `SharedMemoryModel` per project convention.

```python
class Covenant(SharedMemoryModel):
    """The foundational social/magical structure that binds members under a sworn oath.

    Slice A scope: identity, type, level (placeholder until Slice D), formed/dissolved
    timestamps, free-text sworn objective.

    Deferred fields (future slices):
    - durance_focus_FK / battle_encounter_FK — Slice E (type-specific data)
    - structured sworn_objective_FK → SwornObjective — Slice C (replaces TextField)
    - xp, milestone progression fields — Slice D
    - description, crest, motto, cosmetic fields — post-MVP polish
    - dissolution_reason, dissolution_kind — Slice B
    """

    name = CharField(max_length=120)
    covenant_type = CharField(max_length=20, choices=CovenantType.choices, default=CovenantType.DURANCE)
    level = PositiveIntegerField(default=1, help_text="Group progression tier (Slice D will drive growth).")
    sworn_objective = TextField(blank=False, help_text="Free text in Slice A; structured in Slice C.")
    formed_at = DateTimeField(auto_now_add=True)
    dissolved_at = DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        state = "active" if self.dissolved_at is None else "dissolved"
        return f"{self.name} ({self.get_covenant_type_display()}, {state})"
```

No `Meta.ordering` (per project convention; ViewSets paginate with explicit `.order_by`). No `is_active` boolean — `dissolved_at IS NULL` is the active predicate. The deferred-fields list in the docstring is a deliberate signal that the model is not "complete" — future slices add to it rather than creating sibling models.

### 4.2 `CharacterCovenantRole` extension

Two changes:

1. **Add `covenant` FK** with `on_delete=PROTECT` (matches the PROTECT on `covenant_role`):

   ```python
   covenant = models.ForeignKey(
       "covenants.Covenant",
       on_delete=models.PROTECT,
       related_name="memberships",
   )
   ```

2. **Replace the active-uniqueness constraint** in `Meta.constraints`:

   ```python
   # Remove:
   # UniqueConstraint(fields=["character_sheet", "covenant_role"],
   #                  condition=Q(left_at__isnull=True),
   #                  name="covenants_one_active_role_assignment")

   # Add:
   UniqueConstraint(
       fields=["character_sheet", "covenant"],
       condition=Q(left_at__isnull=True),
       name="covenants_one_active_role_per_covenant",
   )
   ```

The model docstring is updated to describe the new shape (one active role per character per covenant; same role permitted across covenants; full role history preserved as a sequence of rows).

### 4.3 Engaged flag on `CharacterCovenantRole`

Add a single boolean field to `CharacterCovenantRole` (`src/world/covenants/models.py`):

```python
engaged = models.BooleanField(
    default=False,
    help_text=(
        "True when the character is currently 'fulfilling' this role for this "
        "covenant. At most one engaged active row per (character_sheet, "
        "covenant.covenant_type) — service-enforced + clean()-enforced. "
        "Drives role bonuses (modifier pipeline) and COVENANT_ROLE Thread pull "
        "eligibility. See spec 2026-05-09 §3.6."
    ),
)
```

No DB-level constraint on the engagement invariant — see §3.6 for why a partial unique referencing `covenant.covenant_type` cannot be authored in Postgres without denormalizing the type onto this row, which CLAUDE.md's "avoid denormalization" rule rules out.

#### `clean()` validation on `CharacterCovenantRole`

The model's `clean()` method enforces the invariant for any non-service mutation path (admin, ad-hoc serializer use, raw `.save()` calls):

```python
def clean(self) -> None:
    super().clean()
    if self.engaged and self.left_at is not None:
        raise ValidationError({"engaged": "Engaged row cannot have left_at set."})
    if self.engaged:
        # At most one engaged active row per (character, covenant_type).
        same_type_engaged = (
            CharacterCovenantRole.objects
            .filter(
                character_sheet=self.character_sheet,
                covenant__covenant_type=self.covenant.covenant_type,
                engaged=True,
                left_at__isnull=True,
            )
            .exclude(pk=self.pk)  # On insert, self.pk is None; exclude(pk=None) is a no-op (correct: unsaved row isn't in the DB to collide with)
            .exists()
        )
        if same_type_engaged:
            raise ValidationError({
                "engaged": (
                    "Another engaged active membership of the same covenant type "
                    "exists for this character."
                ),
            })
```

The service layer (§4.4) follows the same invariant by atomically un-engaging any same-type row before engaging a new one, so service callers never see this `clean()` raise.

#### Migration impact

Adds one BooleanField. Default `False`. Migration initializes every existing `CharacterCovenantRole` row to `engaged=False`. No `CharacterSheet` migration; no cross-app dependency.

#### Why this shape (vs. earlier drafts)

An earlier spec draft proposed two FKs on `CharacterSheet` (`engaged_durance_covenant` + `engaged_battle_covenant`), one per covenant type. Rejected because:

- Spreads engagement state across N fields, where N = number of covenant types
- Forces a schema migration each time a new covenant type is added
- Engagement is conceptually a property of the membership ("this membership is what I'm currently fulfilling"), not of the character ("this is the covenant I'm operating with")
- Two-FK shape forces the handler to look up by FK rather than reading a flag that's already on the rows it iterates

A through-model (`CharacterEngagement`) with a denormalized `covenant_type` was also considered — rejected because the denormalization is exactly the "cached copy of a related field" pattern CLAUDE.md warns against.

The boolean-on-membership shape is the most consolidated; the only cost is service-layer enforcement of the type uniqueness instead of DB-level enforcement, which is acceptable in this codebase where the service path is the documented single source of mutation.

### 4.4 Service surface

`src/world/covenants/services.py` gains the operations below. Per project convention (`URL → View → Serializer → Service`), these services perform atomic side-effects on **already-validated** data. Validation of user-input concerns (covenant not dissolved, role type matches covenant type, membership not already ended, etc.) is the responsibility of serializers — not these services. Slice A ships no API surface for write operations (full Covenant CRUD lands in Slice B), so for now the only callers are tests, which pass valid data directly. When Slice B adds the API, a serializer is added per operation that validates first, then calls the relevant service.

#### Covenant lifecycle services

- **`create_covenant(*, name, covenant_type, sworn_objective, founder_character_sheet, founder_role) -> Covenant`** — atomic. Creates the Covenant row, then creates the founder's `CharacterCovenantRole` row in the same transaction. Invalidates the founder's `covenant_roles` handler cache.
- **`add_member(*, covenant, character_sheet, role) -> CharacterCovenantRole`** — atomic. Creates a new active membership. Invalidates handler cache. The active-uniqueness DB constraint (`covenants_one_active_role_per_covenant`) raises `IntegrityError` if a duplicate active row would result; the serializer is responsible for catching this case before calling the service.
- **`change_role(*, membership, new_role) -> CharacterCovenantRole`** — atomic. Sets `left_at` (and `engaged=False`, see below) on the existing membership, creates a new active membership in the same covenant with `new_role`. Returns the new row. Invalidates handler cache.
- **`dissolve_covenant(*, covenant) -> None`** — atomic. For every active membership of the covenant: sets `engaged = False` and `left_at = now()`. Sets `covenant.dissolved_at = now()`. Invalidates handler cache for every affected character. Idempotent (calling on an already-dissolved covenant is a no-op; the serializer checks state and skips the call, but the service is also defensively idempotent because the same atomic transaction can be safely retried).

The existing `assign_covenant_role` and `end_covenant_role` services are **kept and updated** to require a `covenant` argument. Callers in tests/factories need updating; this is the bulk of the migration churn.

`end_covenant_role(*, assignment) -> None` gains an un-engage step: before setting `left_at`, sets `engaged = False` on the row. This keeps the row coherent with the model invariant (engaged rows must have `left_at IS NULL`). The step is unconditional — setting `engaged=False` on a row that's already non-engaged is a no-op write.

#### Engagement services

- **`set_engaged_membership(*, membership) -> None`** — atomic. Signature takes the membership instance only — `membership.character_sheet` and `membership.covenant.covenant_type` are derived from the row. Operation:
  1. Un-engages every other active membership of the same `covenant.covenant_type` for `membership.character_sheet`: `CharacterCovenantRole.objects.filter(character_sheet=membership.character_sheet, covenant__covenant_type=membership.covenant.covenant_type, engaged=True, left_at__isnull=True).exclude(pk=membership.pk).update(engaged=False)`.
  2. Sets `membership.engaged = True` and saves (`update_fields=["engaged"]`).
  3. Invalidates the character's `covenant_roles` handler cache.

  Both UPDATEs run in the same `@transaction.atomic` block. Engaging a Battle membership doesn't touch Durance memberships and vice versa — the type-scoped invariant is naturally enforced by the `covenant__covenant_type` filter in step 1.
- **`clear_engaged_membership(*, membership) -> None`** — atomic. Sets `membership.engaged = False` and saves. Invalidates the character's `covenant_roles` handler cache.
- **`clear_engaged_for_type(*, character_sheet, covenant_type) -> None`** — atomic. `CharacterCovenantRole.objects.filter(character_sheet=character_sheet, covenant__covenant_type=covenant_type, engaged=True, left_at__isnull=True).update(engaged=False)`. Invalidates handler cache.

All three operations are write-idempotent at the per-row level (re-engaging an already-engaged row is a no-op write; clearing an already-cleared row is a no-op).

These services emit no events in Slice A. Slice B may layer scene/mission triggers on top.

#### Serializer responsibilities (deferred to Slice B's API)

When Slice B adds the API surface, each operation gets a serializer that validates the user-input concerns the services do not check:

| Service | Serializer-side validations |
|---|---|
| `create_covenant` | `founder_role.covenant_type == covenant_type`; founder is a valid character; `name` non-empty; `sworn_objective` non-empty |
| `add_member` | `role.covenant_type == covenant.covenant_type`; `covenant.dissolved_at is None`; character is a valid character; (DB constraint backstops same-character-same-covenant active duplicate) |
| `change_role` | `new_role.covenant_type == membership.covenant.covenant_type`; `membership.left_at is None`; user has authority to change roles in this covenant (Slice B permission concern) |
| `dissolve_covenant` | `covenant.dissolved_at is None`; user has authority to dissolve (Slice B permission concern) |
| `set_engaged_membership` | `membership.left_at is None`; `membership.covenant.dissolved_at is None`; the requesting user owns the character whose membership it is |
| `clear_engaged_membership` | the requesting user owns the character |
| `clear_engaged_for_type` | the requesting user owns the character |

The Slice A spec doesn't ship these serializers (no write API in Slice A); this table documents intent so Slice B picks it up cleanly.

### 4.5 Handler updates

`src/world/covenants/handlers.py` (`CharacterCovenantRoleHandler`) gains and modifies methods:

#### New: `max_covenant_level_for_role(role)`

Used by `compute_anchor_cap`. Returns the maximum `covenant.level` among the character's all-time `CharacterCovenantRole` rows for this `role` (active or historical). Returns `0` if the character has no rows for the role (shouldn't happen if `has_ever_held` was the gate, but a defensive `0` keeps the formula stable).

#### New: `currently_held_role_in(covenant)`

Returns the `CovenantRole` the character actively holds in the specified `covenant`, or `None` if they have no active membership there. Available for any Slice A or future consumer that needs per-covenant role lookup. Note: this method does NOT consider the `engaged` flag — it returns the active role regardless of engagement, which is what gear-bonus / speed-rank consumers care about when they already know which covenant context they're in (e.g., combat encounter setup).

#### Replaced: `currently_held()` → `currently_engaged_roles()` (iterable; supports stacking)

Today `currently_held()` returns "any active role" — the first active row encountered, single-result. Per §3.6, engagement is type-scoped and bonuses stack additively, so a single character can have multiple "currently engaged" roles (one per engaged covenant type). Returning a single role can no longer represent the truth.

**`currently_held()` is removed** from the handler. Per `feedback_explicit_naming_over_migration.md`, renaming a misleading symbol beats preserving callers; the removal forces every consumer to acknowledge the multi-role reality. The new method is named `currently_engaged_roles()` (not `currently_held_roles()`) because the semantic is specifically "roles you are currently *fulfilling*," not "roles you are currently a member in" — the latter would naturally mean every active membership, regardless of engagement.

```python
def currently_engaged_roles(self) -> list[CovenantRole]:
    """Return CovenantRoles for every membership row where engaged=True and left_at IS NULL.

    Returns 0..N roles, where N is the number of distinct covenant types the
    character is simultaneously engaged with. Slice A's two-type system caps
    at 2 (one Durance, one Battle); future types extend.
    """
    return [r.covenant_role for r in self._rows
            if r.engaged and r.left_at is None]
```

This is markedly simpler than the earlier two-FK draft — the handler reads a flag that's already on the rows it's iterating, no separate FK lookup needed.

#### `covenant_role_bonus` refactor (consumer update)

`world/mechanics/services.py::covenant_role_bonus(sheet, target)` is the modifier-pipeline consumer of the old `currently_held()`. It is refactored to iterate `currently_engaged_roles()` and **sum** bonus contributions across engaged roles:

```python
def covenant_role_bonus(sheet: CharacterSheet, target: ModifierTarget) -> int:
    roles = sheet.character.covenant_roles.currently_engaged_roles()
    return sum(_role_bonus_for_target(role, target) for role in roles)
```

Behavior change implications:
- Character with no engaged memberships: returns 0 (empty sum). Matches §3.6 intent.
- Character engaged with one Durance membership (Vanguard): returns Vanguard's bonus for `target`.
- Character engaged with one Durance (Vanguard) + one Battle (Sword): returns Vanguard's bonus + Sword's bonus, additively.
- Character with multiple active Durance memberships, only one engaged: returns the engaged role's bonus only — non-engaged memberships do not contribute.

**For tests and factories that previously relied on `currently_held()` returning a role with active membership alone**, the test fixture now also needs to set `engaged=True` on the membership. The factory layer in §4.4 should provide a convenience helper — e.g., a factory trait or `CovenantFactory.with_engaged_member(...)` — that creates a membership with `engaged=True` in one call.

#### Required `_rows` query change

The existing `_rows` cached property does `select_related("covenant_role")` only. With the new `covenant` FK and the new `max_covenant_level_for_role` method walking `r.covenant.level`, the query MUST be updated to `select_related("covenant_role", "covenant")` — otherwise every membership row fires a separate query to load its `Covenant`, producing an N+1 inside the anchor cap path. The existing zero-query integration test (`world/magic/tests/integration/test_modifier_total_no_query.py`) warms the handler via the (now-removed) `currently_held()` and does not exercise the anchor cap path. Slice A's update to that test calls `currently_engaged_roles()` and `max_covenant_level_for_role` to warm the cache; even after that, the existing assertion does not exercise the anchor cap path. Slice A therefore adds a **targeted zero-query test** that warms `_rows` and then calls `compute_anchor_cap` on a COVENANT_ROLE Thread, asserting zero additional queries.

#### Engagement-aware caching

When any membership row's `engaged` flag changes (via `set_engaged_membership` / `clear_engaged_membership` / `clear_engaged_for_type` / auto-clear in lifecycle services), the handler's cache must be invalidated so a stale `currently_engaged_roles()` result isn't served. Every service that mutates `engaged` calls `handler.invalidate()` on the affected character. The `_rows` cache is per-character and tracks the full row list, so any flag change requires invalidation regardless of which row was touched.

#### Methods unchanged

`has_ever_held(role)`, `invalidate()` — semantics unchanged.

### 4.6 Anchor cap formula update

`src/world/magic/services/threads.py:136-137` — the `COVENANT_ROLE` arm of `compute_anchor_cap`:

```python
# Before:
case TargetKind.COVENANT_ROLE:
    return thread.owner.current_level * 10

# After:
case TargetKind.COVENANT_ROLE:
    role = thread.target_covenant_role
    max_level = thread.owner.character.covenant_roles.max_covenant_level_for_role(role)
    return max_level * 10
```

The lookup goes through the cached handler (per `feedback_no_filter_on_shared_memory_relations.md`) — never via direct `.filter()` on the related manager.

The function's docstring updates to reflect the new formula. The remaining docstring lines about "the placeholder until covenants ship" are removed.

### 4.7 Pull eligibility gating for COVENANT_ROLE Threads

Today, `world/magic/services/resonance.py:272-279` classifies COVENANT_ROLE in `_ALWAYS_IN_ACTION_KINDS`, with the comment *"COVENANT_ROLE threads similarly have their own gate (role held at action time); they bypass anchor-involvement in the same way."* The "own gate" was implicit (just have an active role assignment) and does not match §3.6's design intent: pulling a COVENANT_ROLE Thread should require engagement with a covenant where the character holds the role.

#### Change to `_ALWAYS_IN_ACTION_KINDS` and `_anchor_in_action`

Remove `TargetKind.COVENANT_ROLE` from `_ALWAYS_IN_ACTION_KINDS`:

```python
_ALWAYS_IN_ACTION_KINDS = frozenset(
    {
        TargetKind.RELATIONSHIP_TRACK,
        TargetKind.RELATIONSHIP_CAPSTONE,
        TargetKind.FACET,
        # COVENANT_ROLE removed — gated explicitly in _anchor_in_action below.
    }
)
```

Add an explicit COVENANT_ROLE arm in `_anchor_in_action`:

```python
def _anchor_in_action(thread: Thread, ctx: PullActionContext) -> bool:
    if thread.target_kind in _ALWAYS_IN_ACTION_KINDS:
        return True
    if thread.target_kind == TargetKind.TRAIT:
        return thread.target_trait_id in ctx.involved_traits
    if thread.target_kind == TargetKind.TECHNIQUE:
        return thread.target_technique_id in ctx.involved_techniques
    if thread.target_kind == TargetKind.ROOM:
        return thread.target_object_id in ctx.involved_objects
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        # The thread anchor is in-action when ANY currently-engaged membership
        # has the character fulfilling the anchored role. With per-type stacking,
        # a character engaged with both Durance and Battle memberships and
        # holding the role in either qualifies.
        sheet = thread.owner
        engaged_roles = sheet.character.covenant_roles.currently_engaged_roles()
        target_pk = thread.target_covenant_role_id
        return any(role.pk == target_pk for role in engaged_roles)
    return False
```

#### Behavior implications

- Character with no engaged memberships cannot pull a COVENANT_ROLE Thread — `currently_engaged_roles()` returns empty, no `any()` matches.
- Character engaged with one Durance Vanguard membership: Vanguard Threads are pull-eligible; non-Vanguard COVENANT_ROLE Threads are not.
- Character engaged with one Durance (Vanguard) + one Battle (Sword): both Vanguard and Sword Threads are pull-eligible.
- Character with multiple active Durance memberships (e.g., Vanguard in A and Vanguard in B), only the A membership engaged: Vanguard Thread is pull-eligible because the engaged A membership satisfies the role-pk match. The Thread is anchored on the *role* (Vanguard), not on a specific covenant.
- Character engaged with Durance Vanguard, has a Battle-Sword Thread but no Battle engagement: cannot pull the Battle-Sword Thread (no engaged membership where they fulfill Sword).
- Character with active Vanguard membership but `engaged=False` (member but not currently fulfilling the role): cannot pull a Vanguard Thread. Bonuses are dormant per §3.6 design intent.

This naturally handles both the §3.1 non-exclusive membership case and the §3.6 type-scoped stacking case.

#### Exception when pull is rejected

The existing `_anchor_in_action` returning `False` triggers `InvalidImbueAmount("Thread anchor is not involved in this action.")` in `spend_resonance_for_pull`. For COVENANT_ROLE specifically, this error message will read confusingly to a player ("anchor not involved" doesn't communicate "you need to engage with your covenant first"). Slice A adds a typed exception — `CovenantRoleNotEngagedError(InvalidImbueAmount)` with `user_message` "You're not currently fulfilling this covenant role." — and returns it from the COVENANT_ROLE arm via a more specific raise path. The pull pipeline catches `InvalidImbueAmount` and surfaces `user_message` if present.

(Note: a tighter approach is to wire `_anchor_in_action` into the per-Thread error path so each rejected Thread gets a kind-specific message. That's a refactor of the existing function and out of scope; Slice A's narrower change is to surface the specific COVENANT_ROLE message when the loop calls fail.)

### 4.8 Constants & exceptions

- **`CovenantType`** in `src/world/covenants/constants.py` — already has `DURANCE` and `BATTLE`. No changes.
- **No new exceptions raised by services in Slice A.** Per the service-vs-serializer split documented in §4.4: services don't validate user input, so they don't raise user-input-shaped errors. User-input validation in Slice B's serializer layer surfaces failures via DRF's standard `serializers.ValidationError` mechanism — no project-specific exception classes needed yet.
- **Existing exception** `CovenantRoleNeverHeldError` (raised by the Thread weave gate via `has_ever_held(role)`) — unchanged.
- **`CovenantRoleNotEngagedError(InvalidImbueAmount)`** added in `src/world/magic/exceptions.py` — surfaced by the pull pipeline when a COVENANT_ROLE Thread pull is rejected because no engaged membership matches the anchored role. This is raised from the pull pipeline (which already raises typed `InvalidImbueAmount` errors), not from a covenants service. `user_message`: "You're not currently fulfilling this covenant role."
- **Exception additions** in `src/world/magic/exceptions.py`:
  - `CovenantRoleNotEngagedError(InvalidImbueAmount)` — surfaced when a COVENANT_ROLE Thread pull is rejected because the character is not engaged with a covenant where they hold the role. `user_message`: "You're not currently fulfilling this covenant role."

### 4.9 Migration plan

All migrations in `src/world/covenants/migrations/`. No cross-app migrations (CharacterSheet is unchanged).

1. **`0004_covenant.py`** — creates `Covenant` table.
2. **`0005_charactercovenantrole_covenant_fk_and_engaged.py`** — composite migration:
   - Adds nullable `covenant` FK to `CharacterCovenantRole`.
   - Adds `engaged` BooleanField with `default=False` to `CharacterCovenantRole`.
   - Data migration step: **deletes** all existing `CharacterCovenantRole` rows (per `feedback_local_db_disposable.md` — the local dev DB is disposable, and there are no production covenants to backfill).
   - Makes `covenant` non-null after the wipe.
   - Drops `covenants_one_active_role_assignment` constraint.
   - Adds `covenants_one_active_role_per_covenant` constraint.

Justification for delete-instead-of-backfill on `CharacterCovenantRole`: there is no production data, and pre-MVP test/seed data is regenerated from factories. No alternative is correct (a backfill would need to invent fake `Covenant` rows that don't reflect any real authored content). Per `project_seed_data_strategy.md`, factories are the source of truth for test/seed data; they will be updated in Slice A to create memberships against `Covenant` rows.

Splitting these schema changes into two migrations (one for the FK, one for `engaged`) is also acceptable if it makes the data migration cleaner; the implementer chooses based on what makes the migration most readable. The wipe step must happen in or before the migration that makes `covenant` non-null.

### 4.10 Bundled bug fix #1 — TreatmentAttempt unique constraint

Per `project_treatment_unique_constraint.md`. Today `TreatmentAttempt` has an unconditional `UniqueConstraint(helper, target, scene, treatment)`. The original Spec 6 §4.2 intent was a partial constraint gated on `Q(treatment__once_per_scene_per_helper=True)`, but Django/Postgres reject partial-index `WHERE` clauses that reference joined-table columns.

Fix:

- Add `once_per_scene_guard = BooleanField(default=False, editable=False)` to `TreatmentAttempt`.
- Update the create-attempt service in `world/conditions/services` to stamp `once_per_scene_guard = treatment.once_per_scene_per_helper` at insert time.
- Replace the unconditional unique constraint with `UniqueConstraint(fields=["helper", "target", "scene", "treatment"], condition=Q(once_per_scene_guard=True), name="treatments_unique_once_per_scene")`.
- Migration: backfill the new column from `treatment.once_per_scene_per_helper` for existing rows; flip the constraint.

This is a 2-3 line service change plus a migration. Tests cover: a treatment with `once_per_scene_per_helper=True` still raises on duplicate; a treatment with `once_per_scene_per_helper=False` permits duplicates within a scene.

### 4.11 Bundled bug fix #2 — `perform_anima_ritual` budget overspend

Per `project_ritual_budget_overspend.md`. In `src/world/magic/services/anima.py` Phase 8 severity-reduction loop:

```python
# Before:
while budget > 0 and soulfray_inst.severity > 0:
    decay_condition_severity(soulfray_inst, amount=1)
    severity_reduced += 1
    budget -= config.ritual_severity_cost_per_point

# After:
while budget >= config.ritual_severity_cost_per_point and soulfray_inst.severity > 0:
    decay_condition_severity(soulfray_inst, amount=1)
    severity_reduced += 1
    budget -= config.ritual_severity_cost_per_point
```

When `ritual_severity_cost_per_point=1` (current seed default), behavior is unchanged. When the cost is later tuned above 1, the loop now exits cleanly when the next reduction can't be paid in full — leaving leftover budget for anima refill instead of overspending by one iteration.

The bug only manifests when `soulfray_inst is not None` (a soulfray condition is present) AND `cost_per_point > 1`. When no soulfray is present, the loop body is skipped entirely and `budget` flows untouched into the anima refill path; this code path is unaffected by the fix. The implementer should verify both paths in the test (soulfray-present-with-cost-2 *and* soulfray-absent) so the no-soulfray case remains unchanged.

Tests cover: cost=1 unchanged; cost=2 with budget=3 yields one reduction (2 spent) and 1 leftover for anima (currently yields two reductions for 4 cost and 0 leftover); soulfray-absent with cost=2 yields zero reductions and full budget intact (regression guard).

### 4.12 Tests

Factory-driven coverage in `src/world/covenants/tests/`:

- **`test_models.py`** — `Covenant` field validation; new active-uniqueness constraint enforces correctly across covenants; `covenant` FK PROTECT raises on hard-delete with active members.
- **`test_models.py`** — extends with: `clean()` rejects `engaged=True AND left_at IS NOT NULL`; `clean()` rejects `engaged=True` when another engaged active row of the same covenant_type exists for the character; `clean()` permits `engaged=True` when an existing engaged row is in a different covenant_type; default `engaged=False` for newly-created rows.
- **`test_services.py`** — `create_covenant` creates covenant + founder membership (with `engaged=False` by default) atomically; `add_member` creates a new active membership; the active-uniqueness DB constraint raises `IntegrityError` when a duplicate active row would result (test asserts this with valid-but-conflicting inputs); `change_role` closes the old row (sets `engaged=False` and `left_at`) and creates a new active one (new row defaults `engaged=False`); `dissolve_covenant` sets `engaged=False` and `left_at=now()` on every active membership in the covenant and is idempotent on already-dissolved covenants; `set_engaged_membership` atomically un-engages other same-type rows for the character before engaging the new one; cross-type engagements are unaffected (engaging a Battle membership doesn't touch Durance and vice versa); `clear_engaged_membership` and `clear_engaged_for_type` produce the documented state. Tests pass valid inputs (the services don't validate user-input concerns; that's the serializer's job in Slice B's API layer).
- **`test_handlers.py`** — `max_covenant_level_for_role` returns the max across active and historical memberships; returns 0 when no rows exist; `currently_engaged_roles()` returns empty list when no rows are engaged; returns one role when one row is engaged; returns two roles when one Durance and one Battle row are both engaged (verifies stacking); does NOT include rows where `engaged=True AND left_at IS NOT NULL` (defensive — service should never create this state, but the handler's filter is `engaged AND left_at IS NULL` to be safe); `currently_held_role_in(covenant)` returns the active role (engaged or not) in that specific covenant or `None`. **No test for `currently_held()`** — the method is removed.
- **`test_views.py`** — existing read-only viewsets still work (the `CharacterCovenantRoleViewSet` queryset gets `select_related("covenant")` for prefetch hygiene).

Cross-app coverage:

- **`world/magic/tests/test_thread_anchor_cap.py`** (new or extend existing) — `COVENANT_ROLE` anchor cap reflects max covenant level across the character's memberships for that role; cap is `max_level × 10`; falls back to 0 when the character has no membership rows for the role. Anchor cap is **independent of engagement** — same cap whether engaged or not.
- **Zero-query anchor cap test** — extend `world/magic/tests/integration/test_modifier_total_no_query.py` (or add a sibling test) that warms `_rows` via the handler and then calls `compute_anchor_cap(thread)` for a `COVENANT_ROLE` Thread, asserting zero additional queries fire. This is the regression guard for the §4.5 `select_related("covenant")` requirement.
- **Existing-test migration task — `currently_held()` → `currently_engaged_roles()`.** The implementation plan must call out, as a discrete task, that every existing call site of `currently_held()` in the test suite (confirmed multiple sites in `test_modifier_total_no_query.py` and others via grep) must be migrated to either `currently_engaged_roles()` or `currently_held_role_in(covenant)`. This is mechanical but must not be skipped — any straggler will fail at import time once the handler removes `currently_held`. The plan should include `grep -rn "currently_held(" src/` as a pre-merge verification step.
- **`world/magic/tests/integration/test_covenant_role_thread_pipeline.py`** — existing integration test continues to pass (after factory updates to create memberships against a `Covenant` row AND set `engaged=True` on the membership for any test that exercises pull paths).
- **`world/magic/tests/test_pull_engagement_gate.py`** (NEW) — covers §4.7 behavior:
  - Character with no engaged memberships cannot pull a COVENANT_ROLE Thread.
  - Character with an engaged Durance Vanguard membership CAN pull a Vanguard Thread.
  - Character with an engaged Battle Sword membership CAN pull a Sword Thread.
  - Character engaged with one Durance and one Battle membership, holding the Thread's role in either, CAN pull.
  - Character engaged with Durance only, with a Battle-Sword Thread but no engaged Battle membership, CANNOT pull the Battle-Sword Thread.
  - Character with non-engaged active Vanguard membership (member but not currently fulfilling) cannot pull a Vanguard Thread.
  - Character with multi-covenant non-exclusive Durance memberships (Vanguard in A and B), only A engaged: CAN pull a Vanguard Thread (the engaged A row satisfies); after `set_engaged_membership` switches engagement to B (which atomically un-engages A), the pull still works (the engaged B row now satisfies).
  - Pull rejection raises `CovenantRoleNotEngagedError` with the documented user_message.
- **`world/mechanics/tests/test_covenant_role_bonus_gating.py`** (NEW or extend existing) — `covenant_role_bonus(sheet, target)` returns 0 when no rows are engaged; returns one role's bonus when one Durance row is engaged; returns SUM of both roles' bonuses when one Durance and one Battle row are engaged (verifies additive stacking); does NOT contribute from non-engaged active memberships even if the character holds the role.

Bundled bug fix tests:

- **`world/conditions/tests/test_treatment_constraint.py`** — extend with the partial-constraint cases described in §4.10.
- **`world/magic/tests/test_anima_ritual_budget.py`** — extend with the cost-per-point cases described in §4.11.

### 4.13 Roadmap update

Update `docs/roadmap/covenants.md` in this PR:

- "What Exists" section: add Covenant model and membership FK shipped.
- "What's Needed for MVP" section: tick the Covenant entity bullet; note that anchor cap formula no longer uses character-level placeholder; reorganize remaining bullets into the explicit Slice B–G structure.
- Add a new sub-section: **"Membership is non-exclusive"** — captures §3.1 of this spec as durable design intent.

---

## Out of scope (explicit deferrals)

Each item below has a future slice or is a separate concern entirely. Listed here so they don't accidentally creep into Slice A.

- **Formation ritual** — Slice B. Slice A's `create_covenant` is a raw service used by tests/admin and (eventually) by the formation ritual flow.
- **Member lifecycle UI / invite-accept handshake** — Slice B.
- **Dissolution paths (voluntary / objective_fulfilled / fractured)** — Slice B. Slice A has a single `dissolve_covenant` service with no reason discrimination.
- **Sworn Objective as a structured model** — Slice C. Slice A stores a free-text TextField; C migrates it.
- **Stories/Missions integration** — Slice C.
- **Covenant XP / level progression** — Slice D. Slice A's `Covenant.level` defaults to 1 and never changes; D adds the XP pipeline.
- **Group abilities, sub-role unlocks** — Slices D and F.
- **Battle covenants and Durance × Battle stacking rules** — Slice E. Slice A allows BATTLE covenants to exist (the enum value is shipped) but does not author Battle-specific authoring content.
- **Use-based weave gate and anchor cap (legend in role / time in role)** — Slice G. Slice A keeps `has_ever_held` as the weave gate and uses max-covenant-level for the anchor cap.
- **Primary covenant designation** — separate concern; will be added when player-facing UI requires it. Not Slice A, not Slice B.
- **Polymorphic covenant subclasses** — explicitly rejected per project hard rule.
- **Per-Resonance pull effect catalog for COVENANT_ROLE** — content authoring task, not a code slice. Belongs alongside Slice F or as its own seed task.
- **`CovenantViewSet` / full CRUD API + frontend** — deferred until Slice B's lifecycle services define the actual CRUD surface. Slice A's admin-only access via `/admin/` is sufficient.
- **Auto-set engagement based on scene context** (e.g., "you walked into a scene with covenant-mates, so you're now engaged with that covenant") — Slice B or beyond. Slice A's engagement is only set/cleared by explicit service calls.
- **UI for engage/disengage covenant** — Slice B.
- **Mission-driven engagement** (e.g., "starting a covenant-flagged mission auto-engages you with that covenant") — Slice B or whichever slice introduces the mission-covenant link.
- **Tier-0 passive Thread effect application gating** — passive effects are "always-on while anchor is in scope" per the Thread system; for COVENANT_ROLE the in-scope predicate matches engagement, but the implementation site for passive effect application is not yet investigated. Slice A's pull-pipeline gate (§4.7) covers tier 1-3; tier 0 passive gating is deferred to whichever slice formalizes the application surface (likely Slice F or a parallel magic-system slice).
- **Thread situational gating for non-COVENANT_ROLE kinds** — Slice H. The general principle (Threads are situational; relationship Threads only when relationship is involved, etc.) applies project-wide; Slice A only fixes COVENANT_ROLE. Tightening RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE / FACET out of `_ALWAYS_IN_ACTION_KINDS` is its own design question (what "involved" means for each kind) and belongs in a magic-system slice, not Covenants.
- **Inspection-UI handler method for "all active memberships"** — Slice A's `currently_engaged_roles()` returns roles in *engaged* covenants only (0-2 in Slice A). Some future read-paths may need "every covenant the character is currently a member of, regardless of engagement" (e.g., a profile page listing all covenant memberships). That use-case should NOT call `currently_engaged_roles()`; instead it should query `CharacterCovenantRole.objects.filter(character_sheet=..., left_at__isnull=True).select_related("covenant", "covenant_role")` directly, or use a new handler method explicitly named `all_active_memberships()`. Slice A does not preemptively add this method; it lands when the first consumer needs it.
- **Combat-side stacking precedence (Durance vs. Battle role for speed_rank, gear archetype, etc.)** — Slice E. Slice A only handles modifier-pipeline additive stacking; combat speed_rank stays explicit per-encounter via `CombatParticipant.covenant_role` and Slice E decides which role applies in war contexts.
- **DB-level enforcement of "at most one engaged active row per (character, covenant_type)"** — service-enforced and `clean()`-enforced in Slice A; not enforced at the DB layer. A partial unique constraint cannot reference `covenant.covenant_type` (joined-table column) without denormalization. A future hardening slice may add a Postgres EXCLUDE constraint (raw SQL migration) or denormalize the type if invariant violations become a real concern. For Slice A, the test suite is the audit.

---

## Migration / Rollout

- Two new migrations in `src/world/covenants/`. Two new (or extended) migrations in `src/world/conditions/` and `src/world/magic/` for the bundled bug fixes.
- Local dev DB: regenerate from factories as usual. The `0005_charactercovenantrole_covenant_fk.py` data migration deletes existing rows; this is safe because there is no production data and pre-MVP test/seed data is regenerated.
- CI test DB: fresh creation per run (per project convention `--keepdb` is local-only). Migrations run cleanly from scratch; factories update to attach memberships to a Covenant row.
- No external rollout / no feature flags / no API breakage (no public API surface for Covenant in Slice A).

---

## Components

**New files:**
- `src/world/covenants/migrations/0004_covenant.py`
- `src/world/covenants/migrations/0005_charactercovenantrole_covenant_fk_and_engaged.py`

**Modified files:**
- `src/world/covenants/models.py` — add `Covenant`; modify `CharacterCovenantRole` (add `covenant` FK, add `engaged` boolean, swap active-uniqueness constraint, add `clean()` for engagement invariants).
- `src/world/covenants/services.py` — add `create_covenant`, `add_member`, `change_role`, `dissolve_covenant`, `set_engaged_membership`, `clear_engaged_membership`, `clear_engaged_for_type`; update `assign_covenant_role` / `end_covenant_role` signatures (covenant required + un-engage hook on end).
- `src/world/covenants/handlers.py` — add `max_covenant_level_for_role`, `currently_held_role_in`, and `currently_engaged_roles`; **remove** `currently_held()`; update `_rows` to `select_related("covenant_role", "covenant")`.
- `src/world/covenants/exceptions.py` — no new exception classes in Slice A (services don't validate; user-input validation in Slice B's serializers uses DRF's standard `serializers.ValidationError`). Existing `CovenantRoleNeverHeldError` is unchanged.
- `src/world/covenants/factories.py` — add `CovenantFactory`; update `CharacterCovenantRoleFactory` to require/default a covenant; add a convenience trait or helper (e.g., `engaged=True` trait or `with_engaged_member(...)`) that creates an engaged active membership in one call.
- `src/world/covenants/admin.py` — register `Covenant` in admin; `CharacterCovenantRole` admin shows `engaged` flag.
- `src/world/covenants/serializers.py`, `views.py`, `urls.py` — add `CovenantSerializer` (read-only) and `CovenantViewSet` (read-only, paginated, FilterSet for `covenant_type` / active state). Permissions: staff sees all; non-staff scoped to covenants where they have an active membership chain (mirrors the existing pattern on `CharacterCovenantRoleViewSet`). The `CharacterCovenantRoleViewSet` queryset gains `select_related("covenant")` and exposes `engaged` in the serializer. The full read+write CRUD for `Covenant` lands in Slice B; Slice A ships read-only so frontend can begin building against a stable shape.
- `src/world/mechanics/services.py` — refactor `covenant_role_bonus(sheet, target)` to iterate `currently_engaged_roles()` and sum contributions across engaged roles (additive stacking).
- `src/world/magic/services/threads.py` — modify `compute_anchor_cap` `COVENANT_ROLE` arm; refresh docstring.
- `src/world/magic/services/resonance.py` — modify `_ALWAYS_IN_ACTION_KINDS` (remove COVENANT_ROLE) and add explicit COVENANT_ROLE arm in `_anchor_in_action`; surface `CovenantRoleNotEngagedError`.
- `src/world/magic/exceptions.py` — add `CovenantRoleNotEngagedError(InvalidImbueAmount)`.
- `src/world/conditions/models.py`, `services.py`, `migrations/` — TreatmentAttempt fix (§4.10).
- `src/world/magic/services/anima.py` — perform_anima_ritual loop guard fix (§4.11).
- `docs/roadmap/covenants.md` — roadmap update per §4.13.

**Note: `src/world/character_sheets/` is unchanged in this revision** — engagement lives on the membership row, not on `CharacterSheet`.

**Modified test files:** as enumerated in §4.12.

---

## Verification

- `arx test world.covenants` — all new and updated covenant tests pass.
- `arx test world.magic` — anchor cap, Thread, and pull-engagement tests pass.
- `arx test world.mechanics` — `covenant_role_bonus` engagement-gating tests pass.
- `arx test world.conditions` — treatment constraint test passes.
- `arx test world.combat` — combat speed-rank reads via covenant-aware membership still work.
- (No `world.character_sheets` test scope change — engagement is on `CharacterCovenantRole`, not `CharacterSheet`.)
- `arx test world.covenants world.magic world.mechanics world.conditions world.combat flows` — combined regression for affected suites.
- Full regression run **without `--keepdb`** before push (per `feedback_full_test_scope_for_substrate_changes.md` and the CLAUDE.md note about substrate changes — adding a covenant FK to `CharacterCovenantRole` is a substrate change).
- `pre-commit run --all-files` clean.
- `arx manage makemigrations --check` clean (no phantom migrations).

---

## Risks & considerations

- **`change_role` semantics with non-exclusive memberships.** If a character holds Vanguard in Covenant Alpha and Sentinel in Covenant Beta and wants to change Alpha role to Sentinel, the service needs to scope the role change to the membership row in Alpha (not Beta). The service signature takes a `membership` instance to make this unambiguous; tests verify this.
- **`max_covenant_level_for_role` includes historical memberships.** This is a deliberate design call (Threads keep their cap when memberships end; future Slice G can revisit). Surfacing it explicitly in §3.5 so the slice review catches dissent if any.
- **Roadmap implies one Durance per character.** The roadmap update in §4.13 must be loud enough that future readers don't carry the old assumption forward. A "Membership is non-exclusive" sub-section (not a parenthetical) and a roadmap note in the design-points list both contribute.
- **Bundled bug fixes hide if review is sloppy.** Both bug fixes are guarded by their own discrete test cases (§4.12) and named explicitly in the PR description. The bundling is documented in §3.7 and `feedback_expand_scope_when_diff_is_tiny.md`.
- **Read-only viewset shape may change in Slice B.** Slice A ships a minimal read-only CovenantViewSet. Slice B will add write actions; the read shape may need fields not yet exposed. To mitigate, the Slice A serializer is conservative (id, name, covenant_type, level, formed_at, dissolved_at, sworn_objective, member_count) and FilterSet supports basic filtering only.
- **`currently_held()` removal is a breaking API change.** The handler method is removed (not renamed in-place); every consumer of `currently_held()` MUST migrate to `currently_engaged_roles()` (iterable) or `currently_held_role_in(covenant)` (single role for a specific covenant). The known consumers as of Slice A are `world/mechanics/services.py::covenant_role_bonus` and the test suite. The implementer must grep for `currently_held(` across the codebase before merging — any straggler will fail at import or test time. This is the highest-risk regression vector.
- **Test fixtures that previously relied on "any active role" semantics will now produce zero bonuses.** Tests that create a `CharacterCovenantRole` row and expect role bonuses to fire must additionally set `engaged=True` on the membership. The §4.5 fixture-helper recommendation (a factory trait like `with_engaged_member`) mitigates by making the right pattern the easy pattern. Expect to update every existing test that exercises `covenant_role_bonus` or gear compatibility via the role pipeline.
- **No DB-level enforcement of "at most one engaged active row per (character, covenant_type)."** The invariant is service-enforced (atomic un-engage-then-engage in `set_engaged_membership`) + `clean()`-enforced (rejects a row that would violate the invariant on save). The service is the documented single mutation path; `clean()` is the safety net for non-service mutation paths (admin, ad-hoc serializer use). A buggy migration or raw `.save(update_fields=["engaged"])` call that bypasses `clean()` could create an invariant-violating state. Mitigation: tests cover the invariant; admin uses `ModelForm` (which calls `full_clean`); any future bulk-update code must explicitly route through the service.
- **Coherence invariant: engaged rows must have `left_at IS NULL`.** Enforced by `clean()`. Auto-handled in `end_covenant_role` (un-engages before setting `left_at`) and `dissolve_covenant` (same pattern across all members). The handler's `currently_engaged_roles()` filters defensively on both `engaged AND left_at IS NULL` — a row with `engaged=True AND left_at IS NOT NULL` is a defensive non-event (filtered out) rather than a crash.
- **Tier-0 passive Thread effects on COVENANT_ROLE remain ungated in Slice A.** This is acknowledged in Out of Scope. If passive effects are applied today (e.g., via a modifier-pipeline contribution from `ThreadPullEffect` rows with `tier=0` and `min_thread_level<=t.level`), they will continue to fire regardless of engagement until Slice F (or a parallel slice) addresses them. The implementer should check whether passive effect application is currently wired to anything; if it is, this is a known gap that may need a quick follow-up.
- **Stacking math will need re-tuning when actual Durance × Battle bonus authoring lands.** Slice A implements additive stacking as the SUM of engaged roles' bonuses. If playtest reveals that a Durance Vanguard + Battle Sword character is too strong (because both roles' bonuses apply additively to combat-relevant rolls), the Slice E design may need to switch to a precedence model (Battle takes precedence in war contexts) or a damping rule (e.g., max + 0.5 × min). Slice A's `covenant_role_bonus` refactor is structured so swapping `sum(...)` for a different aggregator is a single-function change.
