# Scope #4: Scene Magic — Technique-Enhanced Social Actions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire technique enhancement into scene social actions with the full consequence pipeline, so players can use magic to augment social interactions.

**Architecture:** Upgrade `respond_to_action_request()` to use `start_action_resolution()` (full pipeline) instead of `resolve_scene_action()` (pass/fail only). When a technique is attached, wrap the action resolution inside `use_technique()` so anima cost, Soulfray, and mishaps apply. The available-actions endpoint returns enhancement options with pre-calculated costs.

**Tech Stack:** Django/DRF backend, React/TypeScript frontend, FactoryBoy for tests, Evennia ObjectDB for characters.

**Spec:** `docs/superpowers/specs/2026-04-02-scope4-scene-magic-enhancement-design.md`

---

### Task 1: Refactor `use_technique()` to Extract CheckResult from resolve_fn Output

Currently `use_technique()` takes an external `check_result` parameter, but when wrapping `start_action_resolution()`, the check result is produced *inside* `resolve_fn()`. Steps 7 (Soulfray) and 8 (mishap) silently skip when `check_result` is None.

**Files:**
- Modify: `src/world/magic/services.py:373-447`
- Test: `src/world/magic/tests/test_services.py` (existing — add new test)

- [ ] **Step 1: Write failing test for check_result extraction**

In `src/world/magic/tests/test_services.py`, add a test that verifies `use_technique()` extracts `check_result` from a `PendingActionResolution` returned by `resolve_fn`:

```python
def test_use_technique_extracts_check_result_from_pending_resolution(self):
    """When resolve_fn returns PendingActionResolution, mishap uses its check_result."""
    from actions.types import PendingActionResolution, StepResult
    from world.checks.types import CheckResult

    mock_check_result = CheckResult(
        check_type=self.check_type,
        outcome=self.failure_outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    mock_resolution = PendingActionResolution(
        template_id=1,
        character_id=self.character.pk,
        target_difficulty=45,
        resolution_context_data={},
        current_phase="COMPLETE",
        main_result=StepResult(
            step_label="main",
            check_result=mock_check_result,
            consequence_id=None,
        ),
    )

    # Technique with control deficit to trigger mishap path
    self.technique.base_control = 1
    self.technique.base_intensity = 10
    self.technique.save(update_fields=["base_control", "base_intensity"])

    result = use_technique(
        character=self.character,
        technique=self.technique,
        resolve_fn=lambda: mock_resolution,
        confirm_soulfray_risk=True,
    )

    # The key assertion: mishap path was reached (not skipped due to None check_result)
    # Whether a mishap actually fires depends on pool existence, but the path was entered
    assert result.resolution_result is mock_resolution
```

- [ ] **Step 2: Run test to verify it fails**

Run: `arx test world.magic.tests.test_services -k test_use_technique_extracts_check_result --keepdb`

Expected: The test passes trivially OR the mishap assertion needs refinement — either way, confirm the current behavior.

- [ ] **Step 3: Implement check_result extraction in `use_technique()`**

In `src/world/magic/services.py`, after `resolve_fn()` returns (line 410), add extraction logic:

```python
    # Steps 5 + 6: Resolution
    resolution_result = resolve_fn()

    # Extract check_result from resolution if not provided explicitly
    effective_check_result = check_result
    if effective_check_result is None and hasattr(resolution_result, "main_result"):
        main = resolution_result.main_result
        if main is not None and hasattr(main, "check_result"):
            effective_check_result = main.check_result
```

Then replace all references to `check_result` in Steps 7 and 8 with `effective_check_result`:
- Line 429: `technique_check_result=effective_check_result`
- Line 437: `if pool is not None and effective_check_result is not None:`
- Line 438: `mishap = _resolve_mishap(character, pool, effective_check_result)`

- [ ] **Step 4: Run test to verify it passes**

Run: `arx test world.magic.tests.test_services --keepdb`

Expected: All existing tests pass plus the new one.

- [ ] **Step 5: Commit**

```bash
git add src/world/magic/services.py src/world/magic/tests/test_services.py
git commit -m "refactor: extract check_result from resolve_fn output in use_technique

Steps 7 (Soulfray) and 8 (mishap) now work when resolve_fn returns a
PendingActionResolution, enabling use_technique as a wrapper around
start_action_resolution."
```

---

### Task 2: Add EnhancedSceneActionResult Type and Update Scene Types

**Files:**
- Modify: `src/world/scenes/types.py`

- [ ] **Step 1: Add the new dataclass to `src/world/scenes/types.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from actions.types import PendingActionResolution
from world.magic.types import TechniqueUseResult


@dataclass
class EnhancedSceneActionResult:
    """Combined result of a social action, optionally technique-enhanced."""

    action_resolution: PendingActionResolution
    action_key: str
    technique_result: TechniqueUseResult | None = None
```

Keep the existing `PersonaPayload`, `InteractionPayload`, and `ReactionAggregation` TypedDicts in the same file.

- [ ] **Step 2: Verify import works**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb` (will fail if import is broken)

Alternatively, verify manually: `uv run python -c "import django; django.setup(); from world.scenes.types import EnhancedSceneActionResult; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/world/scenes/types.py
git commit -m "feat: add EnhancedSceneActionResult dataclass for layered action results"
```

---

### Task 3: Wire Technique FK into `create_action_request()`

The `SceneActionRequest.technique` FK exists but `create_action_request()` never accepts or stores it.

**Files:**
- Modify: `src/world/scenes/action_services.py:20-50`
- Test: `src/world/scenes/tests/test_scene_action_integration.py`

- [ ] **Step 1: Write failing test for technique validation**

In `src/world/scenes/tests/test_scene_action_integration.py`, add a new test class:

```python
from actions.models import ActionEnhancement
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory


