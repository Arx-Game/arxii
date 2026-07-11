"""Unit tests for offer handler path-resolution logic (#1344).

The path-resolution helper (_resolve_path_by_name) has three fiddly branches
(zero match, ambiguous match, auto-select when name omitted) that the E2E test
doesn't reach. These focused tests cover them.

Also covers ``SoulfrayPendingHandler.accept``'s entrance re-dispatch (#2183 Task 5):
when the popped ``PendingCast.kwargs`` carries the ``"entrance": True`` marker, accept
must re-dispatch through the ``entrance`` REGISTRY action rather than ``cast_technique``,
so a soulfray-confirmed entrance completes as an entrance (flourish + suggestion), not a
bare cast.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.social import EntranceAction
from actions.factories import ActionTemplateFactory
from commands.exceptions import CommandError
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import CharacterResonanceFactory, ensure_dramatic_entrance_content
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.magic.types.techniques import SoulfrayWarning
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


def _make_check_mock(success_level: int) -> MagicMock:
    return MagicMock(
        success_level=success_level,
        outcome=MagicMock(name="Outcome"),
        outcome_name="Success" if success_level > 0 else "Failure",
    )


def _make_paths(*names: str):
    return [PathFactory(name=n, stage=PathStage.PUISSANT) for n in names]


class TestResolvePathByName(TestCase):
    def test_exact_match(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        result = _resolve_path_by_name("Ironwood", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_case_insensitive_substring(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        result = _resolve_path_by_name("iron", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_zero_matches_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("Ember", paths)

    def test_ambiguous_match_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood Peak", "Ironwood Vale")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("Ironwood", paths)

    def test_auto_select_single_path_when_name_omitted(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood")
        result = _resolve_path_by_name("", paths)
        self.assertEqual(result.name, "Ironwood")

    def test_no_name_multiple_paths_raises(self) -> None:
        from world.magic.offer_handlers import _resolve_path_by_name

        paths = _make_paths("Ironwood", "Ashfall")
        with self.assertRaises(CommandError):
            _resolve_path_by_name("", paths)


class SoulfrayPendingHandlerAcceptEntranceTests(CastScenarioMixin):
    """accept() re-dispatches an entrance-marked PendingCast through the entrance path (#2183)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        for persona in (cls.caster, cls.target):
            character = persona.character_sheet.character
            character.db_location = cls.scene.location
            character.save()
        ActionTemplateFactory(name="Entrance", grants_entry_flourish=True)
        moment_type = ensure_dramatic_entrance_content()
        CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet,
            resonance=moment_type.resonance,
        )

    def setUp(self) -> None:
        super().setUp()
        import commands.pending_actions as pa

        pa._PENDING.clear()

    def tearDown(self) -> None:
        import commands.pending_actions as pa

        pa._PENDING.clear()
        super().tearDown()

    def test_accept_entrance_soulfray_completes_as_entrance(self) -> None:
        """Confirming a soulfray-gated entrance grants a flourish offer + suggestion.

        A bare ``cast_technique`` re-dispatch (the pre-fix behavior) would resolve the
        technique but never touch the flourish/suggestion hooks — those live only on the
        entrance REGISTRY path.
        """
        from world.magic.offer_handlers import SoulfrayPendingHandler

        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        actor = self.caster.character_sheet.character

        warning = SoulfrayWarning(
            stage_name="Stage One",
            stage_description="Your soul frays at the edges.",
            has_death_risk=False,
        )

        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=warning):
            gate_result = EntranceAction().execute(
                actor,
                None,
                technique_id=technique.pk,
                confirm_soulfray_risk=False,
            )
        self.assertFalse(gate_result.success)
        self.assertIn("soulfray", (gate_result.message or "").lower())
        self.assertFalse(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists(),
            "no hooks fire before the soulfray gate is confirmed",
        )

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            SoulfrayPendingHandler().accept(offer=None, caller=actor, args="")

        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists(),
            "accept must re-dispatch through the entrance path, granting a flourish offer",
        )
        self.assertTrue(
            DramaticMomentSuggestion.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists(),
        )
