"""Tests for obstacle system service functions."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.obstacles.factories import (
    BypassOptionFactory,
    CharacterBypassRecordFactory,
    ObstacleInstanceFactory,
    ObstacleTemplateFactory,
)
from world.obstacles.services import get_obstacles_for_object


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