class TestTechniqueEnhancementValidation(TestCase):
    """Validate technique attachment to action requests."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        cls.technique = TechniqueFactory(name="Mesmerizing Gaze")
        CharacterTechniqueFactory(
            character=cls.initiator.character,
            technique=cls.technique,
        )

    def test_create_request_with_valid_technique(self):
        """Technique is stored when ActionEnhancement exists and character knows it."""
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=self.technique,
        )

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
        )

        assert request.technique == self.technique

    def test_create_request_rejects_technique_without_enhancement(self):
        """Technique rejected when no ActionEnhancement record exists."""
        from django.core.exceptions import ValidationError

        rogue_technique = TechniqueFactory(name="Teleportation")
        CharacterTechniqueFactory(
            character=self.initiator.character,
            technique=rogue_technique,
        )

        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=rogue_technique,
            )

    def test_create_request_rejects_unknown_technique(self):
        """Technique rejected when character doesn't know it."""
        from django.core.exceptions import ValidationError

        unknown_technique = TechniqueFactory(name="Unknown Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Unknown Flirt",
            source_type="technique",
            technique=unknown_technique,
        )
        # Character does NOT have CharacterTechnique for this

        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=unknown_technique,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.scenes.tests.test_scene_action_integration -k TestTechniqueEnhancementValidation --keepdb`

Expected: FAIL — `create_action_request()` doesn't accept `technique` parameter.

- [ ] **Step 3: Implement technique parameter in `create_action_request()`**

In `src/world/scenes/action_services.py`, modify `create_action_request()`:

```python
def create_action_request(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    action_key: str,
    difficulty_choice: str = DifficultyChoice.NORMAL,
    technique: Technique | None = None,
) -> SceneActionRequest:
    """Create a pending action request for consent."""
    if technique is not None:
        _validate_technique_enhancement(
            technique=technique,
            action_key=action_key,
            character=initiator_persona.character,
        )

    return SceneActionRequest.objects.create(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=action_key,
        difficulty_choice=difficulty_choice,
        technique=technique,
    )
```

Add the validation helper:

```python
def _validate_technique_enhancement(
    *,
    technique: Technique,
    action_key: str,
    character: ObjectDB,
) -> None:
    """Validate technique can enhance this action for this character."""
    from django.core.exceptions import ValidationError

    from actions.models import ActionEnhancement
    from world.magic.models import CharacterTechnique

    if not ActionEnhancement.objects.filter(
        base_action_key=action_key,
        source_type="technique",
        technique=technique,
    ).exists():
        raise ValidationError(
            f"No enhancement exists for technique '{technique.name}' on action '{action_key}'."
        )

    if not CharacterTechnique.objects.filter(
        character=character,
        technique=technique,
    ).exists():
        raise ValidationError(
            f"Character does not know technique '{technique.name}'."
        )
```

Add the necessary imports at the top:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Technique
```

