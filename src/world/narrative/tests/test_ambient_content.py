"""Tests for compile_line_filter + deliver_ambient_group (#2471 v2)."""

from __future__ import annotations

from dataclasses import dataclass

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import ResonanceFactory
from world.narrative.ambient_content import compile_line_filter, deliver_ambient_group
from world.narrative.constants import ConditionConnector, ConditionType, NarrativeCategory
from world.narrative.factories import AmbientEmoteConditionFactory, AmbientEmoteLineFactory
from world.narrative.models import NarrativeMessageDelivery
from world.societies.constants import FameTier
from world.societies.factories import SocietyFactory
from world.species.factories import SpeciesFactory


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


@dataclass(frozen=True)
class _FakeMovedPayload:
    character: object
    destination: object


class CompileLineFilterTests(TestCase):
    def test_zero_conditions_compiles_to_none(self) -> None:
        line = AmbientEmoteLineFactory()
        self.assertIsNone(compile_line_filter(line))

    def test_species_condition_compiles_to_equality_leaf(self) -> None:
        species = SpeciesFactory(name="Infernal")
        line = AmbientEmoteLineFactory(bystander_body="A murmur.")
        AmbientEmoteConditionFactory(
            line=line, condition_type=ConditionType.SPECIES, species=species
        )
        compiled = compile_line_filter(line)
        self.assertEqual(
            compiled,
            {"path": "character.item_data.species.name", "op": "==", "value": "Infernal"},
        )

    def test_distinction_condition_compiles_to_public_distinction_leaf(self) -> None:
        distinction = DistinctionFactory(slug="the-iron-duelist")
        line = AmbientEmoteLineFactory(bystander_body="A murmur.")
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.DISTINCTION,
            species=None,
            distinction=distinction,
        )
        compiled = compile_line_filter(line)
        self.assertEqual(
            compiled,
            {"path": "character", "op": "has_public_distinction", "value": "the-iron-duelist"},
        )

    def test_renown_min_condition_compiles_to_fame_tier_leaf(self) -> None:
        line = AmbientEmoteLineFactory(bystander_body="A murmur.")
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.RENOWN_MIN,
            species=None,
            min_fame_tier=FameTier.CELEBRITY,
        )
        compiled = compile_line_filter(line)
        self.assertEqual(
            compiled,
            {
                "path": "character",
                "op": "fame_tier_at_least",
                "value": {"min_tier": "celebrity", "perceiving_society": None},
            },
        )

    def test_renown_min_condition_with_perceiving_society_compiles_society_name(self) -> None:
        society = SocietyFactory(name="The Silver Court")
        line = AmbientEmoteLineFactory(bystander_body="A murmur.")
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.RENOWN_MIN,
            species=None,
            min_fame_tier=FameTier.CELEBRITY,
            perceiving_society=society,
        )
        compiled = compile_line_filter(line)
        self.assertEqual(compiled["value"]["perceiving_society"], "The Silver Court")

    def test_two_conditions_and_connector_compiles_to_and_tree(self) -> None:
        species = SpeciesFactory(name="Infernal")
        resonance = ResonanceFactory(name="Abyssal")
        line = AmbientEmoteLineFactory(
            bystander_body="A murmur.", condition_connector=ConditionConnector.AND
        )
        AmbientEmoteConditionFactory(
            line=line, condition_type=ConditionType.SPECIES, species=species
        )
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.RESONANCE_MIN,
            species=None,
            resonance=resonance,
            minimum_value=50,
        )
        compiled = compile_line_filter(line)
        self.assertIn("and", compiled)
        self.assertEqual(len(compiled["and"]), 2)


class DeliverAmbientGroupTests(TestCase):
    def test_delivers_arriver_only_for_no_condition_group(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        bystander = _character(room)
        line = AmbientEmoteLineFactory(room_profile=profile, arriver_body="The room feels still.")

        fired = deliver_ambient_group(
            payload=_FakeMovedPayload(character=arriver, destination=room), line_ids=[line.pk]
        )

        self.assertTrue(fired)
        arriver_msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=arriver.character_sheet
            ).values_list("message__body", flat=True)
        )
        bystander_msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=bystander.character_sheet
            )
        )
        self.assertEqual(arriver_msgs, ["The room feels still."])
        self.assertEqual(bystander_msgs, [])

    def test_delivers_room_wide_for_conditional_group_uses_renown_category(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        bystander = _character(room)
        line = AmbientEmoteLineFactory(
            room_profile=profile,
            bystander_body="Heads turn.",
            arriver_body="You feel noticed.",
        )
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.RENOWN_MIN,
            species=None,
            min_fame_tier=FameTier.CELEBRITY,
        )

        fired = deliver_ambient_group(
            payload=_FakeMovedPayload(character=arriver, destination=room), line_ids=[line.pk]
        )

        self.assertTrue(fired)
        delivery = NarrativeMessageDelivery.objects.get(
            recipient_character_sheet=bystander.character_sheet
        )
        self.assertEqual(delivery.message.category, NarrativeCategory.RENOWN)

    def test_cooldown_blocks_refire(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        line = AmbientEmoteLineFactory(room_profile=profile, cooldown_minutes=60)
        self.assertTrue(
            deliver_ambient_group(
                payload=_FakeMovedPayload(character=arriver, destination=room), line_ids=[line.pk]
            )
        )
        self.assertFalse(
            deliver_ambient_group(
                payload=_FakeMovedPayload(character=arriver, destination=room), line_ids=[line.pk]
            )
        )

    def test_fire_chance_zero_never_fires(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        line = AmbientEmoteLineFactory(room_profile=profile, fire_chance=0)
        self.assertFalse(
            deliver_ambient_group(
                payload=_FakeMovedPayload(character=arriver, destination=room), line_ids=[line.pk]
            )
        )

    def test_sheetless_arriver_is_silent(self) -> None:
        room, profile = _room()
        line = AmbientEmoteLineFactory(room_profile=profile)
        sheetless = CharacterFactory()
        sheetless.db_location = room
        sheetless.save(update_fields=["db_location"])
        self.assertFalse(
            deliver_ambient_group(
                payload=_FakeMovedPayload(character=sheetless, destination=room),
                line_ids=[line.pk],
            )
        )

    def test_weighted_pick_among_group_only_uses_given_line_ids(self) -> None:
        room, profile = _room()
        arriver = _character(room)
        in_group = AmbientEmoteLineFactory(room_profile=profile, arriver_body="In the group.")
        AmbientEmoteLineFactory(room_profile=profile, arriver_body="Not in the group.")

        deliver_ambient_group(
            payload=_FakeMovedPayload(character=arriver, destination=room),
            line_ids=[in_group.pk],
        )

        msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=arriver.character_sheet
            ).values_list("message__body", flat=True)
        )
        self.assertEqual(msgs, ["In the group."])
