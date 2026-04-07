# Bulk Apply Conditions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `apply_condition` internals to accept pre-fetched data, then build a `bulk_apply_conditions` function that batches DB queries across multiple (target, condition) pairs. Update combat to use it.

**Architecture:** Extract the query-heavy parts of `apply_condition` into a pre-fetchable pattern. A new `_BulkConditionContext` dataclass holds pre-fetched data (active instances, interactions, first stages). `_apply_single` does the logic using pre-fetched data. `apply_condition` becomes a thin wrapper that builds a single-item context and delegates. `bulk_apply_conditions` builds a multi-item context with batched queries and calls `_apply_single` in a loop.

**Tech Stack:** Django ORM, FactoryBoy, conditions service functions

---

## Background

`apply_condition` currently makes 5-7 DB queries per call:
1. `get_active_conditions(target).values_list(...)` — for prevention check
2. `ConditionConditionInteraction` query — prevention (existing prevents incoming)
3. `ConditionConditionInteraction` query — prevention (self-prevention)
4. `get_active_conditions(target)` — for interaction processing
5. `ConditionConditionInteraction` query — application interactions
6. `get_condition_instance(target, template)` — existing instance check
7. `template.stages.order_by(...).first()` — first stage (if progressive)

For bulk operations (e.g., 3 conditions applied to 5 PCs = 15 calls = 75-105 queries), most of these can be batched:
- Active conditions per target: 1 query for all targets
- Interactions for all condition templates: 1-2 queries total
- Existing instances for all (target, condition) pairs: 1 query
- First stages for all progressive templates: 1 query

---

### Task 1: Create `_BulkConditionContext` and batch-fetch function

**Files:**
- Modify: `src/world/conditions/services.py`
- Test: `src/world/conditions/tests/test_services.py`

**Step 1: Write test for the context builder**

Add to `test_services.py`:

```python
class BuildBulkContextTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target_obj = create_object(ObjectDB, key="bulk_target")
        cls.template = ConditionTemplateFactory()
        cls.existing = ConditionInstanceFactory(
            target=cls.target_obj, condition=cls.template,
        )

    def test_context_contains_active_instances(self):
        from world.conditions.services import _build_bulk_context
        targets = [self.target_obj]
        templates = [self.template]
        ctx = _build_bulk_context(targets, templates)
        instances = ctx.active_instances_by_target.get(self.target_obj.pk, [])
        assert len(instances) == 1
        assert instances[0].condition_id == self.template.pk

    def test_context_contains_existing_pair(self):
        from world.conditions.services import _build_bulk_context
        ctx = _build_bulk_context([self.target_obj], [self.template])
        existing = ctx.get_existing_instance(self.target_obj.pk, self.template.pk)
        assert existing is not None
        assert existing.pk == self.existing.pk

    def test_context_empty_for_unknown_target(self):
        from world.conditions.services import _build_bulk_context
        other = create_object(ObjectDB, key="other")
        ctx = _build_bulk_context([other], [self.template])
        instances = ctx.active_instances_by_target.get(other.pk, [])
        assert len(instances) == 0
```

**Step 2: Run tests to verify they fail**

Run: `arx test world.conditions.tests.test_services -k BuildBulkContext`
Expected: FAIL — `_build_bulk_context` does not exist

**Step 3: Implement `_BulkConditionContext` and `_build_bulk_context`**

Add to `src/world/conditions/services.py`:

