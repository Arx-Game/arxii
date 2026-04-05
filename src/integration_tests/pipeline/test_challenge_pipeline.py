"""End-to-end pipeline tests for the challenge system.

Test structure:
  ChallengeAvailabilityTests       — trait-derived capabilities produce correct approaches
  TechniqueChallengePipelineTests  — technique → capability grant → application → approach
  ChallengeResolutionTests         — check → consequence → effects → record
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from integration_tests.game_content.challenges import ChallengeContent
from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.magic import MagicContent
from integration_tests.game_content.social import SocialContent
from world.mechanics.constants import CapabilitySourceType
from world.mechanics.models import ChallengeApproach, ChallengeInstance, CharacterChallengeRecord
from world.mechanics.services import get_available_actions
from world.mechanics.types import CapabilitySource

# ---------------------------------------------------------------------------
# Test Class 1: Challenge Availability
# ---------------------------------------------------------------------------


class ChallengeAvailabilityTests(TestCase):
    """Characters with trait-derived capabilities see correct approaches on active challenges."""

    @classmethod
    def setUpTestData(cls) -> None:
        social_result = SocialContent.create_all()
        cls.content = ChallengeContent.create_all(social_result.outcomes)

        from evennia_extensions.factories import ObjectDBFactory

        cls.room = ObjectDBFactory(
            db_key="test_dungeon", db_typeclass_path="typeclasses.rooms.Room"
        )

        # Create ChallengeInstances for Locked Door and Darkness
        from world.mechanics.factories import ChallengeInstanceFactory

        cls.locked_door_instance = ChallengeInstanceFactory(
            template=cls.content.challenges["Locked Door"],
            location=cls.room,
            target_object=ObjectDBFactory(db_key="rusty_door"),
        )
        cls.darkness_instance = ChallengeInstanceFactory(
            template=cls.content.challenges["Darkness"],
            location=cls.room,
            target_object=ObjectDBFactory(db_key="dark_corridor"),
        )

        cls.warrior_char, cls.warrior_persona = CharacterContent.create_base_challenge_character(
            name="Warrior"
        )

    def _get_display_names(self) -> list[str]:
        """Get display names from all available actions for the warrior in the room."""
        actions = get_available_actions(self.warrior_char, self.room)
        return [a.display_name for a in actions]

    def test_strength_character_sees_force_approaches(self) -> None:
        """Warrior with strength sees 'Break Down' on Locked Door."""
        display_names = self._get_display_names()
        assert "Break Down" in display_names

    def test_perception_character_sees_perception_approaches(self) -> None:
        """Warrior with perception sees 'Scout Ahead' on Darkness."""
        display_names = self._get_display_names()
        assert "Scout Ahead" in display_names

    def test_agility_character_sees_precision_approaches(self) -> None:
        """Warrior with agility (→ precision) sees 'Pick the Lock' on Locked Door."""
        display_names = self._get_display_names()
        assert "Pick the Lock" in display_names

    def test_intellect_character_sees_no_analysis_approaches_without_matching_property(
        self,
    ) -> None:
        """Intellect → analysis, but Locked Door lacks 'mechanical' property so no match.

        The 'Analyze Mechanism' approach is registered on the template but its Application
        ('Solve') targets the 'mechanical' property. The Locked Door only has 'locked',
        'solid', and 'breakable' — so the approach is correctly filtered out.
        """
        actions = get_available_actions(self.warrior_char, self.room)
        analysis_actions = [a for a in actions if a.capability_source.capability_name == "analysis"]
        assert len(analysis_actions) == 0, (
            f"Expected no analysis-based actions (property mismatch), got: "
            f"{[a.display_name for a in analysis_actions]}"
        )

    def test_character_without_relevant_stats_sees_no_approaches(self) -> None:
        """A bare character with no trait values sees no available actions."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import (
            CharacterIdentityFactory,
            CharacterSheetFactory,
        )
        from world.magic.factories import CharacterAnimaFactory

        bare_char = CharacterFactory(db_key="Nobody")
        CharacterIdentityFactory(character=bare_char)
        CharacterSheetFactory(character=bare_char)
        CharacterAnimaFactory(character=bare_char)

        actions = get_available_actions(bare_char, self.room)
        assert len(actions) == 0, f"Expected 0 actions, got {len(actions)}: {actions}"


