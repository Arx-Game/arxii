"""Tests for capture/release services (#931)."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import AlreadyCapturedError, NotHeldError
from world.captivity.models import Captivity, CaptivityConfig
from world.captivity.services import (
    capture_character,
    capture_party,
    escape_captivity,
    rescue_captive,
    resolve_captivity,
    resolve_capture_setup,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom
from world.missions.factories import MissionTemplateFactory
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


class CaptureGroupKeyTests(TestCase):
    def test_same_group_key_shares_one_cell(self) -> None:
        first, second = CharacterSheetFactory(), CharacterSheetFactory()

        a = capture_character(captive=first, group_key="event-1")
        b = capture_character(captive=second, group_key="event-1")

        assert a.cell_id == b.cell_id

    def test_different_group_keys_get_separate_cells(self) -> None:
        first, second = CharacterSheetFactory(), CharacterSheetFactory()

        a = capture_character(captive=first, group_key="event-1")
        b = capture_character(captive=second, group_key="event-2")

        assert a.cell_id != b.cell_id

    def test_resolved_group_cell_is_not_reused(self) -> None:
        first = CharacterSheetFactory()
        a = capture_character(captive=first, group_key="event-1")
        old_cell_id = a.cell_id
        resolve_captivity(a, status=CaptivityStatus.ESCAPED)  # tears the cell down

        second = CharacterSheetFactory()
        b = capture_character(captive=second, group_key="event-1")

        # The old cell is no longer ACTIVE, so a fresh one is spawned.
        assert b.cell_id != old_cell_id


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


class RescueCaptiveTests(TestCase):
    def test_rescue_frees_a_held_captive(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)

        freed = rescue_captive(captive)

        assert freed is True
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RESCUED
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.ALIVE

    def test_rescue_is_a_noop_when_not_held(self) -> None:
        captive = CharacterSheetFactory()
        assert rescue_captive(captive) is False


class EscapeCaptivityTests(TestCase):
    def test_escape_frees_a_held_captive(self) -> None:
        captive = CharacterSheetFactory()
        captivity = capture_character(captive=captive)

        freed = escape_captivity(captive)

        assert freed is True
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.ESCAPED
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.ALIVE

    def test_escape_is_a_noop_when_not_held(self) -> None:
        captive = CharacterSheetFactory()
        assert escape_captivity(captive) is False


class CaptivityConfigTests(TestCase):
    def test_load_is_a_singleton(self) -> None:
        first = CaptivityConfig.load()
        second = CaptivityConfig.load()
        assert first.pk == 1
        assert second.pk == first.pk
        assert CaptivityConfig.objects.count() == 1


class ResolveCaptureSetupTests(TestCase):
    def test_falls_through_to_the_config_default(self) -> None:
        config = CaptivityConfig.load()
        config.captive_template = MissionTemplateFactory(name="default-cell-loop")
        config.rescue_template = MissionTemplateFactory(name="default-rescue")
        config.cell_name = "The Common Gaol"
        config.cell_description = "A default holding cell."
        config.save()

        setup = resolve_capture_setup()

        assert setup.captive_template == config.captive_template
        assert setup.rescue_template == config.rescue_template
        assert setup.cell_name == "The Common Gaol"
        assert setup.cell_description == "A default holding cell."

    def test_override_wins_over_the_config_default(self) -> None:
        config = CaptivityConfig.load()
        config.captive_template = MissionTemplateFactory(name="default-cell-loop")
        config.cell_name = "The Common Gaol"
        config.save()
        override_loop = MissionTemplateFactory(name="ariwn-dungeon-loop")

        setup = resolve_capture_setup(
            captive_template=override_loop,
            cell_name="The Blood Crypt",
        )

        # The marquee captor's hand-crafted cell + loop win.
        assert setup.captive_template == override_loop
        assert setup.cell_name == "The Blood Crypt"
        # Anything the override leaves unset still falls through to the default.
        assert setup.rescue_template == config.rescue_template

    def test_empty_config_yields_empty_flavor_for_spawner_fallback(self) -> None:
        # No config set and no override → empty strings, so capture_character's
        # own placeholder cell flavor is what ends up used.
        setup = resolve_capture_setup()

        assert setup.captive_template is None
        assert setup.rescue_template is None
        assert setup.cell_name == ""
        assert setup.cell_description == ""