(Use runtime import inside the function to avoid circular imports, or TYPE_CHECKING if the FK resolution allows it. Check which pattern the codebase uses.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb`

Expected: All tests pass including the new validation tests.

- [ ] **Step 5: Commit**

```bash
git add src/world/scenes/action_services.py src/world/scenes/tests/test_scene_action_integration.py
git commit -m "feat: wire technique FK into create_action_request with validation

Validates ActionEnhancement record exists and character knows the
technique before storing on SceneActionRequest."
```

---

### Task 4: Upgrade `respond_to_action_request()` to Full Pipeline

Replace `resolve_scene_action()` with `start_action_resolution()` for all social actions. This gives mundane actions consequence pools.

**Files:**
- Modify: `src/world/scenes/action_services.py:53-120`
- Test: `src/world/scenes/tests/test_scene_action_integration.py`

- [ ] **Step 1: Write failing test for consequence application on mundane action**

```python
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance


class TestMundaneActionConsequences(TestCase):
    """Mundane social actions now apply consequences via full pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        # Create a consequence pool for Flirt
        cls.smitten_condition = ConditionTemplateFactory(name="Smitten")
        success_consequence = ConsequenceFactory(
            label="Dazzling Flirt",
            character_loss=False,
        )
        ConsequenceEffectFactory(
            consequence=success_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.TARGET,
            condition_template=cls.smitten_condition,
        )
        cls.flirt_pool = ConsequencePoolFactory(name="Flirt Outcomes")
        # Assign consequence to all outcome tiers so it fires regardless of roll
        from world.traits.models import CheckOutcome
        for outcome in CheckOutcome.objects.all():
            ConsequencePoolEntryFactory(
                pool=cls.flirt_pool,
                consequence=success_consequence,
                outcome_tier=outcome,
                weight=100,
            )

        # Attach pool to template
        cls.flirt_template.consequence_pool = cls.flirt_pool
        cls.flirt_template.save(update_fields=["consequence_pool"])

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        # Give initiator presence for checks
        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

    def test_mundane_flirt_applies_condition_to_target(self):
        """Full pipeline applies consequence effects on mundane actions."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        # Result is now EnhancedSceneActionResult
        assert result.action_resolution is not None
        assert result.technique_result is None  # no technique
```

- [ ] **Step 2: Run test to verify it fails**

Run: `arx test world.scenes.tests.test_scene_action_integration -k TestMundaneActionConsequences --keepdb`

Expected: FAIL — `respond_to_action_request()` still returns `SceneActionResult`, not `EnhancedSceneActionResult`.

- [ ] **Step 3: Implement full pipeline in `respond_to_action_request()`**

In `src/world/scenes/action_services.py`, replace the resolution logic:

```python
from django.db import transaction

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.types import EnhancedSceneActionResult


def respond_to_action_request(
    *,
    action_request: SceneActionRequest,
    decision: str,
) -> EnhancedSceneActionResult | None:
    """Process consent decision on action request."""
    if decision == ConsentDecision.DENY:
        action_request.status = ActionRequestStatus.DENIED
        action_request.resolved_at = timezone.now()
        action_request.save(update_fields=["status", "resolved_at"])
        return None

    difficulty = DIFFICULTY_VALUES.get(
        action_request.difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
    )

    with transaction.atomic():
        action_template = action_request.action_template
        if action_template is None:
            raise ValueError(
                f"Cannot resolve action '{action_request.action_key}': no ActionTemplate set."
            )

        character = action_request.initiator_persona.character
        context = ResolutionContext(character=character)

        if action_request.technique is not None:
            result = _resolve_enhanced_action(
                character=character,
                technique=action_request.technique,
                action_template=action_template,
                action_key=action_request.action_key,
                difficulty=difficulty,
                context=context,
            )
        else:
            action_resolution = start_action_resolution(
                character=character,
                template=action_template,
                target_difficulty=difficulty,
                context=context,
            )
            result = EnhancedSceneActionResult(
                action_resolution=action_resolution,
                action_key=action_request.action_key,
            )

        action_request.status = ActionRequestStatus.RESOLVED
        action_request.resolved_at = timezone.now()
        action_request.resolved_difficulty = difficulty
        action_request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])

        _create_result_interaction(action_request=action_request, result=result)

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb`

Expected: New test passes. Some existing tests may need updates for the new return type — update assertions that reference `.success`, `.action_key`, etc. to use `.action_resolution` and `.action_key`.

- [ ] **Step 5: Fix existing test assertions for new return type**

The return type change from `SceneActionResult` to `EnhancedSceneActionResult` affects multiple files:
- `src/world/scenes/tests/test_scene_action_integration.py` — assertions on result fields
- `src/world/scenes/tests/test_action_services.py` — if it exists and references `SceneActionResult`
- `src/world/mechanics/tests/test_pipeline_integration.py` — imports and asserts against `SceneActionResult`

Search for `SceneActionResult` across the test codebase and update all references.

The existing `TestSceneActionIntegration` tests check `result.success`, `result.check_outcome`, etc. Update them to access `result.action_resolution.main_result`:

```python
# Old:
assert result.check_outcome is not None
assert isinstance(result.success, bool)

# New:
assert result.action_resolution is not None
assert result.action_resolution.main_result is not None
assert result.action_key == "intimidate"
```

- [ ] **Step 6: Run all scene action tests**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb`

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/world/scenes/action_services.py src/world/scenes/tests/test_scene_action_integration.py
git commit -m "feat: upgrade scene actions to full consequence pipeline

respond_to_action_request now uses start_action_resolution instead of
resolve_scene_action, giving all social actions consequence pools."
```

---

### Task 5: Integrate `use_technique()` Wrapper for Enhanced Actions

When a technique is attached, wrap the action resolution inside `use_technique()`.

**Files:**
- Modify: `src/world/scenes/action_services.py`
- Test: `src/world/scenes/tests/test_scene_action_integration.py`

- [ ] **Step 1: Write failing test for technique-enhanced action**

Add to `src/world/scenes/tests/test_scene_action_integration.py`:

```python
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)


class TestEnhancedActionResolution(TestCase):
    """Technique-enhanced social actions run use_technique wrapping full pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        # Magic setup
        cls.technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            base_intensity=5,
            base_control=8,
            anima_cost=3,
        )
        CharacterTechniqueFactory(
            character=cls.initiator.character,
            technique=cls.technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )

        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

    def test_enhanced_action_deducts_anima(self):
        """Technique-enhanced action deducts anima cost."""
        from world.magic.models import CharacterAnima

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.confirmed is True
        assert result.technique_result.anima_cost is not None

        # Anima was deducted
        anima = CharacterAnima.objects.get(character=self.initiator.character)
        assert anima.current < 20  # Started at 20

    def test_enhanced_action_includes_action_resolution(self):
        """Enhanced action also resolves the social action."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result.action_resolution is not None
        assert result.action_resolution.main_result is not None
        assert result.action_key == "flirt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.scenes.tests.test_scene_action_integration -k TestEnhancedActionResolution --keepdb`

Expected: FAIL — `_resolve_enhanced_action` doesn't exist yet.

- [ ] **Step 3: Implement `_resolve_enhanced_action()`**

In `src/world/scenes/action_services.py`, add the helper:

```python
def _resolve_enhanced_action(
    *,
    character: ObjectDB,
    technique: Technique,
    action_template: ActionTemplate,
    action_key: str,
    difficulty: int,
    context: ResolutionContext,
) -> EnhancedSceneActionResult:
    """Resolve a technique-enhanced social action."""
    from world.magic.services import use_technique

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=lambda: start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
        ),
        confirm_soulfray_risk=True,
    )

    return EnhancedSceneActionResult(
        action_resolution=technique_result.resolution_result,
        action_key=action_key,
        technique_result=technique_result,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/world/scenes/action_services.py src/world/scenes/tests/test_scene_action_integration.py
git commit -m "feat: integrate use_technique wrapper for enhanced social actions

Enhanced actions deduct anima, run Soulfray/mishap evaluation, and
wrap the full action resolution pipeline."
```

