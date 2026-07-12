"""Tests for generalized benign-intervention combat seating (#2226).

Any benign (non-hostile) cast that affects an ACTIVE combatant seats the caster
in that combatant's encounter — regardless of targeting mode (SINGLE, AREA,
FILTERED_GROUP) or consent path (immediate or consent-requiring). The cast's
effect still applies normally; the seating is a post-resolution side-effect.

These tests exercise ``seat_caster_for_benign_intervention`` (the multi-target
wrapper) and the ``_maybe_seat_caster_after_benign_cast`` hook in
``_route_immediate_cast``.
"""

from unittest.mock import MagicMock, patch

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatAllegiance,
    EncounterType,
    OpponentStatus,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import (
    CombatParticipant,
    EncounterRiskAcknowledgement,
)
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.vitals.models import CharacterVitals


class SeatCasterForBenignInterventionTests(EvenniaTestCase):
    """Tests for the ``seat_caster_for_benign_intervention`` wrapper."""

    @staticmethod
    def _make_sheets(n=2):
        sheets = []
        for _ in range(n):
            sheet = CharacterSheetFactory()
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
            sheets.append(sheet)
        return sheets

    @staticmethod
    def _make_declaring_encounter():
        return CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            round_number=1,
        )

    def test_single_target_seats_caster(self):
        """A single embattled ally seats the caster."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )

        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[target],
            scene=encounter.scene,
        )

        self.assertIsNotNone(participant)
        self.assertEqual(participant.character_sheet, caster)
        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter,
                character_sheet=caster,
            ).exists()
        )

    def test_multiple_targets_seats_once(self):
        """Multiple embattled allies seat the caster once (first encounter wins)."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, target1, target2 = self._make_sheets(3)
        encounter = self._make_declaring_encounter()
        for t in (target1, target2):
            CombatParticipantFactory(
                encounter=encounter,
                character_sheet=t,
                status=ParticipantStatus.ACTIVE,
            )

        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[target1, target2],
            scene=encounter.scene,
        )

        self.assertIsNotNone(participant)
        # Caster is seated exactly once — one participant row.
        self.assertEqual(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet=caster,
                status=ParticipantStatus.ACTIVE,
            ).count(),
            1,
        )

    def test_self_cast_excluded(self):
        """The caster's own sheet is excluded from the target list."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, _target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        # The caster is themselves an embattled combatant.
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=caster,
            status=ParticipantStatus.ACTIVE,
        )

        # Only the caster's sheet is in the list — should not seat (no other
        # target to intervene on).
        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[caster],
            scene=encounter.scene,
        )

        self.assertIsNone(participant)

    def test_no_embattled_target_returns_none(self):
        """A target that is not in any encounter returns None."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, target = self._make_sheets()
        scene = SceneFactory()

        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[target],
            scene=scene,
        )

        self.assertIsNone(participant)

    def test_already_in_encounter_no_double_seating(self):
        """A caster already in the encounter is not double-seated."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=caster,
            status=ParticipantStatus.ACTIVE,
        )

        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[target],
            scene=encounter.scene,
        )

        # Returns non-None (the existing participant), but only one row.
        self.assertIsNotNone(participant)
        self.assertEqual(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet=caster,
                status=ParticipantStatus.ACTIVE,
            ).count(),
            1,
        )

    def test_ally_opponent_seats_caster(self):
        """A target that is an ALLY opponent (not a participant) also seats."""
        from world.combat.cast_seed import seat_caster_for_benign_intervention

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatOpponentFactory(
            encounter=encounter,
            objectdb_id=target.character.pk,
            allegiance=CombatAllegiance.ALLY,
            status=OpponentStatus.ACTIVE,
        )

        participant = seat_caster_for_benign_intervention(
            caster_sheet=caster,
            target_sheets=[target],
            scene=encounter.scene,
        )

        self.assertIsNotNone(participant)
        self.assertEqual(participant.character_sheet, caster)


class MaybeSeatCasterAfterBenignCastTests(EvenniaTestCase):
    """Tests for the ``_maybe_seat_caster_after_benign_cast`` immediate-path hook."""

    @staticmethod
    def _make_sheet():
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        return sheet

    def _make_mock_result(self, success_level=3):
        """Build a mock EnhancedSceneActionResult with the given success level."""
        result = MagicMock()
        result.action_resolution.main_result.check_result.success_level = success_level
        return result

    def test_failed_cast_does_not_seat(self):
        """A cast with success_level <= 0 does not seat the caster."""
        from world.scenes.cast_services import _maybe_seat_caster_after_benign_cast

        caster = self._make_sheet()
        target = self._make_sheet()
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            round_number=1,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )

        from world.scenes.factories import PersonaFactory

        caster_persona = PersonaFactory(character_sheet=caster)
        target_persona = PersonaFactory(character_sheet=target)
        technique = MagicMock()
        technique.target_type = "SINGLE"

        with patch(
            "world.scenes.cast_services.is_technique_hostile",
            return_value=False,
        ):
            seated = _maybe_seat_caster_after_benign_cast(
                scene=encounter.scene,
                initiator_persona=caster_persona,
                target_persona=target_persona,
                technique=technique,
                supplied_personas=None,
                result=self._make_mock_result(success_level=0),
            )

        self.assertFalse(seated)
        self.assertFalse(
            CombatParticipant.objects.filter(
                encounter=encounter,
                character_sheet=caster,
            ).exists()
        )

    def test_hostile_cast_does_not_seat(self):
        """A hostile cast does not seat via the benign path (handled by _route_hostile_cast)."""
        from world.scenes.cast_services import _maybe_seat_caster_after_benign_cast

        caster = self._make_sheet()
        target = self._make_sheet()
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            round_number=1,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )

        from world.scenes.factories import PersonaFactory

        caster_persona = PersonaFactory(character_sheet=caster)
        target_persona = PersonaFactory(character_sheet=target)
        technique = MagicMock()

        with patch(
            "world.scenes.cast_services.is_technique_hostile",
            return_value=True,
        ):
            seated = _maybe_seat_caster_after_benign_cast(
                scene=encounter.scene,
                initiator_persona=caster_persona,
                target_persona=target_persona,
                technique=technique,
                supplied_personas=None,
                result=self._make_mock_result(success_level=3),
            )

        self.assertFalse(seated)

    def test_non_combatant_target_does_not_seat(self):
        """A benign cast at a non-combatant does not seat the caster."""
        from world.scenes.cast_services import _maybe_seat_caster_after_benign_cast

        caster = self._make_sheet()
        target = self._make_sheet()
        scene = SceneFactory()

        from world.scenes.factories import PersonaFactory

        caster_persona = PersonaFactory(character_sheet=caster)
        target_persona = PersonaFactory(character_sheet=target)
        technique = MagicMock()

        with patch(
            "world.scenes.cast_services.is_technique_hostile",
            return_value=False,
        ):
            seated = _maybe_seat_caster_after_benign_cast(
                scene=scene,
                initiator_persona=caster_persona,
                target_persona=target_persona,
                technique=technique,
                supplied_personas=None,
                result=self._make_mock_result(success_level=3),
            )

        self.assertFalse(seated)

    def test_none_result_does_not_seat(self):
        """A None result (e.g. soulfray-halted cast) does not seat."""
        from world.scenes.cast_services import _maybe_seat_caster_after_benign_cast

        caster = self._make_sheet()
        target = self._make_sheet()

        from world.scenes.factories import PersonaFactory

        caster_persona = PersonaFactory(character_sheet=caster)
        target_persona = PersonaFactory(character_sheet=target)
        technique = MagicMock()

        with patch(
            "world.scenes.cast_services.is_technique_hostile",
            return_value=False,
        ):
            seated = _maybe_seat_caster_after_benign_cast(
                scene=SceneFactory(),
                initiator_persona=caster_persona,
                target_persona=target_persona,
                technique=technique,
                supplied_personas=None,
                result=None,
            )

        self.assertFalse(seated)