```python
@dataclass
class _BulkConditionContext:
    """Pre-fetched data for bulk condition application.

    Holds all DB-fetched state needed by _apply_single, avoiding per-call queries.
    """

    # target_id -> list of active ConditionInstance
    active_instances_by_target: dict[int, list[ConditionInstance]]
    # (target_id, condition_id) -> ConditionInstance or None
    existing_pairs: dict[tuple[int, int], ConditionInstance]
    # All prevention interactions for the template set
    prevention_interactions: list[ConditionConditionInteraction]
    # All application interactions for the template set
    application_interactions: list[ConditionConditionInteraction]
    # condition_id -> first ConditionStage (for progressive templates)
    first_stages: dict[int, ConditionStage]

    def get_existing_instance(
        self, target_id: int, condition_id: int,
    ) -> ConditionInstance | None:
        return self.existing_pairs.get((target_id, condition_id))

    def get_active_condition_ids(self, target_id: int) -> set[int]:
        return {i.condition_id for i in self.active_instances_by_target.get(target_id, [])}


def _build_bulk_context(
    targets: list["ObjectDB"],
    templates: list[ConditionTemplate],
) -> _BulkConditionContext:
    """Batch-fetch all data needed for applying conditions to multiple targets.

    One query per data type instead of per (target, condition) pair.
    """
    target_ids = [t.pk for t in targets]
    template_ids = [t.pk for t in templates]

    # 1. All active condition instances for all targets (1 query)
    all_instances = list(
        ConditionInstance.objects.filter(
            target_id__in=target_ids,
        ).select_related("condition", "condition__category", "current_stage")
    )

    active_by_target: dict[int, list[ConditionInstance]] = {}
    for inst in all_instances:
        active_by_target.setdefault(inst.target_id, []).append(inst)

    # 2. Existing instances for specific (target, template) pairs (1 query)
    existing_for_templates = list(
        ConditionInstance.objects.filter(
            target_id__in=target_ids,
            condition_id__in=template_ids,
        ).select_related("condition", "condition__category", "current_stage")
    )
    existing_pairs: dict[tuple[int, int], ConditionInstance] = {
        (inst.target_id, inst.condition_id): inst for inst in existing_for_templates
    }

    # 3. All prevention interactions involving these templates (2 queries)
    all_condition_ids = {i.condition_id for i in all_instances}
    prevention_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_OTHER,
            )
            | Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_SELF,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 4. All application interactions involving these templates (1 query)
    application_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
            )
            | Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 5. First stages for progressive templates (1 query)
    progressive_ids = [t.pk for t in templates if t.has_progression]
    first_stages: dict[int, ConditionStage] = {}
    if progressive_ids:
        for stage in (
            ConditionStage.objects.filter(condition_id__in=progressive_ids)
            .order_by("condition_id", "stage_order")
            .distinct("condition_id")
        ):
            first_stages[stage.condition_id] = stage

    return _BulkConditionContext(
        active_instances_by_target=active_by_target,
        existing_pairs=existing_pairs,
        prevention_interactions=prevention_interactions,
        application_interactions=application_interactions,
        first_stages=first_stages,
    )
```

**Note on `DISTINCT ON`:** This uses PostgreSQL's `DISTINCT ON` via `.order_by("condition_id", "stage_order").distinct("condition_id")` to get the first stage per condition in a single query. This is a PG-specific feature allowed by the project's "PostgreSQL Only" rule.

**Step 4: Run tests**

Run: `arx test world.conditions.tests.test_services -k BuildBulkContext`
Expected: PASS

**Step 5: Commit**

```
feat(conditions): add _BulkConditionContext and batch fetch builder

Pre-fetches active instances, interactions, existing pairs, and first
stages for multiple targets and templates in ~5 queries total.
```

---

### Task 2: Extract `_apply_single` from `apply_condition`

**Files:**
- Modify: `src/world/conditions/services.py`
- Test: `src/world/conditions/tests/test_services.py`

**Step 1: Extract the core logic into `_apply_single`**

Create `_apply_single` that takes a `_BulkConditionContext` and does the apply logic using pre-fetched data instead of making DB queries. The key changes from `apply_condition`:

- `_check_prevention_interactions` → `_check_prevention_from_context` (reads from `ctx.prevention_interactions` + `ctx.active_instances_by_target`)
- `_process_application_interactions` → `_process_interactions_from_context` (reads from `ctx.application_interactions` + `ctx.active_instances_by_target`)
- `get_condition_instance` → `ctx.get_existing_instance(target_id, template_id)`
- `_create_new_instance` → uses `ctx.first_stages` instead of querying

