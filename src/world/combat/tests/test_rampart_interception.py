"""Tests for rampart interception in combat damage paths (#2209)."""

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.constants import RampartSignature
from world.areas.positioning.factories import (
    PositionFactory,
    RampartElementProfileFactory,
    RampartElementResistanceFactory,
    RampartFactory,
)
from world.areas.positioning.models import Rampart
from world.areas.positioning.services import place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import StrikeDelivery
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import apply_damage_to_participant, apply_rampart_interception
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ensure_radiant_damage_type
from world.conditions.models import ConditionTemplate
from world.magic.effect_palette_content import ensure_force_field_content
from world.vitals.models import CharacterVitals


def _place_pc(room) -> tuple:
    """Return (sheet, character, position) for a PC placed in room."""
    pos = PositionFactory(room=room, name="behind_the_wall")
    sheet = CharacterSheetFactory()
    character = sheet.character
    character.location = room
    character.save()
    place_in_position(character, pos)
    CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
    return sheet, character, pos


class RampartInterceptionFiringOrderTest(TestCase):
    """Rampart interception runs before DAMAGE_PRE_APPLY — an active ward is untouched."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="RampartRoom", nohome=True)
        self.sheet, self.character, self.pos = _place_pc(self.room)
        encounter = CombatEncounterFactory(room=self.room)
        self.participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        profile = RampartElementProfileFactory(
            name="Stone Wall", signature_behavior=RampartSignature.SEAL_EDGES
        )
        self.rampart = RampartFactory(
            position=self.pos, element_profile=profile, integrity=24, max_integrity=24
        )
        # Wire the real force-field reactive trigger so this exercises the
        # actual DAMAGE_PRE_APPLY dispatch, not a mocked stand-in.
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        self.ward = ConditionInstanceFactory(
            condition=template, target=self.character, absorb_remaining=20
        )

    def test_rampart_chips_ward_untouched_pc_takes_zero(self) -> None:
        result = apply_damage_to_participant(self.participant, 10, damage_type=None)

        self.assertEqual(result.damage_dealt, 0)
        self.rampart.refresh_from_db()
        self.assertEqual(self.rampart.integrity, 14)  # 24 - chip(10)
        self.ward.refresh_from_db()
        self.assertEqual(self.ward.absorb_remaining, 20)  # never drained


class RampartInterceptionCollapseTest(TestCase):
    """A chip that clears the rampart's integrity collapses it and lets overflow through."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="RampartRoom2", nohome=True)
        self.sheet, self.character, self.pos = _place_pc(self.room)
        encounter = CombatEncounterFactory(room=self.room)
        self.participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

    def test_overflow_passes_into_normal_pipeline_and_rampart_collapses(self) -> None:
        profile = RampartElementProfileFactory(signature_behavior=RampartSignature.SEAL_EDGES)
        rampart = RampartFactory(
            position=self.pos, element_profile=profile, integrity=5, max_integrity=30
        )

        result = apply_damage_to_participant(self.participant, 10, damage_type=None)

        # chip = max(1, 10 - 0) = 10; overflow = 10 - 5 = 5
        self.assertEqual(result.damage_dealt, 5)
        self.assertFalse(Rampart.objects.filter(pk=rampart.pk).exists())


