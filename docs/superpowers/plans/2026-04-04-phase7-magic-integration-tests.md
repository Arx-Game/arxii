# Phase 7 Pass 2: Magic/Technique Integration Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `MagicContent` builder and technique-enhanced action pipeline tests to the integration test suite, verifying that a character who knows a technique sees it in available actions and that the full technique → anima deduction → condition-on-target path works end-to-end.

**Architecture:** Extends the pattern from Pass 1. `ActionEnhancementFactory` added to `actions/factories.py`. `CharacterContent.create_base_social_character()` updated to also create `CharacterSheet` and `CharacterAnima` (required for technique use). `MagicContent` builder creates 6 techniques + 6 `ActionEnhancement` records and exposes a `grant_techniques_to_character()` helper. Pipeline tests in `test_social_magic_pipeline.py` call `SocialContent.create_all()` + `MagicContent.create_all()` in `setUpTestData` and run the full consent flow with a technique on the request.

**Tech Stack:** Django TestCase, FactoryBoy DjangoModelFactory, existing world.magic factories, existing action_services pipeline.

---

## File Map

| File | Change |
|---|---|
| `src/actions/factories.py` | Add `ActionEnhancementFactory` |
| `src/integration_tests/game_content/characters.py` | Also create `CharacterSheet` + `CharacterAnima` in `create_base_social_character()` |
| `src/integration_tests/game_content/magic.py` | Create `MagicContent` builder (new file) |
| `src/integration_tests/pipeline/test_social_magic_pipeline.py` | Pipeline tests (new file) |

---

### Task 1: ActionEnhancementFactory

**Files:**
- Modify: `src/actions/factories.py`

The `ActionEnhancement` model requires exactly one source FK to be non-null matching `source_type`. For technique enhancements: `source_type="technique"`, `technique=<Technique>`, `distinction=None`, `condition=None`.

- [ ] **Step 1: Add the factory after `ActionTemplateGateFactory`**

In `src/actions/factories.py`, add these imports at the top (already present: `ActionTemplate`, `ActionTemplateGate`, `ConsequencePool`, `ConsequencePoolEntry`):
```python
from actions.constants import ActionTargetType, EnhancementSourceType, GateRole, Pipeline
from actions.models import ActionEnhancement, ActionTemplate, ActionTemplateGate, ConsequencePool, ConsequencePoolEntry
```

Then add at the end of the file:
```python
class ActionEnhancementFactory(DjangoModelFactory):
    """Factory for ActionEnhancement with technique source."""

    class Meta:
        model = ActionEnhancement

    base_action_key = "intimidate"
    variant_name = factory.Sequence(lambda n: f"Enhanced Action {n}")
    is_involuntary = False
    source_type = EnhancementSourceType.TECHNIQUE
    technique = factory.SubFactory("world.magic.factories.TechniqueFactory")
    distinction = None
    condition = None
```

- [ ] **Step 2: Verify it lints clean**

Run: `uv run ruff check src/actions/factories.py`
Expected: no errors

- [ ] **Step 3: Run actions tests to confirm no regressions**

