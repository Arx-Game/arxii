"""#885 — mission journal + located play loop.

Covers the spec's test matrix: anchor recording per grant path, the
location conjunct (ANYWHERE/ANCHOR/ROOMS × override/inherit ×
in-room/elsewhere), journal compass disclosure, the play services
(beat_for / resolve_beat_option incl. re-verification and the
actor/audience narrative split), and the player API endpoints.

Graphs use BRANCH options throughout (no dice) so routing is
deterministic; the CHECK path is already covered by the Phase-3 engine
tests.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.areas.constants import AreaLevel
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import (
    MissionStatus,
    NodeLocationMode,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.missions.services.journal import journal_for
from world.missions.services.play import (
    BeatActionError,
    NotParticipantError,
    beat_for,
    resolve_beat_option,
)
from world.missions.services.resolution import build_option_list
from world.missions.services.run import staff_assign_mission
from world.narrative.models import AmbientStirLine, NarrativeMessageDelivery


def _room(name: str):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room)
    return room, profile


def _pc(room=None):
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    if room is not None:
        character.db_location = room
        character.save(update_fields=["db_location"])
    return character


def _graph(name: str):
    """Entry node with one BRANCH option to a second node, whose single
    BRANCH option is terminal. Returns (template, entry, entry_option,
    second, second_option)."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    entry_option = MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER take the first step",
        branch_target=second,
    )
    second_option = MissionOptionFactory(
        node=second,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER finish it",
        branch_target=None,  # terminal
    )
    return template, entry, entry_option, second, second_option


class AnchorRecordingTests(TestCase):
    def test_staff_assign_records_location_profile(self) -> None:
        room, profile = _room("Anchor Hall")
        character = _pc(room)
        template, *_ = _graph("anchored")
        instance = staff_assign_mission(template, character)
        self.assertEqual(instance.anchor_room_id, profile.pk)

    def test_placeless_grant_records_null_anchor(self) -> None:
        character = _pc()  # no location
        template, *_ = _graph("placeless")
        instance = staff_assign_mission(template, character)
        self.assertIsNone(instance.anchor_room_id)


class LocationConjunctTests(TestCase):
    # setUp (not setUpTestData): Django deepcopies class-level test data per
    # test, and Evennia ObjectDB/RoomProfile instances acquire
    # un-deepcopyable internals when the full suite has loaded typeclass
    # machinery — fresh-per-test creation sidesteps the whole class of
    # failures (passes standalone, breaks in `arx test` otherwise).
    def setUp(self) -> None:
        self.here_room, self.here = _room("Here")
        self.there_room, self.there = _room("There")

    def _run(self, *, mode, node_rooms=(), option_rooms=(), in_room=True):
        template, entry, entry_option, *_ = _graph(
            f"conjunct-{mode}-{len(node_rooms)}-{len(option_rooms)}-{in_room}"
        )
        entry.location_mode = mode
        entry.save(update_fields=["location_mode"])
        entry.locations.set(node_rooms)
        entry_option.locations.set(option_rooms)
        character = _pc(self.here_room if in_room else self.there_room)
        instance = staff_assign_mission(template, character)
        # Re-anchor explicitly so ANCHOR tests pin the anchor to Here even
        # when the character started elsewhere.
        instance.anchor_room = self.here
        instance.save(update_fields=["anchor_room"])
        participant = instance.participants.get(character=character)
        return build_option_list(instance, entry, participant)

    def test_anywhere_is_live_everywhere(self) -> None:
        self.assertEqual(len(self._run(mode=NodeLocationMode.ANYWHERE, in_room=False)), 1)

    def test_anchor_live_only_in_anchor_room(self) -> None:
        self.assertEqual(len(self._run(mode=NodeLocationMode.ANCHOR, in_room=True)), 1)
        self.assertEqual(len(self._run(mode=NodeLocationMode.ANCHOR, in_room=False)), 0)

    def test_rooms_live_only_in_authored_rooms(self) -> None:
        live = self._run(mode=NodeLocationMode.ROOMS, node_rooms=[self.here], in_room=True)
        self.assertEqual(len(live), 1)
        dead = self._run(mode=NodeLocationMode.ROOMS, node_rooms=[self.here], in_room=False)
        self.assertEqual(len(dead), 0)

    def test_option_override_beats_node_default(self) -> None:
        # Node says ROOMS={There}; the option overrides to {Here} — live Here.
        live = self._run(
            mode=NodeLocationMode.ROOMS,
            node_rooms=[self.there],
            option_rooms=[self.here],
            in_room=True,
        )
        self.assertEqual(len(live), 1)
        # And the override means NOT live in the node's own room set.
        dead = self._run(
            mode=NodeLocationMode.ROOMS,
            node_rooms=[self.there],
            option_rooms=[self.here],
            in_room=False,
        )
        self.assertEqual(len(dead), 0)

    def test_null_anchor_never_fires_anchor_options(self) -> None:
        template, entry, *_ = _graph("null-anchor")
        entry.location_mode = NodeLocationMode.ANCHOR
        entry.save(update_fields=["location_mode"])
        character = _pc(self.here_room)
        instance = staff_assign_mission(template, character)
        instance.anchor_room = None
        instance.save(update_fields=["anchor_room"])
        participant = instance.participants.get(character=character)
        self.assertEqual(len(build_option_list(instance, entry, participant)), 0)


