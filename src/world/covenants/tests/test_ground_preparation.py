"""Tests for the ground-preparation rider service (#2646).

Built in ``setUp`` rather than ``setUpTestData`` throughout — factories here
create Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), same
rationale as ``test_perk_evaluators.py`` / ``test_perk_resolution.py``.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory
from world.covenants.perks.services import record_ground_preparation_from_cast
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
from world.room_features.models import PreparedGround


class RecordGroundPreparationFromCastTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.room = create_object("typeclasses.rooms.Room", key="PrepRoom", nohome=True)
        self.perception_technique = TechniqueFactory()
        TechniqueFunctionTagFactory(
            technique=self.perception_technique, function=TechniqueFunction.PERCEPTION
        )

    def _engage_flagged_role(self) -> None:
        role = CovenantRoleFactory(prepares_ground=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=role,
            covenant__covenant_type=role.covenant_type,
            engaged=True,
        )

    def test_false_and_no_row_when_role_not_flagged(self) -> None:
        role = CovenantRoleFactory(prepares_ground=False)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=role,
            covenant__covenant_type=role.covenant_type,
            engaged=True,
        )
        result = record_ground_preparation_from_cast(
            self.sheet, self.perception_technique, self.room
        )
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_false_and_no_row_when_technique_carries_no_perception_tag(self) -> None:
        self._engage_flagged_role()
        non_perception_technique = TechniqueFactory()
        result = record_ground_preparation_from_cast(
            self.sheet, non_perception_technique, self.room
        )
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_false_and_no_row_when_role_not_engaged(self) -> None:
        role = CovenantRoleFactory(prepares_ground=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=role,
            covenant__covenant_type=role.covenant_type,
            engaged=False,
        )
        result = record_ground_preparation_from_cast(
            self.sheet, self.perception_technique, self.room
        )
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_false_and_no_row_when_room_has_no_profile(self) -> None:
        self._engage_flagged_role()
        plain = create_object("typeclasses.objects.Object", key="NotARoom", nohome=True)
        result = record_ground_preparation_from_cast(self.sheet, self.perception_technique, plain)
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_false_and_no_row_when_room_is_none(self) -> None:
        self._engage_flagged_role()
        result = record_ground_preparation_from_cast(self.sheet, self.perception_technique, None)
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_false_and_no_row_when_sheet_in_active_encounter(self) -> None:
        self._engage_flagged_role()
        encounter = CombatEncounterFactory(room=self.room)
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        result = record_ground_preparation_from_cast(
            self.sheet, self.perception_technique, self.room
        )
        self.assertFalse(result)
        self.assertFalse(PreparedGround.objects.filter(prepared_by=self.sheet).exists())

    def test_true_and_row_created_when_every_condition_holds(self) -> None:
        self._engage_flagged_role()
        result = record_ground_preparation_from_cast(
            self.sheet, self.perception_technique, self.room
        )
        self.assertTrue(result)
        ground = PreparedGround.objects.get(prepared_by=self.sheet)
        self.assertEqual(ground.room_profile_id, self.room.room_profile.pk)

    def test_second_call_in_different_room_moves_the_row(self) -> None:
        self._engage_flagged_role()
        record_ground_preparation_from_cast(self.sheet, self.perception_technique, self.room)

        other_room = create_object("typeclasses.rooms.Room", key="OtherPrepRoom", nohome=True)
        result = record_ground_preparation_from_cast(
            self.sheet, self.perception_technique, other_room
        )
        self.assertTrue(result)
        self.assertEqual(PreparedGround.objects.filter(prepared_by=self.sheet).count(), 1)
        ground = PreparedGround.objects.get(prepared_by=self.sheet)
        self.assertEqual(ground.room_profile_id, other_room.room_profile.pk)
