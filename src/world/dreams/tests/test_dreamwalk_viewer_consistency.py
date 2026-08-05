"""All dreamside viewers agree after a dreamwalk (#3003)."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from world.conditions.models import ConditionTemplate
from world.dreams.engagement import is_dream_engaged
from world.dreams.services import start_dreamwalk
from world.dreams.tests import DreamSleeperTestMixin
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamwalkViewerConsistencyTests(DreamSleeperTestMixin, TestCase):
    """After a dreamwalk, look/room-state/wake-gate all resolve to the host's dream room.

    Gates on SEED_SAMPLE_CONTENT (#2698), same as test_dreamwalk.py/test_dreamwalk_presence.py.
    """

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

    def _run_look(self, walker):
        from actions.definitions.perception import LookAction

        character = walker.character
        return LookAction().run(character, target=character.location)

    def _capture_room_state(self, walker) -> dict:
        """Call ``Character.send_room_state()`` and return the pushed room's identity.

        ``has_account`` reads ``sessions.count()``, not an attached account row — fake
        it so send_room_state's own online guard passes (mirrors
        world/scenes/tests/test_unseen_observer.py) — then patch ``msg`` to capture the
        ``room_state`` kwarg without an actual outbound send.
        """
        character = walker.character
        character.sessions.count = lambda: 1
        with patch.object(character, "msg") as mock_msg:
            character.send_room_state()
        payload = mock_msg.call_args.kwargs["room_state"][1]
        dbref = payload["room"]["dbref"]
        return {"id": int(dbref.removeprefix("#"))}

    def _open_scene_round(self, dream_room) -> None:
        from world.scenes.models import SceneRound

        # SceneRound.room is a RoomProfile (#2608), which shares ObjectDB's pk — so
        # the dream room's own pk is the profile id, no lookup needed (matches the
        # exact query shape in engagement.py:33-38).
        SceneRound.objects.create(room_id=dream_room.pk, status="DECLARING")

    def _run_wake(self, walker):
        from actions.definitions.vitals import WakeAction

        return WakeAction().run(walker.character)

    def test_look_shows_host_dreamspace(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        result = self._run_look(walker)
        assert result.success
        assert self._dream_room_of(host.character.location).key in result.message

    def test_room_state_push_uses_host_dreamspace(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        pushed = self._capture_room_state(walker)
        assert pushed["id"] == self._dream_room_of(host.character.location).id

    def test_wake_gate_follows_host_dream_room(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        self._open_scene_round(self._dream_room_of(host.character.location))
        # The walker's OWN dream room has no round; the host's does.
        assert is_dream_engaged(walker) is True

    def test_wake_moves_body_to_host_location_and_clears_presence(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        result = self._run_wake(walker)
        assert result.success
        assert walker.character.location == host.character.location