class AreaLocationConjunctTests(TestCase):
    """NodeLocationMode.AREA matches rooms in the target area subtree (#888)."""

    def setUp(self) -> None:
        from world.areas.factories import AreaFactory

        self.parent_area = AreaFactory(level=AreaLevel.CITY)
        self.child_area = AreaFactory(parent=self.parent_area, level=AreaLevel.NEIGHBORHOOD)
        self.other_area = AreaFactory()

        self.here_room, self.here = _room("AreaHere")
        self.here.area = self.parent_area
        self.here.save(update_fields=["area"])

        self.child_room, self.child = _room("AreaChild")
        self.child.area = self.child_area
        self.child.save(update_fields=["area"])

        self.other_room, self.other = _room("AreaOther")
        self.other.area = self.other_area
        self.other.save(update_fields=["area"])

    def _run_area(self, *, target_area, in_room):
        template, entry, _entry_option, *_ = _graph(f"area-{target_area.pk}-{in_room}")
        entry.location_mode = NodeLocationMode.AREA
        entry.target_area = target_area
        entry.save(update_fields=["location_mode", "target_area"])
        character = _pc(in_room)
        instance = staff_assign_mission(template, character)
        participant = instance.participants.get(character=character)
        return build_option_list(instance, entry, participant)

    def test_area_live_in_target_area(self) -> None:
        live = self._run_area(target_area=self.parent_area, in_room=self.here_room)
        self.assertEqual(len(live), 1)

    def test_area_live_in_descendant_area(self) -> None:
        live = self._run_area(target_area=self.parent_area, in_room=self.child_room)
        self.assertEqual(len(live), 1)

    def test_area_dead_outside_subtree(self) -> None:
        dead = self._run_area(target_area=self.parent_area, in_room=self.other_room)
        self.assertEqual(len(dead), 0)

    def test_area_dead_when_target_area_null(self) -> None:
        template, entry, *_ = _graph("area-null-target")
        # The model's clean() forbids saving AREA with a null target_area, so
        # we test the runtime guard by mutating the in-memory node after saving
        # it with a placeholder area.
        entry.location_mode = NodeLocationMode.AREA
        entry.target_area = self.other_area
        entry.save(update_fields=["location_mode", "target_area"])
        entry.target_area_id = None
        character = _pc(self.here_room)
        instance = staff_assign_mission(template, character)
        participant = instance.participants.get(character=character)
        self.assertEqual(len(build_option_list(instance, entry, participant)), 0)


