"""End-to-end telnet tests for the treat_condition consent flow (#1486 Task 8).

Unlike the sibling ``test_treat_command.py`` unit tests, these run the REAL
consent → resolver → ``perform_treatment`` → ``decay_condition_severity`` chain
through to a visible severity change. Only the non-deterministic dice
(``perform_check``) is pinned to a success-level-1 ``CheckResult``; every gate
(scene/engagement/bond/duplicate/cost) and the reduction itself runs un-mocked,
mirroring ``test_treatment_aftermath.py`` / ``test_treatment_mage_scar.py``.
"""

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
from world.conditions.models import ConditionInstance
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row.

    Copied from ``test_treatment_aftermath.py`` / ``test_treatment_mage_scar.py``:
    pins only the non-deterministic ``perform_check`` outcome while leaving
    every other gate + the reduction REAL.
    """
    outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


class TreatConditionConsentE2ETests(TestCase):
    """Telnet E2E: ``treat`` → ``accept`` runs the real reduction chain."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap;
        # see test_treatment_views.py for the same note).
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
        # TreatmentTemplateFactory defaults reduction_on_success=3; a severity-5
        # instance → 2 after a success (reduced but still open — the strongest
        # "it actually treated" signal: both the drop AND "still present").
        self.treatment = TreatmentTemplateFactory(
            target_condition=self.condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=False,
            scene_required=True,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=self.condition,
            severity=5,
        )

    def _run(self, cmd_cls: type, caller: object, args: str = "") -> object:
        """Instantiate and run a telnet command with a mocked ``caller.msg``.

        Mirrors the helper in ``test_treat_command.py``.
        """
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
    @patch("world.checks.services.perform_check")
    def test_treat_then_accept_reduces_severity_and_resolves_request(
        self,
        mock_perform_check: MagicMock,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """Full telnet consent chain runs perform_treatment REAL and reduces severity.

        Helper ``treat <target>`` lists candidates; helper ``treat <target> 1``
        auto-resolves immediately (#2214: the target is NPC, no db_account wired
        in this fixture) via the custom resolver → ``perform_treatment`` →
        ``decay_condition_severity`` (REAL). Asserts: severity dropped by
        ``reduction_on_success`` (3) and the instance is still open (resolved_at
        NULL), the request is RESOLVED, and the resolver recorded a result
        interaction (the pose) on the scene. A later ``accept`` is a no-op —
        the request already resolved at creation.
        """
        mock_perform_check.return_value = _make_check_result(success_level=1)

        # Helper lists candidates — confirms the candidate the selector will pick.
        self._run(CmdTreatCondition, self.helper_char, self.target_char.db_key)

        # Helper selects candidate 1 -> the NPC target auto-resolves immediately (#2214).
        self._run(
            CmdTreatCondition,
            self.helper_char,
            f"{self.target_char.db_key} 1",
        )
        request = SceneActionRequest.objects.get(
            initiator_persona=self.helper_sheet.primary_persona,
        )
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.treatment_id == self.treatment.pk
        assert request.target_condition_instance_id == self.instance.pk

        # Severity already dropped by reduction_on_success (3): 5 -> 2, still open.
        self.instance.refresh_from_db()
        assert self.instance.severity == 2, self.instance.severity
        assert self.instance.resolved_at is None, "partial reduction must leave the condition OPEN"

        # A later accept is a no-op — the request already resolved at creation.
        self._run(CmdAccept, self.target_char)
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.result_interaction_id is not None
        # The pose interaction belongs to this scene and the initiator.
        from world.scenes.models import Interaction

        interaction = Interaction.objects.get(pk=request.result_interaction_id)
        assert interaction.scene_id == self.scene.pk
        assert interaction.persona_id == self.helper_sheet.primary_persona.pk

        # perform_check (the only mock) fired exactly once — proving the rest of
        # the gate suite + reduction ran on the real path rather than a stub.
        mock_perform_check.assert_called_once()

        # Sanity: no stray second instance was created on the target.
        assert (
            ConditionInstance.objects.filter(
                target=self.target_char,
                condition=self.condition,
            ).count()
            == 1
        )
