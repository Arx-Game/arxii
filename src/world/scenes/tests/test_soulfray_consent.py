"""Tests for the soulfray consent gate in cast_services (#1351).

Verifies that ``request_technique_cast`` with ``confirm_soulfray_risk=False``:
- Returns a ``CastResult`` with ``soulfray_warning`` populated.
- Does NOT persist a ``SceneActionRequest`` row.
- Does NOT deduct anima.

And with ``confirm_soulfray_risk=True``:
- Resolves the cast normally (request persisted, anima deducted).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia import create_object
from evennia.utils.idmapper import models as idmapper_models

from actions.factories import ActionTemplateFactory
from world.magic.factories import BinaryEffectTypeFactory, CharacterAnimaFactory, TechniqueFactory
from world.magic.types import SoulfrayWarning
from world.scenes.action_models import SceneActionRequest
from world.scenes.cast_services import request_technique_cast
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


class SoulfrayConsentCastServicesTests(TestCase):
    """request_technique_cast: confirm_soulfray_risk threading."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        self.room = create_object("typeclasses.rooms.Room", key="SoulfraCastRoom", nohome=True)
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

    def _make_warning(self) -> SoulfrayWarning:
        return SoulfrayWarning(
            stage_name="Fraying",
            stage_description="Soulfray is building.",
            has_death_risk=False,
        )

    def test_confirm_false_with_warning_returns_soulfray_cast_result(self) -> None:
        """confirm_soulfray_risk=False + active warning → soulfray_warning populated."""
        warning = self._make_warning()
        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.persona,
                technique=self.technique,
                confirm_soulfray_risk=False,
            )

        self.assertIsNotNone(cast.soulfray_warning)
        self.assertIsNone(cast.result, "result must be None (cast did not happen)")

    def test_confirm_false_with_warning_does_not_persist_request(self) -> None:
        """confirm_soulfray_risk=False + active warning → no SceneActionRequest created."""
        warning = self._make_warning()
        before = SceneActionRequest.objects.count()

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.persona,
                technique=self.technique,
                confirm_soulfray_risk=False,
            )

        self.assertEqual(
            SceneActionRequest.objects.count(),
            before,
            "No SceneActionRequest must be created when the soulfray gate fires",
        )

    def test_confirm_false_with_warning_does_not_deduct_anima(self) -> None:
        """confirm_soulfray_risk=False + active warning → anima not deducted."""
        warning = self._make_warning()
        anima_before = self.anima.current

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.persona,
                technique=self.technique,
                confirm_soulfray_risk=False,
            )

        self.anima.refresh_from_db()
        self.assertEqual(
            self.anima.current,
            anima_before,
            "anima must NOT be deducted when soulfray gate fires",
        )

    def test_confirm_true_with_warning_resolves_cast(self) -> None:
        """confirm_soulfray_risk=True proceeds even with an active soulfray warning."""
        warning = self._make_warning()

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            cast = request_technique_cast(
                scene=self.scene,
                initiator_persona=self.persona,
                technique=self.technique,
                confirm_soulfray_risk=True,
            )

        self.assertIsNotNone(cast.result, "Cast must resolve when confirm_soulfray_risk=True")
        self.assertIsNone(cast.soulfray_warning, "soulfray_warning must be None on resolved cast")

    def test_confirm_true_with_warning_deducts_anima(self) -> None:
        """confirm_soulfray_risk=True deducts anima (cast resolved)."""
        warning = self._make_warning()
        anima_before = self.anima.current

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=warning,
        ):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.persona,
                technique=self.technique,
                confirm_soulfray_risk=True,
            )

        self.anima.refresh_from_db()
        self.assertLess(
            self.anima.current,
            anima_before,
            "anima.current must decrease when confirm_soulfray_risk=True resolves the cast",
        )

    def test_default_confirm_true_resolves_cast(self) -> None:
        """Default call (no confirm_soulfray_risk) still resolves the cast (backward compat)."""
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.persona,
            technique=self.technique,
        )
        self.assertIsNotNone(cast.result, "Default call must still resolve the cast")
        self.assertIsNone(cast.soulfray_warning)