class RampartInterceptionMathTest(TestCase):
    """Element arithmetic: resist/vulnerability/min-1 floor/wind missile-area adjustment."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="RampartRoom3", nohome=True)
        self.sheet, self.character, self.pos = _place_pc(self.room)
        self.damage_type = ensure_radiant_damage_type()

    def test_resist_shrinks_chip(self) -> None:
        profile = RampartElementProfileFactory(signature_behavior=RampartSignature.SEAL_EDGES)
        RampartElementResistanceFactory(profile=profile, damage_type=self.damage_type, value=5)
        rampart = RampartFactory(position=self.pos, element_profile=profile, integrity=100)

        pass_through = apply_rampart_interception(
            self.character, 10, self.damage_type, attacker_ref=None
        )

        self.assertEqual(pass_through, 0)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 95)  # chip = 10 - 5 = 5

    def test_vulnerability_grows_chip(self) -> None:
        profile = RampartElementProfileFactory(signature_behavior=RampartSignature.SEAL_EDGES)
        RampartElementResistanceFactory(profile=profile, damage_type=self.damage_type, value=-5)
        rampart = RampartFactory(position=self.pos, element_profile=profile, integrity=100)

        pass_through = apply_rampart_interception(
            self.character, 10, self.damage_type, attacker_ref=None
        )

        self.assertEqual(pass_through, 0)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 85)  # chip = 10 - (-5) = 15

    def test_chip_floors_at_one(self) -> None:
        profile = RampartElementProfileFactory(signature_behavior=RampartSignature.SEAL_EDGES)
        RampartElementResistanceFactory(profile=profile, damage_type=self.damage_type, value=100)
        rampart = RampartFactory(position=self.pos, element_profile=profile, integrity=5)

        pass_through = apply_rampart_interception(
            self.character, 10, self.damage_type, attacker_ref=None
        )

        self.assertEqual(pass_through, 0)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 4)  # chip floors at 1

    def test_wind_missile_ward_adjusts_resist_for_missile_delivery(self) -> None:
        profile = RampartElementProfileFactory(
            name="Wind", signature_behavior=RampartSignature.MISSILE_WARD, signature_value=4
        )
        rampart = RampartFactory(position=self.pos, element_profile=profile, integrity=100)

        apply_rampart_interception(
            self.character,
            10,
            None,
            attacker_ref=None,
            delivery=StrikeDelivery.MISSILE,
        )

        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 94)  # chip = 10 - 4 = 6

    def test_wind_missile_ward_adjusts_resist_for_area_strikes(self) -> None:
        profile = RampartElementProfileFactory(
            name="Wind", signature_behavior=RampartSignature.MISSILE_WARD, signature_value=4
        )
        rampart = RampartFactory(position=self.pos, element_profile=profile, integrity=100)

        apply_rampart_interception(
            self.character,
            10,
            None,
            attacker_ref=None,
            delivery=StrikeDelivery.MELEE,
            is_area=True,
        )

        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 86)  # chip = 10 - (-4) = 14


class RampartRetaliationTest(TestCase):
    """MELEE_RETALIATION bites a melee NPC striker without recursing into ramparts."""

    def test_fire_retaliation_hits_attacker_no_recursion(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="RampartRoom4", nohome=True)
        sheet, _character, pos = _place_pc(room)
        damage_type = ensure_radiant_damage_type()

        encounter = CombatEncounterFactory(room=room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        fire_profile = RampartElementProfileFactory(
            name="Fire Wall",
            signature_behavior=RampartSignature.MELEE_RETALIATION,
            signature_value=6,
            signature_damage_type=damage_type,
        )
        target_rampart = RampartFactory(
            position=pos, element_profile=fire_profile, integrity=24, max_integrity=24
        )

        attacker = CombatOpponentFactory(encounter=encounter, health=50, max_health=50)
        attacker_pos = PositionFactory(room=room, name="attacker_spot")
        place_in_position(attacker.objectdb, attacker_pos)
        guard_profile = RampartElementProfileFactory(
            name="Guard Wall", signature_behavior=RampartSignature.SEAL_EDGES
        )
        attacker_rampart = RampartFactory(
            position=attacker_pos, element_profile=guard_profile, integrity=10, max_integrity=10
        )

        result = apply_damage_to_participant(
            participant,
            10,
            damage_type=damage_type,
            source=attacker,
            delivery=StrikeDelivery.MELEE,
        )

        self.assertEqual(result.damage_dealt, 0)  # fully absorbed by the target rampart
        target_rampart.refresh_from_db()
        self.assertEqual(target_rampart.integrity, 14)  # chip = 10 - 0 = 10

        attacker.refresh_from_db()
        self.assertEqual(attacker.health, 44)  # 50 - signature_value(6)

        # bypass_pre_apply=True on the retaliation hit means it never re-enters
        # apply_rampart_interception — the attacker's own rampart is untouched.
        attacker_rampart.refresh_from_db()
        self.assertEqual(attacker_rampart.integrity, 10)

    def test_no_retaliation_against_pc_attacker(self) -> None:
        """ADR-0023: a PC striker is never retaliated against."""
        room = create_object("typeclasses.rooms.Room", key="RampartRoom5", nohome=True)
        sheet, _character, pos = _place_pc(room)
        damage_type = ensure_radiant_damage_type()

        encounter = CombatEncounterFactory(room=room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        fire_profile = RampartElementProfileFactory(
            name="Fire Wall 2",
            signature_behavior=RampartSignature.MELEE_RETALIATION,
            signature_value=6,
            signature_damage_type=damage_type,
        )
        RampartFactory(position=pos, element_profile=fire_profile, integrity=24, max_integrity=24)

        pc_sheet = CharacterSheetFactory()
        pc_attacker = pc_sheet.character

        # No exception, no CombatOpponent to damage — a no-op retaliation branch.
        result = apply_damage_to_participant(
            participant,
            10,
            damage_type=damage_type,
            source=pc_attacker,
            delivery=StrikeDelivery.MELEE,
        )
        self.assertEqual(result.damage_dealt, 0)
