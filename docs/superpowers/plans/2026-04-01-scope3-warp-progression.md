# Scope #3: Anima Warp Progression & Consequence Streams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the technique use consequence model with three independent streams: Warp severity accumulation with stage-driven consequences, control mishap pools, and the MAGICAL_SCARS effect hook.

**Architecture:** Two model changes to `ConditionStage` (`severity_threshold`, `consequence_pool`), three new models in `world/magic` (`WarpConfig`, `MishapPoolTier`, `TechniqueOutcomeModifier`), one new effect type in `checks/constants.py`. New `advance_condition_severity()` in conditions/services.py. Revised `use_technique()` pipeline in magic/services.py replaces overburn-based safety checkpoint with Warp-stage-driven warnings, implements severity accumulation with resilience checks, and implements control mishap pool lookup. Integration tests grow the existing `test_pipeline_integration.py`.

**Tech Stack:** Django, PostgreSQL, FactoryBoy, Evennia SharedMemoryModel

**Spec:** `docs/superpowers/specs/2026-03-31-scope3-warp-progression-design.md`

**Branch:** `scope3-warp-progression` (already exists)

**Key facts from existing code:**
- PipelineTestMixin's Flame Lance: intensity=10, control=7, anima_cost=2
- CharacterAnimaFactory: current=10, maximum=10
- `ConditionStage` at `src/world/conditions/models.py:290-351`
- `ConditionStageFactory` at `src/world/conditions/factories.py:84-96`
- `ConditionCheckModifierFactory` at `src/world/conditions/factories.py:110-121`
- `apply_condition()` at `src/world/conditions/services.py:264-326`
- `EffectType` at `src/world/checks/constants.py:6-16`
- `ConsequenceEffect._REQUIRED_FIELDS` at `src/world/checks/models.py:233-245`
- `_HANDLER_REGISTRY` at `src/world/mechanics/effect_handlers.py:225-234`
- `use_technique()` at `src/world/magic/services.py:345-424`
- `select_mishap_pool()` at `src/world/magic/services.py:334-342`
- `_get_warp_multiplier()` at `src/world/magic/services.py:317-331`
- `get_overburn_severity()` at `src/world/magic/services.py:275-296`
- `OverburnSeverity` at `src/world/magic/types.py:90-95`
- `TechniqueUseResult` at `src/world/magic/types.py:106-115`
- `apply_effect()` at `src/world/mechanics/effect_handlers.py:24` (NOT apply_effect)
- `perform_check()` at `src/world/checks/services.py:27-77`
- `ConditionCheckModifier` at `src/world/conditions/models.py:465-517` (stage FK for per-stage penalties)
- `select_consequence_from_result()` at `src/world/checks/consequence_resolution.py:63-97`
- `ANIMA_WARP_CONDITION_NAME` at `src/world/magic/audere.py:12`
- RuntimeModifierTests at `src/world/mechanics/tests/test_pipeline_integration.py:1063+`

**Important: This project uses `arx test` to run tests. Never use pytest, manage.py test, or any other runner. Always use `--keepdb` for speed.**

**Files referencing removed/renamed symbols (must update in Task 5):**
- `confirm_overburn`: `magic/services.py:350,360,388`, `magic/tests/test_use_technique.py:97,116`, `mechanics/tests/test_pipeline_integration.py:964,991`
- `overburn_severity`: `magic/types.py:111`, `magic/services.py:386,391,419`, `magic/tests/test_use_technique.py:53,101`, `mechanics/tests/test_pipeline_integration.py:944,969`
- `warp_multiplier_applied`: `magic/types.py:115`, `magic/services.py:423`, `magic/tests/test_use_technique.py:187-202`
- `OverburnSeverity` / `get_overburn_severity`: `magic/types.py:91`, `magic/services.py:20,275-296`, `magic/tests/test_anima_services.py:9,12,100-113`
- `_get_warp_multiplier`: `magic/services.py:317-331,403`

---

## File Map

| Task | File | Action | Purpose |
|------|------|--------|---------|
| 1 | `src/world/conditions/models.py` | Modify | Add `severity_threshold`, `consequence_pool` to ConditionStage |
| 1 | `src/world/conditions/factories.py` | Modify | Update ConditionStageFactory with new fields |
| 1 | `src/world/conditions/services.py` | Modify | Add `advance_condition_severity()` |
| 1 | `src/world/conditions/types.py` | Modify | Add `SeverityAdvanceResult` dataclass |
| 2 | `src/world/magic/models.py` | Modify | Add WarpConfig, MishapPoolTier, TechniqueOutcomeModifier models |
| 2 | `src/world/magic/factories.py` | Modify | Add factories for new models |
| 3 | `src/world/checks/constants.py` | Modify | Add MAGICAL_SCARS to EffectType |
| 3 | `src/world/checks/models.py` | Modify | Add MAGICAL_SCARS to _REQUIRED_FIELDS |
| 3 | `src/world/mechanics/effect_handlers.py` | Modify | Add _apply_magical_scars handler |
| 4 | `src/world/magic/types.py` | Modify | Replace OverburnSeverity with WarpWarning and WarpResult |
| 4 | `src/world/magic/services.py` | Modify | Add calculate_warp_severity(), get_warp_warning(), rewrite select_mishap_pool() |
| 5 | `src/world/magic/services.py` | Modify | Rewrite use_technique() Steps 3, 7, 8 |
| 6 | `src/world/mechanics/tests/test_pipeline_integration.py` | Modify | Add WarpProgressionTests class |

---

### Task 1: Severity-Driven Stage Advancement

**Files:**
- Modify: `src/world/conditions/models.py:290-351` (ConditionStage)
- Modify: `src/world/conditions/factories.py:84-96` (ConditionStageFactory)
- Modify: `src/world/conditions/services.py` (append)
- Modify: `src/world/conditions/types.py` (append)
- Test: `src/world/conditions/tests/test_services.py` (append)

This task adds the `severity_threshold` and `consequence_pool` fields to ConditionStage and the `advance_condition_severity()` service function. The consequence_pool FK is added here but not exercised until Task 5.

- [ ] **Step 1: Add SeverityAdvanceResult dataclass**

Append to `src/world/conditions/types.py`:

```python
@dataclass
class SeverityAdvanceResult:
    """Result of advancing a condition's severity."""

    previous_stage: ConditionStage | None
    new_stage: ConditionStage | None
    stage_changed: bool
    total_severity: int
```

