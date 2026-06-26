"""Tests for shared GM telnet resolution helpers."""

from django.test import TestCase

from commands.exceptions import CommandError
from commands.utils.gm_resolution import (
    resolve_actor_or_error,
    resolve_character_sheet_in_room,
    resolve_model_by_pk_or_name,
)
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import Path
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class ResolveActorOrErrorTests(TestCase):
    def test_returns_controlling_account_for_active_tenure(self) -> None:
        account = AccountFactory()
        sheet = CharacterSheetFactory()
        player_data = PlayerDataFactory(account=account)
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)

        result = resolve_actor_or_error(sheet.character)

        assert result == account

    def test_raises_when_no_controlling_account(self) -> None:
        character = CharacterFactory()

        with self.assertRaisesMessage(CommandError, "No controlling account."):
            resolve_actor_or_error(character)


class ResolveModelByPkOrNameTests(TestCase):
    def test_resolves_by_numeric_pk(self) -> None:
        path = PathFactory(name="Iron Will")

        result = resolve_model_by_pk_or_name(
            Path,
            str(path.pk),
            not_found_msg="Not found.",
        )

        assert result == path

    def test_resolves_by_name_case_insensitively(self) -> None:
        path = PathFactory(name="Iron Will")

        result = resolve_model_by_pk_or_name(
            Path,
            "iron will",
            not_found_msg="Not found.",
        )

        assert result == path

    def test_raises_with_custom_message_when_not_found(self) -> None:
        with self.assertRaisesMessage(CommandError, "Missing path."):
            resolve_model_by_pk_or_name(
                Path,
                "Does Not Exist",
                not_found_msg="Missing path.",
            )


class ResolveCharacterSheetInRoomTests(TestCase):
    def test_finds_pc_by_name_in_room(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        sheet = CharacterSheetFactory()
        sheet.character.location = room
        sheet.character.save()

        result = resolve_character_sheet_in_room(
            None,
            sheet.character.db_key,
            room=room,
        )

        assert result == sheet

    def test_finds_pc_by_pk_in_room(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        sheet = CharacterSheetFactory()
        sheet.character.location = room
        sheet.character.save()

        result = resolve_character_sheet_in_room(
            None,
            str(sheet.pk),
            room=room,
        )

        assert result == sheet

    def test_raises_when_pc_is_not_in_room(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        other_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        sheet = CharacterSheetFactory()
        sheet.character.location = other_room
        sheet.character.save()

        with self.assertRaisesMessage(
            CommandError,
            f"No character named {sheet.character.db_key!r} here.",
        ):
            resolve_character_sheet_in_room(
                None,
                sheet.character.db_key,
                room=room,
            )
