from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneUnseenObserver
from world.scenes.services import (
    clear_unseen_observer,
    has_unseen_observers,
    register_unseen_observer,
)


class _FakeSession:
    """Minimal stand-in for an Evennia Session — Object.msg relays to
    ``self.sessions.all()`` and calls ``session.data_out(**kwargs)`` on each."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def data_out(self, **kwargs) -> None:
        self.sent.append(kwargs)


class UnseenObserverTests(TestCase):
    def setUp(self) -> None:
        self.scene = SceneFactory()
        self.observer = CharacterSheetFactory()

    def test_register_creates_row_and_broadcasts(self) -> None:
        with patch("world.scenes.services._broadcast_unseen_observer_state") as broadcast:
            register_unseen_observer(self.scene, self.observer, "concealment")

        self.assertTrue(
            SceneUnseenObserver.objects.filter(scene=self.scene, observer=self.observer).exists()
        )
        broadcast.assert_called_once_with(self.scene)
        self.assertTrue(has_unseen_observers(self.scene))

    def test_register_is_idempotent_and_does_not_rebroadcast(self) -> None:
        register_unseen_observer(self.scene, self.observer, "concealment")
        with patch("world.scenes.services._broadcast_unseen_observer_state") as broadcast:
            register_unseen_observer(self.scene, self.observer, "concealment")
        broadcast.assert_not_called()

    def test_clear_removes_row_and_broadcasts(self) -> None:
        register_unseen_observer(self.scene, self.observer, "concealment")
        with patch("world.scenes.services._broadcast_unseen_observer_state") as broadcast:
            clear_unseen_observer(self.scene, self.observer)
        broadcast.assert_called_once_with(self.scene)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_banner_stays_up_until_all_observers_clear(self) -> None:
        other_observer = CharacterSheetFactory()
        register_unseen_observer(self.scene, self.observer, "concealment")
        register_unseen_observer(self.scene, other_observer, "concealment")

        clear_unseen_observer(self.scene, self.observer)

        self.assertTrue(has_unseen_observers(self.scene))

    def test_broadcast_routes_through_room_state_channel(self) -> None:
        """The OOC state now rides the existing, already-wired room_state channel
        instead of a bespoke unseen_observer payload key (#1225 review fix) — a real
        frontend consumer, and fresh on every login/move, not just at the moment of
        transition."""
        room = create_object("typeclasses.rooms.Room", key="UnseenObserverBroadcastRoom")
        self.scene.location = room
        self.scene.save()

        with patch.object(room, "_broadcast_room_state") as broadcast:
            register_unseen_observer(self.scene, self.observer, "concealment")

        broadcast.assert_called_once_with()

    def test_broadcast_payload_carries_no_observer_identity(self) -> None:
        # Scene.location is a real FK to ObjectDB, so the delivery loop needs a real
        # room with a real puppeted character in it rather than a duck-typed fake.
        # Delivery now goes through Character.msg -> session.data_out (room_state
        # rides real sessions, not account.msg directly — #1225 review fix), so a
        # fake session stands in for a live connection.
        room = create_object("typeclasses.rooms.Room", key="UnseenObserverTestRoom", nohome=True)
        self.scene.location = room
        self.scene.save()
        room.active_scene = self.scene

        witness = CharacterSheetFactory()
        witness.character.db_account = AccountFactory()
        witness.character.save()
        witness.character.location = room

        # send_room_state's own guard (self.has_account) reads sessions.count(), not
        # db_account — fake both count() and all() so the character reads as online.
        fake_session = _FakeSession()
        witness.character.sessions.all = lambda: [fake_session]
        witness.character.sessions.count = lambda: 1

        register_unseen_observer(self.scene, self.observer, "concealment")

        self.assertTrue(fake_session.sent)
        room_state_calls = [kwargs for kwargs in fake_session.sent if "room_state" in kwargs]
        self.assertTrue(room_state_calls)
        for kwargs in fake_session.sent:
            # The observer never appears by dbref/name — this real room_state payload
            # is large and legitimately contains small unrelated integers (scene id,
            # etc.), so a bare numeric-pk substring check would false-positive; the
            # dbref format ("#N") and the observer's character name are the actual
            # shapes identity would leak through.
            self.assertNotIn(self.observer.character.dbref, str(kwargs))
            self.assertNotIn(self.observer.character.key, str(kwargs))
        # And the flag genuinely reflects the new grant, via the real payload shape.
        room_state_payload = room_state_calls[0]["room_state"][1]
        self.assertTrue(room_state_payload["scene"]["has_unseen_observer"])