Add `ConditionStage` to the TYPE_CHECKING imports at the top of the file.

- [ ] **Step 2: Add fields to ConditionStage model**

In `src/world/conditions/models.py`, add to `ConditionStage` after the `severity_multiplier` field:

```python
    # Severity-driven progression (alternative to time-based rounds_to_next)
    severity_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "When accumulated severity reaches this value, "
            "condition advances to this stage. Null = time-based only."
        ),
    )

    # Per-cast consequence pool (fires on every action while at this stage)
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="condition_stages",
        help_text="Consequence pool that fires per action while at this stage.",
    )
```

- [ ] **Step 3: Update ConditionStageFactory**

In `src/world/conditions/factories.py`, update `ConditionStageFactory` to add defaults:

```python
    severity_threshold = None
    consequence_pool = None
```

- [ ] **Step 4: Generate and apply migration**

Run: `uv run arx manage makemigrations conditions`
Then: `uv run arx manage migrate`

- [ ] **Step 5: Write tests for advance_condition_severity()**

Append a new test class to `src/world/conditions/tests/test_services.py`:

```python
class AdvanceConditionSeverityTests(TestCase):
    """Tests for severity-driven stage advancement."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory()
        cls.template = ConditionTemplateFactory(
            has_progression=True,
            is_stackable=False,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.template,
            stage_order=1,
            name="Strain",
            severity_threshold=1,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.template,
            stage_order=2,
            name="Fracture",
            severity_threshold=10,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.template,
            stage_order=3,
            name="Collapse",
            severity_threshold=25,
            severity_multiplier=Decimal("1.00"),
            rounds_to_next=None,
        )

    def test_advance_within_stage(self) -> None:
        """Severity increases without crossing threshold — stage unchanged."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        # Instance starts at severity=1, stage=stage1
        advance_result = advance_condition_severity(instance, 5)
        instance.refresh_from_db()
        assert instance.severity == 6
        assert instance.current_stage == self.stage1
        assert not advance_result.stage_changed
        assert advance_result.total_severity == 6

    def test_advance_crosses_threshold(self) -> None:
        """Severity crossing threshold advances to next stage."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_result = advance_condition_severity(instance, 12)
        instance.refresh_from_db()
        assert instance.severity == 13
        assert instance.current_stage == self.stage2
        assert advance_result.stage_changed
        assert advance_result.previous_stage == self.stage1
        assert advance_result.new_stage == self.stage2

    def test_advance_skips_stages(self) -> None:
        """Large severity jump can skip intermediate stages."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_result = advance_condition_severity(instance, 30)
        instance.refresh_from_db()
        assert instance.severity == 31
        assert instance.current_stage == self.stage3
        assert advance_result.stage_changed
        assert advance_result.previous_stage == self.stage1
        assert advance_result.new_stage == self.stage3

    def test_advance_at_final_stage(self) -> None:
        """Severity keeps accumulating past final stage without error."""
        result = apply_condition(self.character, self.template)
        instance = result.instance
        advance_condition_severity(instance, 30)  # reach stage3
        advance_result = advance_condition_severity(instance, 50)
        instance.refresh_from_db()
        assert instance.severity == 81
        assert instance.current_stage == self.stage3
        assert not advance_result.stage_changed

    def test_advance_no_severity_threshold_stages_ignored(self) -> None:
        """Stages without severity_threshold are not considered."""
        # Use a separate template to avoid polluting shared test data
        template = ConditionTemplateFactory(has_progression=True, is_stackable=False)
        s1 = ConditionStageFactory(
            condition=template, stage_order=1, name="S1",
            severity_threshold=1, rounds_to_next=None,
        )
        ConditionStageFactory(
            condition=template, stage_order=2, name="Time-Only",
            severity_threshold=None, rounds_to_next=5,
        )
        s3 = ConditionStageFactory(
            condition=template, stage_order=3, name="S3",
            severity_threshold=25, rounds_to_next=None,
        )
        result = apply_condition(self.character, template)
        instance = result.instance
        advance_condition_severity(instance, 30)
        instance.refresh_from_db()
        assert instance.current_stage == s3
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run arx test conditions.tests.test_services.AdvanceConditionSeverityTests --keepdb`
Expected: FAIL — `advance_condition_severity` not defined

- [ ] **Step 7: Implement advance_condition_severity()**

Append to `src/world/conditions/services.py`:

```python
def advance_condition_severity(
    instance: ConditionInstance,
    amount: int,
) -> SeverityAdvanceResult:
    """Increment a condition's severity and advance stage if threshold crossed.

    Used for conditions like Anima Warp where severity accumulates from
    external events rather than being set once at creation.

    Stages with severity_threshold=None are ignored (time-based only).
    Can skip multiple stages if the severity jump is large enough.
    """
    previous_stage = instance.current_stage
    instance.severity += amount

    # Find the highest severity-threshold stage that's been reached
    new_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=instance.severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    stage_changed = False
    if new_stage and new_stage != previous_stage:
        instance.current_stage = new_stage
        stage_changed = True

    instance.save(update_fields=["severity", "current_stage"])

    return SeverityAdvanceResult(
        previous_stage=previous_stage,
        new_stage=instance.current_stage,
        stage_changed=stage_changed,
        total_severity=instance.severity,
    )
```

Add the necessary imports at the top of the function or in the file's import block:
- `from world.conditions.types import SeverityAdvanceResult`

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run arx test conditions.tests.test_services.AdvanceConditionSeverityTests --keepdb`
Expected: All 5 tests PASS

- [ ] **Step 9: Run full conditions test suite**

Run: `uv run arx test conditions --keepdb`
Expected: All existing tests still pass

- [ ] **Step 10: Commit**

```
git add src/world/conditions/
git commit -m "feat(conditions): add severity-driven stage advancement

