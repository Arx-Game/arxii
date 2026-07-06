"""Tests for CmdOutfit — the outfit CRUD + wear/undress/present namespace."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionResult
from commands.outfit import CmdOutfit
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, OutfitFactory


class CmdOutfitTests(TestCase):
    def _caller(self):
        room = ObjectDBFactory(db_key="CmdOutfitRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="cmdoutfit_account")
        caller = CharacterFactory(db_key="CmdOutfitAlice", location=room)
        caller.db_account = account
        caller.save()
        CharacterSheetFactory(character=caller)
        return caller

    def _run(self, caller, args: str) -> list[str]:
        cmd = CmdOutfit()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"outfit {args}"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005
        cmd.func()
        return messages

    def test_outfit_save_dispatches_save_outfit_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="CmdOutfitWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
            location=caller,
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            holder_character_sheet=caller.sheet_data,
            game_object=wardrobe_obj,
        )
        caller.search = MagicMock(return_value=wardrobe_obj)
        with patch("commands.outfit.SaveOutfitAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Saved.")
            self._run(caller, f"save Formal wardrobe={wardrobe.game_object.id}")
        mocked.assert_called_once()

    def test_outfit_wear_dispatches_apply_outfit_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitWardrobe2", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Formal")
        with patch("commands.outfit.ApplyOutfitAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Worn.")
            self._run(caller, f"wear {outfit.pk}")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit_id"] == outfit.pk

    def test_bare_outfit_shows_hub(self):
        caller = self._caller()
        messages = self._run(caller, "")
        assert any("outfit" in m.lower() for m in messages)

    def test_outfit_rename_dispatches_rename_outfit_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitRenameWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Old")
        with patch("commands.outfit.RenameOutfitAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Renamed.")
            self._run(caller, f"rename {outfit.pk}=New Name")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit"] == outfit
        assert mocked.call_args.kwargs["name"] == "New Name"

    def test_outfit_delete_dispatches_delete_outfit_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitDeleteWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Casual")
        with patch("commands.outfit.DeleteOutfitAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Outfit deleted.")
            self._run(caller, f"delete {outfit.pk}")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit"] == outfit

    def test_outfit_addslot_dispatches_add_outfit_slot_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitAddSlotWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Casual")
        item_template = ItemTemplateFactory(name="CmdOutfitAddSlotShirt")
        item_obj = ObjectDBFactory(
            db_key="CmdOutfitAddSlotShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
            location=caller,
        )
        item_instance = ItemInstanceFactory(
            template=item_template,
            holder_character_sheet=caller.sheet_data,
            game_object=item_obj,
        )
        caller.search = MagicMock(return_value=item_obj)
        with patch("commands.outfit.AddOutfitSlotAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Slot added.")
            self._run(caller, f"addslot {outfit.pk} item={item_obj.id} region=torso layer=base")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit"] == outfit
        assert mocked.call_args.kwargs["item_instance"] == item_instance
        assert mocked.call_args.kwargs["body_region"] == "torso"
        assert mocked.call_args.kwargs["equipment_layer"] == "base"

    def test_outfit_removeslot_dispatches_remove_outfit_slot_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitRemoveSlotWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Casual")
        with patch("commands.outfit.RemoveOutfitSlotAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Slot removed.")
            self._run(caller, f"removeslot {outfit.pk} region=torso layer=base")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit"] == outfit
        assert mocked.call_args.kwargs["body_region"] == "torso"
        assert mocked.call_args.kwargs["equipment_layer"] == "base"

    def test_outfit_undress_dispatches_undress_action(self):
        caller = self._caller()
        with patch("commands.outfit.UndressAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Undressed.")
            self._run(caller, "undress")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["actor"] == caller

    def test_outfit_present_dispatches_present_outfit_action(self):
        caller = self._caller()
        wardrobe_template = ItemTemplateFactory(
            name="CmdOutfitPresentWardrobe", is_wardrobe=True, is_container=True
        )
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template, holder_character_sheet=caller.sheet_data
        )
        outfit = OutfitFactory(character_sheet=caller.sheet_data, wardrobe=wardrobe, name="Casual")
        with patch("commands.outfit.PresentOutfitAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Presented.")
            self._run(caller, f"present {outfit.pk} event=42")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["outfit_id"] == outfit.pk
        assert mocked.call_args.kwargs["event_id"] == 42
