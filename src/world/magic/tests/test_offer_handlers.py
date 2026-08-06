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

from django.test import TestCase, override_settings

from actions.definitions.social import EntranceAction
from actions.factories import ActionTemplateFactory
from commands.exceptions import CommandError
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.exceptions import GiftResonanceUnresolvable
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ensure_dramatic_entrance_content,
    wire_audere_power_multipliers,
)
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.magic.tests.majora_fixtures import build_crossing_world
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


class CrossingOfferHandlerAcceptTests(TestCase):
    """``CrossingOfferHandler.accept`` error mapping (#2971 final-review fix).

    A ``GiftResonanceUnresolvable`` from ``resolve_audere_majora_offer`` (e.g. the
    crossed-into path's gift grant can't resolve a resonance) must map to the
    handler's ``CommandError`` idiom, not propagate as an unhandled exception.
    """

    def test_accept_maps_unresolvable_gift_resonance_to_command_error(self) -> None:
        from world.magic.offer_handlers import CrossingOfferHandler

        wire_audere_power_multipliers()
        character, _sheet, _threshold, _prospect, puissant_path, offer = build_crossing_world(
            15, "_offer_handler_unresolvable"
        )

        with patch(
            "world.magic.audere_majora.resolve_audere_majora_offer",
            side_effect=GiftResonanceUnresolvable,
        ):
            with self.assertRaises(CommandError):
                CrossingOfferHandler().accept(
                    offer,
                    character,
                    f"path={puissant_path.name} declaration=I step beyond.",
                )


@override_settings(SEED_SAMPLE_CONTENT=True)
class SoulfrayPendingHandlerAcceptEntranceTests(CastScenarioMixin):
    """accept() re-dispatches an entrance-marked PendingCast through the entrance path (#2183).

    The DramaticMomentType is content-repo-owned (#2698); ``SEED_SAMPLE_CONTENT``
    opts this suite into the sample-seeding path.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        for persona in (cls.caster, cls.target):
            character = persona.character_sheet.character
            character.db_location = cls.scene.location
            character.save()
        ActionTemplateFactory(name="Entrance", grants_entry_flourish=True)
        # "Grand Entrance" carries no resonance of its own since #2967, and
        # suggestion eligibility no longer filters on a claimed one — the
        # resonance is resolved at confirm time from the entrance technique.
        cls.moment_type = ensure_dramatic_entrance_content()
        # A claimed resonance, needed for the entry-flourish offer (which skips a
        # character with none). It is deliberately NOT the moment type's: "Grand
        # Entrance" carries no resonance of its own since #2967, and suggestion
        # eligibility no longer filters on a claimed one.
        CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet,
            resonance=ResonanceFactory(),
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

    def test_accept_entrance_soulfray_surfaces_redispatch_failure(self) -> None:
        """A failed entrance re-dispatch surfaces its real failure message.

        Before the fix, ``accept()`` discarded ``dispatch_player_action``'s
        ``DispatchResult`` entirely and always returned the canned "You steel
        yourself..." success-flavored fallback — so a failed re-dispatch (e.g. "There
        is no active scene here.") was silently reported as success (#2183 finding 1).
        """
        from actions.constants import ActionBackend
        from actions.types import ActionResult, DispatchResult
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

        failure = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=False, message="There is no active scene here."),
        )
        with patch("actions.player_interface.dispatch_player_action", return_value=failure):
            message = SoulfrayPendingHandler().accept(offer=None, caller=actor, args="")

        self.assertEqual(message, "There is no active scene here.")
