"""Unit tests for the reaction/favorite REGISTRY Actions (#1341)."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.scene_reactions import (
    ReactToWindowAction,
    ToggleFavoriteAction,
    ToggleReactionAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
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
from world.scenes.models import (
    InteractionFavorite,
    InteractionReaction,
    WindowReaction,
)
from world.scenes.reaction_services import open_reaction_window


def _make_char_in_room(room: ObjectDB) -> ObjectDB:
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


def _wire_account(sheet):
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return tenure.player_data.account


class ToggleFavoriteActionTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(db_key="FavRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.actor_char = _make_char_in_room(self.room)
        self.actor_sheet = CharacterSheetFactory(character=self.actor_char)
        self.actor_account = _wire_account(self.actor_sheet)
        SceneParticipationFactory(scene=self.scene, account=self.actor_account)
        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.actor_sheet.primary_persona,  # writer; but we react to OTHERS
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        # A pose by ANOTHER character for the actor to favorite:
        self.target_char = _make_char_in_room(self.room)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.target_account = _wire_account(self.target_sheet)
        SceneParticipationFactory(scene=self.scene, account=self.target_account)
        self.target_pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_toggle_on_creates_favorite(self) -> None:
        result = ToggleFavoriteAction().run(actor=self.actor_char, interaction=self.target_pose)
        self.assertTrue(result.success)
        self.assertEqual(InteractionFavorite.objects.count(), 1)
        fav = InteractionFavorite.objects.get()
        self.assertEqual(fav.roster_entry, self.actor_sheet.roster_entry)

    def test_toggle_off_removes_favorite(self) -> None:
        ToggleFavoriteAction().run(actor=self.actor_char, interaction=self.target_pose)
        result = ToggleFavoriteAction().run(actor=self.actor_char, interaction=self.target_pose)
        self.assertTrue(result.success)
        self.assertEqual(InteractionFavorite.objects.count(), 0)

    def test_cannot_favorite_without_roster_entry(self) -> None:
        # actor with no roster entry: sheet_data.roster_entry missing
        from world.character_sheets.factories import CharacterSheetFactory

        bare_char = _make_char_in_room(self.room)
        CharacterSheetFactory(character=bare_char)  # sheet but no RosterEntry
        result = ToggleFavoriteAction().run(actor=bare_char, interaction=self.target_pose)
        self.assertFalse(result.success)


class ToggleReactionActionTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(db_key="RxnRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.actor_char = _make_char_in_room(self.room)
        self.actor_sheet = CharacterSheetFactory(character=self.actor_char)
        self.actor_account = _wire_account(self.actor_sheet)
        self.target_char = _make_char_in_room(self.room)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        _wire_account(self.target_sheet)
        self.target_pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
        )

    def test_toggle_on_creates_reaction(self) -> None:
        result = ToggleReactionAction().run(
            actor=self.actor_char, interaction=self.target_pose, emoji="\U0001f389"
        )
        self.assertTrue(result.success)
        self.assertEqual(InteractionReaction.objects.count(), 1)

    def test_toggle_off_removes_reaction(self) -> None:
        ToggleReactionAction().run(
            actor=self.actor_char, interaction=self.target_pose, emoji="\U0001f389"
        )
        ToggleReactionAction().run(
            actor=self.actor_char, interaction=self.target_pose, emoji="\U0001f389"
        )
        self.assertEqual(InteractionReaction.objects.count(), 0)


class ReactToWindowActionTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(db_key="WinRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.actor_char = _make_char_in_room(self.room)
        self.actor_sheet = CharacterSheetFactory(character=self.actor_char)
        self.actor_account = _wire_account(self.actor_sheet)
        self.actor_char.db_account = self.actor_account
        self.actor_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.actor_account)
        self.target_char = _make_char_in_room(self.room)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.target_account = _wire_account(self.target_sheet)
        self.target_char.db_account = self.target_account
        self.target_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.target_account)
        # An ENTRY pose opens an ENTRANCE reaction window automatically.
        self.entry_pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            pose_kind=PoseKind.ENTRY,
        )
        self.resonance = ResonanceFactory(name="TestResonance1341")
        CharacterResonanceFactory(character_sheet=self.target_sheet, resonance=self.resonance)

    def test_react_lazy_open_kudos(self) -> None:
        # A standard (non-entry) pose; kudos is lazy_open.
        pose = InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        result = ReactToWindowAction().run(
            actor=self.actor_char,
            interaction=pose,
            kind=ReactionWindowKind.KUDOS,
            choice="kudos",
        )
        self.assertTrue(result.success)
        self.assertEqual(WindowReaction.objects.count(), 1)

    def test_react_to_open_entrance_window(self) -> None:
        # The entry_pose's ENTRANCE window already exists (opened on pose submit
        # in the viewset; here we open it explicitly since the factory bypasses that).
        open_reaction_window(interaction=self.entry_pose, kind=ReactionWindowKind.ENTRANCE)
        result = ReactToWindowAction().run(
            actor=self.actor_char,
            interaction=self.entry_pose,
            kind=ReactionWindowKind.ENTRANCE,
            choice=str(self.resonance.pk),
        )
        self.assertTrue(result.success)
        self.assertEqual(WindowReaction.objects.count(), 1)

    def test_react_validation_failure_is_reported(self) -> None:
        # Reacting to your own pose is blocked by react_to_window.
        my_pose = InteractionFactory(
            scene=self.scene,
            persona=self.actor_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        result = ReactToWindowAction().run(
            actor=self.actor_char,
            interaction=my_pose,
            kind=ReactionWindowKind.KUDOS,
            choice="kudos",
        )
        self.assertFalse(result.success)