class JournalCompassTests(TestCase):
    # setUp, not setUpTestData — see LocationConjunctTests.
    def setUp(self) -> None:
        self.inn_room, self.inn = _room("Lantern Row Inn")
        self.hall_room, self.hall = _room("Merchants Guildhall")

    def test_compass_lists_ungated_override_rooms(self) -> None:
        template, _entry, entry_option, *_ = _graph("compass-ungated")
        entry_option.locations.set([self.inn])
        character = _pc(self.hall_room)
        staff_assign_mission(template, character)
        (entry_row,) = [e for e in journal_for(character) if e.template_name == template.name]
        self.assertIn("Lantern Row Inn", entry_row.compass_rooms)
        self.assertFalse(entry_row.compass_anywhere)

    def test_compass_never_leaks_gated_override_rooms(self) -> None:
        template, _entry, entry_option, *_ = _graph("compass-gated")
        entry_option.locations.set([self.inn])
        entry_option.visibility_rule = {"leaf": "min_character_level", "params": {"level": 99}}
        entry_option.save(update_fields=["visibility_rule"])
        character = _pc(self.hall_room)
        staff_assign_mission(template, character)
        (entry_row,) = [e for e in journal_for(character) if e.template_name == template.name]
        self.assertNotIn("Lantern Row Inn", entry_row.compass_rooms)

    def test_compass_anchor_names_the_grant_room(self) -> None:
        template, entry, *_ = _graph("compass-anchor")
        entry.location_mode = NodeLocationMode.ANCHOR
        entry.save(update_fields=["location_mode"])
        character = _pc(self.hall_room)
        staff_assign_mission(template, character)
        (entry_row,) = [e for e in journal_for(character) if e.template_name == template.name]
        self.assertIn("Merchants Guildhall", entry_row.compass_rooms)

    def test_compass_area_names_target_area(self) -> None:
        from world.areas.factories import AreaFactory

        district = AreaFactory(name="Lowtown", level=AreaLevel.CITY)
        template, entry, *_ = _graph("compass-area")
        entry.location_mode = NodeLocationMode.AREA
        entry.target_area = district
        entry.save(update_fields=["location_mode", "target_area"])
        character = _pc(self.hall_room)
        staff_assign_mission(template, character)
        (entry_row,) = [e for e in journal_for(character) if e.template_name == template.name]
        self.assertIn("Lowtown", entry_row.compass_rooms)
        self.assertFalse(entry_row.compass_anywhere)

    def test_compass_area_null_target_is_empty(self) -> None:
        from world.areas.factories import AreaFactory

        template, entry, *_ = _graph("compass-area-null")
        # Model clean() forbids saving AREA with a null target_area; test the
        # runtime fallback by saving with a placeholder and clearing it in memory.
        entry.location_mode = NodeLocationMode.AREA
        entry.target_area = AreaFactory()
        entry.save(update_fields=["location_mode", "target_area"])
        entry.target_area_id = None
        character = _pc(self.hall_room)
        staff_assign_mission(template, character)
        (entry_row,) = [e for e in journal_for(character) if e.template_name == template.name]
        self.assertEqual(entry_row.compass_rooms, ())
        self.assertFalse(entry_row.compass_anywhere)

    def test_epilogue_only_on_complete(self) -> None:
        template, _entry, entry_option, _second, second_option = _graph("compass-epilogue")
        template.epilogue = "PLACEHOLDER the dust settles."
        template.save()
        character = _pc(self.hall_room)
        instance = staff_assign_mission(template, character)
        (active_row,) = [e for e in journal_for(character) if e.instance_id == instance.pk]
        self.assertEqual(active_row.epilogue, "")
        resolve_beat_option(instance, character, option_id=entry_option.pk)
        resolve_beat_option(instance, character, option_id=second_option.pk)
        (done_row,) = [e for e in journal_for(character) if e.instance_id == instance.pk]
        self.assertEqual(done_row.status, MissionStatus.COMPLETE)
        self.assertEqual(done_row.epilogue, "PLACEHOLDER the dust settles.")