---

### Task 6: Update `_create_result_interaction()` for New Result Type

The interaction recording function needs to handle `EnhancedSceneActionResult` instead of `SceneActionResult`.

**Files:**
- Modify: `src/world/scenes/action_services.py:123-142`
- Test: `src/world/scenes/tests/test_scene_action_integration.py`

- [ ] **Step 1: Write failing test**

```python
def test_enhanced_action_creates_interaction(self):
    """Enhanced action records an interaction in the scene."""
    request = create_action_request(
        scene=self.scene,
        initiator_persona=self.initiator,
        target_persona=self.target,
        action_key="flirt",
        technique=self.technique,
    )
    request.action_template = self.flirt_template
    request.save(update_fields=["action_template"])

    respond_to_action_request(
        action_request=request,
        decision=ConsentDecision.ACCEPT,
    )

    request.refresh_from_db()
    assert request.result_interaction is not None
    assert request.status == ActionRequestStatus.RESOLVED
    # Interaction content mentions the technique
    assert self.technique.name in request.result_interaction.content
```

Add this to `TestEnhancedActionResolution`.

- [ ] **Step 2: Run test to verify it fails**

Run: `arx test world.scenes.tests.test_scene_action_integration -k test_enhanced_action_creates_interaction --keepdb`

Expected: FAIL — `_create_result_interaction` doesn't handle the new type.

- [ ] **Step 3: Update `_create_result_interaction()`**

```python
def _create_result_interaction(
    *,
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
) -> Interaction | None:
    """Create an interaction recording the result of a scene action."""
    initiator = action_request.initiator_persona
    target = action_request.target_persona

    # Build content from resolution
    main = result.action_resolution.main_result
    outcome_name = main.check_result.outcome_name if main else "Unknown"
    success = main.check_result.success_level > 0 if main else False
    status_word = "Success" if success else "Failure"

    content = f"{initiator.name} attempts to {result.action_key} {target.name}: {status_word} ({outcome_name})"

    # Add technique info if enhanced
    if result.technique_result is not None and action_request.technique is not None:
        technique_name = action_request.technique.name
        anima_spent = result.technique_result.anima_cost.effective_cost
        content = f"{initiator.name} uses {technique_name} to {result.action_key} {target.name}: {status_word} ({outcome_name}) [Anima: {anima_spent}]"

    interaction = create_interaction(
        scene=action_request.scene,
        persona=initiator,
        content=content,
        mode=InteractionMode.ACTION,
        target_personas=[target],
    )

    if interaction:
        action_request.result_interaction = interaction
        action_request.save(update_fields=["result_interaction"])

    return interaction
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `arx test world.scenes.tests.test_scene_action_integration --keepdb`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/world/scenes/action_services.py src/world/scenes/tests/test_scene_action_integration.py
git commit -m "feat: update interaction recording for enhanced scene action results"
```

---

### Task 7: Add `technique_id` to Create Serializer and Fix View

The create serializer doesn't accept `technique_id`, the view uses implicit first-item persona selection, and the respond action needs to return the new result shape.

**Files:**
- Modify: `src/world/scenes/action_serializers.py`
- Modify: `src/world/scenes/action_views.py`
- Test: API tests can be deferred to the integration test task (Task 10)

- [ ] **Step 1: Update `SceneActionRequestCreateSerializer`**

In `src/world/scenes/action_serializers.py`:

```python
class SceneActionRequestCreateSerializer(serializers.Serializer):
    scene = serializers.IntegerField()
    target_persona = serializers.IntegerField()
    action_key = serializers.CharField(max_length=100)
    difficulty_choice = serializers.CharField(max_length=20, required=False)
    technique_id = serializers.IntegerField(required=False, allow_null=True)
```

- [ ] **Step 2: Add response serializer for `EnhancedSceneActionResult`**

```python
class StepResultSerializer(serializers.Serializer):
    step_label = serializers.CharField()
    check_outcome = serializers.SerializerMethodField()
    consequence_id = serializers.IntegerField(allow_null=True)

    def get_check_outcome(self, obj: StepResult) -> str:
        return obj.check_result.outcome_name


class ActionResolutionSerializer(serializers.Serializer):
    current_phase = serializers.CharField()
    main_result = StepResultSerializer(allow_null=True)
    gate_results = StepResultSerializer(many=True)


class TechniqueResultSerializer(serializers.Serializer):
    confirmed = serializers.BooleanField()
    anima_spent = serializers.SerializerMethodField()
    soulfray_stage = serializers.SerializerMethodField()
    mishap_label = serializers.SerializerMethodField()

    def get_anima_spent(self, obj: TechniqueUseResult) -> int:
        return obj.anima_cost.effective_cost

    def get_soulfray_stage(self, obj: TechniqueUseResult) -> str | None:
        if obj.soulfray_result and obj.soulfray_result.stage_name:
            return obj.soulfray_result.stage_name
        return None

    def get_mishap_label(self, obj: TechniqueUseResult) -> str | None:
        if obj.mishap:
            return obj.mishap.consequence_label
        return None


class EnhancedSceneActionResultSerializer(serializers.Serializer):
    action_key = serializers.CharField()
    action_resolution = ActionResolutionSerializer()
    technique_result = TechniqueResultSerializer(allow_null=True)
```

