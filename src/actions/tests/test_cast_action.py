"""Tests for CastTechniqueAction (#1351): immediate cast, soulfray gate, accept soulfray.

Three TDD scenarios:
(a) Immediate cast resolves + deducts anima (existing path still works with default confirm=True).
(b) When get_soulfray_warning is non-None, first cast (confirm=False) registers a pending entry,
    returns success=False with the warning message, and does NOT resolve (no anima deducted).
(c) accept soulfray → re-dispatch with confirm=True resolves the cast.

Uses setUp (not setUpTestData) for ObjectDB objects to avoid the DbHolder deepcopy trap in CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia import create_object
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.cast import CastTechniqueAction
from actions.factories import ActionTemplateFactory
from commands.pending_actions import peek_pending, pop_pending
from world.magic.factories import BinaryEffectTypeFactory, CharacterAnimaFactory, TechniqueFactory
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


class CastTechniqueActionTests(TestCase):
    """CastTechniqueAction: immediate cast, soulfray gate, soulfray accept."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        self.room = create_object("typeclasses.rooms.Room", key="CastActionTestRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)

        self.persona = PersonaFactory()
        self.character = self.persona.character_sheet.character
        self.character.db_location = self.room
        self.character.save()

        self.technique = TechniqueFactory(
            anima_cost=20,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        grant_technique(self.persona, self.technique)

        CharacterVitals.objects.create(
            character_sheet=self.persona.character_sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=30,
        )

        self._check_patcher = patch(
            "actions.services.perform_check",
            return_value=MagicMock(
                success_level=2,
                outcome=MagicMock(name="Success"),
                outcome_name="Success",
            ),
        )
        self._check_patcher.start()
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()

    def tearDown(self) -> None:
        self._check_patcher.stop()
        self._accrue_patcher.stop()
        # Clean up any pending cast state.
        pop_pending(self.persona.character_sheet.pk)

    # -------------------------------------------------------------------------
    # (a) Immediate cast resolves and deducts anima.
    # -------------------------------------------------------------------------

    def test_immediate_cast_returns_success(self) -> None:
        """CastTechniqueAction.execute returns success=True for a clean immediate cast."""
        action = CastTechniqueAction()
        result = action.run(
            actor=self.character,
            technique_id=self.technique.pk,
            confirm_soulfray_risk=True,
        )
        self.assertTrue(result.success, f"Expected success=True, got: {result.message}")

    def test_immediate_cast_deducts_anima(self) -> None:
        """An immediate cast deducts anima via use_technique."""
        anima_before = self.anima.current

        action = CastTechniqueAction()
        result = action.run(
            actor=self.character,
            technique_id=self.technique.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success)
        self.anima.refresh_from_db()
        self.assertLess(
            self.anima.current,
            anima_before,
            "anima.current must decrease after a resolved cast",
        )

    def test_no_active_scene_returns_failure(self) -> None:
        """Returns success=False when there is no active scene at the character's location."""
        empty_room = create_object("typeclasses.rooms.Room", key="EmptyRoom", nohome=True)
        self.character.db_location = empty_room
        self.character.save()

        action = CastTechniqueAction()
        result = action.run(
            actor=self.character,
            technique_id=self.technique.pk,
        )
        self.assertFalse(result.success)
        self.assertIn("no active scene", result.message or "")

    # -------------------------------------------------------------------------
    # (b) Soulfray gate: first cast (confirm=False) registers pending, success=False.
    # -------------------------------------------------------------------------

    def _make_soulfray_warning(self):
        """Minimal SoulfrayWarning mock."""
        from world.magic.types import SoulfrayWarning

        return SoulfrayWarning(
            stage_name="Fraying",
            stage_description="Your soul fringes with soulfray.",
            has_death_risk=False,
        )

    def test_soulfray_gate_returns_failure(self) -> None:
        """When soulfray warning is active, first cast (confirm=False) returns success=False."""
        warning = self._make_soulfray_warning()

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            result = action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )

        self.assertFalse(result.success, "Soulfray gate must return success=False")

    def test_soulfray_gate_message_contains_warning(self) -> None:
        """The failure message includes the soulfray stage_description."""
        warning = self._make_soulfray_warning()

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            result = action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )

        self.assertIn(warning.stage_description, result.message or "")
        self.assertIn("accept soulfray", result.message or "")

    def test_soulfray_gate_registers_pending_cast(self) -> None:
        """When soulfray gate fires, a PendingCast is registered for the character."""
        warning = self._make_soulfray_warning()
        sheet_pk = self.persona.character_sheet.pk

        # Ensure no pre-existing pending.
        pop_pending(sheet_pk)

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )

        pending = peek_pending(sheet_pk)
        self.assertIsNotNone(pending, "A PendingCast must be registered after soulfray gate")
        self.assertEqual(pending.technique_id, self.technique.pk)

    def test_soulfray_gate_does_not_deduct_anima(self) -> None:
        """When soulfray gate fires, anima is NOT deducted."""
        warning = self._make_soulfray_warning()
        anima_before = self.anima.current

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )

        self.anima.refresh_from_db()
        self.assertEqual(
            self.anima.current,
            anima_before,
            "anima must NOT be deducted when soulfray gate fires",
        )

    def test_soulfray_gate_does_not_advance_quorum(self) -> None:
        """The dispatcher records anti-spam + pose-order side-effects only when success=True.

        Verifies that the cast_services path does not create a SceneActionRequest
        (no DB row persisted) when soulfray gate fires — the cast simply did not happen.
        """
        from world.scenes.action_models import SceneActionRequest

        warning = self._make_soulfray_warning()

        before_count = SceneActionRequest.objects.count()
        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )

        after_count = SceneActionRequest.objects.count()
        self.assertEqual(
            before_count,
            after_count,
            "No SceneActionRequest must be created when soulfray gate fires (cast did not happen)",
        )

    # -------------------------------------------------------------------------
    # (c) accept soulfray → re-dispatch with confirm=True resolves the cast.
    # -------------------------------------------------------------------------

    def test_confirm_soulfray_resolves_cast(self) -> None:
        """Re-dispatching with confirm_soulfray_risk=True resolves the cast even with a warning.

        Simulates the accept-soulfray path: call with confirm=True when soulfray is active.
        The cast should proceed and succeed.
        """
        warning = self._make_soulfray_warning()

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            # First call: gate fires.
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )
            # Second call: confirm=True → cast resolves.
            result = action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=True,
            )

        self.assertTrue(
            result.success,
            f"Re-dispatch with confirm_soulfray_risk=True must succeed; got: {result.message}",
        )

    def test_confirm_soulfray_deducts_anima(self) -> None:
        """Re-dispatching with confirm=True deducts anima (the cast resolved)."""
        warning = self._make_soulfray_warning()
        anima_before = self.anima.current

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            action = CastTechniqueAction()
            # Gate fires on first call; no anima deducted.
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=False,
            )
            # Accept: confirm=True → cast resolves → anima deducted.
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=True,
            )

        self.anima.refresh_from_db()
        self.assertLess(
            self.anima.current,
            anima_before,
            "anima.current must decrease after a confirmed cast",
        )


