"""Tests for the ``originated_as_entrance`` marker threaded through the standalone-cast

pipeline (#2183). Task 1's tests verify the flag is stamped onto the PENDING
``SceneActionRequest`` row created by a consent-gated benign cast, and that it defaults to
False when the caller doesn't pass it. Task 5's tests verify the deferred-resolution hooks
(flourish + suggestion + disposition + intervention-join / from_entrance-declaration) fire
when ``resolve_accepted_cast`` resolves an entrance-originated PENDING request.
"""

from unittest.mock import MagicMock, patch

from actions.factories import ActionTemplateFactory
from world.combat.constants import ParticipantStatus, RiskLevel
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatParticipant, CombatRoundAction
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import CharacterResonanceFactory, ensure_dramatic_entrance_content
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import request_technique_cast, resolve_accepted_cast
from world.scenes.constants import RoundStatus
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    attach_behavior_altering_condition,
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


class TestEntranceCastThreading(CastScenarioMixin):
    """originated_as_entrance is threaded from request_technique_cast to the PENDING request."""

    def test_benign_consent_pending_request_stamped(self) -> None:
        """A consent-gated benign cast called with originated_as_entrance=True stamps it."""
        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
            originated_as_entrance=True,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        self.assertTrue(cast.request.originated_as_entrance)

    def test_default_is_false(self) -> None:
        """Without the kwarg, originated_as_entrance defaults to False."""
        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        self.assertFalse(cast.request.originated_as_entrance)


class TestAcceptedEntranceCastHooks(CastScenarioMixin):
    """resolve_accepted_cast fires the deferred entrance hooks (#2183 Task 5).

    Consent-gated benign entrances resolve on accept, at which point the real
    success level becomes known — the flourish offer, dramatic-moment suggestion,
    disposition delta, and combat-intervention join all fire here instead of at
    request time.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        ActionTemplateFactory(name="Entrance", grants_entry_flourish=True)
        moment_type = ensure_dramatic_entrance_content()
        CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet,
            resonance=moment_type.resonance,
        )

    def _make_embattled_encounter(self):
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
        return encounter

    def test_accepted_entrance_cast_fires_hooks(self) -> None:
        """A high-success accepted entrance fires flourish + suggestion + intervention join."""
        encounter = self._make_embattled_encounter()

        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
            originated_as_entrance=True,
        )
        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            result = resolve_accepted_cast(cast.request)

        self.assertIsNotNone(result)
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
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet=self.caster.character_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )

    def test_accepted_non_entrance_cast_no_hooks(self) -> None:
        """Regression pin: a non-entrance accepted cast fires none of the #2183 hooks."""
        self._make_embattled_encounter()

        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )
        self.assertFalse(cast.request.originated_as_entrance)

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            resolve_accepted_cast(cast.request)

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
        self.assertFalse(
            CombatParticipant.objects.filter(
                character_sheet=self.caster.character_sheet,
            ).exists()
        )

    def test_accepted_hostile_entrance_declaration_marked_from_entrance(self) -> None:
        """A #777-gated hostile entrance accept stamps from_entrance on the declaration."""
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=RiskLevel.LETHAL,
            round_number=1,
        )

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
            originated_as_entrance=True,
        )
        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)

        result = resolve_accepted_cast(cast.request)

        self.assertIsNone(result)
        caster_participant = CombatParticipant.objects.get(
            encounter=encounter, character_sheet=self.caster.character_sheet
        )
        action = CombatRoundAction.objects.get(
            participant=caster_participant, round_number=encounter.round_number
        )
        self.assertTrue(action.from_entrance)
        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )
        self.assertFalse(
            DramaticMomentSuggestion.objects.filter(
                character_sheet=self.caster.character_sheet
            ).exists()
        )