class PlayServiceTests(TestCase):
    # setUp, not setUpTestData — see LocationConjunctTests.
    def setUp(self) -> None:
        self.room, self.profile = _room("Warehouse")

    def _start(self, name: str):
        template, _entry, entry_option, _second, second_option = _graph(name)
        character = _pc(self.room)
        instance = staff_assign_mission(template, character)
        return instance, character, entry_option, second_option

    def test_beat_for_surfaces_live_options(self) -> None:
        instance, character, entry_option, _ = self._start("beat-live")
        beat = beat_for(instance, character)
        self.assertIsNotNone(beat)
        self.assertEqual([o.option_id for o in beat.options], [entry_option.pk])
        self.assertEqual(beat.node_key, "entry")

    def test_resolve_advances_and_returns_next_beat(self) -> None:
        instance, character, entry_option, second_option = self._start("resolve-advance")
        result = resolve_beat_option(instance, character, option_id=entry_option.pk)
        self.assertFalse(result.is_terminal)
        self.assertEqual(result.next_beat.node_key, "second")
        self.assertEqual([o.option_id for o in result.next_beat.options], [second_option.pk])

    def test_terminal_resolve_returns_epilogue(self) -> None:
        instance, character, entry_option, second_option = self._start("resolve-terminal")
        instance.template.epilogue = "PLACEHOLDER and so it ended."
        instance.template.save()
        resolve_beat_option(instance, character, option_id=entry_option.pk)
        result = resolve_beat_option(instance, character, option_id=second_option.pk)
        self.assertTrue(result.is_terminal)
        self.assertIsNone(result.next_beat)
        self.assertEqual(result.epilogue, "PLACEHOLDER and so it ended.")

    def test_actor_gets_story_message_room_gets_ambient(self) -> None:
        AmbientStirLine.objects.create(body="PLACEHOLDER something stirs.")
        instance, character, entry_option, _ = self._start("narrative-split")
        bystander = _pc(self.room)
        resolve_beat_option(instance, character, option_id=entry_option.pk)

        actor_bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=character.sheet_data
            ).values_list("message__body", "message__category")
        )
        bystander_bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=bystander.sheet_data
            ).values_list("message__body", "message__category")
        )
        self.assertTrue(any(cat == "story" for _, cat in actor_bodies))
        self.assertTrue(all(body != "PLACEHOLDER something stirs." for body, _ in actor_bodies))
        self.assertEqual(bystander_bodies, [("PLACEHOLDER something stirs.", "happenstance")])

    def test_empty_ambient_pool_is_silent(self) -> None:
        instance, character, entry_option, _ = self._start("silent-pool")
        bystander = _pc(self.room)
        resolve_beat_option(instance, character, option_id=entry_option.pk)
        self.assertFalse(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=bystander.sheet_data
            ).exists()
        )

    def test_resolve_reverifies_location(self) -> None:
        instance, character, entry_option, _ = self._start("reverify")
        entry = instance.current_node
        entry.location_mode = NodeLocationMode.ANCHOR
        entry.save(update_fields=["location_mode"])
        elsewhere, _ = _room("Elsewhere")
        character.db_location = elsewhere
        character.save(update_fields=["db_location"])
        with self.assertRaises(BeatActionError):
            resolve_beat_option(instance, character, option_id=entry_option.pk)

    def test_non_participant_raises_not_participant(self) -> None:
        instance, _character, entry_option, _ = self._start("interloper")
        interloper = _pc(self.room)
        with self.assertRaises(NotParticipantError):
            resolve_beat_option(instance, interloper, option_id=entry_option.pk)