- [ ] **Step 3: Update the view's `create()` to pass technique**

In `src/world/scenes/action_views.py`, update the `create()` method to resolve `technique_id` to a `Technique` instance and pass it to `create_action_request()`:

```python
def create(self, request, *args, **kwargs):
    serializer = SceneActionRequestCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Resolve technique if provided
    technique = None
    technique_id = data.get("technique_id")
    if technique_id is not None:
        from world.magic.models import Technique
        technique = get_object_or_404(Technique, pk=technique_id)

    # ... existing persona/scene resolution ...

    action_request = create_action_request(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=data["action_key"],
        difficulty_choice=data.get("difficulty_choice", DifficultyChoice.NORMAL),
        technique=technique,
    )
    # ... return response ...
```

- [ ] **Step 4: Fix implicit first-item persona selection**

In `create()`, replace:
```python
initiator_persona = Persona.objects.filter(pk__in=persona_ids).first()
```

With explicit selection requiring the frontend to pass `initiator_persona_id`, or using the active persona from the scene participation. Check the existing convention — if persona_ids always has exactly one, document that assumption. If it can have multiple, require explicit selection.

- [ ] **Step 5: Update `respond()` action to serialize `EnhancedSceneActionResult`**

```python
@action(detail=True, methods=["post"])
def respond(self, request, pk=None):
    action_request = self.get_object()
    # ... existing validation ...

    result = respond_to_action_request(
        action_request=action_request,
        decision=consent_data["decision"],
    )

    response_data = SceneActionRequestSerializer(action_request).data
    if result is not None:
        response_data["result"] = EnhancedSceneActionResultSerializer(result).data

    return Response(response_data, status=status.HTTP_200_OK)
```

- [ ] **Step 6: Run linting**

Run: `ruff check src/world/scenes/action_serializers.py src/world/scenes/action_views.py`

- [ ] **Step 7: Commit**

```bash
git add src/world/scenes/action_serializers.py src/world/scenes/action_views.py
git commit -m "feat: add technique_id to create serializer and enhanced result serializer

Updates API contract: create accepts technique_id, respond returns
EnhancedSceneActionResult with action_resolution and technique_result."
```

---

### Task 8: Available Actions Endpoint with Enhancement Data

Build the endpoint that returns available actions with technique enhancement options.

**Files:**
- Modify: `src/world/scenes/action_views.py`
- Create: `src/world/scenes/action_availability.py` (service function)
- Test: `src/world/scenes/tests/test_scene_action_integration.py`

- [ ] **Step 1: Write failing test for available actions with enhancements**

```python
class TestAvailableActionsEndpoint(TestCase):
    """Available actions endpoint returns enhancement options."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()

        # Magic setup
        cls.technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            base_intensity=5,
            base_control=8,
            anima_cost=3,
        )
        CharacterTechniqueFactory(
            character=cls.initiator.character,
            technique=cls.technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )

    def test_returns_enhancements_for_known_techniques(self):
        """Available actions include technique enhancements the character knows."""
        from world.scenes.action_availability import get_available_scene_actions

        actions = get_available_scene_actions(
            character=self.initiator.character,
        )

        flirt_action = next(a for a in actions if a.action_key == "flirt")
        assert len(flirt_action.enhancements) == 1
        assert flirt_action.enhancements[0].technique == self.technique
        assert flirt_action.enhancements[0].enhancement.variant_name == "Enchanted Flirt"

    def test_excludes_unknown_techniques(self):
        """Enhancements for techniques the character doesn't know are excluded."""
        from world.scenes.action_availability import get_available_scene_actions

        unknown_technique = TechniqueFactory(name="Unknown Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Unknown Flirt",
            source_type="technique",
            technique=unknown_technique,
        )

        actions = get_available_scene_actions(
            character=self.initiator.character,
        )

        flirt_action = next(a for a in actions if a.action_key == "flirt")
        assert len(flirt_action.enhancements) == 1  # still just the one they know
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `arx test world.scenes.tests.test_scene_action_integration -k TestAvailableActionsEndpoint --keepdb`

Expected: FAIL — `action_availability` module doesn't exist.

- [ ] **Step 3: Create `src/world/scenes/action_availability.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from actions.models import ActionEnhancement, ActionTemplate
from world.magic.models import CharacterAnima, CharacterTechnique, Technique
from world.magic.services import (
    calculate_effective_anima_cost,
    get_runtime_technique_stats,
    get_soulfray_warning,
)
from world.magic.types import SoulfrayWarning

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class AvailableEnhancement:
    """A technique enhancement option for a social action."""

    enhancement: ActionEnhancement
    technique: Technique
    effective_cost: int
    soulfray_warning: SoulfrayWarning | None = None


@dataclass
class AvailableSceneAction:
    """A social action with its available technique enhancements."""

    action_key: str
    action_template: ActionTemplate
    enhancements: list[AvailableEnhancement] = field(default_factory=list)


