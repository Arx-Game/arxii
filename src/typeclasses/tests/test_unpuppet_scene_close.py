"""Tests for Character.at_post_unpuppet's scene auto-close wiring (#1361)."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory


def _find_unpuppet_owner(character):
    """Return the MRO class that directly defines at_post_unpuppet.

    Character inherits (ObjectParent, DefaultCharacter); ObjectParent is a
    plain mixin (see typeclasses/mixins.py) that does not define
    at_post_unpuppet, so the simple `__mro__[1]` used by the analogous
    `_patch_super_puppet` in typeclasses/tests/test_account_puppet_broadcast.py
    (which works there because Account has single inheritance straight to
    DefaultAccount) lands on the wrong class here. Walk the MRO to find the
    actual owner (DefaultCharacter) instead.
    """
    for klass in type(character).__mro__[1:]:
        if "at_post_unpuppet" in klass.__dict__:
            return klass
    msg = "at_post_unpuppet not found in MRO"
    raise AttributeError(msg)


def _patch_super_unpuppet(character, fake):
    """Replace the parent class's at_post_unpuppet with `fake`; return the original.

    Character.at_post_unpuppet calls `super().at_post_unpuppet(...)`, which is
    Evennia's base DefaultCharacter implementation — it relocates the character
    to a null location only when this is the last connected session
    (`self.sessions.count() == 0`). Rather than fighting real Evennia session
    plumbing to simulate "still connected," stub the parent method directly on
    the MRO, mirroring the existing `_patch_super_puppet` pattern in
    typeclasses/tests/test_account_puppet_broadcast.py.
    """
    parent = _find_unpuppet_owner(character)
    original = parent.at_post_unpuppet
    parent.at_post_unpuppet = fake
    return original


def _restore_super_unpuppet(character, original):
    parent = _find_unpuppet_owner(character)
    parent.at_post_unpuppet = original


class UnpuppetFinishesEmptySceneTests(TestCase):
    _PATCH_BASE = "world.scenes.scene_admin_services"

    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.character = CharacterFactory(db_key="Solo", location=self.room)
        CharacterSheetFactory(character=self.character)

    def test_disconnect_that_relocates_finishes_the_scene(self):
        """super().at_post_unpuppet relocating the character (last session out)
        must trigger maybe_finish_empty_scene for the room it just vacated."""

        def fake_relocate(char_self, account=None, session=None, **kwargs):
            char_self.location = None  # mimics the real base behavior

        original = _patch_super_unpuppet(self.character, fake_relocate)
        try:
            with (
                mock.patch(f"{self._PATCH_BASE}.on_scene_finished"),
                mock.patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
                mock.patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
            ):
                self.character.at_post_unpuppet()
        finally:
            _restore_super_unpuppet(self.character, original)

        self.scene.refresh_from_db()
        assert self.scene.is_finished is True

    def test_disconnect_that_does_not_relocate_does_not_close_scene(self):
        """A still-connected session (base class no-ops) must not trigger the
        scene-close check at all."""

        def fake_noop(char_self, account=None, session=None, **kwargs):
            pass  # mimics "still has another session" — location unchanged

        original = _patch_super_unpuppet(self.character, fake_noop)
        try:
            with mock.patch(
                "world.scenes.round_services.maybe_finish_empty_scene"
            ) as mock_maybe_finish:
                self.character.at_post_unpuppet()
        finally:
            _restore_super_unpuppet(self.character, original)

        mock_maybe_finish.assert_not_called()
        self.scene.refresh_from_db()
        assert self.scene.is_finished is False

    def test_real_evennia_relocation_finishes_the_scene_end_to_end(self):
        """No mocking of super() at all — a freshly-created CharacterFactory has
        zero attached sessions, so Evennia's real DefaultCharacter.at_post_unpuppet
        takes its `not self.sessions.count()` branch and relocates for real."""
        with (
            mock.patch(f"{self._PATCH_BASE}.on_scene_finished"),
            mock.patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            mock.patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            self.character.at_post_unpuppet()

        assert self.character.location is None
        assert self.character.db.prelogout_location.pk == self.room.pk
        self.scene.refresh_from_db()
        assert self.scene.is_finished is True

    def test_real_relocation_with_another_pc_present_keeps_scene_active(self):
        """Disconnect, not alone: real relocation still happens (this PC leaves
        the room), but another PC remains — the scene must stay active."""
        other_pc = CharacterFactory(db_key="Staying", location=self.room)
        CharacterSheetFactory(character=other_pc)

        with (
            mock.patch(f"{self._PATCH_BASE}.on_scene_finished"),
            mock.patch(f"{self._PATCH_BASE}.process_deferred_fatigue_resets"),
            mock.patch(f"{self._PATCH_BASE}.broadcast_scene_message"),
        ):
            self.character.at_post_unpuppet()

        assert self.character.location is None  # this character still relocated
        self.scene.refresh_from_db()
        assert self.scene.is_finished is False  # but the scene stays open


class UnpuppetPausesCombatBattleMissionTests(TestCase):
    """Character.at_post_unpuppet also pauses live CombatEncounter/Battle/
    MissionInstance participation on disconnect (#1899)."""

    def setUp(self) -> None:
        # A location is required: at_post_unpuppet captures `origin = self.location`
        # before calling super(), and only runs the guarded block (scene-close +
        # pause calls) `if origin is not None and self.location is None` — i.e. only
        # when the base hook's own "last session out" relocation actually fires. A
        # character created with no location at all (origin already None) never
        # takes that branch, so the pause calls would never run regardless of
        # wiring. Mirrors the room setup `UnpuppetFinishesEmptySceneTests` uses above.
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.character = CharacterFactory(db_key="PauseTester", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_disconnect_pauses_combat_encounter(self) -> None:
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory

        encounter = CombatEncounterFactory()
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )

        self.character.at_post_unpuppet()

        encounter.refresh_from_db()
        assert encounter.is_paused is True

    def test_disconnect_pauses_small_battle(self) -> None:
        from world.battles.constants import BattleParticipantStatus
        from world.battles.factories import (
            BattleFactory,
            BattleParticipantFactory,
            BattleSideFactory,
        )

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=self.sheet,
            status=BattleParticipantStatus.ACTIVE,
        )

        self.character.at_post_unpuppet()

        battle.refresh_from_db()
        assert battle.is_paused is True

    def test_disconnect_pauses_mission_instance(self) -> None:
        from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory

        instance = MissionInstanceFactory()
        MissionParticipantFactory(instance=instance, character=self.character)

        self.character.at_post_unpuppet()

        instance.refresh_from_db()
        assert instance.is_paused is True

    def test_disconnect_with_no_combat_battle_mission_does_not_raise(self) -> None:
        self.character.at_post_unpuppet()  # No participation rows anywhere — must not raise.