Run: `uv run arx test actions --keepdb`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/actions/factories.py
git commit -m "feat: add ActionEnhancementFactory"
```

---

### Task 2: Update CharacterContent to create CharacterSheet and CharacterAnima

**Files:**
- Modify: `src/integration_tests/game_content/characters.py`

`CharacterTechnique.character` → FK to `CharacterSheet` (pk == ObjectDB pk, so no join needed).
`CharacterAnima.character` → OneToOne to `ObjectDB`.
Both must exist before technique operations work.

- [ ] **Step 1: Update `create_base_social_character` to create CharacterSheet and CharacterAnima**

Replace the body of `create_base_social_character` in `src/integration_tests/game_content/characters.py`:

```python
    @staticmethod
    def create_base_social_character(
        *,
        name: str | None = None,
    ) -> tuple[ObjectDB, Persona]:
        """Create a character with social trait values, CharacterSheet, and CharacterAnima.

        Sets up CharacterTraitValue records for all 6 social stats at value 50,
        giving 50 total points via the 1-point-per-level STAT conversion range.
        With CheckRank thresholds at 0/30/60, a trait total of 50 maps to rank 1.

        Also creates CharacterSheet (required for CharacterTechnique) and
        CharacterAnima (required for technique anima deduction).

        Args:
            name: Optional character name (defaults to factory sequence name).

        Returns:
            Tuple of (ObjectDB character, PRIMARY Persona).
        """
        from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
        from world.character_sheets.factories import (  # noqa: PLC0415
            CharacterIdentityFactory,
            CharacterSheetFactory,
        )
        from world.magic.factories import CharacterAnimaFactory  # noqa: PLC0415
        from world.traits.factories import StatTraitFactory  # noqa: PLC0415
        from world.traits.models import CharacterTraitValue  # noqa: PLC0415

        kwargs: dict[str, object] = {}
        if name is not None:
            kwargs["db_key"] = name

        character = CharacterFactory(**kwargs)
        identity = CharacterIdentityFactory(character=character)
        persona = identity.active_persona

        CharacterSheetFactory(character=character)
        CharacterAnimaFactory(character=character, current=20, maximum=30)

        for stat_name in _SOCIAL_STAT_NAMES:
            trait = StatTraitFactory(name=stat_name)
            CharacterTraitValue.objects.get_or_create(
                character=character,
                trait=trait,
                defaults={"value": _SOCIAL_TRAIT_VALUE},
            )

        return character, persona
