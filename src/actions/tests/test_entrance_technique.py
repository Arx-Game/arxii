"""Tests for EntranceAction's technique-driven combat-entrance path (#2183 Task 4).

``EntranceAction.execute`` branches at the top on ``technique_id``: absent, it runs the
pre-existing ActionTemplate check-resolution path unchanged; present, it dispatches
``_execute_technique_entrance`` which mirrors ``CastTechniqueAction.execute`` (scene/
persona/technique/target resolution + soulfray gate) and routes through
``request_technique_cast`` per the #2183 deferral matrix:

- resolved inline (self/room/no-target, or a benign no-consent cast at another PC) →
  full hooks (flourish + disposition + suggestion) when the success level clears 0, plus
  a benign-intervention combat join when the target is another sheet's ACTIVE combatant.
- hostile cast at another PC → seeds/feeds combat; flourish only (the success level isn't
  known yet — Task 5 fires the suggestion at round resolution).
- benign consent-gated or hostile risk-gated → PENDING; no hooks now (Task 5 wires them
  at accept-time resolution).
- already an ACTIVE participant in a feedable encounter → clean failure.
- no active scene at the actor's location → the cast seam's exact failure message.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.definitions.social import EntranceAction
from actions.factories import ActionTemplateFactory
from world.combat.constants import ParticipantStatus, RiskLevel
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import CharacterResonanceFactory, ensure_dramatic_entrance_content
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.scenes.constants import RoundStatus
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
    make_hostile_castable_technique,
)


def _make_check_mock(success_level: int) -> MagicMock:
    return MagicMock(
        success_level=success_level,
        outcome=MagicMock(name="Outcome"),
        outcome_name="Success" if success_level > 0 else "Failure",
    )


def _make_protective_technique():
    """A benign ALLY-targeting technique that does NOT require consent.

    ``make_benign_castable_technique`` defaults to a SELF targeting relationship
    (no condition_applications at all), which ``validate_cast_target`` rejects for
    any target other than the caster. Attaching a non-behavior-altering ALLY
    condition_application flips ``derive_target_relationship`` to ALLY (so another
    PC is a valid target) while keeping ``cast_requires_consent`` False (the
    category's ``alters_behavior`` stays at its model default of False) — so the
    cast still resolves immediately instead of routing to the PENDING consent path.
    """
    from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
    from world.magic.factories import TechniqueAppliedConditionFactory
    from world.magic.models.techniques import ConditionTargetKind

    technique = make_benign_castable_technique()
    category = ConditionCategoryFactory(alters_behavior=False)
    condition = ConditionTemplateFactory(category=category)
    TechniqueAppliedConditionFactory(
        technique=technique,
        condition=condition,
        target_kind=ConditionTargetKind.ALLY,
        minimum_success_level=1,
    )
    return technique


class EntranceTechniqueActionTests(CastScenarioMixin):
    """EntranceAction._execute_technique_entrance: the technique-driven entrance path."""

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

    def _actor(self):
        return self.caster.character_sheet.character

    # -------------------------------------------------------------------------
    # Regression pin — no technique_id keeps the pre-existing ActionTemplate path.
    # -------------------------------------------------------------------------

    def test_social_path_unchanged(self) -> None:
        from actions.tests.resolution_helpers import make_resolution

        actor = self._actor()
        actor.location.active_scene = self.scene
        context = MagicMock()

        with patch("actions.services.start_action_resolution", return_value=make_resolution(1)):
            result = EntranceAction().execute(actor, context)

        self.assertTrue(result.success)
        self.assertIn("flourish", (result.message or "").lower())
        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Hostile technique at another PC → seeds combat.
    # -------------------------------------------------------------------------

    def test_hostile_technique_entrance_seeds_combat(self) -> None:
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        caster_participant = CombatParticipant.objects.get(
            encounter=encounter,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        action_row = CombatRoundAction.objects.get(
            participant=caster_participant, round_number=encounter.round_number
        )
        self.assertTrue(action_row.from_entrance)
        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Benign non-consent technique at an ACTIVE-participant ally → intervention join.
    # -------------------------------------------------------------------------

    def test_protective_entrance_seats_caster(self) -> None:
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            round_number=1,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.target.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        technique = _make_protective_technique()
        grant_technique(self.caster, technique)

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            result = EntranceAction().execute(
                self._actor(),
                None,
                technique_id=technique.pk,
                target_persona_id=self.target.pk,
                confirm_soulfray_risk=True,
            )

        self.assertTrue(result.success, result.message)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet=self.caster.character_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )
        self.assertTrue(
            DramaticMomentSuggestion.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Benign cast, no encounter anywhere → hooks fire, no combat rows created.
    # -------------------------------------------------------------------------

    def test_standalone_entrance_no_combat(self) -> None:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            result = EntranceAction().execute(
                self._actor(), None, technique_id=technique.pk, confirm_soulfray_risk=True
            )

        self.assertTrue(result.success, result.message)
        self.assertFalse(
            CombatParticipant.objects.filter(character_sheet=self.caster.character_sheet).exists()
        )
        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )
        self.assertTrue(
            DramaticMomentSuggestion.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )

    # -------------------------------------------------------------------------
    # A fizzled (SL 0) resolution runs no hooks.
    # -------------------------------------------------------------------------

    def test_fizzle_no_hooks(self) -> None:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        with patch("actions.services.perform_check", return_value=_make_check_mock(0)):
            result = EntranceAction().execute(
                self._actor(), None, technique_id=technique.pk, confirm_soulfray_risk=True
            )

        self.assertFalse(result.success)
        self.assertFalse(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )
        self.assertFalse(
            DramaticMomentSuggestion.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Guard: already an ACTIVE participant in the room's live encounter.
    # -------------------------------------------------------------------------

    def test_already_in_fight_guard(self) -> None:
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            round_number=1,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(), None, technique_id=technique.pk, confirm_soulfray_risk=True
        )

        self.assertFalse(result.success)
        self.assertIn("already in the fight", (result.message or "").lower())

    # -------------------------------------------------------------------------
    # No active scene at the actor's location.
    # -------------------------------------------------------------------------

    def test_no_scene_fails_cleanly(self) -> None:
        from evennia import create_object

        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        empty_room = create_object(
            "typeclasses.rooms.Room", key="EmptyEntranceTechniqueRoom", nohome=True
        )
        character = self._actor()
        character.db_location = empty_room
        character.save()

        result = EntranceAction().execute(
            character, None, technique_id=technique.pk, confirm_soulfray_risk=True
        )

        self.assertFalse(result.success)
        self.assertIn("no active scene", result.message or "")

    # -------------------------------------------------------------------------
    # Disposition applies only for a non-hostile technique with a target.
    # -------------------------------------------------------------------------

    def test_disposition_only_non_hostile(self) -> None:
        from world.scenes.types import CastResult

        hostile_technique = make_hostile_castable_technique()
        grant_technique(self.caster, hostile_technique)
        benign_technique = make_benign_castable_technique()
        grant_technique(self.caster, benign_technique)

        # Mock request_technique_cast directly (rather than driving the hostile
        # branch for real) so the two calls stay independent — a real hostile cast
        # would seat the caster as an ACTIVE combat participant and trip the
        # already-in-the-fight guard on the second (benign) call.
        hostile_cast = CastResult(encounter=MagicMock())
        resolution = MagicMock()
        resolution.main_result.check_result.success_level = 1
        benign_cast = CastResult(result=MagicMock(action_resolution=resolution))

        with (
            patch(
                "world.scenes.cast_services.request_technique_cast",
                side_effect=[hostile_cast, benign_cast],
            ),
            patch(
                "world.npc_services.social_disposition.apply_social_disposition_delta"
            ) as mock_disposition,
        ):
            # Hostile at another PC seeds combat — never reaches the resolved-inline
            # branch where disposition is applied.
            EntranceAction().execute(
                self._actor(),
                None,
                technique_id=hostile_technique.pk,
                target_persona_id=self.target.pk,
                confirm_soulfray_risk=True,
            )
            mock_disposition.assert_not_called()

            result = EntranceAction().execute(
                self._actor(),
                None,
                technique_id=benign_technique.pk,
                target_persona_id=self.target.pk,
                confirm_soulfray_risk=True,
            )

        self.assertTrue(result.success, result.message)
        mock_disposition.assert_called_once()
        call_args = mock_disposition.call_args.args
        self.assertEqual(call_args[0], self._actor())
        self.assertEqual(call_args[1], self.target.pk)
        self.assertIs(call_args[2], resolution)
