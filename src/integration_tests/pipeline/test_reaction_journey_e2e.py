"""Telnet E2E: reaction/favorite journey — react favorite/emoji/kudos (#1341).

Proves ``CmdReact`` reaches the same services the web viewsets use, via the
shared Actions. Two characters in a room with an active scene; mock only
``character.msg``; drive real commands + real services. Uses ``setUp`` (not
``setUpTestData``) for ObjectDB-bearing fixtures (idmapper deepcopy fails in
CI shard runs — see project memory).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.react import CmdReact
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import InteractionFavorite, InteractionReaction, WindowReaction


def _make_char_in_room(room: ObjectDB) -> ObjectDB:
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


def _wire_account(sheet):
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return tenure.player_data.account


class ReactionJourneyE2ETests(TestCase):
    """CmdReact drives the real reaction/favorite services end-to-end."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDB.objects.create(
            db_key="ReactionE2ERoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        # Reactor
        self.reactor_char = _make_char_in_room(self.room)
        self.reactor_sheet = CharacterSheetFactory(character=self.reactor_char)
        self.reactor_account = _wire_account(self.reactor_sheet)
        self.reactor_char.db_account = self.reactor_account
        self.reactor_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.reactor_account)

        # Poser
        self.poser_char = _make_char_in_room(self.room)
        self.poser_sheet = CharacterSheetFactory(character=self.poser_char)
        self.poser_account = _wire_account(self.poser_sheet)
        self.poser_char.db_account = self.poser_account
        self.poser_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.poser_account)

        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.poser_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        self.reactor_char.msg = MagicMock()

    def _run_cmd(self, args: str) -> MagicMock:
        cmd = CmdReact()
        cmd.caller = self.reactor_char
        cmd.args = args
        cmd.raw_string = f"react {args}"
        cmd.func()
        return self.reactor_char.msg

    def _output(self) -> str:
        return " ".join(str(c[0][0]) for c in self.reactor_char.msg.call_args_list if c[0])

    def test_favorite_toggle_on_then_off(self) -> None:
        self._run_cmd(f"favorite {self.poser_char.name} #1")
        self.assertEqual(InteractionFavorite.objects.count(), 1)
        self._run_cmd(f"favorite {self.poser_char.name} #1")
        self.assertEqual(InteractionFavorite.objects.count(), 0)

    def test_emoji_toggle(self) -> None:
        self._run_cmd(f"emoji {self.poser_char.name} #1 \U0001f389")
        self.assertEqual(InteractionReaction.objects.count(), 1)
        self.assertEqual(InteractionReaction.objects.get().emoji, "\U0001f389")

    def test_kudos_lazy_open(self) -> None:
        self._run_cmd(f"kudos {self.poser_char.name} #1")
        self.assertEqual(WindowReaction.objects.count(), 1)

    def test_react_no_active_scene_shows_error(self) -> None:
        empty_room = ObjectDB.objects.create(
            db_key="EmptyRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.reactor_char.location = empty_room
        self.reactor_char.save()
        self.reactor_char.msg.reset_mock()
        cmd = CmdReact()
        cmd.caller = self.reactor_char
        cmd.args = f"favorite {self.poser_char.name} #1"
        cmd.raw_string = "react ..."
        cmd.func()
        self.assertIn("scene", self._output().lower())
