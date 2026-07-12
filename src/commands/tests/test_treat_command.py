"""Telnet commands for the treat_condition action."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.conditions import CmdTreatCondition
from commands.consent import CmdAccept
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory


class TreatCommandTests(TestCase):
    """End-to-end telnet tests for listing and requesting treatment."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="Clinic",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.helper_char = CharacterFactory(location=self.room)
        self.target_char = CharacterFactory(location=self.room)
        self.helper_sheet = CharacterSheetFactory(character=self.helper_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.scene = SceneFactory(is_active=True, location=self.room)

        # Bust the per-location active-scene cache.
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        self.condition = ConditionTemplateFactory(name="Test Ailment")
        self.treatment = TreatmentTemplateFactory(
            target_condition=self.condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=False,
            scene_required=True,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=self.condition,
        )

    def _run(self, cmd_cls: type, caller: object, args: str = "") -> object:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}".strip()
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_lists_candidates(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """Bare treat <target> prints the candidate listing."""
        self._run(CmdTreatCondition, self.helper_char, self.target_char.db_key)

        call_args = self.helper_char.msg.call_args
        self.assertIsNotNone(call_args)
        message = call_args[0][0]
        self.assertIn("Treatable conditions on", message)
        self.assertIn(self.treatment.name, message)
        self.assertIn(str(self.instance), message)

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    @patch("world.conditions.services.perform_treatment")
    def test_treat_creates_resolved_request_with_fks(
        self,
        mock_perform_treatment: MagicMock,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """treat <target> 1 creates a SceneActionRequest with treatment FKs set.

        #2214: the target is NPC (no db_account wired in this fixture), so the
        request auto-resolves immediately instead of staying PENDING.
        """
        outcome = MagicMock()
        outcome.target_resolved = False
        mock_perform_treatment.return_value = outcome

        self._run(
            CmdTreatCondition,
            self.helper_char,
            f"{self.target_char.db_key} 1",
        )

        request = SceneActionRequest.objects.get(
            initiator_persona=self.helper_sheet.primary_persona,
        )
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertEqual(request.action_key, "treat_condition")
        self.assertEqual(request.target_persona, self.target_sheet.primary_persona)
        self.assertEqual(request.treatment, self.treatment)
        self.assertEqual(request.target_condition_instance, self.instance)
        self.assertIsNone(request.target_pending_alteration)
        self.assertIsNone(request.thread_used)

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    @patch("world.conditions.services.perform_treatment")
    def test_target_accept_invokes_perform_treatment(
        self,
        mock_perform_treatment: MagicMock,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """Target runs accept and the custom resolver calls perform_treatment."""
        outcome = MagicMock()
        outcome.target_resolved = False
        mock_perform_treatment.return_value = outcome

        self._run(
            CmdTreatCondition,
            self.helper_char,
            f"{self.target_char.db_key} 1",
        )
        request = SceneActionRequest.objects.get(
            initiator_persona=self.helper_sheet.primary_persona,
        )

        self._run(CmdAccept, self.target_char)

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        mock_perform_treatment.assert_called_once()
        call_kwargs = mock_perform_treatment.call_args.kwargs
        self.assertEqual(call_kwargs["helper_sheet"], self.helper_sheet)
        self.assertEqual(call_kwargs["target_sheet"], self.target_sheet)
        self.assertEqual(call_kwargs["treatment"], self.treatment)
        self.assertEqual(call_kwargs["target_effect"], self.instance)