def get_available_scene_actions(
    *,
    character: ObjectDB,
) -> list[AvailableSceneAction]:
    """Return available social actions with technique enhancement options."""
    # Get all social action templates
    templates = ActionTemplate.objects.filter(category="social")

    # Get character's known techniques in one query
    known_technique_ids = set(
        CharacterTechnique.objects.filter(
            character=character,
        ).values_list("technique_id", flat=True)
    )

    # Get all technique enhancements for social actions, pre-fetching technique
    all_enhancements = ActionEnhancement.objects.filter(
        source_type="technique",
        technique_id__in=known_technique_ids,
    ).select_related("technique")

    # Group enhancements by action key
    enhancements_by_action: dict[str, list[ActionEnhancement]] = {}
    for enh in all_enhancements:
        enhancements_by_action.setdefault(enh.base_action_key, []).append(enh)

    # Pre-calculate shared data once
    soulfray_warning = _get_soulfray_warning_if_magical(character, known_technique_ids)
    anima = _get_character_anima(character)

    # Cache runtime stats per technique (not per enhancement)
    stats_cache: dict[int, tuple[int, int]] = {}

    actions: list[AvailableSceneAction] = []
    for template in templates:
        action_key = template.name.lower()
        enhancements = enhancements_by_action.get(action_key, [])

        available_enhancements: list[AvailableEnhancement] = []
        for enh in enhancements:
            technique = enh.technique
            if technique.pk not in stats_cache:
                stats = get_runtime_technique_stats(technique, character)
                stats_cache[technique.pk] = (stats.intensity, stats.control)

            intensity, control = stats_cache[technique.pk]
            if anima is not None:
                cost = calculate_effective_anima_cost(
                    base_cost=technique.anima_cost,
                    runtime_intensity=intensity,
                    runtime_control=control,
                    current_anima=anima.current,
                )
                effective_cost = cost.effective_cost
            else:
                effective_cost = 0

            # Only include Soulfray warning if there's an actual cost
            warning = soulfray_warning if effective_cost > 0 else None

            available_enhancements.append(
                AvailableEnhancement(
                    enhancement=enh,
                    technique=technique,
                    effective_cost=effective_cost,
                    soulfray_warning=warning,
                )
            )

        actions.append(
            AvailableSceneAction(
                action_key=action_key,
                action_template=template,
                enhancements=available_enhancements,
            )
        )

    return actions


def _get_soulfray_warning_if_magical(
    character: ObjectDB,
    known_technique_ids: set[int],
) -> SoulfrayWarning | None:
    """Get Soulfray warning once if character has magical ability."""
    if not known_technique_ids:
        return None
    return get_soulfray_warning(character)


def _get_character_anima(character: ObjectDB) -> CharacterAnima | None:
    """Get character's anima record, or None if non-magical."""
    try:
        return CharacterAnima.objects.get(character=character)
    except CharacterAnima.DoesNotExist:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `arx test world.scenes.tests.test_scene_action_integration -k TestAvailableActionsEndpoint --keepdb`

Expected: All tests pass.

- [ ] **Step 5: Wire endpoint in the view**

Add a list action or separate view in `action_views.py` that calls `get_available_scene_actions()` and serializes the result. Add a corresponding serializer for `AvailableSceneAction` and `AvailableEnhancement`.

- [ ] **Step 6: Commit**

```bash
git add src/world/scenes/action_availability.py src/world/scenes/action_views.py src/world/scenes/action_serializers.py src/world/scenes/tests/test_scene_action_integration.py
git commit -m "feat: available-actions endpoint with technique enhancement data

Returns social actions with pre-calculated technique costs and
Soulfray warnings. Queries are batched to avoid N+1."
```

---

### Task 9: Frontend — Enhancement Selection and Soulfray Warning

Update the frontend to show enhancement options and handle Soulfray warnings.

**Files:**
- Modify: `frontend/src/scenes/actionTypes.ts`
- Modify: `frontend/src/scenes/actionQueries.ts`
- Modify: `frontend/src/scenes/components/ActionPanel.tsx`
- Create: `frontend/src/scenes/components/SoulfrayWarning.tsx`

- [ ] **Step 1: Update type definitions**

In `frontend/src/scenes/actionTypes.ts`, add:

```typescript
export interface SoulfrayWarningData {
  stage_name: string;
  stage_description: string;
  has_death_risk: boolean;
}

export interface AvailableEnhancement {
  technique_id: number;
  technique_name: string;
  variant_name: string;
  effective_cost: number;
  soulfray_warning: SoulfrayWarningData | null;
}

export interface AvailableSceneAction {
  action_key: string;
  action_template_name: string;
  icon: string;
  enhancements: AvailableEnhancement[];
}
```

Update `AvailableActionsResponse`:

```typescript
export interface AvailableActionsResponse {
  self_actions: AvailableAction[];
  targeted_actions: AvailableSceneAction[];
  technique_actions: TechniqueAction[];
}
```

- [ ] **Step 2: Wire available-actions query**

In `frontend/src/scenes/actionQueries.ts`, update `fetchAvailableActions()`:

```typescript
export async function fetchAvailableActions(
  sceneId: string,
): Promise<AvailableActionsResponse> {
  const response = await apiClient.get<AvailableActionsResponse>(
    `/api/action-requests/available/?scene=${sceneId}`,
  );
  return response.data;
}
```

Update `createActionRequest()` to pass `technique_id`:

```typescript
export async function createActionRequest(
  sceneId: string,
  body: { action_key: string; target_persona_id?: number; technique_id?: number },
): Promise<ActionRequestResponse> {
  const requestBody: Record<string, unknown> = {
    scene: Number(sceneId),
    action_key: body.action_key,
  };
  if (body.target_persona_id) {
    requestBody.target_persona = body.target_persona_id;
  }
  if (body.technique_id) {
    requestBody.technique_id = body.technique_id;
  }
  // ... rest unchanged
}
```

- [ ] **Step 3: Create SoulfrayWarning component**

