"""TDD tests for Task 3 (#1454): soulfray gate in round_declaration.

When a character with an active Soulfray stage declares a cast into a combat
round WITHOUT confirming the risk:
- round_declaration must return an ActionResult (NOT a tuple).
- No CombatRoundAction is recorded (the dispatcher never calls record_declaration).
- A PendingCast is registered carrying all the combat declaration kwargs.

When the player accepts (re-dispatch with confirm_soulfray_risk=True):
- round_declaration returns the normal (PlayerAction, decl_kwargs) tuple.
- ctx.record_declaration creates a CombatRoundAction with confirm_soulfray_risk=True.

The _dispatch_scene_adaptive dispatcher must also handle an ActionResult return
from round_declaration (short-circuit: no record_declaration, no run()).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.combat.round_context import CombatRoundContext
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.types.techniques import SoulfrayWarning
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

_MOCK_WARNING = SoulfrayWarning(
    stage_name="Stage One",
    stage_description="You are accruing soulfray.",
    has_death_risk=False,
)

_PATCH_PATH = "world.magic.services.soulfray.get_soulfray_warning"


def _make_combat_setup():
    """Build a DECLARING encounter + participant + CombatRoundContext.

    Returns a dict with: sheet, character, encounter, participant, ctx.
    Creates CharacterVitals so declare_action (called by record_declaration) passes.
    """
    sheet = CharacterSheetFactory()
    encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
    participant = CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
    )
    CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
    ctx = CombatRoundContext(participant)
    return {
        "sheet": sheet,
        "character": sheet.character,
        "encounter": encounter,
        "participant": participant,
        "ctx": ctx,
    }


def _make_self_targeting_technique():
    """Build a buff technique with a self-targeting applied condition row.

    Using base_power=None avoids auto-creation of a TechniqueDamageProfile,
    so declare_action succeeds without a focused_opponent_target.
    """
    gift = GiftFactory()
    effect_type = EffectTypeFactory(base_power=None)
    technique = TechniqueFactory(gift=gift, effect_type=effect_type, damage_profile=False)
    TechniqueAppliedConditionFactory(technique=technique, target_kind="self")
    return technique


class CombatCastSoulfrayGateUnitTests(TestCase):
    """round_declaration returns ActionResult (not tuple) when soulfray gate fires."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        import commands.pending_actions as pa

        pa._PENDING.clear()

    def tearDown(self) -> None:
        import commands.pending_actions as pa

        pa._PENDING.clear()

    def test_soulfray_gate_returns_action_result_not_tuple(self) -> None:
        """round_declaration returns ActionResult when warning present and not confirmed."""
        from actions.definitions.cast import CastTechniqueAction
        from actions.types import ActionResult

        data = _make_combat_setup()
        technique = TechniqueFactory()

        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            result = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                effort_level="medium",
            )

        self.assertIsInstance(
            result,
            ActionResult,
            "round_declaration must return ActionResult (not a tuple) when soulfray gate fires.",
        )
        self.assertFalse(result.success)
        self.assertIn("accept soulfray", result.message)
        self.assertIn("decline soulfray", result.message)

    def test_soulfray_gate_includes_warning_description_in_message(self) -> None:
        """The soulfray warning stage_description is included in the result message."""
        from actions.definitions.cast import CastTechniqueAction
        from actions.types import ActionResult

        data = _make_combat_setup()
        technique = TechniqueFactory()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            result = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
            )

        self.assertIsInstance(result, ActionResult)
        self.assertIn(_MOCK_WARNING.stage_description, result.message)

    def test_no_combat_round_action_written_when_gate_fires(self) -> None:
        """No CombatRoundAction is written when the soulfray gate fires.

        Since round_declaration returns ActionResult, the dispatcher will NOT
        call ctx.record_declaration, so no row is written.
        """
        from actions.definitions.cast import CastTechniqueAction

        data = _make_combat_setup()
        technique = TechniqueFactory()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
            )

        self.assertFalse(
            CombatRoundAction.objects.filter(participant=data["participant"]).exists(),
            "No CombatRoundAction should be written when the soulfray gate fires.",
        )

    def test_pending_cast_registered_with_combat_kwargs(self) -> None:
        """register_pending is called with the combat declaration kwargs stashed."""
        from actions.definitions.cast import CastTechniqueAction
        from commands.pending_actions import peek_pending

        data = _make_combat_setup()
        technique = TechniqueFactory()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                effort_level="high",
            )

        pending = peek_pending(data["sheet"].pk)
        self.assertIsNotNone(pending, "A PendingCast must be registered when the gate fires.")
        self.assertEqual(pending.technique_id, technique.pk)
        self.assertIsNone(
            pending.target_persona_id,
            "target_persona_id must be None for a combat declaration (combat uses focused_*_id).",
        )
        self.assertEqual(pending.kwargs.get("effort_level"), "high")

    def test_pending_cast_carries_focused_opponent_target_id(self) -> None:
        """focused_opponent_target_id is stashed in PendingCast.kwargs."""
        from actions.definitions.cast import CastTechniqueAction
        from commands.pending_actions import peek_pending

        data = _make_combat_setup()
        technique = TechniqueFactory()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                focused_opponent_target_id=42,
            )

        pending = peek_pending(data["sheet"].pk)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.kwargs.get("focused_opponent_target_id"), 42)

    def test_gate_skipped_when_confirm_soulfray_risk_true(self) -> None:
        """round_declaration returns a tuple (not ActionResult) when confirm_soulfray_risk=True."""
        from actions.definitions.cast import CastTechniqueAction

        data = _make_combat_setup()
        technique = _make_self_targeting_technique()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            result = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                confirm_soulfray_risk=True,
            )

        # Must be a (PlayerAction, decl_kwargs) tuple, not an ActionResult.
        self.assertIsNotNone(result, "round_declaration must return a tuple when confirmed.")
        self.assertIsInstance(result, tuple)
        _pa, decl_kwargs = result
        self.assertTrue(decl_kwargs.get("confirm_soulfray_risk"))

    def test_gate_skipped_when_no_warning(self) -> None:
        """round_declaration returns a tuple when get_soulfray_warning returns None."""
        from actions.definitions.cast import CastTechniqueAction

        data = _make_combat_setup()
        technique = TechniqueFactory()
        action = CastTechniqueAction()

        with patch(_PATCH_PATH, return_value=None):
            result = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
            )

        self.assertIsNotNone(
            result,
            "round_declaration must return a tuple when no soulfray warning is present.",
        )
        self.assertIsInstance(result, tuple)


