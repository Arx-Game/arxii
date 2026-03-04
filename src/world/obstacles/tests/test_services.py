"""Tests for obstacle system service functions."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory
from world.obstacles.constants import DiscoveryType
from world.obstacles.factories import (
    BypassCapabilityRequirementFactory,
    BypassCheckRequirementFactory,
    BypassOptionFactory,
    CharacterBypassDiscoveryFactory,
    CharacterBypassRecordFactory,
    ObstacleInstanceFactory,
    ObstaclePropertyFactory,
    ObstacleTemplateFactory,
)
from world.obstacles.services import get_bypass_options_for_character, get_obstacles_for_object


class GetObstaclesForObjectTest(TestCase):
    """Tests for get_obstacles_for_object service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.exit_obj = ObjectDBFactory(db_key="North Exit")
        cls.character = ObjectDBFactory(db_key="Alice")
        cls.template = ObstacleTemplateFactory(name="Rushing River")

    def test_no_obstacles(self) -> None:
        obstacles = get_obstacles_for_object(self.exit_obj)
        assert obstacles == []

    def test_returns_active_obstacles(self) -> None:
        ObstacleInstanceFactory(template=self.template, target=self.exit_obj)
        obstacles = get_obstacles_for_object(self.exit_obj)
        assert len(obstacles) == 1
        assert obstacles[0].template == self.template

    def test_excludes_inactive_obstacles(self) -> None:
        ObstacleInstanceFactory(
            template=self.template,
            target=self.exit_obj,
            is_active=False,
        )
        obstacles = get_obstacles_for_object(self.exit_obj)
        assert obstacles == []

    def test_multiple_obstacles(self) -> None:
        template2 = ObstacleTemplateFactory(name="Arcane Ward")
        ObstacleInstanceFactory(template=self.template, target=self.exit_obj)
        ObstacleInstanceFactory(template=template2, target=self.exit_obj)
        obstacles = get_obstacles_for_object(self.exit_obj)
        assert len(obstacles) == 2

    def test_excludes_personally_bypassed_for_character(self) -> None:
        instance = ObstacleInstanceFactory(template=self.template, target=self.exit_obj)
        bypass = BypassOptionFactory(name="Swim Across")
        CharacterBypassRecordFactory(
            character=self.character,
            obstacle_instance=instance,
            bypass_option=bypass,
        )
        obstacles = get_obstacles_for_object(self.exit_obj, character=self.character)
        assert obstacles == []

    def test_personally_bypassed_still_blocks_others(self) -> None:
        instance = ObstacleInstanceFactory(template=self.template, target=self.exit_obj)
        bypass = BypassOptionFactory(name="Fly Over")
        CharacterBypassRecordFactory(
            character=self.character,
            obstacle_instance=instance,
            bypass_option=bypass,
        )
        other_char = ObjectDBFactory(db_key="Bob")
        obstacles = get_obstacles_for_object(self.exit_obj, character=other_char)
        assert len(obstacles) == 1