Add severity_threshold and consequence_pool fields to ConditionStage.
New advance_condition_severity() increments severity and advances stage
when thresholds are crossed. Supports stage-skipping on large jumps."
```

---

### Task 2: WarpConfig, MishapPoolTier, TechniqueOutcomeModifier Models

**Files:**
- Modify: `src/world/magic/models.py` (append)
- Modify: `src/world/magic/factories.py` (append)
- Modify: `src/world/magic/admin.py` (register new models)
- Test: `src/world/magic/tests/test_models.py` (append)

Three new SharedMemoryModel config tables in the magic app.

- [ ] **Step 1: Add WarpConfig model**

Append to `src/world/magic/models.py`:

```python
class WarpConfig(SharedMemoryModel):
    """Global configuration for Warp severity accumulation and resilience checks.

    Single-row table (queried with .first()), same pattern as AudereThreshold.
    """

    warp_threshold_ratio = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text=(
            "Anima ratio (current/max) below which technique use "
            "accumulates Warp severity. E.g., 0.30 = below 30%%."
        ),
    )
    severity_scale = models.PositiveIntegerField(
        help_text="Base scaling factor for converting depletion into severity.",
    )
    deficit_scale = models.PositiveIntegerField(
        help_text="Additional scaling factor for deficit (anima spent beyond zero).",
    )
    resilience_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        help_text="Check type for Warp resilience (e.g., magical endurance).",
    )
    base_check_difficulty = models.PositiveIntegerField(
        help_text="Base difficulty for the resilience check before stage modifiers.",
    )

    class Meta:
        verbose_name = "Warp Configuration"
        verbose_name_plural = "Warp Configurations"

    def __str__(self) -> str:
        return f"WarpConfig(threshold={self.warp_threshold_ratio}, scale={self.severity_scale})"
```

- [ ] **Step 2: Add MishapPoolTier model**

Append to `src/world/magic/models.py`:

```python
class MishapPoolTier(SharedMemoryModel):
    """Maps control deficit ranges to consequence pools for imprecision mishaps.

    Ranges must not overlap. Validated via clean().
    Control mishap pools must never contain character_loss consequences.
    """

    min_deficit = models.PositiveIntegerField(
        help_text="Minimum control deficit for this tier (inclusive).",
    )
    max_deficit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum control deficit for this tier (inclusive). Null = no upper bound.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.CASCADE,
        related_name="mishap_tiers",
        help_text="Consequence pool for this deficit range.",
    )

    def __str__(self) -> str:
        upper = self.max_deficit or "∞"
        return f"Mishap {self.min_deficit}-{upper}"

    def clean(self) -> None:
        """Validate that this tier's range does not overlap with existing tiers."""
        from django.core.exceptions import ValidationError

        overlapping = MishapPoolTier.objects.exclude(pk=self.pk)
        if self.max_deficit is not None:
            overlapping = overlapping.filter(
                min_deficit__lte=self.max_deficit,
            ).exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        else:
            # Unbounded upper — overlaps anything with min_deficit >= our min
            overlapping = overlapping.exclude(
                max_deficit__isnull=False,
                max_deficit__lt=self.min_deficit,
            )
        if overlapping.exists():
            raise ValidationError("Deficit range overlaps with an existing MishapPoolTier.")
```

- [ ] **Step 3: Add TechniqueOutcomeModifier model**

Append to `src/world/magic/models.py`:

```python
class TechniqueOutcomeModifier(SharedMemoryModel):
    """Maps technique check outcome tiers to signed modifiers for the Warp resilience check.

    When a character uses a technique while in Warp, the technique's check outcome
    modifies the subsequent resilience check. Botching penalizes; critting helps.
    """

    outcome = models.OneToOneField(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="technique_warp_modifier",
        help_text="The technique check outcome tier.",
    )
    modifier_value = models.IntegerField(
        help_text="Signed modifier applied to the Warp resilience check. Negative = penalty.",
    )

    class Meta:
        verbose_name = "Technique Outcome Modifier"
        verbose_name_plural = "Technique Outcome Modifiers"

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        return f"{self.outcome}: {sign}{self.modifier_value} to resilience"
```

- [ ] **Step 4: Add factories**

Append to `src/world/magic/factories.py`:

```python
class WarpConfigFactory(DjangoModelFactory):
    """Factory for WarpConfig."""

    class Meta:
        model = WarpConfig

    warp_threshold_ratio = Decimal("0.30")
    severity_scale = 10
    deficit_scale = 5
    resilience_check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    base_check_difficulty = 15


class MishapPoolTierFactory(DjangoModelFactory):
    """Factory for MishapPoolTier."""

    class Meta:
        model = MishapPoolTier

    min_deficit = 1
    max_deficit = None
    consequence_pool = factory.SubFactory("actions.factories.ConsequencePoolFactory")


class TechniqueOutcomeModifierFactory(DjangoModelFactory):
    """Factory for TechniqueOutcomeModifier."""

    class Meta:
        model = TechniqueOutcomeModifier

    outcome = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")
    modifier_value = 0
