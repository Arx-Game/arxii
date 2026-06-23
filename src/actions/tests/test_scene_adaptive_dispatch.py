"""Tests for SCENE_ADAPTIVE dispatch backend + anti-spam floor.

Covers:
- open (no ctx) → action.run() called, deferred=False
- pose-order blocked → ActionDispatchError(ROUND_REPEAT_BLOCKED)
- strict + round_declaration returns decl → record_declaration called, deferred=True
- anti-spam cooldown active → ActionDispatchError(ANTI_SPAM_COOLDOWN)
- pose-order immediate: SceneActionDeclaration(is_immediate=True) created, round advances
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import django.test

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.types import ActionRef, DispatchResult
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory


def _make_character_with_sheet():
    """Return (character_mock, sheet) where character.sheet_data == sheet."""
    sheet = CharacterSheetFactory()
    character = MagicMock()
    character.sheet_data = sheet
    return character, sheet


def _make_scene_adaptive_ref(registry_key: str = "test_action") -> ActionRef:
    return ActionRef(backend=ActionBackend.SCENE_ADAPTIVE, registry_key=registry_key)


class SceneAdaptiveBackendValueTest(django.test.TestCase):
    """SCENE_ADAPTIVE is present on ActionBackend."""

    def test_value_exists(self):
        self.assertEqual(ActionBackend.SCENE_ADAPTIVE, "scene_adaptive")

    def test_ref_requires_registry_key(self):
        with self.assertRaises(ValueError):
            ActionRef(backend=ActionBackend.SCENE_ADAPTIVE)


class AntiSpamFloorTest(django.test.TestCase):
    """Anti-spam floor: check_anti_spam / mark_acted behave correctly."""

    def setUp(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def tearDown(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def test_no_prior_act_returns_none(self):
        from commands.pending_actions import check_anti_spam

        self.assertIsNone(check_anti_spam(sheet_pk=99, seconds=5))

    def test_immediate_repeat_blocked(self):
        from commands.pending_actions import check_anti_spam, mark_acted

        mark_acted(sheet_pk=1)
        remaining = check_anti_spam(sheet_pk=1, seconds=5)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 0)

    def test_different_sheet_not_blocked(self):
        from commands.pending_actions import check_anti_spam, mark_acted

        mark_acted(sheet_pk=1)
        self.assertIsNone(check_anti_spam(sheet_pk=2, seconds=5))


class SceneAdaptiveDispatchOpenTest(django.test.TestCase):
    """No ctx (open) → action.run() called, deferred=False."""

    def setUp(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def tearDown(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def test_open_runs_immediately(self):
        from actions.player_interface import _dispatch_scene_adaptive

        character, _sheet = _make_character_with_sheet()
        ref = _make_scene_adaptive_ref("test_action")

        action_mock = MagicMock()
        action_mock.round_declaration.return_value = None
        action_mock.run.return_value = MagicMock()

        with patch("actions.player_interface.get_action", return_value=action_mock):
            result = _dispatch_scene_adaptive(character, ref, {}, ctx=None)

        self.assertIsInstance(result, DispatchResult)
        self.assertFalse(result.deferred)
        self.assertEqual(result.backend, ActionBackend.SCENE_ADAPTIVE)
        action_mock.run.assert_called_once()


class SceneAdaptiveDispatchPoseOrderBlockedTest(django.test.TestCase):
    """ctx.is_repeat_blocked → ActionDispatchError(ROUND_REPEAT_BLOCKED)."""

    def setUp(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def tearDown(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def test_pose_order_blocked_rejects(self):
        from actions.player_interface import _dispatch_scene_adaptive

        character, _sheet = _make_character_with_sheet()
        ref = _make_scene_adaptive_ref("test_action")

        ctx = MagicMock()
        ctx.is_declaration_open = False
        ctx.is_repeat_blocked.return_value = True

        action_mock = MagicMock()
        action_mock.round_declaration.return_value = None

        with patch("actions.player_interface.get_action", return_value=action_mock):
            with self.assertRaises(ActionDispatchError) as cm:
                _dispatch_scene_adaptive(character, ref, {}, ctx=ctx)

        self.assertEqual(cm.exception.code, ActionDispatchError.ROUND_REPEAT_BLOCKED)
        action_mock.run.assert_not_called()


class SceneAdaptiveDispatchStrictDeferTest(django.test.TestCase):
    """ctx.is_declaration_open + round_declaration returns decl → deferred=True."""

    def setUp(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def tearDown(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def test_strict_defers_via_round_declaration(self):
        from actions.player_interface import _dispatch_scene_adaptive

        character, sheet = _make_character_with_sheet()
        ref = _make_scene_adaptive_ref("test_action")

        player_action = MagicMock()
        decl_kwargs = {"effort_level": "medium"}

        ctx = MagicMock()
        ctx.is_declaration_open = True
        ctx.is_repeat_blocked.return_value = False

        action_mock = MagicMock()
        action_mock.round_declaration.return_value = (player_action, decl_kwargs)

        with patch("actions.player_interface.get_action", return_value=action_mock):
            result = _dispatch_scene_adaptive(character, ref, {}, ctx=ctx)

        self.assertIsInstance(result, DispatchResult)
        self.assertTrue(result.deferred)
        self.assertEqual(result.backend, ActionBackend.SCENE_ADAPTIVE)
        ctx.record_declaration.assert_called_once_with(sheet, player_action, decl_kwargs)
        action_mock.run.assert_not_called()


class SceneAdaptiveAntiSpamDispatchTest(django.test.TestCase):
    """Anti-spam cooldown active → ActionDispatchError(ANTI_SPAM_COOLDOWN)."""

    def setUp(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def tearDown(self):
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()

    def test_anti_spam_floor_rejects_rapid_repeat(self):
        from actions.player_interface import _dispatch_scene_adaptive
        from commands.pending_actions import mark_acted

        character, sheet = _make_character_with_sheet()
        ref = _make_scene_adaptive_ref("test_action")

        # Mark as acted so cooldown is active
        mark_acted(sheet.pk)

        action_mock = MagicMock()

        with patch("actions.player_interface.get_action", return_value=action_mock):
            with self.assertRaises(ActionDispatchError) as cm:
                _dispatch_scene_adaptive(character, ref, {}, ctx=None)

        self.assertEqual(cm.exception.code, ActionDispatchError.ANTI_SPAM_COOLDOWN)
        action_mock.run.assert_not_called()


class PoseOrderImmediateIntegrationTest(django.test.TestCase):
    """POSE_ORDER immediate: SceneActionDeclaration(is_immediate=True) created + round advances."""

    def test_immediate_pose_order_records_and_advances_on_quorum(self):
        from world.scenes.models import SceneActionDeclaration
        from world.scenes.round_context import SceneRoundContext

        rnd = SceneRoundFactory(
            status=RoundStatus.DECLARING,
            mode=SceneRoundMode.POSE_ORDER,
            round_number=1,
            advance_quorum_pct=100,
        )
        sheet = CharacterSheetFactory()
        participant = SceneRoundParticipantFactory(
            scene_round=rnd,
            character_sheet=sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

        ctx = SceneRoundContext(rnd)
        ctx.record_immediate_action(sheet, None, None)

        decl = SceneActionDeclaration.objects.get(
            scene_round=rnd, participant=participant, is_immediate=True
        )
        self.assertTrue(decl.is_immediate)

        rnd.refresh_from_db()
        self.assertEqual(rnd.round_number, 2)

    def test_open_mode_is_noop(self):
        from world.scenes.models import SceneActionDeclaration
        from world.scenes.round_context import SceneRoundContext

        rnd = SceneRoundFactory(
            status=RoundStatus.DECLARING,
            mode=SceneRoundMode.OPEN,
            round_number=1,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(
            scene_round=rnd,
            character_sheet=sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

        ctx = SceneRoundContext(rnd)
        ctx.record_immediate_action(sheet, None, None)

        # OPEN mode → no declaration row
        self.assertFalse(SceneActionDeclaration.objects.filter(scene_round=rnd).exists())
        rnd.refresh_from_db()
        self.assertEqual(rnd.round_number, 1)
