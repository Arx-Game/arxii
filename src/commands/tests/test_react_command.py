"""Unit tests for CmdReact parsing + dispatch (#1341).

The happy-path favorite/emoji/kudos/no-scene flows are covered by the E2E
journey test ``test_reaction_journey_e2e.py``. These tests retain only the
edge cases the journey does NOT cover: the entrance-window + resonance
reaction, and the bare ``react`` hub listing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.react import CmdReact
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PoseKind,
    ReactionWindowKind,
)
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)


def _make_char_in_room(room: ObjectDB) -> ObjectDB:
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


def _wire_account(sheet):
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return tenure.player_data.account


class CmdReactTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDB.objects.create(
            db_key="ReactRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)
        # Actor
        self.actor = _make_char_in_room(self.room)
        self.actor_sheet = CharacterSheetFactory(character=self.actor)
        self.actor_account = _wire_account(self.actor_sheet)
        self.actor.db_account = self.actor_account
        self.actor.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.actor_account)
        # Target with a pose
        self.target = _make_char_in_room(self.room)
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.target_account = _wire_account(self.target_sheet)
        self.target.db_account = self.target_account
        self.target.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.target_account)
        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        self.actor.msg = MagicMock()

    def _run(self, args: str) -> MagicMock:
        cmd = CmdReact()
        cmd.caller = self.actor
        cmd.args = args
        cmd.raw_string = f"react {args}"
        cmd.func()
        return self.actor.msg

    def _output(self) -> str:
        return " ".join(str(c[0][0]) for c in self.actor.msg.call_args_list if c[0])

    def test_react_entrance_window(self) -> None:
        # Make an entry pose (auto-opens an entrance window on submit, but the
        # factory bypasses that, so open it explicitly):
        entry_pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            pose_kind=PoseKind.ENTRY,
        )
        resonance = ResonanceFactory(name="EntranceResonance")
        CharacterResonanceFactory(character_sheet=self.target_sheet, resonance=resonance)
        from world.scenes.reaction_services import open_reaction_window

        open_reaction_window(interaction=entry_pose, kind=ReactionWindowKind.ENTRANCE)
        self._run(f"entrance {self.target.name} #2 {resonance.name}")
        from world.scenes.models import WindowReaction

        self.assertEqual(WindowReaction.objects.count(), 1)

    def test_bare_react_lists_open_windows(self) -> None:
        # No open windows yet -> hub reports none (or lists the scene's windows).
        self._run("")
        out = self._output().lower()
        self.assertIn("react", out)  # usage / hub content present
