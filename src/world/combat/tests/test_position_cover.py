"""Tests for attack-cover from PositionShelter in apply_damage_to_participant (#2011)."""

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.models import PositionShelter
from world.areas.positioning.services import (
    create_position,
    place_in_position,
)
from world.combat.factories import CombatParticipantFactory
from world.combat.models import CombatEncounter
from world.combat.services import apply_damage_to_participant
from world.conditions.factories import ensure_radiant_damage_type
from world.vitals.models import CharacterVitals


class PositionCoverDamageReductionTest(TestCase):
    """Attack-cover reduces incoming damage of the matching damage type."""

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.factories import SceneFactory

        self.room = create_object("typeclasses.rooms.Room", key="CoverRoom", nohome=True)
        self.pos = create_position(self.room, "cover_pos")
        self.damage_type = ensure_radiant_damage_type()

        self.scene = SceneFactory(location=self.room)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()
        place_in_position(self.character, self.pos)

        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)

        encounter = CombatEncounter.objects.create(
            scene=self.scene,
            room=self.room,
        )
        self.participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.sheet,
        )

    def test_attack_cover_reduces_damage(self):
        """A PositionShelter with applies_to_attacks=True reduces incoming damage."""
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.damage_type,
            value=20,
            applies_to_attacks=True,
        )
        result = apply_damage_to_participant(
            self.participant,
            50,
            damage_type=self.damage_type,
        )
        # 50 - 20 cover = 30 damage dealt
        self.assertEqual(result.damage_dealt, 30)

    def test_no_cover_full_damage(self):
        """Without attack-cover, full damage applies."""
        result = apply_damage_to_participant(
            self.participant,
            50,
            damage_type=self.damage_type,
        )
        self.assertEqual(result.damage_dealt, 50)

    def test_hazard_shelter_does_not_reduce_attacks(self):
        """A hazard-only PositionShelter does not reduce attacks."""
        PositionShelter.objects.create(
            position=self.pos,
            damage_type=self.damage_type,
            value=50,
            applies_to_attacks=False,
        )
        result = apply_damage_to_participant(
            self.participant,
            50,
            damage_type=self.damage_type,
        )
        self.assertEqual(result.damage_dealt, 50)