```

Add `from decimal import Decimal` to imports if not already present.

- [ ] **Step 5: Register in admin**

In `src/world/magic/admin.py`, add simple admin registrations for all three models.

- [ ] **Step 6: Generate and apply migration**

Run: `uv run arx manage makemigrations magic`
Then: `uv run arx manage migrate`

- [ ] **Step 7: Write model tests**

Append to `src/world/magic/tests/test_models.py` (or create if needed):

```python
class MishapPoolTierCleanTests(TestCase):
    """Tests for MishapPoolTier overlap validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.pool1 = ConsequencePoolFactory()
        cls.pool2 = ConsequencePoolFactory()

    def test_non_overlapping_tiers_valid(self) -> None:
        """Tiers with distinct ranges pass validation."""
        tier1 = MishapPoolTierFactory(min_deficit=1, max_deficit=5, consequence_pool=self.pool1)
        tier2 = MishapPoolTier(min_deficit=6, max_deficit=None, consequence_pool=self.pool2)
        tier2.clean()  # should not raise

    def test_overlapping_tiers_raise(self) -> None:
        """Overlapping ranges fail validation."""
        tier1 = MishapPoolTierFactory(min_deficit=1, max_deficit=10, consequence_pool=self.pool1)
        tier2 = MishapPoolTier(min_deficit=5, max_deficit=15, consequence_pool=self.pool2)
        with self.assertRaises(ValidationError):
            tier2.clean()
```

- [ ] **Step 8: Run tests**

Run: `uv run arx test magic.tests.test_models --keepdb`
Expected: PASS

- [ ] **Step 9: Commit**

```
git add src/world/magic/
git commit -m "feat(magic): add WarpConfig, MishapPoolTier, TechniqueOutcomeModifier

Three new config models for Scope #3:
- WarpConfig: anima threshold, severity scaling, resilience check config
- MishapPoolTier: control deficit ranges to consequence pools
- TechniqueOutcomeModifier: technique outcome to resilience check modifier"
```

---

### Task 3: MAGICAL_SCARS Effect Type and Handler

**Files:**
- Modify: `src/world/checks/constants.py:6-16` (add choice)
- Modify: `src/world/checks/models.py:233-245` (add to _REQUIRED_FIELDS)
- Modify: `src/world/mechanics/effect_handlers.py` (add handler)
- Test: `src/world/mechanics/tests/test_effect_handlers.py` (append, or create)

- [ ] **Step 1: Add MAGICAL_SCARS to EffectType**

In `src/world/checks/constants.py`, add after GRANT_CODEX:

```python
    MAGICAL_SCARS = "magical_scars", "Magical Scars"
```

- [ ] **Step 2: Add to _REQUIRED_FIELDS**

In `src/world/checks/models.py`, add to the `_REQUIRED_FIELDS` dict:

```python
        EffectType.MAGICAL_SCARS: [("condition_template", "condition_template_id")],
```

This reuses the `condition_template` FK — the authored entry points at a placeholder "Magical Scars" ConditionTemplate.

- [ ] **Step 3: Write test for handler**

```python
class MagicalScarsHandlerTests(TestCase):
    """Tests for the MAGICAL_SCARS effect handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory()
        cls.scar_template = ConditionTemplateFactory(
            name="Magical Scars",
            default_duration_type=DurationType.PERMANENT,
        )
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.MAGICAL_SCARS,
            condition_template=cls.scar_template,
        )

    def test_magical_scars_applies_condition(self) -> None:
        """MAGICAL_SCARS handler applies the pointed-to condition template."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        assert result.applied
        assert ConditionInstance.objects.filter(
            target=self.character,
            condition=self.scar_template,
        ).exists()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run arx test mechanics.tests.test_effect_handlers.MagicalScarsHandlerTests --keepdb`
Expected: FAIL — handler not registered

- [ ] **Step 5: Implement handler**

In `src/world/mechanics/effect_handlers.py`, add the handler function (near `_apply_condition`):

```python
def _apply_magical_scars(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply a magical scars condition (stub for future alteration system).

    Currently identical to _apply_condition. When the full magical alteration
    system is built, this handler will be replaced to call a resolution function
    that considers the character's resonances, affinity, and Warp state.
    """
    target = _resolve_target(effect, context)
    severity = effect.condition_severity or 1
    apply_condition(target, effect.condition_template, severity=severity)
    condition_name = effect.condition_template.name
    return AppliedEffect(
        effect_type=EffectType.MAGICAL_SCARS,
        description=f"Magical scars: {condition_name} (severity {severity}) on {target.db_key}",
        applied=True,
    )
```

Register it:

```python
_HANDLER_REGISTRY[EffectType.MAGICAL_SCARS] = _apply_magical_scars
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run arx test mechanics.tests.test_effect_handlers.MagicalScarsHandlerTests --keepdb`
Expected: PASS

- [ ] **Step 7: Generate migration for EffectType change**

The EffectType is a CharField with choices — Django may or may not need a migration depending on whether the choices are enforced at DB level. Check: `uv run arx manage makemigrations checks`. If no changes detected, that's fine.

- [ ] **Step 8: Commit**

```
git add src/world/checks/ src/world/mechanics/
git commit -m "feat(checks): add MAGICAL_SCARS effect type and handler

Stub handler applies a condition template, identical to APPLY_CONDITION.
Will be replaced when the full magical alteration system is built to
consider character resonances, affinity, and Warp state."
```

---

### Task 4: Warp Severity Calculation, Warning, and Mishap Pool Lookup

**Files:**
- Modify: `src/world/magic/types.py` (replace OverburnSeverity, update TechniqueUseResult)
- Modify: `src/world/magic/services.py` (add calculate_warp_severity, get_warp_warning, rewrite select_mishap_pool, remove old functions)
- Test: `src/world/magic/tests/test_anima_services.py` (append)

These are the pure calculation and lookup functions, tested independently before wiring into use_technique().

- [ ] **Step 1: Update types**

In `src/world/magic/types.py`:

Remove `OverburnSeverity` dataclass (lines 90-95).

Add:

```python
@dataclass
class WarpWarning:
    """Warning information for the safety checkpoint based on current Warp stage."""

    stage_name: str
    stage_description: str
    has_death_risk: bool  # True if current stage's pool has character_loss consequences


@dataclass
class WarpResult:
    """Result of Warp accumulation in Step 7 of use_technique()."""

    severity_added: int
    stage_name: str | None
    stage_advanced: bool
    resilience_check: CheckResult | None = None
    stage_consequence: AppliedEffect | None = None