# ---------------------------------------------------------------------------
# Test Class 2: Technique Challenge Pipeline
# ---------------------------------------------------------------------------


class TechniqueChallengePipelineTests(TestCase):
    """Full technique -> capability grant -> application -> challenge approach pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        social_result = SocialContent.create_all()
        cls.content = ChallengeContent.create_all(social_result.outcomes)
        cls.magic_result = MagicContent.create_all()

        # Create elemental techniques with capability grants
        cls.elemental_techniques, cls.elemental_grants = MagicContent.create_elemental_techniques(
            cls.content.capability_types
        )

        # Wire social technique capabilities
        cls.social_grants = MagicContent.wire_social_technique_capabilities(
            cls.magic_result.techniques, cls.content.capability_types
        )

        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.factories import ChallengeInstanceFactory

        cls.room = ObjectDBFactory(
            db_key="technique_dungeon", db_typeclass_path="typeclasses.rooms.Room"
        )

        cls.flood_instance = ChallengeInstanceFactory(
            template=cls.content.challenges["Flooded Chamber"],
            location=cls.room,
            target_object=ObjectDBFactory(db_key="flooded_room"),
        )
        cls.darkness_instance = ChallengeInstanceFactory(
            template=cls.content.challenges["Darkness"],
            location=cls.room,
            target_object=ObjectDBFactory(db_key="dark_passage"),
        )
        cls.noble_instance = ChallengeInstanceFactory(
            template=cls.content.challenges["Proud Noble"],
            location=cls.room,
            target_object=ObjectDBFactory(db_key="noble_npc"),
        )

        # Fire character: knows Flame Lance
        cls.fire_char, _ = CharacterContent.create_base_challenge_character(name="Pyro")
        MagicContent.grant_techniques_to_character(
            cls.fire_char, [cls.elemental_techniques["Flame Lance"]]
        )

        # Shadow character: knows Shadow Step
        cls.shadow_char, _ = CharacterContent.create_base_challenge_character(name="Shade")
        MagicContent.grant_techniques_to_character(
            cls.shadow_char, [cls.elemental_techniques["Shadow Step"]]
        )

        # Social character: knows all social techniques
        cls.social_char, _ = CharacterContent.create_base_social_character(name="Diplomat")
        MagicContent.grant_techniques_to_character(
            cls.social_char, list(cls.magic_result.techniques.values())
        )

    def test_flame_lance_sees_generation_approaches_on_flood(self) -> None:
        """Flame Lance grants generation capability -> 'Boil Away' on Flooded Chamber."""
        actions = get_available_actions(self.fire_char, self.room)
        display_names = [a.display_name for a in actions]
        assert "Boil Away" in display_names

    def test_flame_lance_sees_force_approaches_on_flood(self) -> None:
        """Flame Lance grants force capability -> 'Force Drain' on Flooded Chamber."""
        actions = get_available_actions(self.fire_char, self.room)
        display_names = [a.display_name for a in actions]
        assert "Force Drain" in display_names

    def test_flame_lance_sees_illuminate_on_darkness(self) -> None:
        """Flame Lance grants generation capability -> 'Create Light' on Darkness."""
        actions = get_available_actions(self.fire_char, self.room)
        display_names = [a.display_name for a in actions]
        assert "Create Light" in display_names

    def test_shadow_step_sees_navigate_on_darkness(self) -> None:
        """Shadow Step grants traversal capability -> 'Navigate Blind' on Darkness."""
        actions = get_available_actions(self.shadow_char, self.room)
        display_names = [a.display_name for a in actions]
        assert "Navigate Blind" in display_names

    def test_social_technique_sees_social_approaches_on_noble(self) -> None:
        """Social techniques grant intimidation capability -> 'Cow' on Proud Noble."""
        actions = get_available_actions(self.social_char, self.room)
        display_names = [a.display_name for a in actions]
        assert "Cow" in display_names

    def test_multi_capability_technique_produces_multiple_approaches(self) -> None:
        """Technique-sourced actions should produce >= 3 approaches."""
        actions = get_available_actions(self.fire_char, self.room)
        technique_actions = [
            a for a in actions if a.capability_source.source_type == CapabilitySourceType.TECHNIQUE
        ]
        assert len(technique_actions) >= 3, (
            f"Expected >= 3 technique-sourced actions, got {len(technique_actions)}"
        )


# ---------------------------------------------------------------------------
# Test Class 3: Challenge Resolution
# ---------------------------------------------------------------------------


class ChallengeResolutionTests(TestCase):
    """Full resolution: check -> consequence -> effects -> record."""

    @classmethod
    def setUpTestData(cls) -> None:
        social_result = SocialContent.create_all()
        cls.content = ChallengeContent.create_all(social_result.outcomes)

        # Need elemental techniques for technique-sourced actions on Darkness
        cls.elemental_techniques, cls.elemental_grants = MagicContent.create_elemental_techniques(
            cls.content.capability_types
        )

        from evennia_extensions.factories import ObjectDBFactory

        cls.room = ObjectDBFactory(
            db_key="resolution_dungeon", db_typeclass_path="typeclasses.rooms.Room"
        )
        cls.darkness_template = cls.content.challenges["Darkness"]

        # Character with challenge stats
        cls.char, _ = CharacterContent.create_base_challenge_character(name="Resolver")

    def _create_fresh_instance(self) -> ChallengeInstance:
        """Create a new active ChallengeInstance for each test (resolution may deactivate)."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.factories import ChallengeInstanceFactory

        return ChallengeInstanceFactory(
            template=self.darkness_template,
            location=self.room,
            target_object=ObjectDBFactory(),
        )

    def _get_approach_and_source(
        self, instance: ChallengeInstance
    ) -> tuple[ChallengeApproach, CapabilitySource]:
        """Get first available approach and its capability source for the test character."""
        actions = get_available_actions(self.char, self.room)
        matching = [a for a in actions if a.challenge_instance_id == instance.pk]
        assert matching, "No available actions found for the challenge instance"
        action = matching[0]
        approach = ChallengeApproach.objects.get(pk=action.approach_id)
        return approach, action.capability_source

    def test_successful_resolution_creates_record(self) -> None:
        """A high roll creates a CharacterChallengeRecord."""
        from world.mechanics.challenge_resolution import resolve_challenge

        instance = self._create_fresh_instance()
        approach, source = self._get_approach_and_source(instance)

        with patch("world.checks.services.random.randint", return_value=90):
            resolve_challenge(self.char, instance, approach, source)

        assert CharacterChallengeRecord.objects.filter(
            character=self.char,
            challenge_instance=instance,
        ).exists()

    def test_failed_resolution_leaves_challenge_active(self) -> None:
        """A low roll leaves the challenge active."""
        from world.mechanics.challenge_resolution import resolve_challenge

        instance = self._create_fresh_instance()
        approach, source = self._get_approach_and_source(instance)

        with patch("world.checks.services.random.randint", return_value=5):
            resolve_challenge(self.char, instance, approach, source)

        instance.refresh_from_db()
        assert instance.is_active is True

    def test_critical_success_applies_bonus_condition(self) -> None:
        """A maximum roll creates a record with a non-null consequence."""
        from world.mechanics.challenge_resolution import resolve_challenge

        instance = self._create_fresh_instance()
        approach, source = self._get_approach_and_source(instance)

        with patch("world.checks.services.random.randint", return_value=100):
            resolve_challenge(self.char, instance, approach, source)

        record = CharacterChallengeRecord.objects.get(
            character=self.char,
            challenge_instance=instance,
        )
        assert record.consequence is not None
