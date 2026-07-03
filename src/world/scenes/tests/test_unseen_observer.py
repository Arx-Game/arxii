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

    def test_broadcast_payload_carries_no_observer_identity(self) -> None:
        # Scene.location is a real FK to ObjectDB, so the delivery loop needs a real
        # room with a real puppeted character in it rather than a duck-typed fake.
        room = create_object("typeclasses.rooms.Room", key="UnseenObserverTestRoom", nohome=True)
        self.scene.location = room
        self.scene.save()

        witness = CharacterSheetFactory()
        witness.character.db_account = AccountFactory()
        witness.character.save()
        witness.character.location = room

        sent_payloads = []
        witness.character.account.msg = lambda **kwargs: sent_payloads.append(kwargs)

        register_unseen_observer(self.scene, self.observer, "concealment")

        self.assertTrue(sent_payloads)
        for payload in sent_payloads:
            self.assertNotIn(str(self.observer.pk), str(payload))
            self.assertNotIn(self.observer.character.key, str(payload))
