"""Tests for bare-object ObjectProperty affordances in get_available_actions (#2503).

A flammable torch with no authored ChallengeInstance still presents "Ignite" to
a character with a matching capability source, via
``Application.default_template`` (Task 1's curated gate).
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.conditions.factories import CapabilityTypeFactory
from world.items.factories import ItemTemplateFactory, ItemTemplatePropertyFactory
from world.items.services.staging import stage_prop
from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    ObjectPropertyFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.mechanics.services import get_available_actions
from world.mechanics.types import CapabilitySource


def _make_source(
    capability_id: int,
    capability_name: str = "generation_oa",
    value: int = 10,
) -> CapabilitySource:
    """Helper to build a CapabilitySource for tests."""
    return CapabilitySource(
        capability_name=capability_name,
        capability_id=capability_id,
        value=value,
        source_type=CapabilitySourceType.TECHNIQUE,
        source_name="Ember Spark",
        source_id=1,
    )


@patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)
class BareObjectAffordanceTests(TestCase):
    """Torch + flammable + generation source → a synthesized Ignite action."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDBFactory(db_key="AffordanceChar")
        cls.location = ObjectDBFactory(db_key="AffordanceRoom")
        cls.torch = ObjectDBFactory(db_key="Torch", location=cls.location)
        cls.elsewhere = ObjectDBFactory(db_key="ElsewhereRoom")
        cls.distant_torch = ObjectDBFactory(db_key="DistantTorch", location=cls.elsewhere)

        cls.capability = CapabilityTypeFactory(name="generation_oa")
        cls.prop_flammable = PropertyFactory(name="flammable_oa")

        cls.template = ChallengeTemplateFactory(name="Ignite Torch", severity=3)
        cls.application = ApplicationFactory(
            name="Ignite",
            capability=cls.capability,
            target_property=cls.prop_flammable,
            default_template=cls.template,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Ignite it",
            custom_description="Set the torch alight",
        )

        ObjectPropertyFactory(object=cls.torch, property=cls.prop_flammable)
        # Same property elsewhere — must NOT surface (object not at the location).
        ObjectPropertyFactory(object=cls.distant_torch, property=cls.prop_flammable)

        # A second Application on the same property with no default_template —
        # must never synthesize a bare-object action, even with a matching source.
        cls.prop_scorched = PropertyFactory(name="flammable_no_template_oa")
        cls.no_template_application = ApplicationFactory(
            name="Scorch",
            capability=cls.capability,
            target_property=cls.prop_scorched,
            default_template=None,
        )
        ObjectPropertyFactory(object=cls.torch, property=cls.prop_scorched)

    def _ignite_actions(self, actions):
        return [a for a in actions if a.application_name == "Ignite"]

    def test_bare_object_action_surfaces(self, _mock_diff: object) -> None:  # noqa: PT019
        """Torch + flammable + generation source → Ignite appears, unminted."""
        source = _make_source(capability_id=self.capability.id)
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        matching = self._ignite_actions(actions)
        assert len(matching) == 1
        action = matching[0]
        assert action.target_object == self.torch
        assert action.resolved_default_template == self.template
        assert action.challenge_instance_id is None
        assert action.resolved_challenge_instance is None
        assert action.approach_id == self.approach.id
        assert action.resolved_challenge_approach == self.approach
        assert action.check_type_name == self.approach.check_type.name
        assert action.resolved_check_type == self.approach.check_type

    def test_no_default_template_excluded(self, _mock_diff: object) -> None:  # noqa: PT019
        """An Application without default_template never synthesizes an action."""
        source = _make_source(capability_id=self.capability.id)
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        assert not [a for a in actions if a.application_name == "Scorch"]
        # Sanity: Ignite (which DOES have a default_template) still surfaces.
        assert self._ignite_actions(actions)

    def test_no_capability_source_excluded(self, _mock_diff: object) -> None:  # noqa: PT019
        """Without a matching capability source, no Ignite action is synthesized."""
        source = _make_source(capability_id=999999, capability_name="unrelated_oa")
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        assert not self._ignite_actions(actions)

    def test_object_not_at_location_excluded(self, _mock_diff: object) -> None:  # noqa: PT019
        """A flammable object elsewhere never surfaces an action for this location."""
        source = _make_source(capability_id=self.capability.id)
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        matching = self._ignite_actions(actions)
        assert len(matching) == 1
        assert matching[0].target_object == self.torch  # never distant_torch

    def test_active_instance_deduplicates(self, _mock_diff: object) -> None:  # noqa: PT019
        """An active authored ChallengeInstance on the same object+template dedupes."""
        ChallengeInstance.objects.create(
            template=self.template,
            location=self.location,
            target_object=self.torch,
            is_active=True,
            is_revealed=True,
        )
        source = _make_source(capability_id=self.capability.id)
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        # The synthesized (instance-less) Ignite action for the torch must be gone —
        # only the authored-instance's own action (if any) could remain.
        synthesized = [
            a
            for a in self._ignite_actions(actions)
            if a.resolved_challenge_instance is None and a.target_object == self.torch
        ]
        assert not synthesized


@patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)
class BareObjectRoomAffordanceTests(TestCase):
    """The room itself carrying a property (e.g. "dark") surfaces an action."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDBFactory(db_key="DarkRoomChar")
        cls.location = ObjectDBFactory(db_key="DarkRoom")

        cls.capability = CapabilityTypeFactory(name="perception_oa")
        cls.prop_dark = PropertyFactory(name="dark_oa")

        cls.template = ChallengeTemplateFactory(name="Illuminate Room", severity=2)
        cls.application = ApplicationFactory(
            name="Illuminate",
            capability=cls.capability,
            target_property=cls.prop_dark,
            default_template=cls.template,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Light it up",
        )

        ObjectPropertyFactory(object=cls.location, property=cls.prop_dark)

    def test_room_property_surfaces_action(self, _mock_diff: object) -> None:  # noqa: PT019
        """A property on the location itself (not its contents) still surfaces."""
        source = _make_source(capability_id=self.capability.id, capability_name="perception_oa")
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        matching = [a for a in actions if a.application_name == "Illuminate"]
        assert len(matching) == 1
        assert matching[0].target_object == self.location
        assert matching[0].resolved_default_template == self.template


@patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)
class GMStagedPropAffordanceTests(TestCase):
    """GM stages a torch mid-scene (#2503) -> the room's next available-actions read
    shows Ignite, with zero bespoke wiring -- the staged prop rides the same
    materialization chokepoint (``materialize_item_game_object_in_room``) a crafted or
    looted torch would, so it carries the same template-default ``ObjectProperty`` rows.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDBFactory(db_key="PyromancerChar")
        cls.location = ObjectDBFactory(db_key="StagingRoom")

        cls.capability = CapabilityTypeFactory(name="generation_stage_oa")
        cls.prop_flammable = PropertyFactory(name="flammable_stage_oa")

        cls.template = ChallengeTemplateFactory(name="Ignite Staged Torch", severity=3)
        cls.application = ApplicationFactory(
            name="Ignite Staged",
            capability=cls.capability,
            target_property=cls.prop_flammable,
            default_template=cls.template,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Ignite it",
        )

        cls.item_template = ItemTemplateFactory(name="Staged Torch Template")
        ItemTemplatePropertyFactory(item_template=cls.item_template, property=cls.prop_flammable)

    def test_staged_prop_surfaces_ignite(self, _mock_diff: object) -> None:  # noqa: PT019
        torch = stage_prop(self.item_template, self.location)

        source = _make_source(
            capability_id=self.capability.id, capability_name="generation_stage_oa"
        )
        actions = get_available_actions(self.character, self.location, capability_sources=[source])

        matching = [a for a in actions if a.application_name == "Ignite Staged"]
        assert len(matching) == 1
        assert matching[0].target_object == torch
        assert matching[0].resolved_default_template == self.template