```

Update `TechniqueUseResult`:
- Remove `overburn_severity: OverburnSeverity | None = None`
- Remove `warp_multiplier_applied: int = 1`
- Add `warp_result: WarpResult | None = None`
- Add `warp_warning: WarpWarning | None = None`
- Rename `confirmed` field semantics in docstring (no rename needed in code — still a bool)

- [ ] **Step 2: Write tests for calculate_warp_severity**

Append to `src/world/magic/tests/test_anima_services.py`:

```python
class CalculateWarpSeverityTests(TestCase):
    """Tests for Warp severity calculation from anima state."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.check_type = CheckTypeFactory()
        cls.config = WarpConfigFactory(
            warp_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.check_type,
            base_check_difficulty=15,
        )

    def test_above_threshold_no_severity(self) -> None:
        """Anima above threshold produces zero severity."""
        result = calculate_warp_severity(
            current_anima=50, max_anima=100, deficit=0, config=self.config,
        )
        assert result == 0

    def test_at_threshold_no_severity(self) -> None:
        """Anima exactly at threshold produces zero severity."""
        result = calculate_warp_severity(
            current_anima=30, max_anima=100, deficit=0, config=self.config,
        )
        assert result == 0

    def test_below_threshold_produces_severity(self) -> None:
        """Anima below threshold produces positive severity."""
        result = calculate_warp_severity(
            current_anima=15, max_anima=100, deficit=0, config=self.config,
        )
        assert result > 0

    def test_empty_anima_max_depletion_severity(self) -> None:
        """Zero anima with no deficit produces maximum depletion severity."""
        result = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=0, config=self.config,
        )
        # depletion = (0.30 - 0.0) / 0.30 = 1.0, severity = ceil(10 * 1.0) = 10
        assert result == 10

    def test_deficit_adds_severity(self) -> None:
        """Deficit adds severity on top of depletion."""
        no_deficit = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=0, config=self.config,
        )
        with_deficit = calculate_warp_severity(
            current_anima=0, max_anima=100, deficit=10, config=self.config,
        )
        # deficit contribution: ceil(5 * 10) = 50
        assert with_deficit == no_deficit + 50

    def test_severity_scales_with_depletion(self) -> None:
        """More depletion = more severity."""
        mild = calculate_warp_severity(
            current_anima=20, max_anima=100, deficit=0, config=self.config,
        )
        severe = calculate_warp_severity(
            current_anima=5, max_anima=100, deficit=0, config=self.config,
        )
        assert severe > mild
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run arx test magic.tests.test_anima_services.CalculateWarpSeverityTests --keepdb`
Expected: FAIL — `calculate_warp_severity` not defined

- [ ] **Step 4: Implement calculate_warp_severity**

In `src/world/magic/services.py`:

```python
def calculate_warp_severity(
    current_anima: int,
    max_anima: int,
    deficit: int,
    config: WarpConfig,
) -> int:
    """Compute Warp severity contribution from post-deduction anima state.

    Returns 0 if anima ratio is at or above the threshold. Otherwise,
    returns severity scaled by how far below the threshold the ratio is,
    plus additional severity from any deficit (anima spent beyond zero).
    """
    from decimal import Decimal as D
    from math import ceil

    if max_anima <= 0:
        return 0

    ratio = D(current_anima) / D(max_anima)
    threshold = config.warp_threshold_ratio

    if ratio >= threshold:
        return 0

    # How far below the threshold (0.0 = at threshold, 1.0 = empty)
    depletion = float((threshold - ratio) / threshold)
    severity = ceil(config.severity_scale * depletion)

    if deficit > 0:
        severity += ceil(config.deficit_scale * deficit)

    return severity
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run arx test magic.tests.test_anima_services.CalculateWarpSeverityTests --keepdb`
Expected: PASS

- [ ] **Step 6: Implement get_warp_warning**

In `src/world/magic/services.py`:

```python
def get_warp_warning(character: ObjectDB) -> WarpWarning | None:
    """Return the current Warp stage warning for the safety checkpoint.

    Returns None if the character has no active Anima Warp condition.
    """
    from world.conditions.models import ConditionInstance

    warp_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=ANIMA_WARP_CONDITION_NAME,
        )
        .select_related("current_stage", "current_stage__consequence_pool")
        .first()
    )

    if warp_instance is None or warp_instance.current_stage is None:
        return None

    stage = warp_instance.current_stage
    has_death_risk = False
    if stage.consequence_pool_id:
        from world.checks.models import Consequence

        has_death_risk = Consequence.objects.filter(
            consequence_pool_entries__pool=stage.consequence_pool,
            character_loss=True,
        ).exists()

    return WarpWarning(
        stage_name=stage.name,
        stage_description=stage.description,
        has_death_risk=has_death_risk,
    )
```

Import `ANIMA_WARP_CONDITION_NAME` from `world.magic.audere` at the top of the file (if not already imported).

- [ ] **Step 7: Rewrite select_mishap_pool**

Replace the existing stub `select_mishap_pool()` in `src/world/magic/services.py`:

```python
def select_mishap_pool(control_deficit: int) -> ConsequencePool | None:
    """Select a control mishap consequence pool based on deficit magnitude.

    Queries MishapPoolTier for the matching deficit range. Returns None
    if no tier matches (deficit too small or no tiers authored).
    """
    from world.magic.models import MishapPoolTier

    tier = (
        MishapPoolTier.objects.filter(min_deficit__lte=control_deficit)
        .filter(
            models.Q(max_deficit__gte=control_deficit) | models.Q(max_deficit__isnull=True),
        )
        .order_by("-min_deficit")
        .first()
    )
    return tier.consequence_pool if tier else None
```

- [ ] **Step 8: Write unit tests for get_warp_warning**

Append to `src/world/magic/tests/test_anima_services.py`:

```python
class GetWarpWarningTests(TestCase):
    """Tests for get_warp_warning."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory()
        cls.warp_template = ConditionTemplateFactory(
            name=ANIMA_WARP_CONDITION_NAME,
            has_progression=True,
            is_stackable=False,
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.warp_template,
            stage_order=1,
            name="Strain",
            severity_threshold=1,
            consequence_pool=None,
        )

    def test_no_warp_returns_none(self) -> None:
        assert get_warp_warning(self.character) is None

    def test_warp_present_returns_warning(self) -> None:
        result = apply_condition(self.character, self.warp_template)
        result.instance.current_stage = self.stage1
        result.instance.save(update_fields=["current_stage"])
        warning = get_warp_warning(self.character)
        assert warning is not None
        assert warning.stage_name == "Strain"
        assert not warning.has_death_risk