```python
def _check_prevention_from_context(
    target_id: int,
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> ConditionTemplate | None:
    """Check prevention using pre-fetched interactions."""
    active_condition_ids = ctx.get_active_condition_ids(target_id)
    for interaction in ctx.prevention_interactions:
        # Check "existing prevents incoming"
        if (
            interaction.other_condition_id == incoming_condition.pk
            and interaction.condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_OTHER_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_OTHER
        ):
            return interaction.condition
        # Check "incoming self-prevents"
        if (
            interaction.condition_id == incoming_condition.pk
            and interaction.other_condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_SELF_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_SELF
        ):
            return interaction.other_condition
    return None


def _process_interactions_from_context(
    target_id: int,
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> InteractionResult:
    """Process application interactions using pre-fetched data."""
    result = InteractionResult()
    active_instances = list(ctx.active_instances_by_target.get(target_id, []))
    active_condition_ids = {i.condition_id for i in active_instances}

    for interaction in ctx.application_interactions:
        # Filter to interactions relevant to this target's active conditions
        if interaction.condition_id == incoming_condition.pk:
            if interaction.other_condition_id not in active_condition_ids:
                continue
            match_id = interaction.other_condition_id
        elif interaction.other_condition_id == incoming_condition.pk:
            if interaction.condition_id not in active_condition_ids:
                continue
            match_id = interaction.condition_id
        else:
            continue

        existing_instance = next(
            (i for i in active_instances if i.condition_id == match_id), None,
        )
        if not existing_instance:
            continue

        if _should_remove_existing(interaction, incoming_condition):
            result.removed.append(existing_instance.condition)
            existing_instance.delete()
            active_instances.remove(existing_instance)
            active_condition_ids.discard(match_id)

    return result


def _create_instance_from_context(
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Create a new condition instance using pre-fetched stage data."""
    rounds = params.duration_rounds or template.default_duration_value
    rounds_remaining = rounds if template.default_duration_type == DurationType.ROUNDS else None

    first_stage = ctx.first_stages.get(template.pk) if template.has_progression else None
    stage_rounds = first_stage.rounds_to_next if first_stage and first_stage.rounds_to_next else None

    instance = ConditionInstance.objects.create(
        target=params.target,
        condition=template,
        severity=params.severity,
        stacks=1,
        rounds_remaining=rounds_remaining,
        current_stage=first_stage,
        stage_rounds_remaining=stage_rounds,
        source_character=params.source_character,
        source_technique=params.source_technique,
        source_description=params.source_description,
    )

    return ApplyConditionResult(
        success=True,
        instance=instance,
        stacks_added=1,
        message=f"{template.name} applied",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


def _apply_single(
    target: "ObjectDB",
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Apply a single condition using pre-fetched context data.

    Core logic extracted from apply_condition. All DB reads come from ctx;
    only writes (create/save/delete) hit the database.
    """
    prevention = _check_prevention_from_context(target.pk, template, ctx)
    if prevention:
        return ApplyConditionResult(
            success=False,
            was_prevented=True,
            prevented_by=prevention,
            message=f"{template.name} was prevented by {prevention.name}",
        )

    interaction_results = _process_interactions_from_context(target.pk, template, ctx)

    existing = ctx.get_existing_instance(target.pk, template.pk)

    if existing:
        if template.is_stackable and existing.stacks < template.max_stacks:
            return _handle_stacking(existing, template, params, interaction_results)
        return _handle_refresh(existing, template, params, interaction_results)

    return _create_instance_from_context(template, params, interaction_results, ctx)
```

**Step 2: Rewrite `apply_condition` as a thin wrapper**

```python
@transaction.atomic
def apply_condition(  # noqa: PLR0913
    target: "ObjectDB",
    condition: ConditionTemplate,
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,
    source_technique=None,
    source_description: str = "",
) -> ApplyConditionResult:
    """Apply a condition to a target, handling stacking and interactions.

    Thin wrapper around _apply_single — builds a single-item context
    and delegates. For applying multiple conditions, use bulk_apply_conditions.
    """
    ctx = _build_bulk_context([target], [condition])
    params = _ApplyConditionParams(
        target=target,
        severity=severity,
        duration_rounds=duration_rounds,
        source_character=source_character,
        source_technique=source_technique,
        source_description=source_description,
    )
    return _apply_single(target, condition, params, ctx)
```

**Step 3: Run ALL existing condition tests**

Run: `arx test world.conditions`
Expected: ALL PASS — behavior is identical, just refactored internals

This is the critical verification. If any existing test fails, the extraction broke something.

**Step 4: Commit**

```
refactor(conditions): extract _apply_single from apply_condition

Core logic now uses pre-fetched _BulkConditionContext instead of
per-call DB queries. apply_condition is a thin wrapper that builds
a single-item context. No behavior change — all existing tests pass.
```

---

### Task 3: Implement `bulk_apply_conditions`

**Files:**
- Modify: `src/world/conditions/services.py`
- Test: `src/world/conditions/tests/test_services.py`

**Step 1: Write tests for bulk_apply_conditions**

