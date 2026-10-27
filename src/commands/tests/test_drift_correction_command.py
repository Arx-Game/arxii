"""Argument parsing for the telnet ``drift`` command (#4733).

The typed-line journey (handler, real rite) is Task 8; here the command's own parsing is
checked: how ``convert`` turns text into the action's kwargs, and what it refuses.
"""

from __future__ import annotations

from unittest.mock import patch

from django.utils import timezone

from actions.definitions.drift_correction import PerformDriftCorrectionAction
from commands.drift_correction import CmdDrift
from commands.exceptions import CommandError
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemFacetFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.factories import (
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    FacetFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
)
from world.magic.tests.test_drift_correction_rite import DriftRiteTestBase, _tied_item
from world.scenes.factories import SceneFactory


class DriftCommandTestBase(DriftRiteTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.caller = self.sheet.character
        # The caller's motif ties this facet to Dawnlight, so an item bearing it counts.
        self.motif_facet = FacetFactory()
        link = MotifResonanceFactory(motif__character=self.sheet, resonance=self.dawnlight)
        MotifResonanceAssociationFactory(motif_resonance=link, facet=self.motif_facet)

    def carry(self, item: ItemInstance) -> ItemInstance:
        item.holder_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(item, self.sheet)
        return item

    def faceted(self, name: str) -> ItemInstance:
        """A carried item bearing a facet the caller's motif ties to Dawnlight."""
        item = ItemInstanceFactory(template=ItemTemplateFactory(name=name))
        ItemFacetFactory(item_instance=item, facet=self.motif_facet)
        return self.carry(item)

    def command(self, args: str) -> CmdDrift:
        cmd = CmdDrift()
        cmd.caller = self.caller
        cmd.args = f" {args}" if args else ""
        cmd.raw_string = f"drift {args}".strip()
        return cmd

    def lines(self, args: str) -> str:
        cmd = self.command(args)
        with patch.object(cmd, "msg") as msg:
            cmd.func()
        sent = [call.args[0] for call in msg.call_args_list if call.args]
        # Typed lines go out as (text, options).
        return "\n".join(line[0] if isinstance(line, tuple) else line for line in sent)


class ResolveActionArgsTests(DriftCommandTestBase):
    def test_convert_with_amount_resolves_to_action_kwargs(self) -> None:
        kwargs = self.command("convert Drift Dread=Drift Dawnlight 5").resolve_action_args()
        self.assertEqual(kwargs["offer"], self.offer)
        self.assertEqual(kwargs["source_resonance"], self.dread)
        self.assertEqual(kwargs["target_resonance"], self.dawnlight)
        self.assertEqual(kwargs["amount"], 5)
        self.assertEqual(kwargs["components_provided"], [])

    def test_names_are_case_insensitive(self) -> None:
        kwargs = self.command("convert drift dread = drift dawnlight 5").resolve_action_args()
        self.assertEqual(kwargs["source_resonance"], self.dread)
        self.assertEqual(kwargs["target_resonance"], self.dawnlight)

    def test_amount_defaults_to_the_most_shown(self) -> None:
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["amount"], 12)

    def test_carried_items_are_gathered_from_the_callers_contents(self) -> None:
        item = _tied_item(self.dawnlight)
        item.holder_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(item, self.sheet)
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["components_provided"], [item])

    def test_items_held_by_someone_else_are_not_gathered(self) -> None:
        mine = _tied_item(self.dawnlight)
        mine.holder_character_sheet = self.sheet
        mine.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(mine, self.sheet)
        stray = _tied_item(self.dawnlight)
        stray.holder_character_sheet = CharacterSheetFactory()
        stray.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(stray, self.sheet)
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["components_provided"], [mine])

    def test_a_faceted_item_is_not_offered_unless_named(self) -> None:
        material = self.carry(_tied_item(self.dawnlight))
        cloak = self.faceted("Faceted Cloak")
        plain = self.carry(ItemInstanceFactory())
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["components_provided"], [material, plain])
        self.assertNotIn(cloak, kwargs["components_provided"])

    def test_with_names_the_item_to_spend_in_place_of_the_material(self) -> None:
        material = self.carry(_tied_item(self.dawnlight))
        cloak = self.faceted("Faceted Cloak")
        kwargs = self.command(
            "convert Drift Dread=Drift Dawnlight 5 with faceted cloak"
        ).resolve_action_args()
        self.assertEqual(kwargs["amount"], 5)
        self.assertEqual(kwargs["target_resonance"], self.dawnlight)
        self.assertEqual(kwargs["components_provided"], [cloak])
        self.assertNotIn(material, kwargs["components_provided"])

    def test_with_matches_part_of_a_name(self) -> None:
        cloak = self.faceted("Faceted Cloak")
        kwargs = self.command(
            "convert Drift Dread=Drift Dawnlight with cloak"
        ).resolve_action_args()
        self.assertEqual(kwargs["components_provided"], [cloak])

    def test_with_an_unknown_name_is_a_command_error(self) -> None:
        self.faceted("Faceted Cloak")
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight with lantern").resolve_action_args()
        self.assertEqual(ctx.exception.msg, "You carry nothing called 'lantern'.")

    def test_with_an_ambiguous_name_is_a_command_error_naming_both(self) -> None:
        self.faceted("Faceted Cloak")
        self.faceted("Faceted Cloak Pin")
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight with faceted").resolve_action_args()
        self.assertIn("More than one thing you carry matches 'faceted'", ctx.exception.msg)
        self.assertIn("Faceted Cloak Pin", ctx.exception.msg)

    def test_with_an_item_that_does_not_count_says_so(self) -> None:
        self.carry(ItemInstanceFactory(template=ItemTemplateFactory(name="Plain Mug")))
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight with mug").resolve_action_args()
        self.assertEqual(
            ctx.exception.msg, "Plain Mug does not count as an offering for Drift Dawnlight."
        )

    def test_with_and_no_name_is_a_usage_error(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight with ").resolve_action_args()
        self.assertIn("Usage:", ctx.exception.msg)

    def test_unknown_resonance_is_a_command_error_naming_what_you_hold(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Nonsense=Drift Dawnlight 3").resolve_action_args()
        self.assertIn("You hold no resonance called 'Nonsense'", ctx.exception.msg)
        self.assertIn("Drift Dread", ctx.exception.msg)

    def test_someone_elses_resonance_is_unknown_to_you(self) -> None:
        with self.assertRaises(CommandError):
            self.command("convert Drift Dread=Drift Wild 3").resolve_action_args()

    def test_missing_equals_is_a_usage_error(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread").resolve_action_args()
        self.assertIn("Usage:", ctx.exception.msg)

    def test_no_offer_in_this_scene_is_a_command_error(self) -> None:
        self.offer.delete()
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight 3").resolve_action_args()
        self.assertEqual(ctx.exception.msg, "You have no open chance to correct drift.")

    def test_default_amount_with_nothing_convertible_is_a_command_error(self) -> None:
        with self.assertRaises(CommandError):
            self.command("convert Drift Dawnlight=Drift Dread").resolve_action_args()


class OfferLookupTests(DriftCommandTestBase):
    def test_a_character_who_left_the_scene_room_still_sees_and_acts_on_the_offer(self) -> None:
        elsewhere = ObjectDBFactory(db_key="Elsewhere", db_typeclass_path="typeclasses.rooms.Room")
        self.caller.location = elsewhere
        self.assertIn("Toward Drift Dawnlight: up to 12.", self.lines(""))
        kwargs = self.command("convert Drift Dread=Drift Dawnlight 4").resolve_action_args()
        self.assertEqual(kwargs["offer"], self.offer)

    def test_a_finished_scenes_offer_is_not_offered(self) -> None:
        self.offer.delete()
        finished = SceneFactory(is_active=False, date_finished=timezone.now())
        DriftConversionOfferFactory(character_sheet=self.sheet, scene=finished)
        self.assertEqual(self.lines(""), "You have no open chance to correct drift.")

    def test_with_two_open_offers_the_most_recent_is_used(self) -> None:
        newer = DriftConversionOfferFactory(character_sheet=self.sheet, scene=SceneFactory())
        DriftConversionCapFactory(offer=newer, target_resonance=self.sunrise, cap=3)
        self.assertIn("Toward Drift Sunrise: up to 3.", self.lines(""))

    def test_a_sheetless_caller_gets_the_friendly_refusal(self) -> None:
        cmd = self.command("")
        cmd.caller = CharacterFactory(db_key="Sheetless")
        with patch.object(cmd, "msg") as msg:
            cmd.func()
        sent = msg.call_args_list[0].args[0]
        self.assertEqual(sent[0], "You don't have a character sheet.")


class CommandWiringTests(DriftCommandTestBase):
    def test_drift_is_a_player_command_over_the_rite_action(self) -> None:
        self.assertEqual(CmdDrift.key, "drift")
        self.assertEqual(CmdDrift.locks, "cmd:all()")
        self.assertIsInstance(CmdDrift.action, PerformDriftCorrectionAction)

    def test_unknown_subverb_prints_the_usage(self) -> None:
        self.assertIn("Usage:", self.lines("frobnicate"))

    def test_bare_drift_shows_target_cap_sources_and_rate(self) -> None:
        text = self.lines("")
        self.assertIn("Toward Drift Dawnlight: up to 12.", text)
        self.assertIn("From Drift Dread: you hold 30", text)
        self.assertIn("would give 6", text)

    def test_bare_drift_lists_carried_qualifying_items_with_their_route(self) -> None:
        item = _tied_item(self.dawnlight)
        item.holder_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(item, self.sheet)
        self.assertIn("(material)", self.lines(""))

    def test_bare_drift_marks_a_faceted_item_as_spent_only_when_named(self) -> None:
        self.carry(_tied_item(self.dawnlight))
        self.faceted("Faceted Cloak")
        text = self.lines("")
        self.assertIn("(material).", text)
        self.assertIn("Spent only if named (|wwith <item>|n): Faceted Cloak (facet).", text)

    def test_decline_removes_the_offer(self) -> None:
        from world.magic.models import DriftConversionOffer

        self.lines("decline")
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_bare_drift_with_no_offer_says_so(self) -> None:
        self.offer.delete()
        self.assertEqual(self.lines(""), "You have no open chance to correct drift.")