```

- [ ] **Step 2: Run the existing pipeline tests to confirm they still pass**

Run: `uv run arx test integration_tests --keepdb`
Expected: 10 tests pass

- [ ] **Step 3: Commit**

```bash
git add src/integration_tests/game_content/characters.py
git commit -m "feat: create CharacterSheet and CharacterAnima in create_base_social_character"
```

---

### Task 3: MagicContent builder

**Files:**
- Create: `src/integration_tests/game_content/magic.py`

Creates 6 techniques (one per social action) each with an `ActionEnhancement` linking it to the correct action key. Exposes `grant_techniques_to_character()` as a separate step so tests can control which characters know which techniques.

Technique parameters: `intensity=2, control=2, anima_cost=2` — no control deficit (no mishap), base cost of 2 anima. Tests can verify `current_anima` decreases after use.

- [ ] **Step 1: Create the file**

```python
"""MagicContent — technique and ActionEnhancement records for social action tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from world.magic.models import Technique

# Maps action_key → technique name (narrative, not mechanical)
ACTION_TECHNIQUE_MAP: dict[str, str] = {
    "intimidate": "Soul Crush",
    "persuade": "Silver Tongue",
    "deceive": "Veil of Lies",
    "flirt": "Heartstring Pull",
    "perform": "Echoing Song",
    "entrance": "Commanding Presence",
}


@dataclass
class MagicContentResult:
    """Returned by MagicContent.create_all()."""

    techniques: dict[str, Technique]  # action_key → Technique
    enhancements: dict[str, ActionEnhancement]  # action_key → ActionEnhancement


class MagicContent:
    """Creates techniques and ActionEnhancement records for social action integration tests."""

    @staticmethod
    def create_all() -> MagicContentResult:
        """Create 6 techniques and 6 ActionEnhancement records (one per social action).

        Techniques use intensity=2, control=2, anima_cost=2 — no control deficit,
        predictable anima deduction of 2 per use.

        Safe to call from setUpTestData across multiple test classes.

        Returns:
            MagicContentResult with techniques and enhancements dicts.
        """
        from actions.constants import EnhancementSourceType  # noqa: PLC0415
        from actions.factories import ActionEnhancementFactory  # noqa: PLC0415
        from world.magic.factories import GiftFactory, TechniqueFactory  # noqa: PLC0415

        gift = GiftFactory(name="Social Arts")
        techniques: dict[str, Technique] = {}
        enhancements: dict[str, ActionEnhancement] = {}

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            technique = TechniqueFactory(
                name=technique_name,
                gift=gift,
                intensity=2,
                control=2,
                anima_cost=2,
            )
            techniques[action_key] = technique

            enhancement = ActionEnhancementFactory(
                base_action_key=action_key,
                variant_name=f"Magical {action_key.title()}",
                source_type=EnhancementSourceType.TECHNIQUE,
                technique=technique,
            )
            enhancements[action_key] = enhancement

        return MagicContentResult(techniques=techniques, enhancements=enhancements)

    @staticmethod
    def grant_techniques_to_character(
        character: ObjectDB,
        techniques: list[Technique],
    ) -> None:
        """Create CharacterTechnique records so the character knows each technique.

        Args:
            character: The ObjectDB character (must have a CharacterSheet created first).
            techniques: Techniques to grant. Duplicate grants are ignored (get_or_create).
        """
        from world.magic.factories import CharacterTechniqueFactory  # noqa: PLC0415

        sheet = character.sheet_data
        for technique in techniques:
            CharacterTechniqueFactory(character=sheet, technique=technique)
```

- [ ] **Step 2: Lint check**

Run: `uv run ruff check src/integration_tests/game_content/magic.py`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/integration_tests/game_content/magic.py
git commit -m "feat: add MagicContent builder for technique/enhancement integration tests"
```

---

### Task 4: Pipeline tests

**Files:**
- Create: `src/integration_tests/pipeline/test_social_magic_pipeline.py`

Two test classes:
- `SocialMagicAvailabilityTests` — character who knows a technique sees it in `get_available_scene_actions`; character who doesn't know any techniques sees none
- `SocialMagicConsequenceTests` — full pipeline: technique-enhanced action applies condition to target and deducts anima from initiator

The test creates a request with `technique=technique` via `create_action_request(technique=...)`, sets `action_template`, then calls `respond_to_action_request(decision=ACCEPT)`. The `_validate_technique_enhancement` check fires automatically.

- [ ] **Step 1: Create the test file**

```python
"""End-to-end pipeline tests for technique-enhanced social actions.

Test structure:
  SocialMagicAvailabilityTests   — technique-enhanced actions appear in available actions
  SocialMagicConsequenceTests    — full pipeline: anima deducted, condition on target
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP, MagicContent
from integration_tests.game_content.social import SocialContent
from world.conditions.services import has_condition
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import SceneFactory