```

- [ ] **Step 9: Write unit tests for select_mishap_pool**

Append to `src/world/magic/tests/test_anima_services.py`:

```python
class SelectMishapPoolTests(TestCase):
    """Tests for select_mishap_pool with MishapPoolTier."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.minor_pool = ConsequencePoolFactory(name="Minor Mishaps")
        cls.severe_pool = ConsequencePoolFactory(name="Severe Mishaps")
        MishapPoolTierFactory(
            min_deficit=1, max_deficit=5, consequence_pool=cls.minor_pool,
        )
        MishapPoolTierFactory(
            min_deficit=6, max_deficit=None, consequence_pool=cls.severe_pool,
        )

    def test_no_match_returns_none(self) -> None:
        assert select_mishap_pool(0) is None

    def test_low_deficit_returns_minor(self) -> None:
        assert select_mishap_pool(3) == self.minor_pool

    def test_high_deficit_returns_severe(self) -> None:
        assert select_mishap_pool(10) == self.severe_pool

    def test_boundary_returns_correct_tier(self) -> None:
        assert select_mishap_pool(5) == self.minor_pool
        assert select_mishap_pool(6) == self.severe_pool
```

- [ ] **Step 10: Remove old functions and update existing tests**

Remove from `src/world/magic/services.py`:
- `get_overburn_severity()` (lines 275-296)
- `_get_warp_multiplier()` (lines 317-331)
- `_DEATH_RISK_THRESHOLD` and `_DANGEROUS_THRESHOLD` constants (lines 271-272)
- `OverburnSeverity` import (line 20)

Remove from `src/world/magic/types.py`:
- `OverburnSeverity` dataclass (lines 90-95)

Update existing tests — these files reference removed symbols:
- `src/world/magic/tests/test_anima_services.py`: Delete `OverburnSeverityTests` class (lines 100-113), remove imports of `get_overburn_severity` and `OverburnSeverity`
- `src/world/magic/tests/test_use_technique.py`: Remove references to `overburn_severity` in assertions (lines 53, 101), delete `test_warp_multiplier_applied_during_audere` and its counterpart (lines 187-202), remove `warp_multiplier_applied` assertions

Do NOT update `confirm_overburn` references yet — that is in Task 5.

- [ ] **Step 11: Run full magic test suite**

Run: `uv run arx test magic --keepdb`
Expected: PASS — all old tests updated, new unit tests pass

- [ ] **Step 12: Commit**

```
git add src/world/magic/
git commit -m "feat(magic): add Warp severity calc, warning, and mishap pool lookup

- calculate_warp_severity(): anima ratio to severity with threshold
- get_warp_warning(): Warp stage-driven safety checkpoint
- select_mishap_pool(): queries MishapPoolTier by deficit range
- Remove OverburnSeverity, get_overburn_severity, _get_warp_multiplier"
```

---

### Task 5: Rewrite use_technique() Pipeline (Steps 3, 7, 8)

**Files:**
- Modify: `src/world/magic/services.py:345-424` (rewrite use_technique)
- Test: `src/world/magic/tests/test_anima_services.py` (update existing use_technique tests)

This task rewrites the three changed steps and updates existing unit tests.

- [ ] **Step 1: Rewrite use_technique()**

Replace the existing `use_technique()` function. Key changes:

- Rename `confirm_overburn` parameter to `confirm_warp_risk`
- **Step 3:** Replace deficit-based checkpoint with `get_warp_warning()`. If warning exists and `confirm_warp_risk` is False, return early with the warning.
- **Step 7:** After deduction, call `calculate_warp_severity()`. If severity > 0, look up or create Warp condition, call `advance_condition_severity()`. If current stage has a `consequence_pool`, perform resilience check (with technique outcome modifier) and select consequence.
- **Step 8:** Call rewritten `select_mishap_pool()` instead of stub.

```python
def use_technique(
    *,
    character: ObjectDB,
    technique: Technique,
    resolve_fn: Callable[..., Any],
    confirm_warp_risk: bool = True,
    check_result: CheckResult | None = None,
) -> TechniqueUseResult:
    """Orchestrate technique use: cost -> checkpoint -> resolve -> warp -> mishap.

    Args:
        character: The character using the technique.
        technique: The technique being used.
        resolve_fn: Callable that performs the actual resolution.
        confirm_warp_risk: Whether the player confirms despite Warp warning.
        check_result: If provided, reused for mishap consequence selection.

    Returns:
        TechniqueUseResult with cost info, resolution, warp, and mishap.
    """
    from world.conditions.models import ConditionInstance, ConditionTemplate
    from world.conditions.services import advance_condition_severity, apply_condition
    from world.magic.audere import ANIMA_WARP_CONDITION_NAME
    from world.magic.models import TechniqueOutcomeModifier, WarpConfig

    # Step 1: Calculate runtime stats
    stats = get_runtime_technique_stats(technique, character)

    # Step 2: Calculate effective anima cost
    anima = CharacterAnima.objects.get(character=character)
    cost = calculate_effective_anima_cost(
        base_cost=technique.anima_cost,
        runtime_intensity=stats.intensity,
        runtime_control=stats.control,
        current_anima=anima.current,
    )

    # Step 3: Safety checkpoint (Warp stage-driven)
    warp_warning = get_warp_warning(character)

    if warp_warning and not confirm_warp_risk:
        return TechniqueUseResult(
            anima_cost=cost,
            warp_warning=warp_warning,
            confirmed=False,
        )

    # Step 4: Deduct anima
    deficit = deduct_anima(character, cost.effective_cost)

    # Steps 5 + 6: Resolution
    resolution_result = resolve_fn()

    # Step 7: Warp accumulation and stage consequences
    warp_result = None
    warp_config = WarpConfig.objects.first()
    if warp_config:
        anima.refresh_from_db()
        warp_severity = calculate_warp_severity(
            current_anima=anima.current,
            max_anima=anima.maximum,
            deficit=deficit,
            config=warp_config,
        )

        if warp_severity > 0:
            warp_result = _handle_warp_accumulation(
                character=character,
                warp_severity=warp_severity,
                warp_config=warp_config,
                technique_check_result=check_result,
            )

    # Step 8: Mishap rider
    mishap = None
    control_deficit = stats.intensity - stats.control
    if control_deficit > 0:
        pool = select_mishap_pool(control_deficit)
        if pool is not None and check_result is not None:
            mishap = _resolve_mishap(character, pool, check_result)

    return TechniqueUseResult(
        anima_cost=cost,
        warp_warning=warp_warning,
        confirmed=True,
        resolution_result=resolution_result,
        warp_result=warp_result,
        mishap=mishap,
    )
```

- [ ] **Step 2: Implement _handle_warp_accumulation helper**

```python
def _handle_warp_accumulation(
    *,
    character: ObjectDB,
    warp_severity: int,
    warp_config: WarpConfig,
    technique_check_result: CheckResult | None,
) -> WarpResult:
    """Handle Warp severity accumulation, stage advancement, and stage consequence pool."""
    from world.checks.consequence_resolution import (
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.services import perform_check
    from world.checks.types import ResolutionContext
    from world.conditions.models import ConditionInstance, ConditionTemplate
    from world.conditions.services import advance_condition_severity, apply_condition
    from world.magic.audere import ANIMA_WARP_CONDITION_NAME
    from world.magic.models import TechniqueOutcomeModifier

    # Find or create Warp condition
    warp_instance = ConditionInstance.objects.filter(
        target=character,
        condition__name=ANIMA_WARP_CONDITION_NAME,
    ).select_related("current_stage").first()

    if warp_instance is None:
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(target=character, condition=warp_template)
        warp_instance = result.instance
        # apply_condition creates with severity=1. Use advance_condition_severity
        # to set the real severity and resolve the correct stage.
        advance_result = advance_condition_severity(warp_instance, warp_severity - 1)
        warp_instance.refresh_from_db()

        return WarpResult(
            severity_added=warp_severity,
            stage_name=warp_instance.current_stage.name if warp_instance.current_stage else None,
            stage_advanced=warp_instance.current_stage is not None,
        )

    # Advance existing condition
    advance_result = advance_condition_severity(warp_instance, warp_severity)
    warp_instance.refresh_from_db()

    # Fire stage consequence pool if present
    resilience_check = None
    stage_consequence = None
    current_stage = warp_instance.current_stage

    if current_stage and current_stage.consequence_pool_id:
        from actions.services import get_effective_consequences

        consequences = get_effective_consequences(current_stage.consequence_pool)
        if consequences:
            # Build resilience check modifiers from two sources:
            # 1. Stage penalty via ConditionCheckModifier (escalating per stage)
            from world.conditions.models import ConditionCheckModifier

            stage_modifier = 0
            stage_check_mod = ConditionCheckModifier.objects.filter(
                stage=current_stage,
                check_type=warp_config.resilience_check_type,
            ).first()
            if stage_check_mod:
                stage_modifier = stage_check_mod.modifier_value

            # 2. Technique outcome modifier (botch = penalty, crit = bonus)
            outcome_modifier = 0
            if technique_check_result and technique_check_result.outcome:
                outcome_mod = TechniqueOutcomeModifier.objects.filter(
                    outcome=technique_check_result.outcome,
                ).first()
                if outcome_mod:
                    outcome_modifier = outcome_mod.modifier_value

            total_modifier = stage_modifier + outcome_modifier

            # Perform resilience check
            resilience_check = perform_check(
                character=character,
                check_type=warp_config.resilience_check_type,
                target_difficulty=warp_config.base_check_difficulty,
                extra_modifiers=total_modifier,
            )

            # Select and apply consequence
            pending = select_consequence_from_result(
                character, resilience_check, consequences,
            )
            context = ResolutionContext(character=character)
            applied = apply_resolution(pending, context)
            if applied:
                stage_consequence = applied[0]

    return WarpResult(
        severity_added=warp_severity,
        stage_name=current_stage.name if current_stage else None,
        stage_advanced=advance_result.stage_changed,
        resilience_check=resilience_check,
        stage_consequence=stage_consequence,
    )
```

- [ ] **Step 3: Rename confirm_overburn across all call sites**

Rename `confirm_overburn` to `confirm_warp_risk` in all files that reference it:
- `src/world/magic/tests/test_use_technique.py`: lines 97, 116 — rename kwarg
- `src/world/mechanics/tests/test_pipeline_integration.py`: lines 964, 991 — rename kwarg
- Update `overburn_severity` assertions to use `warp_warning` / `warp_result` in:
  - `src/world/magic/tests/test_use_technique.py`: lines 53, 101
  - `src/world/mechanics/tests/test_pipeline_integration.py`: lines 944, 969

- [ ] **Step 4: Run magic test suite**

Run: `uv run arx test magic --keepdb`
Expected: PASS (after fixing updated references)

- [ ] **Step 5: Commit**

```
git add src/world/magic/
git commit -m "feat(magic): rewrite use_technique steps 3, 7, 8 for Warp progression

Step 3: Warp-stage-driven safety checkpoint replaces deficit-based
Step 7: Warp severity accumulation with resilience check + stage pool
Step 8: select_mishap_pool queries MishapPoolTier for real pools"
```

---

### Task 6: Pipeline Integration Tests

**Files:**
- Modify: `src/world/mechanics/tests/test_pipeline_integration.py` (append new test class)

This task adds the `WarpProgressionTests` class to the pipeline integration tests, exercising the full technique use flow with Warp accumulation, stage consequences, and control mishaps.

- [ ] **Step 1: Write WarpProgressionTests setup**

Append a new class after `RuntimeModifierTests`. The setup needs:
- Anima Warp condition template with 3 stages (severity thresholds 1, 10, 25)
- ConditionCheckModifier records on each stage for the resilience check type (escalating penalties)
- Consequence pools for each stage with consequences at various outcome tiers
- WarpConfig with threshold, scales, check type, difficulty
- MishapPoolTier with a pool for control deficits
- TechniqueOutcomeModifier entries for at least two outcome tiers
- A late-stage consequence with `character_loss=True`
- A consequence with `MAGICAL_SCARS` effect type

```python
class WarpProgressionTests(PipelineTestMixin, TestCase):
    """End-to-end tests for Warp progression and consequence streams."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # ... (full setup in implementation)