Create `frontend/src/scenes/components/SoulfrayWarning.tsx`:

```tsx
import type { SoulfrayWarningData } from '../actionTypes';

interface SoulfrayWarningProps {
  warning: SoulfrayWarningData;
  techniqueName: string;
  animaCost: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SoulfrayWarning({
  warning,
  techniqueName,
  animaCost,
  onConfirm,
  onCancel,
}: SoulfrayWarningProps) {
  const isDangerous = warning.has_death_risk;

  return (
    <div
      className={`rounded-lg border p-4 ${isDangerous ? 'border-red-500 bg-red-950/50' : 'border-amber-500 bg-amber-950/50'}`}
    >
      <h3
        className={`mb-2 font-bold ${isDangerous ? 'text-red-400' : 'text-amber-400'}`}
      >
        {isDangerous ? 'DANGER: ' : ''}Soulfray Warning — {warning.stage_name}
      </h3>
      <p className="mb-2 text-sm text-gray-300">{warning.stage_description}</p>
      <p className="mb-4 text-sm text-gray-400">
        Using <strong>{techniqueName}</strong> will cost{' '}
        <strong>{animaCost} anima</strong> and may worsen your condition.
      </p>
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="rounded bg-gray-700 px-3 py-1 text-sm hover:bg-gray-600"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className={`rounded px-3 py-1 text-sm ${isDangerous ? 'bg-red-700 hover:bg-red-600' : 'bg-amber-700 hover:bg-amber-600'}`}
        >
          {isDangerous ? 'Accept Risk' : 'Proceed'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update ActionPanel to show enhancement options**

In `frontend/src/scenes/components/ActionPanel.tsx`, modify the "Social Actions" section to show available enhancements per action. Add state for `selectedEnhancement` and `soulfrayWarning`. When an enhancement with a warning is selected, show `SoulfrayWarning` before submitting.

Key changes:
- Each targeted action shows an expandable list of enhancements below it
- Enhancement shows: variant_name, cost ("Free" or "X anima"), warning icon
- Clicking an enhancement with no warning submits the action request with `technique_id`
- Clicking an enhancement with a warning shows the `SoulfrayWarning` dialog first

- [ ] **Step 5: Run frontend checks**

Run from `frontend/` directory:
```bash
pnpm typecheck
pnpm lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/scenes/
git commit -m "feat: frontend enhancement selection with Soulfray warnings

ActionPanel shows technique enhancements per social action with
pre-calculated anima costs. Soulfray warnings gate commitment."
```

---

### Task 10: Frontend — Layered Result Display

Update ActionResult to render both social and technique outcomes.

**Files:**
- Modify: `frontend/src/scenes/actionTypes.ts`
- Modify: `frontend/src/scenes/components/ActionResult.tsx`

- [ ] **Step 1: Update ActionResultData type**

In `frontend/src/scenes/actionTypes.ts`, update:

```typescript
export interface TechniqueResultData {
  confirmed: boolean;
  anima_spent: number;
  soulfray_stage: string | null;
  mishap_label: string | null;
}

export interface ActionResultData {
  interaction_id: number;
  action_key: string | null;
  action_resolution: {
    current_phase: string;
    main_result: {
      step_label: string;
      check_outcome: string;
      consequence_id: number | null;
    } | null;
    gate_results: Array<{
      step_label: string;
      check_outcome: string;
      consequence_id: number | null;
    }>;
  };
  technique_result: TechniqueResultData | null;
  technique_name: string | null;
}
```

- [ ] **Step 2: Update ActionResult component**

Update `frontend/src/scenes/components/ActionResult.tsx` to render the layered result:
- Social outcome line from `action_resolution.main_result.check_outcome`
- Technique line (if `technique_result` present): anima spent, Soulfray stage, mishap
- Keep existing color coding based on check outcome

- [ ] **Step 3: Run frontend checks**

```bash
pnpm --dir frontend typecheck
pnpm --dir frontend lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/scenes/
git commit -m "feat: layered action result display for technique-enhanced actions

Shows social outcome and technique effects as distinct but simultaneous
results. Color coding from social outcome tier."
```

---

### Task 11: Full Integration Tests

End-to-end tests that exercise the complete pipeline through the service layer.

**Files:**
- Create: `src/world/scenes/tests/test_scene_magic_integration.py`

- [ ] **Step 1: Create integration test file with shared setup**

```python
"""Integration tests for technique-enhanced scene actions.

Exercises the full pipeline: enhancement validation → action creation →
consent → full resolution with consequences → technique pipeline →
interaction recording.
"""

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.models import ActionEnhancement
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    ConsequenceEffectFactory,
    ConsequenceFactory,
    create_social_action_templates,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    MishapPoolTierFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CharacterTraitValue, Trait