class SocialMagicAvailabilityTests(TestCase):
    """Character with known techniques sees them in get_available_scene_actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.magic = MagicContent.create_all()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Mira"
        )
        cls.other_char, cls.other_persona = CharacterContent.create_base_social_character(
            name="Fen"
        )
        # Mira knows all 6 techniques; Fen knows none
        MagicContent.grant_techniques_to_character(
            cls.initiator_char, list(cls.magic.techniques.values())
        )

    def test_known_techniques_appear_as_enhancements(self) -> None:
        actions = get_available_scene_actions(character=self.initiator_char)
        actions_by_key = {a.action_key: a for a in actions}
        for action_key in ACTION_TECHNIQUE_MAP:
            assert actions_by_key[action_key].enhancements, (
                f"Expected enhancement on {action_key}"
            )

    def test_enhancement_links_correct_technique(self) -> None:
        actions = get_available_scene_actions(character=self.initiator_char)
        actions_by_key = {a.action_key: a for a in actions}
        intimidate = actions_by_key["intimidate"]
        assert intimidate.enhancements[0].technique == self.magic.techniques["intimidate"]

    def test_character_without_techniques_has_no_enhancements(self) -> None:
        actions = get_available_scene_actions(character=self.other_char)
        for action in actions:
            assert action.enhancements == []


class SocialMagicConsequenceTests(TestCase):
    """Full pipeline: technique-enhanced action deducts anima and applies condition to target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.content = SocialContent.create_all()
        cls.magic = MagicContent.create_all()
        cls.scene = SceneFactory()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Corvus"
        )
        cls.target_char, cls.target_persona = CharacterContent.create_base_social_character(
            name="Wren"
        )
        MagicContent.grant_techniques_to_character(
            cls.initiator_char, list(cls.magic.techniques.values())
        )

    def _accept_enhanced_action(self, action_key: str) -> None:
        """Create and accept a technique-enhanced action request."""
        template = self.content.templates[action_key]
        technique = self.magic.techniques[action_key]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key=action_key,
            technique=technique,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

    def test_enhanced_intimidate_applies_shaken_to_target(self) -> None:
        """Technique-enhanced Intimidate applies Shaken to TARGET, not initiator."""
        condition = self.content.conditions["Shaken"]
        # Roll 90 → Success on diff=1 chart (Success: 86-100)
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_enhanced_action("intimidate")

        assert has_condition(self.target_char, condition), "Target should have Shaken"
        assert not has_condition(self.initiator_char, condition), "Initiator should not have Shaken"

    def test_enhanced_action_deducts_anima_from_initiator(self) -> None:
        """Technique use deducts anima from the initiator's pool."""
        anima_before = self.initiator_char.anima.current
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_enhanced_action("persuade")

        self.initiator_char.anima.refresh_from_db()
        assert self.initiator_char.anima.current < anima_before

    def test_enhanced_action_result_has_technique_result(self) -> None:
        """respond_to_action_request returns EnhancedSceneActionResult with technique_result."""
        template = self.content.templates["flirt"]
        technique = self.magic.techniques["flirt"]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="flirt",
            technique=technique,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        with patch("world.checks.services.random.randint", return_value=90):
            result = respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.anima_cost.effective_cost >= 0
```

- [ ] **Step 2: Run the new tests — expect failures (MagicContent doesn't exist yet)**

Wait — MagicContent was created in Task 3. Run them now:

Run: `uv run arx test integration_tests.pipeline.test_social_magic_pipeline --keepdb`
Expected: all pass (or investigate failures)

- [ ] **Step 3: Run full integration suite to confirm no regressions**

Run: `uv run arx test integration_tests --keepdb`
Expected: 10 + new tests all pass

- [ ] **Step 4: Commit**

```bash
git add src/integration_tests/pipeline/test_social_magic_pipeline.py
git commit -m "feat: technique-enhanced social action pipeline tests"
```

---

### Task 5: Full regression and roadmap update

**Files:**
- Modify: `docs/roadmap/capabilities-and-challenges.md`

- [ ] **Step 1: Run all affected test suites**

Run: `uv run arx test world.checks world.mechanics world.scenes world.magic world.traits world.conditions integration_tests --keepdb`
Expected: all pass

- [ ] **Step 2: Mark Pass 2 complete in roadmap**

In `docs/roadmap/capabilities-and-challenges.md`, under the Phase 7 section, update the "Pass 2" entry:

```markdown
**Pass 2 — Magic/Technique Content: COMPLETE**
- `ActionEnhancementFactory` added to `actions/factories.py`
- `CharacterContent` now creates `CharacterSheet` + `CharacterAnima` for all social characters
- `MagicContent.create_all()`: 6 techniques + 6 ActionEnhancement records (one per social action)
- `MagicContent.grant_techniques_to_character()`: grants technique knowledge to a character
- `integration_tests/pipeline/test_social_magic_pipeline.py`: 6 tests verifying availability
  and consequence application through the technique-enhanced path
```

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap/capabilities-and-challenges.md
git commit -m "docs: mark Phase 7 Pass 2 complete in roadmap"
```