```

- [ ] **Step 2: Test — No Warp above threshold**

```python
    def test_no_warp_above_threshold(self) -> None:
        """Technique use with plenty of anima produces no Warp."""
        # Set anima high enough that ratio stays above threshold
        self.anima.current = self.anima.maximum
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
        )
        assert result.warp_result is None
```

- [ ] **Step 3: Test — Warp accumulation from low anima**

```python
    def test_warp_accumulation_from_low_anima(self) -> None:
        """Technique use below threshold creates Warp with correct severity."""
        # Set anima low enough to be below threshold after cost
        self.anima.current = 2
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
        )
        assert result.warp_result is not None
        assert result.warp_result.severity_added > 0
        # Verify condition exists
        assert ConditionInstance.objects.filter(
            target=self.character,
            condition__name=ANIMA_WARP_CONDITION_NAME,
        ).exists()
```

- [ ] **Step 4: Test — First Warp is unwarned**

```python
    def test_first_warp_is_unwarned(self) -> None:
        """Character with no Warp gets no warning before casting."""
        self.anima.current = 2
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
        )
        assert result.warp_warning is None
        assert result.confirmed is True
        # But Warp was accumulated
        assert result.warp_result is not None
```

- [ ] **Step 5: Test — Safety checkpoint from Warp stage**

```python
    def test_safety_checkpoint_from_warp_stage(self) -> None:
        """Character with existing Warp gets warning on next cast."""
        # Create Warp condition manually
        from world.conditions.services import apply_condition
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(self.character, warp_template)
        instance = result.instance
        instance.severity = 5
        instance.current_stage = self.stage1
        instance.save(update_fields=["severity", "current_stage"])

        # Cast without confirming
        self.anima.current = 2
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "should not be called",
            confirm_warp_risk=False,
        )
        assert result.confirmed is False
        assert result.warp_warning is not None
        assert result.warp_warning.stage_name == "Strain"
