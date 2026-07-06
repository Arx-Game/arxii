"""Tests for CmdCraft — the craft/removefacet/style/quote telnet namespace."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.crafting import CmdCraft
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)


class CmdCraftTests(TestCase):
    def _make_caller_with_item(self):
        room = ObjectDBFactory(db_key="CmdCraftRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="cmdcraft_account")
        caller = CharacterFactory(db_key="CmdCraftAlice", location=room)
        caller.db_account = account
        caller.save()
        sheet = CharacterSheetFactory(character=caller)
        template = ItemTemplateFactory(name="CmdCraftSword")
        item_obj = ObjectDBFactory(
            db_key="CmdCraftSwordObj",
            db_typeclass_path="typeclasses.objects.Object",
            location=caller,
        )
        instance = ItemInstanceFactory(
            template=template, holder_character_sheet=sheet, game_object=item_obj
        )
        return caller, item_obj, instance

    def _run(self, caller, args: str) -> list[str]:
        cmd = CmdCraft()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"craft {args}"
        messages: list[str] = []
        cmd.msg = lambda *a, **kw: messages.append(a[0] if a else "")  # noqa: ARG005
        cmd.func()
        return messages

    def test_bare_craft_shows_usage(self):
        caller, _, _ = self._make_caller_with_item()
        messages = self._run(caller, "")
        assert any("facet" in m for m in messages)

    def test_craft_facet_dispatches_attach_facet_action(self):
        caller, item_obj, instance = self._make_caller_with_item()
        from world.magic.models import Facet

        facet = Facet.objects.create(name="CmdCraftGlow")
        caller.search = MagicMock(return_value=item_obj)
        with patch(
            "commands.crafting.AttachFacetAction.run",
        ) as mocked:
            from actions.types import ActionResult

            mocked.return_value = ActionResult(success=True, message="Attached.")
            self._run(caller, f"facet {facet.name} item={item_obj.id}")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["facet"] == facet
        assert mocked.call_args.kwargs["item_instance"] == instance

    def test_craft_removefacet_dispatches_detach_action(self):
        caller, _item_obj, item_instance = self._make_caller_with_item()
        from world.items.models import ItemFacet
        from world.magic.models import Facet

        facet = Facet.objects.create(name="CmdCraftTestFacet")
        quality_tier = QualityTierFactory(name="Common")
        item_facet = ItemFacet.objects.create(
            item_instance=item_instance, facet=facet, attachment_quality_tier=quality_tier
        )
        with patch("commands.crafting.DetachFacetAction.run") as mocked:
            from actions.types import ActionResult

            mocked.return_value = ActionResult(success=True, message="Detached.")
            self._run(caller, f"removefacet {item_facet.id}")
        mocked.assert_called_once()

    def test_craft_unknown_subverb_errors(self):
        caller, _, _ = self._make_caller_with_item()
        messages = self._run(caller, "bogus")
        assert any("Unknown" in m for m in messages)

    def test_craft_style_dispatches_attach_style_action(self):
        caller, item_obj, instance = self._make_caller_with_item()
        from world.items.models import Style

        style = Style.objects.create(name="CmdCraftSharp")
        caller.search = MagicMock(return_value=item_obj)
        with patch("commands.crafting.AttachStyleAction.run") as mocked:
            from actions.types import ActionResult

            mocked.return_value = ActionResult(success=True, message="Styled.")
            self._run(caller, f"style {style.name} item={item_obj.id}")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["style"] == style
        assert mocked.call_args.kwargs["item_instance"] == instance

    def test_craft_quote_calls_build_crafting_quote(self):
        caller, item_obj, _instance = self._make_caller_with_item()
        from world.magic.models import Facet

        facet = Facet.objects.create(name="CmdCraftQuoteGlow")
        caller.search = MagicMock(return_value=item_obj)
        fake_quote = MagicMock(costs="10 coppers", affordable=True, max_quality_tier="Fine")
        with patch(
            "world.items.crafting.services.build_crafting_quote", return_value=fake_quote
        ) as mocked:
            messages = self._run(caller, f"quote facet={facet.name} item={item_obj.id}")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["target"] == facet
        assert any("Fine" in m for m in messages)
