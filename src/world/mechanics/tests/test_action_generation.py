"""Tests for action generation service."""

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.mechanics.services import get_available_actions
from world.mechanics.types import CapabilitySource


def _make_source(  # noqa: PLR0913
    capability_name: str = "fire_control",
    capability_id: int = 1,
    value: int = 10,
    source_type: CapabilitySourceType = CapabilitySourceType.TECHNIQUE,
    source_name: str = "Fireball",
    source_id: int = 1,
    effect_property_ids: list[int] | None = None,
) -> CapabilitySource:
    """Helper to build a CapabilitySource for tests."""
    return CapabilitySource(
        capability_name=capability_name,
        capability_id=capability_id,
        value=value,
        source_type=source_type,
        source_name=source_name,
        source_id=source_id,
        effect_property_ids=effect_property_ids or [],
    )


class ActionGenerationTests(TestCase):
    """Tests for get_available_actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="ActionChar")
        cls.location = ObjectDB.objects.create(db_key="ActionRoom")

        cls.capability = CapabilityTypeFactory(name="fire_control_ag")
        cls.prop_flammable = PropertyFactory(name="flammable_ag")
        cls.application = ApplicationFactory(
            name="Burn",
            capability=cls.capability,
            target_property=cls.prop_flammable,
        )

        cls.template = ChallengeTemplateFactory(
            name="Wooden Door",
            severity=5,
        )
        cls.template.properties.add(cls.prop_flammable)

        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Burn it down",
            custom_description="Set the door on fire",
        )

        cls.challenge_instance = ChallengeInstance.objects.create(
            template=cls.template,
            location=cls.location,
            target_object=cls.location,
            is_active=True,
            is_revealed=True,
        )

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.MODERATE,
    )
    def test_matching_action(self, _mock: object) -> None:  # noqa: PT019
        """Character with matching capability sees an Action."""
        source = _make_source(
            capability_name="fire_control_ag",
            capability_id=self.capability.id,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 1

        action = actions[0]
        assert action.application_name == "Burn"
        assert action.challenge_name == "Wooden Door"
        assert action.display_name == "Burn it down"
        assert action.challenge_instance_id == self.challenge_instance.id

    def test_no_matching_capability(self) -> None:
        """Character without matching capability sees no Actions."""
        source = _make_source(
            capability_name="ice_control",
            capability_id=9999,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 0

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.IMPOSSIBLE,
    )
    def test_impossible_difficulty_filtered_out(self, _mock_diff: object) -> None:  # noqa: PT019
        """Actions at IMPOSSIBLE difficulty are excluded from results."""
        source = _make_source(
            capability_name="fire_control_ag",
            capability_id=self.capability.id,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 0

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.MODERATE,
    )
    def test_unrevealed_challenge_hidden(self, _mock: object) -> None:  # noqa: PT019
        """Unrevealed challenge produces no Actions."""
        hidden_ci = ChallengeInstance.objects.create(
            template=self.template,
            location=self.location,
            target_object=self.location,
            is_active=True,
            is_revealed=False,
        )
        source = _make_source(
            capability_name="fire_control_ag",
            capability_id=self.capability.id,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        # Should only match the revealed instance, not the hidden one
        matching = [a for a in actions if a.challenge_instance_id == hidden_ci.id]
        assert len(matching) == 0


class EffectPropertyFilterTests(TestCase):
    """Tests that required_effect_property filtering works correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="EffectChar")
        cls.location = ObjectDB.objects.create(db_key="EffectRoom")

        cls.prop_flammable = PropertyFactory(name="flammable_epf")
        cls.prop_fire = PropertyFactory(name="fire_effect_epf")
        cls.capability = CapabilityTypeFactory(name="elemental_control_epf")

        cls.application = ApplicationFactory(
            name="Fire Blast EPF",
            capability=cls.capability,
            target_property=cls.prop_flammable,
            required_effect_property=cls.prop_fire,
        )

        cls.template = ChallengeTemplateFactory(
            name="Wooden Wall EPF",
            severity=5,
        )
        cls.template.properties.add(cls.prop_flammable)

        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Fire Blast EPF",
        )

        cls.challenge_instance = ChallengeInstance.objects.create(
            template=cls.template,
            location=cls.location,
            target_object=cls.location,
            is_active=True,
            is_revealed=True,
        )

    def test_source_without_effect_property_excluded(self) -> None:
        """Source missing required_effect_property produces no action."""
        source = _make_source(
            capability_name="elemental_control_epf",
            capability_id=self.capability.id,
            value=10,
            effect_property_ids=[],
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 0

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.MODERATE,
    )
    def test_source_with_effect_property_included(self, _mock: object) -> None:  # noqa: PT019
        """Source with required_effect_property produces an action."""
        source = _make_source(
            capability_name="elemental_control_epf",
            capability_id=self.capability.id,
            value=10,
            effect_property_ids=[self.prop_fire.id],
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 1
        assert actions[0].application_name == "Fire Blast EPF"


class DifficultyIndicatorForCheckTests(TestCase):
    """Tests for _get_difficulty_indicator_for_check via get_available_actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="DiffChar")
        cls.location = ObjectDB.objects.create(db_key="DiffRoom")

        cls.capability = CapabilityTypeFactory(name="diff_check_cap")
        cls.prop = PropertyFactory(name="diff_check_prop")
        cls.application = ApplicationFactory(
            name="DiffAction",
            capability=cls.capability,
            target_property=cls.prop,
        )
        cls.template = ChallengeTemplateFactory(name="DiffChallenge", severity=5)
        cls.template.properties.add(cls.prop)

        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="DiffApproach",
        )
        cls.challenge_instance = ChallengeInstance.objects.create(
            template=cls.template,
            location=cls.location,
            target_object=cls.location,
            is_active=True,
            is_revealed=True,
        )

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.HARD,
    )
    def test_action_has_difficulty_from_check_pipeline(self, _mock: object) -> None:  # noqa: PT019
        """Difficulty indicator on actions comes from the check pipeline."""
        source = _make_source(
            capability_name="diff_check_cap",
            capability_id=self.capability.id,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 1
        assert actions[0].difficulty_indicator == DifficultyIndicator.HARD

    @patch(
        "world.mechanics.services._get_difficulty_indicator_for_check",
        return_value=DifficultyIndicator.IMPOSSIBLE,
    )
    def test_impossible_excluded(self, _mock: object) -> None:  # noqa: PT019
        """IMPOSSIBLE difficulty excludes the action from results."""
        source = _make_source(
            capability_name="diff_check_cap",
            capability_id=self.capability.id,
            value=10,
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])
        assert len(actions) == 0
