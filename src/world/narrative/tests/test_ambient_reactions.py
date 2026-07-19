"""Unit tests for emit_room_ambient_reaction (#2471) — direct calls, not via MOVED."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.locations.constants import LocationParentType
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.narrative.constants import AmbientTriggerType, NarrativeCategory
from world.narrative.factories import AmbientEmoteLineFactory
from world.narrative.models import NarrativeMessageDelivery
from world.narrative.services import emit_room_ambient_reaction
from world.societies.constants import FameTier
from world.societies.factories import SocietyFactory
from world.species.factories import SpeciesFactory


@dataclass(frozen=True)
class _FakeMovedPayload:
    character: object
    destination: object


def _room():
    room = ObjectDBFactory(db_key="Test Room", db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room)
    return room, profile


def _character(room):
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


def _bystander_msgs(sheet):
    return list(
        NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet).values_list(
            "message__body", flat=True
        )
    )


class NoneTriggerTests(TestCase):
    def test_fires_privately_no_bystanders(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        bystander = _character(room)
        AmbientEmoteLineFactory(room_profile=profile, arriver_body="The room feels still.")

        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )

        self.assertTrue(fired)
        self.assertEqual(_bystander_msgs(arriver.character_sheet), ["The room feels still."])
        self.assertEqual(_bystander_msgs(bystander.character_sheet), [])

    def test_no_lines_is_silent(self) -> None:
        room, _profile = _room()
        arriver = _character(room)
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertFalse(fired)

    def test_unauthored_room_is_silent(self) -> None:
        bare_room = ObjectDBFactory(db_key="Bare", db_typeclass_path="typeclasses.rooms.Room")
        arriver = _character(bare_room)
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=bare_room)
        )
        self.assertFalse(fired)

    def test_sheetless_arriver_is_silent(self) -> None:
        room, profile = _room()
        AmbientEmoteLineFactory(room_profile=profile)
        sheetless = CharacterFactory()
        sheetless.db_location = room
        sheetless.save(update_fields=["db_location"])
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=sheetless, destination=room)
        )
        self.assertFalse(fired)


class ConditionalTriggerTests(TestCase):
    def test_species_matches_and_broadcasts_to_bystanders(self) -> None:
        room, profile = _room()
        species = SpeciesFactory()
        arriver = _character(room)
        arriver.character_sheet.species = species
        arriver.character_sheet.save(update_fields=["species"])
        bystander = _character(room)
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.SPECIES,
            trigger_species=species,
            bystander_body="A murmur runs through the room.",
            arriver_body="You feel eyes on you.",
        )

        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )

        self.assertTrue(fired)
        self.assertEqual(
            _bystander_msgs(bystander.character_sheet), ["A murmur runs through the room."]
        )
        self.assertEqual(_bystander_msgs(arriver.character_sheet), ["You feel eyes on you."])

    def test_species_mismatch_is_silent(self) -> None:
        room, profile = _room()
        species = SpeciesFactory()
        other_species = SpeciesFactory()
        arriver = _character(room)
        arriver.character_sheet.species = other_species
        arriver.character_sheet.save(update_fields=["species"])
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.SPECIES,
            trigger_species=species,
            bystander_body="A murmur runs through the room.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertFalse(fired)

    def test_resonance_min_uses_lifetime_earned(self) -> None:
        room, profile = _room()
        resonance = ResonanceFactory()
        arriver = _character(room)
        CharacterResonanceFactory(
            character_sheet=arriver.character_sheet, resonance=resonance, lifetime_earned=100
        )
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.RESONANCE_MIN,
            trigger_resonance=resonance,
            trigger_minimum_value=50,
            bystander_body="The air grows heavy.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertTrue(fired)

    def test_resonance_min_below_threshold_is_silent(self) -> None:
        room, profile = _room()
        resonance = ResonanceFactory()
        arriver = _character(room)
        CharacterResonanceFactory(
            character_sheet=arriver.character_sheet, resonance=resonance, lifetime_earned=10
        )
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.RESONANCE_MIN,
            trigger_resonance=resonance,
            trigger_minimum_value=50,
            bystander_body="The air grows heavy.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertFalse(fired)

    def test_distinction_matches_public_distinction(self) -> None:
        room, profile = _room()
        distinction = DistinctionFactory()
        arriver = _character(room)
        CharacterDistinction.objects.create(character=arriver, distinction=distinction)
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.DISTINCTION,
            trigger_distinction=distinction,
            bystander_body="Recognition dawns.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertTrue(fired)

    def test_distinction_relocated_into_secret_is_silent(self) -> None:
        """A secret-relocated distinction must never leak through an ambient reaction."""
        from world.secrets.factories import SecretFactory

        room, profile = _room()
        distinction = DistinctionFactory()
        arriver = _character(room)
        secret = SecretFactory()
        CharacterDistinction.objects.create(
            character=arriver, distinction=distinction, secret=secret
        )
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.DISTINCTION,
            trigger_distinction=distinction,
            bystander_body="Recognition dawns.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertFalse(fired)

    def test_renown_min_actor_audience_split(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        persona = arriver.character_sheet.primary_persona
        persona.fame_tier = FameTier.CELEBRITY
        persona.save(update_fields=["fame_tier"])
        bystander = _character(room)
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.RENOWN_MIN,
            trigger_min_fame_tier=FameTier.CELEBRITY,
            bystander_body="Heads turn as someone notable arrives.",
            arriver_body="You feel the room take notice.",
        )
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertTrue(fired)
        self.assertEqual(
            _bystander_msgs(bystander.character_sheet),
            ["Heads turn as someone notable arrives."],
        )
        self.assertEqual(
            _bystander_msgs(arriver.character_sheet), ["You feel the room take notice."]
        )
        self.assertEqual(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=bystander.character_sheet
            )
            .first()
            .message.category,
            NarrativeCategory.RENOWN,
        )

    def test_renown_min_insular_society_perceives_less(self) -> None:
        room, profile = _room()
        insular = SocietyFactory(fame_perception_offset=-2)
        arriver = _character(room)
        persona = arriver.character_sheet.primary_persona
        persona.fame_tier = FameTier.CELEBRITY
        persona.save(update_fields=["fame_tier"])
        AmbientEmoteLineFactory(
            room_profile=profile,
            trigger_type=AmbientTriggerType.RENOWN_MIN,
            trigger_min_fame_tier=FameTier.CELEBRITY,
            trigger_perceiving_society=insular,
            bystander_body="Heads turn.",
        )
        # CELEBRITY (index 2) - 2 = NORMAL < CELEBRITY threshold -> silent.
        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )
        self.assertFalse(fired)


class CooldownAndFireChanceTests(TestCase):
    def test_cooldown_blocks_refire(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        line = AmbientEmoteLineFactory(room_profile=profile, cooldown_minutes=60)
        self.assertTrue(
            emit_room_ambient_reaction(
                payload=_FakeMovedPayload(character=arriver, destination=room)
            )
        )
        line.refresh_from_db()
        self.assertIsNotNone(line.last_fired_at)
        self.assertFalse(
            emit_room_ambient_reaction(
                payload=_FakeMovedPayload(character=arriver, destination=room)
            )
        )

    def test_cooldown_elapsed_refires(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        line = AmbientEmoteLineFactory(room_profile=profile, cooldown_minutes=1)
        line.last_fired_at = timezone.now() - timedelta(minutes=5)
        line.save(update_fields=["last_fired_at"])
        self.assertTrue(
            emit_room_ambient_reaction(
                payload=_FakeMovedPayload(character=arriver, destination=room)
            )
        )

    def test_fire_chance_zero_never_fires(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        AmbientEmoteLineFactory(room_profile=profile, fire_chance=0)
        self.assertFalse(
            emit_room_ambient_reaction(
                payload=_FakeMovedPayload(character=arriver, destination=room)
            )
        )


class MostSpecificWinsTests(TestCase):
    def test_room_pool_replaces_area_pool(self) -> None:
        area = AreaFactory()
        room, profile = _room()
        profile.area = area
        profile.save(update_fields=["area"])
        arriver = _character(room)
        AmbientEmoteLineFactory(
            parent_type=LocationParentType.AREA,
            area=area,
            room_profile=None,
            arriver_body="The area's generic mood.",
        )
        AmbientEmoteLineFactory(room_profile=profile, arriver_body="This room, specifically.")

        emit_room_ambient_reaction(payload=_FakeMovedPayload(character=arriver, destination=room))

        self.assertEqual(_bystander_msgs(arriver.character_sheet), ["This room, specifically."])

    def test_area_pool_used_when_room_has_no_lines(self) -> None:
        area = AreaFactory()
        room, profile = _room()
        profile.area = area
        profile.save(update_fields=["area"])
        arriver = _character(room)
        AmbientEmoteLineFactory(
            parent_type=LocationParentType.AREA,
            area=area,
            room_profile=None,
            arriver_body="The area's generic mood.",
        )

        fired = emit_room_ambient_reaction(
            payload=_FakeMovedPayload(character=arriver, destination=room)
        )

        self.assertTrue(fired)
        self.assertEqual(_bystander_msgs(arriver.character_sheet), ["The area's generic mood."])
