"""Tests for the combat-side entrance-seeding pieces (#2183 Task 2).

- ``seed_or_feed_encounter_from_benign_intervention``: the benign sibling of
  ``seed_or_feed_encounter_from_cast`` — a protective entrance cast landing on
  an already-embattled ally seats the caster in the fight, with no opponent
  row, no stakes lock, and no FOCUSED declaration.
- ``seed_or_feed_encounter_from_cast(..., from_entrance=True)``: stamps
  ``CombatRoundAction.from_entrance`` on the caster's declared round action,
  so a later task can fire recognition when the declared cast resolves.
"""

from unittest.mock import patch

from evennia.utils.test_resources import EvenniaTestCase


class SeedOrFeedEncounterFromBenignInterventionTests(EvenniaTestCase):
    """Integration tests for the benign-intervention join service."""

    @staticmethod
    def _make_sheets():
        from world.character_sheets.factories import CharacterSheetFactory
        from world.vitals.models import CharacterVitals

        caster = CharacterSheetFactory()
        target = CharacterSheetFactory()
        for sheet in (caster, target):
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
        return caster, target

    @staticmethod
    def _make_declaring_encounter():
        from world.combat.constants import EncounterType, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.scenes.constants import RoundStatus

        return CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            round_number=1,
        )

    def _intervene(self, caster, target, scene):
        from world.combat.cast_seed import seed_or_feed_encounter_from_benign_intervention

        return seed_or_feed_encounter_from_benign_intervention(
            caster_sheet=caster,
            target_sheet=target,
            scene=scene,
        )

    def test_benign_intervention_seats_caster(self):
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatParticipantFactory
        from world.combat.models import (
            CombatOpponent,
            CombatParticipant,
            EncounterRiskAcknowledgement,
        )

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )

        with patch("world.combat.cast_seed.activate_stakes_for_scene") as mock_activate_stakes:
            participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNotNone(participant)
        self.assertIsInstance(participant, CombatParticipant)
        self.assertEqual(participant.character_sheet, caster)
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)
        self.assertEqual(participant.encounter, encounter)

        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter,
                character_sheet=caster,
            ).exists()
        )
        self.assertFalse(CombatOpponent.objects.filter(encounter=encounter).exists())
        mock_activate_stakes.assert_not_called()

    def test_benign_intervention_ally_opponent(self):
        from world.combat.constants import CombatAllegiance, OpponentStatus
        from world.combat.factories import CombatOpponentFactory

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatOpponentFactory(
            encounter=encounter,
            objectdb_id=target.character.pk,
            allegiance=CombatAllegiance.ALLY,
            status=OpponentStatus.ACTIVE,
        )

        participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNotNone(participant)
        self.assertEqual(participant.character_sheet, caster)

    def test_benign_intervention_no_encounter_returns_none(self):
        from world.scenes.factories import SceneFactory

        caster, target = self._make_sheets()
        scene = SceneFactory()

        participant = self._intervene(caster, target, scene)

        self.assertIsNone(participant)

    def test_benign_intervention_target_not_embattled_returns_none(self):
        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        # Encounter is live, but the target has no participant/opponent row.

        participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNone(participant)


class SeedOrFeedEncounterFromCastEntranceMarkerTests(EvenniaTestCase):
    """Tests for the ``from_entrance`` marker on the hostile-cast declaration path."""

    @staticmethod
    def _make_caster_and_target():
        from world.character_sheets.factories import CharacterSheetFactory
        from world.vitals.models import CharacterVitals

        caster = CharacterSheetFactory()
        target = CharacterSheetFactory()
        for sheet in (caster, target):
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
        return caster, target

    @staticmethod
    def _make_damage_technique():
        from world.magic.factories import TechniqueFactory

        return TechniqueFactory()

    @staticmethod
    def _make_scene_with_room():
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="Entrance Cast Room", nohome=True)
        scene = SceneFactory(location=room)
        return scene, room

    def test_hostile_seed_marks_from_entrance(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import CombatParticipant, CombatRoundAction

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
            from_entrance=True,
        )

        caster_part = CombatParticipant.objects.get(encounter=encounter, character_sheet=caster)
        action = CombatRoundAction.objects.get(
            participant=caster_part,
            round_number=encounter.round_number,
        )
        self.assertTrue(action.from_entrance)

    def test_hostile_seed_from_entrance_defaults_false(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import CombatParticipant, CombatRoundAction

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        caster_part = CombatParticipant.objects.get(encounter=encounter, character_sheet=caster)
        action = CombatRoundAction.objects.get(
            participant=caster_part,
            round_number=encounter.round_number,
        )
        self.assertFalse(action.from_entrance)