class SceneMagicTestMixin:
    """Shared setup for scene magic integration tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # Check system
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")
        cls.intimidate_template = next(t for t in templates if t.name == "Intimidate")

        # Scene + personas
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        # Give initiator presence
        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

        # Technique with comfortable control margin (free to use)
        cls.charm_technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            base_intensity=3,
            base_control=8,
            anima_cost=2,
        )
        CharacterTechniqueFactory(
            character=cls.initiator.character,
            technique=cls.charm_technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )

        # ActionEnhancement linking technique to flirt
        cls.flirt_enhancement = ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.charm_technique,
        )

        # Consequence pool for flirt
        cls.smitten = ConditionTemplateFactory(name="Smitten")
        success_consequence = ConsequenceFactory(
            label="Dazzling Flirt", character_loss=False,
        )
        ConsequenceEffectFactory(
            consequence=success_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.TARGET,
            condition_template=cls.smitten,
        )
        cls.flirt_pool = ConsequencePoolFactory(name="Flirt Outcomes")
        from world.traits.models import CheckOutcome
        for outcome in CheckOutcome.objects.all():
            ConsequencePoolEntryFactory(
                pool=cls.flirt_pool,
                consequence=success_consequence,
                outcome_tier=outcome,
                weight=100,
            )
        cls.flirt_template.consequence_pool = cls.flirt_pool
        cls.flirt_template.save(update_fields=["consequence_pool"])
```

- [ ] **Step 2: Add test cases**

```python
class TestMundaneActionWithConsequences(SceneMagicTestMixin, TestCase):

    def test_mundane_flirt_full_pipeline(self):
        """Mundane flirt runs full pipeline and applies consequences."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.action_resolution.main_result is not None
        assert result.technique_result is None


class TestEnhancedActionFullPipeline(SceneMagicTestMixin, TestCase):

    def test_enhanced_flirt_deducts_anima_and_resolves(self):
        """Enhanced flirt deducts anima and resolves social action."""
        from world.magic.models import CharacterAnima

        initial_anima = CharacterAnima.objects.get(
            character=self.initiator.character,
        ).current

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.charm_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.confirmed is True
        assert result.action_resolution.main_result is not None

        # Anima deducted (control > intensity so effective cost may be 0)
        final_anima = CharacterAnima.objects.get(
            character=self.initiator.character,
        ).current
        expected_cost = result.technique_result.anima_cost.effective_cost
        assert final_anima == initial_anima - expected_cost

    def test_free_technique_no_soulfray_warning(self):
        """Technique where control >> intensity has no Soulfray warning."""
        actions = get_available_scene_actions(
            character=self.initiator.character,
        )

        flirt = next(a for a in actions if a.action_key == "flirt")
        assert len(flirt.enhancements) == 1
        enhancement = flirt.enhancements[0]
        # Control (8) >> Intensity (3), cost should be 0 or very low
        assert enhancement.soulfray_warning is None

    def test_enhancement_rejected_without_record(self):
        """Cannot attach technique without ActionEnhancement."""
        from django.core.exceptions import ValidationError

        unlinked_technique = TechniqueFactory(name="Fireball")
        CharacterTechniqueFactory(
            character=self.initiator.character,
            technique=unlinked_technique,
        )

        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=unlinked_technique,
            )

    def test_enhanced_action_creates_interaction_with_technique(self):
        """Enhanced action records interaction mentioning technique."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.charm_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        request.refresh_from_db()
        assert request.result_interaction is not None
        assert "Mesmerizing Gaze" in request.result_interaction.content


class TestAvailableActionsFiltering(SceneMagicTestMixin, TestCase):

    def test_only_known_techniques_appear(self):
        """Only techniques the character knows appear as enhancements."""
        unknown = TechniqueFactory(name="Unknown Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Unknown Flirt",
            source_type="technique",
            technique=unknown,
        )

        actions = get_available_scene_actions(
            character=self.initiator.character,
        )

        flirt = next(a for a in actions if a.action_key == "flirt")
        technique_names = [e.technique.name for e in flirt.enhancements]
        assert "Mesmerizing Gaze" in technique_names
        assert "Unknown Spell" not in technique_names

    def test_non_magical_character_has_no_enhancements(self):
        """Character without anima gets empty enhancement lists."""
        non_magical_persona = PersonaFactory()

        actions = get_available_scene_actions(
            character=non_magical_persona.character,
        )

        for action in actions:
            assert len(action.enhancements) == 0
```

- [ ] **Step 3: Run all integration tests**

Run: `arx test world.scenes.tests.test_scene_magic_integration --keepdb`

Expected: All tests pass.

- [ ] **Step 4: Run broader regression tests**

Run: `arx test world.scenes world.magic actions world.mechanics world.checks --keepdb`

Expected: All tests pass — no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/world/scenes/tests/test_scene_magic_integration.py
git commit -m "test: full integration tests for technique-enhanced scene actions

Covers: mundane with consequences, enhanced with anima/Soulfray,
enhancement validation, available-actions filtering, non-magical
characters."
```

---

### Task 12: Linting, Type Checking, and Final Regression

**Files:** All modified files

- [ ] **Step 1: Run Python linting on all changed files**

```bash
ruff check src/world/scenes/ src/world/magic/services.py src/actions/
ruff format src/world/scenes/ src/world/magic/services.py src/actions/
```

- [ ] **Step 2: Run frontend checks**

```bash
pnpm --dir frontend typecheck && pnpm --dir frontend lint
```

- [ ] **Step 3: Run full regression test suite**

```bash
arx test world.scenes world.magic actions world.mechanics world.checks world.conditions --keepdb
```

- [ ] **Step 4: Fix any issues found**

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git commit -m "fix: linting and type checking cleanup for scope 4"
```

---

### Task 13: Update Roadmap Documentation

**Files:**
- Modify: `docs/roadmap/magic.md`
- Modify: `docs/roadmap/capabilities-and-challenges.md`

- [ ] **Step 1: Update magic roadmap**

Mark technique-enhanced social actions as complete. Document what was built.

- [ ] **Step 2: Update capabilities roadmap**

Note that social actions now use the full consequence pipeline.

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap/
git commit -m "docs: update roadmaps for Scope #4 completion"
```