class GetBypassOptionsForCharacterTest(TestCase):
    """Tests for get_bypass_options_for_character service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDBFactory(db_key="Alice")
        cls.exit_obj = ObjectDBFactory(db_key="North Exit")

        # Set up a "tall" obstacle with two bypass options
        cls.tall = ObstaclePropertyFactory(name="tall")
        cls.fly_bypass = BypassOptionFactory(
            obstacle_property=cls.tall,
            name="Fly Over",
            discovery_type=DiscoveryType.OBVIOUS,
        )
        cls.phase_bypass = BypassOptionFactory(
            obstacle_property=cls.tall,
            name="Phase Through",
            discovery_type=DiscoveryType.DISCOVERABLE,
        )
        cls.flight = CapabilityTypeFactory(name="flight")
        cls.phasing = CapabilityTypeFactory(name="phasing")
        BypassCapabilityRequirementFactory(
            bypass_option=cls.fly_bypass,
            capability_type=cls.flight,
            minimum_value=1,
        )
        BypassCapabilityRequirementFactory(
            bypass_option=cls.phase_bypass,
            capability_type=cls.phasing,
            minimum_value=3,
        )

        cls.template = ObstacleTemplateFactory(name="High Ledge")
        cls.template.properties.set([cls.tall])

    def _make_instance(self) -> "ObstacleInstance":
        return ObstacleInstanceFactory(
            template=self.template,
            target=self.exit_obj,
        )

    def test_obvious_bypass_visible_without_capability(self) -> None:
        """Obvious bypasses are always visible, but can_attempt=False if
        character lacks the capability."""
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance, self.character, character_capabilities={}
        )
        fly = next(o for o in options if o.bypass_option == self.fly_bypass)
        assert fly.can_attempt is False
        assert "flight" in fly.missing_capabilities

    def test_obvious_bypass_attemptable_with_capability(self) -> None:
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"flight": 5},
        )
        fly = next(o for o in options if o.bypass_option == self.fly_bypass)
        assert fly.can_attempt is True
        assert fly.missing_capabilities == []

    def test_discoverable_bypass_hidden_without_discovery(self) -> None:
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"phasing": 10},
        )
        names = [o.bypass_option.name for o in options]
        assert "Phase Through" not in names

    def test_discoverable_bypass_visible_after_discovery(self) -> None:
        instance = self._make_instance()
        CharacterBypassDiscoveryFactory(
            character=self.character,
            bypass_option=self.phase_bypass,
        )
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"phasing": 10},
        )
        phase = next(o for o in options if o.bypass_option == self.phase_bypass)
        assert phase.can_attempt is True

    def test_capability_below_threshold(self) -> None:
        """Character has capability but at too low a value."""
        # Use a separate bypass to avoid SharedMemoryModel cache pollution
        low_bypass = BypassOptionFactory(
            obstacle_property=self.tall,
            name="Endurance Run",
            discovery_type=DiscoveryType.OBVIOUS,
        )
        BypassCapabilityRequirementFactory(
            bypass_option=low_bypass,
            capability_type=CapabilityTypeFactory(name="endurance"),
            minimum_value=10,
        )
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"endurance": 3},
        )
        run = next(o for o in options if o.bypass_option == low_bypass)
        assert run.can_attempt is False
        assert "endurance" in run.missing_capabilities

    def test_check_requirement_included(self) -> None:
        athletics = CheckTypeFactory(name="Athletics")
        BypassCheckRequirementFactory(
            bypass_option=self.fly_bypass,
            check_type=athletics,
            base_target_difficulty=20,
        )
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"flight": 5},
        )
        fly = next(o for o in options if o.bypass_option == self.fly_bypass)
        assert fly.check_type == athletics
        # severity=1, so effective = 20 * 1 = 20
        assert fly.effective_difficulty == 20

    def test_severity_scales_difficulty(self) -> None:
        self.template.severity = 3
        self.template.save()
        athletics = CheckTypeFactory(name="Athletics")
        BypassCheckRequirementFactory(
            bypass_option=self.fly_bypass,
            check_type=athletics,
            base_target_difficulty=20,
        )
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={"flight": 5},
        )
        fly = next(o for o in options if o.bypass_option == self.fly_bypass)
        # severity=3, so effective = 20 * 3 = 60
        assert fly.effective_difficulty == 60
        # Restore severity for other tests
        self.template.severity = 1
        self.template.save()

    def test_no_capability_requirements_always_attemptable(self) -> None:
        """A bypass with no capability requirements is always attemptable."""
        no_req_bypass = BypassOptionFactory(
            obstacle_property=self.tall,
            name="Climb Rope",
            discovery_type=DiscoveryType.OBVIOUS,
        )
        instance = self._make_instance()
        options = get_bypass_options_for_character(
            instance,
            self.character,
            character_capabilities={},
        )
        rope = next(o for o in options if o.bypass_option == no_req_bypass)
        assert rope.can_attempt is True
