"""Tests for the crafting Actions (facet/style attach, facet detach)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.crafting import (
    AttachFacetAction,
    AttachStyleAction,
    DetachFacetAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.exceptions import FacetAlreadyAttached
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.types import FacetCraftResult, StyleCraftResult
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class AttachFacetActionTests(TestCase):
    def _actor_and_item(self):
        room = ObjectDBFactory(db_key="AttachFacetRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="attach_facet_account")
        actor = CharacterFactory(db_key="AttachFacetAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=account),
        )
        template = ItemTemplateFactory(name="AttachFacetSword")
        instance = ItemInstanceFactory(template=template, holder_character_sheet=sheet)
        return actor, instance

    def test_attach_facet_success(self):
        actor, instance = self._actor_and_item()
        facet = object()  # stand-in Facet; craft_attach_facet is mocked below
        result = FacetCraftResult(
            attached=True,
            outcome=None,
            item_facet=None,
            quality_tier=None,
            consumed=None,
            consequence_label="",
        )
        with patch(
            "actions.definitions.crafting.craft_attach_facet", return_value=result
        ) as mocked:
            action_result = AttachFacetAction().run(
                actor=actor, item_instance=instance, facet=facet
            )
        assert action_result.success
        assert action_result.data["result"] is result
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["item_instance"] == instance
        assert mocked.call_args.kwargs["facet"] is facet

    def test_attach_facet_not_holding_item_fails(self):
        room = ObjectDBFactory(
            db_key="AttachFacetRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="attach_facet_account_2")
        actor = CharacterFactory(db_key="AttachFacetBob", location=room)
        sheet = CharacterSheetFactory(character=actor)
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=account),
        )
        other_account = AccountFactory(username="attach_facet_account_2_other")
        other_actor = CharacterFactory(db_key="AttachFacetOtherOwner", location=room)
        other_sheet = CharacterSheetFactory(character=other_actor)
        other_roster_entry = RosterEntryFactory(character_sheet=other_sheet)
        RosterTenureFactory(
            roster_entry=other_roster_entry,
            player_data=PlayerDataFactory(account=other_account),
        )
        template = ItemTemplateFactory(name="AttachFacetElsewhereSword")
        instance = ItemInstanceFactory(template=template, holder_character_sheet=other_sheet)

        action_result = AttachFacetAction().run(actor=actor, item_instance=instance, facet=object())
        assert not action_result.success

    def test_attach_facet_translates_domain_exception(self):
        actor, instance = self._actor_and_item()
        with patch(
            "actions.definitions.crafting.craft_attach_facet",
            side_effect=FacetAlreadyAttached("already attached"),
        ):
            action_result = AttachFacetAction().run(
                actor=actor, item_instance=instance, facet=object()
            )
        assert not action_result.success
        assert action_result.message


class AttachStyleActionTests(TestCase):
    def test_attach_style_success(self):
        room = ObjectDBFactory(db_key="AttachStyleRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="attach_style_account")
        actor = CharacterFactory(db_key="AttachStyleAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=account),
        )
        template = ItemTemplateFactory(name="AttachStyleCoat")
        instance = ItemInstanceFactory(template=template, holder_character_sheet=sheet)
        result = StyleCraftResult(
            attached=True,
            outcome=None,
            item_style=None,
            quality_tier=None,
            consumed=None,
            consequence_label="",
        )
        with patch(
            "actions.definitions.crafting.craft_attach_style", return_value=result
        ) as mocked:
            action_result = AttachStyleAction().run(
                actor=actor, item_instance=instance, style=object()
            )
        assert action_result.success
        assert action_result.data["result"] is result
        mocked.assert_called_once()


class DetachFacetActionTests(TestCase):
    def test_detach_facet_requires_holding_item(self):
        room = ObjectDBFactory(db_key="DetachFacetRoom", db_typeclass_path="typeclasses.rooms.Room")
        account = AccountFactory(username="detach_facet_account")
        actor = CharacterFactory(db_key="DetachFacetAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=account),
        )
        other_account = AccountFactory(username="detach_facet_account_other")
        other_actor = CharacterFactory(db_key="DetachFacetOtherOwner", location=room)
        other_sheet = CharacterSheetFactory(character=other_actor)
        other_roster_entry = RosterEntryFactory(character_sheet=other_sheet)
        RosterTenureFactory(
            roster_entry=other_roster_entry,
            player_data=PlayerDataFactory(account=other_account),
        )
        template = ItemTemplateFactory(name="DetachFacetShield")
        instance = ItemInstanceFactory(template=template, holder_character_sheet=other_sheet)

        class _FakeItemFacet:
            item_instance = instance

        action_result = DetachFacetAction().run(actor=actor, item_facet=_FakeItemFacet())
        assert not action_result.success

    def test_detach_facet_success(self):
        room = ObjectDBFactory(
            db_key="DetachFacetRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="detach_facet_account_2")
        actor = CharacterFactory(db_key="DetachFacetBob", location=room)
        sheet = CharacterSheetFactory(character=actor)
        roster_entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=account),
        )
        template = ItemTemplateFactory(name="DetachFacetSword")
        instance = ItemInstanceFactory(template=template, holder_character_sheet=sheet)

        class _FakeItemFacet:
            item_instance = instance

        item_facet = _FakeItemFacet()
        with patch("actions.definitions.crafting.remove_facet_from_item") as mocked:
            action_result = DetachFacetAction().run(actor=actor, item_facet=item_facet)
        assert action_result.success
        mocked.assert_called_once_with(item_facet=item_facet)