class CastTechniqueActionPullTests(TestCase):
    """CastTechniqueAction.execute forwards cast_pull into request_technique_cast (#1455)."""

    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        from actions.factories import ActionTemplateFactory
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            CharacterAnimaFactory,
            TechniqueFactory,
        )
        from world.scenes.factories import PersonaFactory, SceneFactory
        from world.scenes.tests.cast_test_helpers import grant_technique
        from world.traits.factories import CheckSystemSetupFactory
        from world.vitals.models import CharacterVitals

        CheckSystemSetupFactory.create()

        self.room = create_object(
            "typeclasses.rooms.Room", key="CastPullActionTestRoom", nohome=True
        )
        self.scene = SceneFactory(location=self.room)

        self.persona = PersonaFactory()
        self.character = self.persona.character_sheet.character
        self.character.db_location = self.room
        self.character.save()

        self.technique = TechniqueFactory(
            anima_cost=20,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        grant_technique(self.persona, self.technique)

        CharacterVitals.objects.create(
            character_sheet=self.persona.character_sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=30,
        )

        self._check_patcher = patch(
            "actions.services.perform_check",
            return_value=MagicMock(
                success_level=2,
                outcome=MagicMock(name="Success"),
                outcome_name="Success",
            ),
        )
        self._check_patcher.start()
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()

    def tearDown(self) -> None:
        self._check_patcher.stop()
        self._accrue_patcher.stop()

    def _make_mock_pull(self):
        """Return a minimal CastPullDeclaration mock."""
        from world.magic.types.pull import CastPullDeclaration

        return MagicMock(spec=CastPullDeclaration)

    def test_cast_pull_forwarded_to_request_technique_cast(self) -> None:
        """CastTechniqueAction.execute passes cast_pull into request_technique_cast."""
        mock_pull = self._make_mock_pull()

        with patch(
            "world.scenes.cast_services.request_technique_cast",
        ) as mock_request:
            mock_cast = MagicMock()
            mock_cast.soulfray_warning = None
            mock_request.return_value = mock_cast

            action = CastTechniqueAction()
            result = action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=True,
                cast_pull=mock_pull,
            )

        self.assertTrue(result.success, f"Expected success=True, got: {result.message}")
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        self.assertIs(call_kwargs.get("cast_pull"), mock_pull)

    def test_no_cast_pull_forwards_none_to_request_technique_cast(self) -> None:
        """When cast_pull is omitted, request_technique_cast receives cast_pull=None."""
        with patch(
            "world.scenes.cast_services.request_technique_cast",
        ) as mock_request:
            mock_cast = MagicMock()
            mock_cast.soulfray_warning = None
            mock_request.return_value = mock_cast

            action = CastTechniqueAction()
            action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=True,
            )

        call_kwargs = mock_request.call_args.kwargs
        self.assertIsNone(call_kwargs.get("cast_pull"))

    def test_magic_error_from_pull_returns_clean_failure(self) -> None:
        """A MagicError raised by request_technique_cast becomes a clean failure result."""
        from world.magic.exceptions import MagicError

        mock_pull = self._make_mock_pull()

        with patch(
            "world.scenes.cast_services.request_technique_cast",
            side_effect=MagicError("Pull anchor not in action."),
        ):
            action = CastTechniqueAction()
            result = action.run(
                actor=self.character,
                technique_id=self.technique.pk,
                confirm_soulfray_risk=True,
                cast_pull=mock_pull,
            )

        self.assertFalse(result.success)
        self.assertIn("Pull anchor not in action.", result.message or "")
