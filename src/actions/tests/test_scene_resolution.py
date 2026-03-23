"""Tests for resolve_scene_action."""

from django.test import TestCase

from actions.services import resolve_scene_action


class TestResolveSceneAction(TestCase):
    def test_known_action_succeeds(self) -> None:
        result = resolve_scene_action(action_key="intimidate", difficulty=45)
        assert result.success is True
        assert result.action_key == "intimidate"
        assert result.difficulty == 45

    def test_unknown_action_fails(self) -> None:
        result = resolve_scene_action(action_key="nonexistent", difficulty=45)
        assert result.success is False
        assert "Unknown action" in (result.message or "")

    def test_result_has_message(self) -> None:
        result = resolve_scene_action(action_key="persuade", difficulty=30)
        assert result.message is not None
        assert "Persuade" in result.message