```python
class BulkApplyConditionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target1 = create_object(ObjectDB, key="bulk_t1")
        cls.target2 = create_object(ObjectDB, key="bulk_t2")
        cls.template1 = ConditionTemplateFactory(name="Burn")
        cls.template2 = ConditionTemplateFactory(name="Poison")

    def test_applies_to_multiple_targets(self):
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target2, self.template1)],
        )
        assert len(results) == 2
        assert all(r.success for r in results)
        assert ConditionInstance.objects.filter(condition=self.template1).count() == 2

    def test_applies_multiple_conditions_to_one_target(self):
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target1, self.template2)],
        )
        assert len(results) == 2
        assert all(r.success for r in results)
        assert ConditionInstance.objects.filter(target=self.target1).count() == 2

    def test_prevention_still_works(self):
        # Create a condition that prevents template2
        blocker = ConditionTemplateFactory(name="Blocker")
        ConditionInstanceFactory(target=self.target1, condition=blocker)
        ConditionConditionInteractionFactory(
            condition=blocker,
            other_condition=self.template2,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )
        results = bulk_apply_conditions(
            [(self.target1, self.template1), (self.target1, self.template2)],
        )
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].was_prevented is True

    def test_empty_list_returns_empty(self):
        results = bulk_apply_conditions([])
        assert results == []

    def test_severity_and_source_passed_through(self):
        source = create_object(ObjectDB, key="caster")
        results = bulk_apply_conditions(
            [(self.target1, self.template1)],
            severity=3,
            source_character=source,
            source_description="spell hit",
        )
        assert results[0].success is True
        inst = results[0].instance
        assert inst.severity == 3
        assert inst.source_character == source
        assert inst.source_description == "spell hit"
```

**Step 2: Run to verify they fail**

Run: `arx test world.conditions.tests.test_services -k BulkApplyConditions`
Expected: FAIL — `bulk_apply_conditions` does not exist

**Step 3: Implement `bulk_apply_conditions`**

```python
@transaction.atomic
def bulk_apply_conditions(
    applications: list[tuple["ObjectDB", ConditionTemplate]],
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,
    source_technique: "Technique | None" = None,
    source_description: str = "",
) -> list[ApplyConditionResult]:
    """Apply multiple conditions in a single transaction with batched queries.

    Fetches all needed data (active instances, interactions, stages) in ~5
    queries regardless of how many (target, condition) pairs are passed.
    Each application still respects prevention, interaction, and stacking rules.

    Args:
        applications: List of (target, condition_template) pairs.
        severity: Applied to all conditions (same severity for batch).
        duration_rounds: Override default duration for all.
        source_character: Who caused these conditions.
        source_technique: What technique caused them.
        source_description: Freeform source description.

    Returns:
        List of ApplyConditionResult in same order as applications.
    """
    if not applications:
        return []

    targets = list({target for target, _ in applications})
    templates = list({template for _, template in applications})

    ctx = _build_bulk_context(targets, templates)

    results: list[ApplyConditionResult] = []
    for target, template in applications:
        params = _ApplyConditionParams(
            target=target,
            severity=severity,
            duration_rounds=duration_rounds,
            source_character=source_character,
            source_technique=source_technique,
            source_description=source_description,
        )
        result = _apply_single(target, template, params, ctx)
        results.append(result)

    return results
```

**Step 4: Run tests**

Run: `arx test world.conditions.tests.test_services`
Expected: ALL PASS (old and new)

**Step 5: Commit**

```
feat(conditions): add bulk_apply_conditions with batched queries

Applies multiple (target, condition) pairs in ~5 DB queries instead of
5-7 per pair. Uses _BulkConditionContext for pre-fetched data. Respects
prevention, interaction, and stacking rules identically to apply_condition.
```

---

### Task 4: Update combat to use `bulk_apply_conditions`

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_round_orchestrator.py`

**Step 1: Update `_resolve_npc_action` to collect conditions and bulk-apply**

In `src/world/combat/services.py`, the current pattern in `_resolve_npc_action` is:

```python
for target_participant in targets:
    # ... damage ...
    if dmg_result.damage_dealt > 0 and conditions:
        for condition_template in conditions:
            apply_condition(target_obj, condition_template)
```

Replace with collecting pairs and calling bulk at the end:

```python
condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

for target_participant in targets:
    # ... damage ...
    if dmg_result.damage_dealt > 0 and conditions:
        target_obj = target_participant.character_sheet.character
        for condition_template in conditions:
            condition_applications.append((target_obj, condition_template))

# Bulk-apply all conditions from this NPC action
if condition_applications:
    from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
    bulk_apply_conditions(condition_applications)
```

Remove the single `apply_condition` import.

**Step 2: Run combat tests**

Run: `arx test world.combat`
Expected: ALL PASS

**Step 3: Commit**

```
refactor(combat): use bulk_apply_conditions in NPC action resolution

Replaces per-target per-condition apply_condition loop with a single
bulk_apply_conditions call. Reduces condition-related queries from
O(targets * conditions * 5) to ~5 total.
```

---

### Task 5: Add `begin_declaration_phase` opponent validation

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_services.py`

