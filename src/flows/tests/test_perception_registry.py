"""Tests for the broadcast-exclusion registry — Axis 1 of the perception taxonomy (#2997)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.scene_data_manager import SceneDataManager
from flows.service_functions import perception_registry
from flows.service_functions.communication import _dreamside_occupants, message_location


class ResolveBroadcastExclusionsTests(TestCase):
    def setUp(self):
        # Isolate the module-level registry per test — production code only
        # ever appends at import time, but a test that registers a fake
        # resolver must not leak it into other tests.
        self._original_resolvers = list(perception_registry._RESOLVERS)
        self.addCleanup(self._restore_resolvers)

    def _restore_resolvers(self):
        perception_registry._RESOLVERS[:] = self._original_resolvers

    def test_empty_registry_returns_empty_set(self):
        """No registered resolvers -> empty set, byte-identical to the old ``or None`` path."""
        perception_registry._RESOLVERS.clear()
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

        assert perception_registry.resolve_broadcast_exclusions(room) == set()

    def test_dreamside_is_registered_by_default(self):
        """``_dreamside_occupants`` self-registers at import time (communication.py)."""
        assert _dreamside_occupants in perception_registry._RESOLVERS

    def test_second_resolver_composes_with_dreamside(self):
        """A second registered resolver's exclusions UNION with dreamside's, not replace them."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        haunted_watcher = ObjectDBFactory(
            db_typeclass_path="typeclasses.characters.Character", location=room
        )

        def fake_resolver(location):
            return [haunted_watcher] if location == room else []

        perception_registry.register_broadcast_exclusion(fake_resolver)

        excluded = perception_registry.resolve_broadcast_exclusions(room)
        assert haunted_watcher in excluded

    def test_message_location_calls_registry_not_dreamside_directly(self):
        """``message_location`` routes through the registry union, not ``_dreamside_occupants``."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        caller = ObjectDBFactory(
            db_typeclass_path="typeclasses.characters.Character", location=room
        )

        sdm = SceneDataManager()
        caller_state = sdm.initialize_state_for_object(caller)
        room_state = sdm.initialize_state_for_object(room)

        with (
            patch.object(room, "msg_contents") as mock_msg_contents,
            patch(
                "flows.service_functions.communication.resolve_broadcast_exclusions"
            ) as mock_resolve,
        ):
            mock_resolve.return_value = {caller}
            message_location(caller_state, "waves.", location_state=room_state)

        mock_resolve.assert_called_once_with(room)
        assert mock_msg_contents.call_args.kwargs["exclude"] == {caller}
