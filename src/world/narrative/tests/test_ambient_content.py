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

    def test_legend_deed_condition_compiles_to_has_legend_deeds_op(self) -> None:
        line = AmbientEmoteLineFactory(bystander_body="A murmur.")
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.LEGEND_DEED,
            species=None,
        )
        compiled = compile_line_filter(line)
        self.assertEqual(
            compiled,
            {"path": "character", "op": "has_legend_deeds", "value": None},
        )

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


class FormatDeedListTests(TestCase):
    def test_empty_returns_empty_string(self) -> None:
        from world.narrative.ambient_content import _format_deed_list

        self.assertEqual(_format_deed_list([]), "")

    def test_single_title(self) -> None:
        from world.narrative.ambient_content import _format_deed_list

        self.assertEqual(_format_deed_list(["Slew the Emperor"]), "Slew the Emperor")

    def test_two_titles_joined_with_and(self) -> None:
        from world.narrative.ambient_content import _format_deed_list

        self.assertEqual(
            _format_deed_list(["Slew the Emperor", "Broke the Seal"]),
            "Slew the Emperor and Broke the Seal",
        )

    def test_three_titles_oxford_comma(self) -> None:
        from world.narrative.ambient_content import _format_deed_list

        self.assertEqual(
            _format_deed_list(["A", "B", "C"]),
            "A, B, and C",
        )


class RenderBodyTests(TestCase):
    def test_static_body_passes_through_unchanged(self) -> None:
        from world.narrative.ambient_content import _render_body

        room, _profile = _room()
        character = _character(room)
        body = "A chill wind blows through the room."
        self.assertEqual(_render_body(body, character), body)

    def test_substitutes_name_placeholder(self) -> None:
        from world.narrative.ambient_content import _render_body

        room, _profile = _room()
        character = _character(room)
        persona = character.character_sheet.primary_persona
        body = "The crowd turns to look at {name}."
        self.assertEqual(
            _render_body(body, character), f"The crowd turns to look at {persona.name}."
        )

    def test_substitutes_deeds_placeholder(self) -> None:
        from world.narrative.ambient_content import _render_body
        from world.societies.factories import (
            LegendEntryFactory,
            LegendSpreadFactory,
        )

        room, _profile = _room()
        character = _character(room)
        persona = character.character_sheet.primary_persona
        deed = LegendEntryFactory(
            persona=persona, base_value=10, is_active=True, title="Slew the Emperor"
        )
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        body = "Word has it: {name}, {deeds}."
        result = _render_body(body, character)
        self.assertIn(persona.name, result)
        self.assertIn("Slew the Emperor", result)

    def test_no_sheet_returns_body_unchanged(self) -> None:
        from world.narrative.ambient_content import _render_body

        character = CharacterFactory()
        body = "Something happens. {name} is here."
        self.assertEqual(_render_body(body, character), body)


class LegendMurmurJourneyTests(TestCase):
    """End-to-end: a legend-murmur AmbientEmoteLine fires for a notable persona."""

    def test_murmur_fires_and_renders_deeds_for_notable_persona(self) -> None:
        from world.societies.factories import (
            LegendEntryFactory,
            LegendSpreadFactory,
        )

        room, profile = _room()
        arriver = _character(room)
        bystander = _character(room)
        persona = arriver.character_sheet.primary_persona
        persona.fame_tier = FameTier.CELEBRITY
        persona.save(update_fields=["fame_tier"])

        deed = LegendEntryFactory(
            persona=persona, base_value=10, is_active=True, title="Slew the Emperor"
        )
        LegendSpreadFactory(legend_entry=deed, value_added=40)

        line = AmbientEmoteLineFactory(
            room_profile=profile,
            bystander_body="A murmur ripples through the crowd as {name} enters — {deeds}.",
            arriver_body="",
            fire_chance=100,
            cooldown_minutes=0,
        )
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.LEGEND_DEED,
            species=None,
        )

        fired = deliver_ambient_group(
            payload=_FakeMovedPayload(character=arriver, destination=room),
            line_ids=[line.pk],
        )

        self.assertTrue(fired)
        delivery = NarrativeMessageDelivery.objects.get(
            recipient_character_sheet=bystander.character_sheet
        )
        self.assertIn(persona.name, delivery.message.body)
        self.assertIn("Slew the Emperor", delivery.message.body)
        self.assertEqual(delivery.message.category, NarrativeCategory.RENOWN)

    def test_murmur_does_not_fire_for_persona_without_deeds(self) -> None:
        """The has_legend_deeds filter blocks personas with no common-knowledge deeds."""
        from flows.filters.evaluator import evaluate_filter
        from world.narrative.ambient_content import compile_line_filter

        room, profile = _room()
        arriver = _character(room)

        line = AmbientEmoteLineFactory(
            room_profile=profile,
            bystander_body="A murmur ripples through the crowd as {name} enters — {deeds}.",
            arriver_body="",
        )
        AmbientEmoteConditionFactory(
            line=line,
            condition_type=ConditionType.LEGEND_DEED,
            species=None,
        )

        compiled = compile_line_filter(line)
        payload = _FakeMovedPayload(character=arriver, destination=room)
        result = evaluate_filter(compiled, payload, self_ref=arriver)
        self.assertFalse(result)