**Step 1: Write failing test**

Add to `BeginDeclarationPhaseTest` in `test_services.py`:

```python
def test_rejects_no_opponents(self):
    encounter = CombatEncounterFactory(status=EncounterStatus.BETWEEN_ROUNDS)
    # No opponents added
    with pytest.raises(ValueError, match="no active opponents"):
        begin_declaration_phase(encounter)
```

**Step 2: Run test to verify it fails**

Run: `arx test world.combat.tests.test_services -k test_rejects_no_opponents`
Expected: FAIL

**Step 3: Add validation to `begin_declaration_phase`**

In `src/world/combat/services.py`, add after the status check in `begin_declaration_phase`:

```python
has_opponents = CombatOpponent.objects.filter(
    encounter=enc,
    status=OpponentStatus.ACTIVE,
).exists()
if not has_opponents:
    msg = "Cannot begin declaration phase: no active opponents in encounter."
    raise ValueError(msg)
```

**Step 4: Run tests**

Run: `arx test world.combat.tests.test_services`
Expected: ALL PASS

**Step 5: Commit**

```
fix(combat): require active opponents to begin declaration phase

Prevents starting a round with no opponents, which would immediately
complete the encounter on resolution.
```

---

### Task 6: Fix bare string literals in combat tests

**Files:**
- Modify: `src/world/combat/tests/test_damage.py`
- Modify: `src/world/combat/tests/test_combos.py`
- Modify: `src/world/combat/tests/test_round_orchestrator.py`

**Step 1: Replace all bare string literals with constants**

Search for and replace:
- `"physical"` → `ActionCategory.PHYSICAL`
- `"social"` → `ActionCategory.SOCIAL`
- `"mental"` → `ActionCategory.MENTAL`
- `"medium"` → `EffortLevel.MEDIUM`
- `"high"` → `EffortLevel.HIGH` (if used)
- `"boss"` → `OpponentTier.BOSS`
- `"mook"` → `OpponentTier.MOOK`

Add imports at top of each file as needed:
```python
from world.combat.constants import ActionCategory, OpponentTier
from world.fatigue.constants import EffortLevel
```

**Step 2: Run tests**

Run: `arx test world.combat`
Expected: ALL PASS

**Step 3: Commit**

```
fix(combat): replace bare string literals with constants in tests

Use ActionCategory, EffortLevel, and OpponentTier constants instead of
raw strings. Prevents typo bugs and aligns with CLAUDE.md requirements.
```

---

### Task 7: Squash combat and vitals migrations

**Files:**
- Modify: `src/world/combat/migrations/`
- Modify: `src/world/vitals/migrations/`

**Step 1: Squash combat migrations**

Since combat is still in dev and this branch hasn't been merged, we can replace all migrations with a single fresh one:

```bash
# Remove all combat migrations except __init__.py
# Then regenerate
arx manage makemigrations combat
```

Do the same for vitals if it has multiple dev migrations.

**IMPORTANT:** Check that no other app's migrations depend on specific combat migration names before squashing. If they do, update references.

**Step 2: Verify**

```bash
arx manage migrate --check
arx test world.combat world.vitals --keepdb
```

**Step 3: Commit**

```
chore: squash combat and vitals migrations for clean merge
```

---

### Task 8: Final verification and cleanup

**Step 1: Run ruff**

Run: `ruff check src/world/combat/ src/world/vitals/ src/world/conditions/`

**Step 2: Run full affected test suites**

Run: `arx test world.combat world.vitals world.conditions world.covenants`

**Step 3: Verify migrations clean**

Run: `arx manage makemigrations --check`

**Step 4: Update roadmap if needed**

Update `docs/roadmap/combat.md` with `bulk_apply_conditions` in "What Exists" if not already noted.

**Step 5: Commit if fixups needed**

---

## Task Dependency Graph

```
Task 1 (_BulkConditionContext) ──┐
                                 ├── Task 3 (bulk_apply_conditions) ──┐
Task 2 (Extract _apply_single) ─┘                                    │
                                                                      ├── Task 4 (Combat integration)
Task 5 (Opponent validation) ── independent                           │
Task 6 (String literals) ── independent                               │
Task 7 (Squash migrations) ── independent (do last)                   │
                                                                      │
Task 8 (Final verification) ──────────────────────────────────────────┘
```

Tasks 1+2 must come first (conditions internals). Task 3 depends on both.
Task 4 depends on Task 3. Tasks 5, 6, 7 are independent.
Task 8 is final cleanup.
