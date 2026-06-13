"""Tests for capture/release services (#931)."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import AlreadyCapturedError, NotHeldError
from world.captivity.models import Captivity
from world.captivity.services import (
    capture_character,
    capture_party,
    resolve_captivity,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.scenes.factories import SceneFactory


class CaptureCharacterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.return_room = ObjectDB.objects.create(
            db_key="Capture Site",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_capture_spawns_cell_flips_lifecycle_and_moves_captive(self) -> None:
        captive = CharacterSheetFactory()

        captivity = capture_character(captive=captive, return_location=self.return_room)

        assert captivity.status == CaptivityStatus.HELD
        assert captivity.offscreen_loss_allowed is False
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.CAPTURED
        assert captive.lifecycle_state_at is not None
        # The body is inside the spawned cell, and the cell knows where to return them.
        assert captive.character.location == captivity.cell.room
        assert captivity.cell.return_location == self.return_room
        assert captivity.cell.status == InstanceStatus.ACTIVE

    def test_offscreen_loss_flag_is_recorded(self) -> None:
        captive = CharacterSheetFactory()

        captivity = capture_character(captive=captive, offscreen_loss_allowed=True)

        assert captivity.offscreen_loss_allowed is True

    def test_double_capture_is_rejected(self) -> None:
        captive = CharacterSheetFactory()
        capture_character(captive=captive)

        with self.assertRaises(AlreadyCapturedError):
            capture_character(captive=captive)


class CapturePartyTests(TestCase):
    def test_party_shares_one_cell(self) -> None:
        captives = [CharacterSheetFactory() for _ in range(3)]

        captivities = capture_party(captives=captives)

        assert len(captivities) == 3
        cells = {c.cell_id for c in captivities}
        assert len(cells) == 1  # one shared cell, the default
        for captivity, captive in zip(captivities, captives, strict=True):
            assert captivity.status == CaptivityStatus.HELD
            captive.refresh_from_db()
            assert captive.lifecycle_state == LifecycleState.CAPTURED
            assert captive.character.location == captivity.cell.room

    def test_empty_party_is_noop(self) -> None:
        assert capture_party(captives=[]) == []
        assert Captivity.objects.count() == 0
        assert InstancedRoom.objects.count() == 0


class ResolveCaptivityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.return_room = ObjectDB.objects.create(
            db_key="Home Square",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def test_resolve_last_held_frees_captive_and_completes_cell(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive, return_location=self.return_room)
        # A scene in the cell keeps the room from being torn down so we can
        # assert the instance was completed rather than deleted.
        cell = captivity.cell
        SceneFactory(location=cell.room)

        resolve_captivity(captivity, status=CaptivityStatus.ESCAPED)

        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.ESCAPED
        assert captivity.resolved_at is not None
        assert captivity.cell is None  # detached from the cell on resolution
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.ALIVE
        cell.refresh_from_db()
        assert cell.status == InstanceStatus.COMPLETED

    def test_resolve_with_others_held_keeps_shared_cell(self) -> None:
        first, second = CharacterSheetFactory(), CharacterSheetFactory()
        held = capture_party(captives=[first, second], return_location=self.return_room)

        resolve_captivity(held[0], status=CaptivityStatus.RESCUED)

        # Freed captive walks; cell stays standing for the one still held.
        held[0].refresh_from_db()
        assert held[0].status == CaptivityStatus.RESCUED
        first.refresh_from_db()
        assert first.lifecycle_state == LifecycleState.ALIVE
        assert first.character.location == self.return_room

        held[1].refresh_from_db()
        assert held[1].status == CaptivityStatus.HELD
        second.refresh_from_db()
        assert second.lifecycle_state == LifecycleState.CAPTURED
        held[1].cell.refresh_from_db()
        assert held[1].cell.status == InstanceStatus.ACTIVE

    def test_resolve_last_held_without_scene_preserves_history(self) -> None:
        # The common case: a cell with no Scene is torn down on resolution.
        # The Captivity row (status, resolved_at, captor, ransom link) MUST
        # survive that teardown — cell is SET_NULL, not CASCADE.
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive, return_location=self.return_room)
        cell_room = captivity.cell.room

        resolve_captivity(captivity, status=CaptivityStatus.RANSOMED)

        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED
        assert captivity.resolved_at is not None
        assert captivity.cell is None  # cell torn down, FK nulled — row lives on
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.ALIVE
        # Freed captive was relocated to the return location (not the deleted cell).
        assert captive.character.location == self.return_room
        assert not ObjectDB.objects.filter(pk=cell_room.pk).exists()

    def test_resolve_relocates_an_offline_captive(self) -> None:
        # complete_instanced_room only moves puppeted (online) chars; the
        # captivity service must relocate an offline freed captive itself.
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive, return_location=self.return_room)
        assert not captive.character.sessions.all()  # offline — no sessions

        resolve_captivity(captivity, status=CaptivityStatus.RESCUED)

        captive.refresh_from_db()
        assert captive.character.location == self.return_room

    def test_resolving_an_ended_captivity_is_rejected(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)
        resolve_captivity(captivity, status=CaptivityStatus.RELEASED)

        with self.assertRaises(NotHeldError):
            resolve_captivity(captivity, status=CaptivityStatus.ESCAPED)

    def test_resolve_rejects_a_non_terminal_status(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)

        with self.assertRaises(ValueError):
            resolve_captivity(captivity, status=CaptivityStatus.HELD)
