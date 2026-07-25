"""Journey test: a target's level and Path-aspect match raise the difficulty of an
opposed social action through the resist path (#2707 Task 4).

``compute_resist_increment`` now routes through ``compute_check_rating``, so a
defender's Composure rating -- and therefore the difficulty a resisting target adds
-- carries the defender's OWN level points (via ``get_character_path_level``) and any
aspect match on their Path, not trait points alone. This mirrors
``test_action_services.py``'s ``TestActiveResistanceRaisesDifficultyAndChargesFatigue``
setup, but varies the TARGET across three defenders instead of asserting a single
fixed increment.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.checks.factories import CheckTypeAspectFactory, create_resistance_check_types
from world.classes.factories import (
    AspectFactory,
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathAspectFactory,
    PathFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import StatTraitFactory
from world.traits.models import CharacterTraitValue, PointConversionRange, Trait, TraitType


def _make_pending_resolution(success: bool = True) -> PendingActionResolution:
    """Build a minimal PendingActionResolution for mocking (mirrors test_action_services.py)."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class LevelOpposedSocialJourneyTests(TestCase):
    """A higher-level, then aspect-matched, target raises the resist difficulty."""

    @classmethod
    def setUpTestData(cls) -> None:
        Trait.flush_instance_cache()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

        check_types = create_resistance_check_types()
        cls.composure_check_type = check_types["Composure"]
        cls.willpower_trait = StatTraitFactory(name="willpower")

        cls.character_class = CharacterClassFactory()

        # Aspect wired onto Composure -- a defender whose Path matches it resists harder.
        cls.aspect_path = PathFactory(name="JourneyAspectPath")
        aspect = AspectFactory(name="JourneyComposureAspect")
        PathAspectFactory(character_path=cls.aspect_path, aspect=aspect, weight=2)
        CheckTypeAspectFactory(
            check_type=cls.composure_check_type, aspect=aspect, weight=Decimal("1.0")
        )

        # Three targets, identical willpower, differing only in level / aspect match.
        cls.low_level_target = PersonaFactory()
        cls.high_level_target = PersonaFactory()
        cls.matched_target = PersonaFactory()

        for persona in (cls.low_level_target, cls.high_level_target, cls.matched_target):
            CharacterTraitValue.objects.create(
                character=persona.character_sheet, trait=cls.willpower_trait, value=10
            )

        CharacterClassLevelFactory(
            character=cls.low_level_target.character_sheet,
            character_class=cls.character_class,
            level=1,
            is_primary=True,
        )
        CharacterClassLevelFactory(
            character=cls.high_level_target.character_sheet,
            character_class=cls.character_class,
            level=5,
            is_primary=True,
        )
        CharacterClassLevelFactory(
            character=cls.matched_target.character_sheet,
            character_class=cls.character_class,
            level=5,
            is_primary=True,
        )
        CharacterPathHistoryFactory(
            character=cls.matched_target.character_sheet, path=cls.aspect_path
        )

    def setUp(self) -> None:
        from world.checks.models import CheckType

        CharacterTraitValue.flush_instance_cache()
        CheckType.flush_instance_cache()

        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    def _resolved_difficulty_against(self, target) -> int:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=target,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
        )
        from world.scenes.action_models import SceneActionRequest

        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template

        with patch("world.scenes.action_services.start_action_resolution") as mock_resolve:
            mock_resolve.return_value = _make_pending_resolution(success=True)
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
                difficulty=DifficultyChoice.NORMAL,
                resist_effort="medium",
            )

        request.refresh_from_db()
        return request.resolved_difficulty

    def test_higher_level_target_raises_difficulty(self) -> None:
        low = self._resolved_difficulty_against(self.low_level_target)
        high = self._resolved_difficulty_against(self.high_level_target)
        self.assertGreater(high, low)

    def test_aspect_matched_target_raises_difficulty_further(self) -> None:
        high = self._resolved_difficulty_against(self.high_level_target)
        matched = self._resolved_difficulty_against(self.matched_target)
        self.assertGreater(matched, high)

    def test_base_difficulty_is_the_floor(self) -> None:
        """Sanity check: every resolved difficulty is at least the flat base tier."""
        base = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        low = self._resolved_difficulty_against(self.low_level_target)
        self.assertGreaterEqual(low, base)