```

- [ ] **Step 6: Test — Resilience check drives consequence selection**

```python
    def test_resilience_check_drives_warp_consequence(self) -> None:
        """Warp stage consequence pool fires with resilience check."""
        # Put character at stage with consequence pool, very low anima
        from world.conditions.services import apply_condition
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(self.character, warp_template)
        instance = result.instance
        instance.severity = 10
        instance.current_stage = self.stage2  # stage with consequence pool
        instance.save(update_fields=["severity", "current_stage"])

        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
        )
        assert result.warp_result is not None
        assert result.warp_result.resilience_check is not None
```

- [ ] **Step 7: Test — Stage advancement through pipeline**

```python
    def test_severity_advances_stage_through_pipeline(self) -> None:
        """Repeated technique use accumulates severity and advances Warp stage."""
        # Start with existing Warp at stage 1
        from world.conditions.services import apply_condition
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(self.character, warp_template)
        instance = result.instance
        instance.severity = 9  # just below stage2 threshold of 10
        instance.current_stage = self.stage1
        instance.save(update_fields=["severity", "current_stage"])

        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
        )
        assert result.warp_result is not None
        assert result.warp_result.stage_advanced
        instance.refresh_from_db()
        assert instance.current_stage == self.stage2
```

- [ ] **Step 8: Test — Technique outcome modifies resilience check**

```python
    def test_technique_outcome_modifies_resilience_check(self) -> None:
        """Botching technique applies penalty to Warp resilience check."""
        from world.conditions.services import apply_condition
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(self.character, warp_template)
        instance = result.instance
        instance.severity = 10
        instance.current_stage = self.stage2
        instance.save(update_fields=["severity", "current_stage"])

        self.anima.current = 1
        self.anima.save(update_fields=["current"])

        # Use a check result that maps to a negative TechniqueOutcomeModifier
        bad_check = self._make_check_result(outcome=self.botch_outcome)

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
            check_result=bad_check,
        )
        assert result.warp_result is not None
        assert result.warp_result.resilience_check is not None
        # The botch penalty should have been applied to the resilience check
        # (exact outcome depends on authored data, but we can verify the check ran)
```

- [ ] **Step 9: Test — Control mishap fires independently of Warp**

```python
    def test_control_mishap_fires_independently(self) -> None:
        """Character with full anima and no Warp but intensity > control gets mishap."""
        self.anima.current = self.anima.maximum
        self.anima.save(update_fields=["current"])

        # Use a technique where intensity > control
        high_intensity_technique = TechniqueFactory(
            intensity=20,
            control=5,
            anima_cost=1,
        )
        TechniqueCapabilityGrantFactory(
            technique=high_intensity_technique,
            capability=self.capability,
        )

        result = use_technique(
            character=self.character,
            technique=high_intensity_technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
            check_result=self._make_check_result(),
        )
        assert result.mishap is not None
        assert result.warp_result is None  # anima is fine
```

- [ ] **Step 8: Test — Full flow (all three streams)**

```python
    def test_full_flow_all_three_streams(self) -> None:
        """Low anima + high intensity: warp warning, warp accumulation, and control mishap."""
        # Set up existing Warp
        from world.conditions.services import apply_condition
        warp_template = ConditionTemplate.objects.get(name=ANIMA_WARP_CONDITION_NAME)
        result = apply_condition(self.character, warp_template)
        instance = result.instance
        instance.severity = 10
        instance.current_stage = self.stage2
        instance.save(update_fields=["severity", "current_stage"])

        # Low anima + high intensity technique
        self.anima.current = 1
        self.anima.save(update_fields=["current"])
        high_intensity_technique = TechniqueFactory(
            intensity=20,
            control=5,
            anima_cost=1,
        )
        TechniqueCapabilityGrantFactory(
            technique=high_intensity_technique,
            capability=self.capability,
        )

        result = use_technique(
            character=self.character,
            technique=high_intensity_technique,
            resolve_fn=lambda: "resolved",
            confirm_warp_risk=True,
            check_result=self._make_check_result(),
        )
        # All three streams fire
        assert result.warp_warning is not None  # warned before cast
        assert result.warp_result is not None   # Warp accumulated
        assert result.mishap is not None         # control mishap fired
        assert result.confirmed is True
```

- [ ] **Step 9: Add helper method for check results**

The test class needs a helper `_make_check_result()` that creates a plausible CheckResult for reuse in mishap resolution. Check existing test classes in the file for the pattern they use.

- [ ] **Step 10: Run all integration tests**

Run: `uv run arx test mechanics.tests.test_pipeline_integration --keepdb`
Expected: All existing tests pass + all new WarpProgressionTests pass

- [ ] **Step 11: Run full regression across affected suites**

Run: `uv run arx test conditions magic mechanics checks actions --keepdb`
Expected: All pass

- [ ] **Step 12: Commit**

```
git add src/world/mechanics/tests/test_pipeline_integration.py
git commit -m "test(integration): add WarpProgressionTests for Scope #3

8 integration tests covering: Warp accumulation, stage advancement,
resilience checks, safety checkpoints, control mishaps, and the full
three-stream flow."
```

---

### Task 7: Cleanup and Documentation

**Files:**
- Modify: `docs/roadmap/magic.md` (update Scope #3 status)
- Modify: `docs/roadmap/capabilities-and-challenges.md` (note new effect type)

- [ ] **Step 1: Update magic roadmap**

In `docs/roadmap/magic.md`, update Scope #3 from design notes to DONE with a summary of what was built.

- [ ] **Step 2: Update capabilities roadmap**

Note the new MAGICAL_SCARS effect type and the MishapPoolTier infrastructure.

- [ ] **Step 2b: Add deprecation comment to AudereThreshold.warp_multiplier**

In `src/world/magic/audere.py`, add a comment on the `warp_multiplier` field noting it is no longer used by the Warp severity calculation (Scope #3 removed the dependency). The field can be removed in a future cleanup.

- [ ] **Step 3: Run ruff on all changed files**

Run: `ruff check src/world/conditions/ src/world/magic/ src/world/mechanics/ src/world/checks/ --fix`
Then: `ruff format src/world/conditions/ src/world/magic/ src/world/mechanics/ src/world/checks/`

- [ ] **Step 4: Final commit**

```
git add docs/roadmap/ src/
git commit -m "docs: update roadmap for Scope #3 completion"
```