class JournalApiTests(TestCase):
    # setUp, not setUpTestData — see LocationConjunctTests.
    def setUp(self) -> None:
        self.room, self.profile = _room("Api Hall")
        self.account = AccountFactory(username="journal-player")
        self.character = _pc(self.room)
        (
            self.template,
            self.entry,
            self.entry_option,
            self.second,
            self.second_option,
        ) = _graph(f"api-mission-{self._testMethodName}")
        self.instance = staff_assign_mission(self.template, self.character)
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        patcher = mock.patch("world.missions.views._puppet_character", return_value=self.character)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_list_returns_journal_entries(self) -> None:
        res = self.client.get("/api/missions/journal/")
        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["template_name"], self.template.name)
        self.assertEqual(results[0]["current_node_key"], "entry")

    def test_beat_returns_live_options(self) -> None:
        res = self.client.get(f"/api/missions/journal/{self.instance.pk}/beat/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["node_key"], "entry")
        self.assertEqual([o["option_id"] for o in body["options"]], [self.entry_option.pk])

    def test_non_participant_gets_404(self) -> None:
        outsider = _pc(self.room)
        with mock.patch("world.missions.views._puppet_character", return_value=outsider):
            res = self.client.get(f"/api/missions/journal/{self.instance.pk}/beat/")
        self.assertEqual(res.status_code, 404)

    def test_resolve_happy_path(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/resolve/",
            {"option_id": self.entry_option.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertFalse(body["is_terminal"])
        self.assertEqual(body["next_beat"]["node_key"], "second")
        # Fresh DB read — the run actually advanced.
        self.assertEqual(
            MissionInstance.objects.get(pk=self.instance.pk).current_node_id,
            self.second.pk,
        )

    def test_resolve_unknown_option_is_400(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/resolve/",
            {"option_id": 999999},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_completed_run_beat_is_404(self) -> None:
        resolve_beat_option(self.instance, self.character, option_id=self.entry_option.pk)
        resolve_beat_option(self.instance, self.character, option_id=self.second_option.pk)
        res = self.client.get(f"/api/missions/journal/{self.instance.pk}/beat/")
        self.assertEqual(res.status_code, 404)


class TaleApiTests(TestCase):
    """#2047 — POST /api/missions/journal/{id}/tale/ endpoint."""

    def setUp(self) -> None:
        self.room, self.profile = _room("Tale Hall")
        self.account = AccountFactory(username="tale-player")
        self.character = _pc(self.room)
        (
            self.template,
            self.entry,
            self.entry_option,
            self.second,
            self.second_option,
        ) = _graph(f"tale-api-{self._testMethodName}")
        self.instance = staff_assign_mission(self.template, self.character)
        # Advance to terminal so the run is COMPLETE.
        resolve_beat_option(self.instance, self.character, option_id=self.entry_option.pk)
        resolve_beat_option(self.instance, self.character, option_id=self.second_option.pk)
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        patcher = mock.patch("world.missions.views._puppet_character", return_value=self.character)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_post_tale_on_complete_run(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/tale/",
            {"text": "A glorious victory."},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["tale"], "A glorious victory.")

    def test_post_tale_active_run_is_400(self) -> None:
        instance = staff_assign_mission(self.template, self.character)
        res = self.client.post(
            f"/api/missions/journal/{instance.pk}/tale/",
            {"text": "text"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_non_participant_gets_404(self) -> None:
        outsider = _pc(self.room)
        with mock.patch("world.missions.views._puppet_character", return_value=outsider):
            res = self.client.post(
                f"/api/missions/journal/{self.instance.pk}/tale/",
                {"text": "text"},
                format="json",
            )
        self.assertEqual(res.status_code, 404)

    def test_journal_includes_tale_after_save(self) -> None:
        self.client.post(
            f"/api/missions/journal/{self.instance.pk}/tale/",
            {"text": "My epic tale."},
            format="json",
        )
        res = self.client.get("/api/missions/journal/")
        results = res.json()["results"]
        entry = next(e for e in results if e["instance_id"] == self.instance.pk)
        self.assertEqual(entry["tale"], "My epic tale.")
        self.assertFalse(entry["can_tell_tale"])

    def test_journal_shows_can_tell_tale_on_terminal_run(self) -> None:
        res = self.client.get("/api/missions/journal/")
        results = res.json()["results"]
        entry = next(e for e in results if e["instance_id"] == self.instance.pk)
        self.assertIsNone(entry["tale"])
        self.assertTrue(entry["can_tell_tale"])


class InstancedPlayTests(TestCase):
    """#886 — option-driven instanced rooms (spawn, gate, reuse, teardown)."""

    def setUp(self) -> None:
        self.start_room, self.start_profile = _room("Inn Hallway")

    def _spawning_run(self):
        template, entry, entry_option, second, second_option = _graph("instanced")
        entry_option.spawns_instance = True
        entry_option.instance_name = "Darkened Interior"
        entry_option.instance_description = "PLACEHOLDER a ransacked parlor"
        entry_option.save()
        second.location_mode = NodeLocationMode.INSTANCE
        second.save(update_fields=["location_mode"])
        character = _pc(self.start_room)
        instance = staff_assign_mission(template, character)
        participant = instance.participants.get(character=character)
        return instance, entry, entry_option, second, second_option, character, participant

    def test_resolving_spawning_option_moves_actor_into_instance(self) -> None:
        from world.instances.models import InstancedRoom
        from world.missions.services.resolution import resolve_option

        instance, entry, entry_option, _s, _so, character, participant = self._spawning_run()

        resolve_option(instance, entry, entry_option, participant)

        instance.refresh_from_db()
        assert instance.spawned_room_id is not None
        spawned = instance.spawned_room.objectdb
        assert spawned.db_key == "Darkened Interior"
        character.refresh_from_db()
        assert character.location == spawned
        assert InstancedRoom.objects.filter(room=spawned).exists()

    def test_instance_mode_gates_to_spawned_room(self) -> None:
        from world.missions.services.resolution import resolve_option

        instance, entry, entry_option, second, _so, _character, participant = self._spawning_run()

        # Before the spawn, INSTANCE-mode options are nowhere.
        assert build_option_list(instance, second, participant) == []

        resolve_option(instance, entry, entry_option, participant)
        instance.refresh_from_db()

        # Inside the spawned room, the follow-up node is live.
        live = build_option_list(instance, second, participant)
        assert len(live) == 1

    def test_spawn_is_idempotent_per_run(self) -> None:
        from world.missions.services.resolution import resolve_option

        instance, entry, entry_option, _s, _so, character, participant = self._spawning_run()
        resolve_option(instance, entry, entry_option, participant)
        instance.refresh_from_db()
        first_room_id = instance.spawned_room_id

        # Walk out and resolve the doorway again — same interior.
        character.db_location = self.start_room
        character.save(update_fields=["db_location"])
        instance.current_node = entry
        instance.save(update_fields=["current_node"])
        resolve_option(instance, entry, entry_option, participant)
        instance.refresh_from_db()
        assert instance.spawned_room_id == first_room_id
        character.refresh_from_db()
        assert character.location == instance.spawned_room.objectdb

    def test_terminal_completion_tears_down_instance(self) -> None:
        from world.instances.constants import InstanceStatus
        from world.instances.models import InstancedRoom
        from world.missions.services.resolution import resolve_option

        instance, entry, entry_option, second, second_option, _character, participant = (
            self._spawning_run()
        )
        resolve_option(instance, entry, entry_option, participant)
        instance.refresh_from_db()
        spawned = instance.spawned_room.objectdb

        resolve_option(instance, second, second_option, participant)

        record = InstancedRoom.objects.filter(room_id=spawned.pk).first()
        # Completed (occupants relocated) — or already deleted as ephemeral.
        assert record is None or record.status == InstanceStatus.COMPLETED


class MaybePauseMissionForDisconnectTests(TestCase):
    def test_pauses_active_instance(self) -> None:
        from world.missions.services.play import maybe_pause_mission_for_disconnect

        instance = MissionInstanceFactory()
        sheet = CharacterSheetFactory()
        MissionParticipantFactory(instance=instance, character=sheet.character)

        maybe_pause_mission_for_disconnect(sheet)

        instance.refresh_from_db()
        assert instance.is_paused is True

    def test_no_active_participation_is_a_noop(self) -> None:
        from world.missions.services.play import maybe_pause_mission_for_disconnect

        sheet = CharacterSheetFactory()
        maybe_pause_mission_for_disconnect(sheet)  # No MissionParticipant row — must not raise.

    def test_non_active_instance_is_not_paused(self) -> None:
        from world.missions.constants import MissionStatus
        from world.missions.services.play import maybe_pause_mission_for_disconnect

        instance = MissionInstanceFactory(status=MissionStatus.COMPLETE)
        sheet = CharacterSheetFactory()
        MissionParticipantFactory(instance=instance, character=sheet.character)

        maybe_pause_mission_for_disconnect(sheet)

        instance.refresh_from_db()
        assert instance.is_paused is False

    def test_pauses_all_concurrent_active_instances(self) -> None:
        """Regression (#1899 spec review): a naive .first() would silently
        leave a second concurrently-active mission unpaused."""
        from world.missions.services.play import maybe_pause_mission_for_disconnect

        sheet = CharacterSheetFactory()
        instance_a = MissionInstanceFactory()
        instance_b = MissionInstanceFactory()
        MissionParticipantFactory(instance=instance_a, character=sheet.character)
        MissionParticipantFactory(instance=instance_b, character=sheet.character)

        maybe_pause_mission_for_disconnect(sheet)

        instance_a.refresh_from_db()
        instance_b.refresh_from_db()
        assert instance_a.is_paused is True
        assert instance_b.is_paused is True