class CombatCastSoulfrayAcceptPathTests(TestCase):
    """Accept path: re-dispatch with confirm_soulfray_risk=True records the declaration."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        import commands.pending_actions as pa

        pa._PENDING.clear()

    def tearDown(self) -> None:
        import commands.pending_actions as pa

        pa._PENDING.clear()

    def test_accept_path_records_combat_round_action_with_confirm_flag(self) -> None:
        """Full accept path: round_declaration with confirm_soulfray_risk=True → CombatRoundAction.

        Simulates the re-dispatch that SoulfrayPendingHandler.accept triggers:
        round_declaration is called again with confirm_soulfray_risk=True, returning
        a (PlayerAction, decl_kwargs) tuple. ctx.record_declaration then writes the
        CombatRoundAction with confirm_soulfray_risk=True.
        """
        from actions.definitions.cast import CastTechniqueAction

        data = _make_combat_setup()
        technique = _make_self_targeting_technique()
        action = CastTechniqueAction()

        # Phase 1: gate fires (no confirm).
        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            gate_result = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                effort_level="medium",
            )

        # Gate must have fired.
        from actions.types import ActionResult

        self.assertIsInstance(gate_result, ActionResult)
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=data["participant"]).exists(),
        )

        # Phase 2: accept — re-dispatch with confirm_soulfray_risk=True.
        with patch(_PATCH_PATH, return_value=_MOCK_WARNING):
            decl = action.round_declaration(
                data["ctx"],
                technique_id=technique.pk,
                effort_level="medium",
                confirm_soulfray_risk=True,
            )

        self.assertIsInstance(decl, tuple, "Accept path must return a declaration tuple.")
        pa_obj, decl_kwargs = decl
        self.assertTrue(decl_kwargs.get("confirm_soulfray_risk"))

        # Record the declaration.
        data["ctx"].record_declaration(data["sheet"], pa_obj, decl_kwargs)

        round_action = CombatRoundAction.objects.filter(
            participant=data["participant"],
            round_number=data["encounter"].round_number,
        ).first()
        self.assertIsNotNone(
            round_action,
            "CombatRoundAction must exist after accept re-dispatch.",
        )
        self.assertTrue(
            round_action.confirm_soulfray_risk,
            "CombatRoundAction must have confirm_soulfray_risk=True after accept.",
        )


class DispatcherSoulfrayShortCircuitTests(TestCase):
    """_dispatch_scene_adaptive handles ActionResult from round_declaration without run()."""

    def setUp(self) -> None:
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()
        pa._PENDING.clear()

    def tearDown(self) -> None:
        import commands.pending_actions as pa

        pa._LAST_ACTED.clear()
        pa._PENDING.clear()

    def _make_character_with_sheet(self):
        """Return (character_mock, sheet) where character.sheet_data == sheet."""
        sheet = CharacterSheetFactory()
        character = MagicMock()
        character.sheet_data = sheet
        return character, sheet

    def test_dispatcher_handles_action_result_from_round_declaration(self) -> None:
        """_dispatch_scene_adaptive short-circuits when round_declaration returns ActionResult.

        - DispatchResult(deferred=False, detail=ActionResult(...)) is returned.
        - action.run() is NOT called.
        - ctx.record_declaration is NOT called.
        """
        from actions.constants import ActionBackend
        from actions.player_interface import _dispatch_scene_adaptive
        from actions.types import ActionRef, ActionResult, DispatchResult

        character, _sheet = self._make_character_with_sheet()
        ref = ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key="cast_technique",
            technique_id=99,
        )

        gate_result = ActionResult(
            success=False,
            message="You are accruing soulfray. Use |waccept soulfray|n to proceed.",
        )

        ctx = MagicMock()
        ctx.is_declaration_open = True
        ctx.is_repeat_blocked.return_value = False

        action_mock = MagicMock()
        action_mock.round_declaration.return_value = gate_result  # ActionResult, not a tuple

        with patch("actions.player_interface.get_action", return_value=action_mock):
            result = _dispatch_scene_adaptive(character, ref, {}, ctx=ctx)

        self.assertIsInstance(result, DispatchResult)
        self.assertFalse(result.deferred, "deferred must be False for a short-circuit result.")
        self.assertIs(result.detail, gate_result)
        self.assertEqual(result.backend, ActionBackend.SCENE_ADAPTIVE)

        action_mock.run.assert_not_called()
        ctx.record_declaration.assert_not_called()
