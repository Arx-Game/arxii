"""Current room scope for typed object, exit and place reads."""

from dataclasses import replace
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.objects.models import ObjectDB

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
    StaffCharacterFactory,
)
from flows.object_states.base_state import BaseState, project_display_name, select_display_name
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.serializers.room_state import (
    ObjectStateSerializer,
    RoomStatePayloadSerializer,
    exit_hidden_from_viewer,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.gm.factories import GMProfileFactory
from world.instances.models import InstancedRoom
from world.items.factories import ItemInstanceFactory
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
from world.scenes.constants import PlaceStatus
from world.scenes.factories import PlaceFactory, PlacePresenceFactory
from world.scenes.models import Scene
from world.scenes.place_models import Place, PlacePresence
from world.scenes.place_services import active_places
from world.scenes.place_views import PlaceViewSet


def initialize_with_place_write(state, pkg):
    """Prove an attached initialize hook can perform a real database write."""
    Place.objects.create(name=f"initialize-write-{pkg.pk}")


class ObjectPlaceExitTargetTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.profile = RoomProfileFactory(objectdb=self.room, published_at=timezone.now())
        self.remote_profile = RoomProfileFactory(
            objectdb=self.remote, published_at=timezone.now(),
        )
        self.actor = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.actor)
        self.actor.db_account = AccountFactory(is_staff=False)
        self.actor.save(update_fields=["db_account"])
        self.other = CharacterFactory(location=self.room)
        self.other_sheet = CharacterSheetFactory(character=self.other)
        self.obj = ObjectDBFactory(location=self.room)
        self.exit = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room, destination=self.remote,
        )
        self.place = PlaceFactory(room=self.profile, name="The hearth")

    def _request(self, kind, target):
        return MenuTargetRequest(kind, target.pk)

    def _resolve(self, kind, target, *, actor=None, **context):
        return resolve_menu_target(
            self.actor if actor is None else actor,
            replace(self._request(kind, target), **context),
        )

    def _move(self, obj, location):
        obj.location = location
        assert ObjectDB.objects.filter(pk=obj.pk, db_location=location).exists()

    def _conceal(self, obj):
        return ConditionInstanceFactory(
            target=obj,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True),
            ),
        )

    def _payload_hidden(self, actor, *, instances):
        context = SceneDataManager()
        exit_state = self.exit.get_object_state(context)
        caller_state = actor.get_object_state(context)
        return RoomStatePayloadSerializer()._exit_hidden_from_looker(
            exit_state, caller_state, instances,
        )

    def test_plain_object_and_actual_item_relation(self):
        result = self._resolve(MenuTargetKind.OBJECTS, self.obj)
        assert result is not None
        assert result.request == self._request(MenuTargetKind.OBJECTS, self.obj)
        assert result.game_object == self.obj
        assert result.item is None
        assert result.place is None
        assert result.label == self.obj.key
        # Force a different ItemInstance PK and visible name from ObjectDB.
        item = ItemInstanceFactory(
            pk=self.obj.pk + 100000, game_object=self.obj, custom_name="A silver cup",
        )
        assert item.pk != self.obj.pk
        result = self._resolve(MenuTargetKind.OBJECTS, self.obj)
        assert result is not None
        assert result.item == item
        assert item.display_name != self.obj.key
        assert result.label == item.display_name
        assert result.game_object == self.obj
        assert result.request.target_id == self.obj.pk
        assert self._resolve(MenuTargetKind.OBJECTS, item) is None
        assert self._resolve(MenuTargetKind.ITEMS, item).item == item
        item.contained_in = ItemInstanceFactory(game_object=None)
        item.save(update_fields=["contained_in"])
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj) is None
        item.contained_in = None
        item.destroyed_at = timezone.now()
        item.save(update_fields=["contained_in", "destroyed_at"])
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj) is None

    def test_object_scope_and_kind_are_not_guessed(self):
        for target in (self.actor, self.other, self.room, self.exit):
            with self.subTest(target=target):
                assert self._resolve(MenuTargetKind.OBJECTS, target) is None
        for location in (self.actor, self.other, self.remote, self.exit, None):
            with self.subTest(location=location):
                self._move(self.obj, location)
                assert self._resolve(MenuTargetKind.OBJECTS, self.obj) is None
        self._move(self.obj, self.room)
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj) is not None

    def test_object_and_exit_concealment_is_current_and_per_observer(self):
        for kind, target in (
            (MenuTargetKind.OBJECTS, self.obj), (MenuTargetKind.EXITS, self.exit),
        ):
            with self.subTest(kind=kind):
                assert self._resolve(kind, target) is not None
                condition = self._conceal(target)
                assert self._resolve(kind, target) is None
                absent = replace(self._request(kind, target), target_id=999999999)
                assert resolve_menu_target(self.actor, absent) is None
                register_detection(self.other_sheet, target)
                assert self._resolve(kind, target) is None
                register_detection(self.sheet, target)
                assert self._resolve(kind, target) is not None
                condition.detected_by.remove(self.sheet)
                assert self._resolve(kind, target) is None

    def test_exit_scope_null_destination_and_lock_are_not_traversal_checks(self):
        assert self._resolve(MenuTargetKind.EXITS, self.obj) is None
        assert self._resolve(MenuTargetKind.EXITS, self.actor) is None
        self.exit.db.locked = True
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is not None
        self.exit.destination = None
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is not None
        assert self._resolve(MenuTargetKind.OBJECTS, self.exit) is None
        assert self._payload_hidden(self.actor, instances={}) is False
        for location in (self.actor, self.other, self.remote, None):
            self._move(self.exit, location)
            assert self._resolve(MenuTargetKind.EXITS, self.exit) is None

    def test_exit_publication_matches_payload_and_rechecks(self):
        self.remote_profile.published_at = None
        self.remote_profile.save(update_fields=["published_at"])
        assert self._payload_hidden(self.actor, instances={}) is True
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is None
        staff = StaffCharacterFactory(location=self.room)
        CharacterSheetFactory(character=staff)
        assert staff.is_story_runner is True
        assert self._payload_hidden(staff, instances={}) is False
        assert self._resolve(MenuTargetKind.EXITS, self.exit, actor=staff) is not None
        self.remote_profile.published_at = timezone.now()
        self.remote_profile.save(update_fields=["published_at"])
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is not None
        self.remote_profile.published_at = None
        self.remote_profile.save(update_fields=["published_at"])
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is None

    def test_instance_owner_participant_gm_and_staff_match_payload(self):
        gm = GMProfileFactory()
        instance = InstancedRoom.objects.create(
            room=self.remote_profile, owner=self.other_sheet, gm_owner=gm,
        )
        instances = {self.remote.pk: instance}
        staff = StaffCharacterFactory(location=self.room)
        CharacterSheetFactory(character=staff)
        gm_character = CharacterFactory(location=self.room)
        CharacterSheetFactory(character=gm_character)
        gm_character.db_account = gm.account
        gm_character.save(update_fields=["db_account"])
        for actor, visible in (
            (self.actor, False), (self.other, True),
            (gm_character, True), (staff, False),
        ):
            with self.subTest(actor=actor):
                assert self._payload_hidden(actor, instances=instances) is (not visible)
                result = self._resolve(MenuTargetKind.EXITS, self.exit, actor=actor)
                assert (result is not None) is visible
        mission = MissionInstanceFactory(spawned_room_id=self.remote.pk)
        participant = MissionParticipantFactory(instance=mission, character=self.sheet)
        assert self._payload_hidden(self.actor, instances=instances) is False
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is not None
        participant.delete()
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is None
        instance.owner = self.sheet
        instance.save(update_fields=["owner"])
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is not None
        # Instance admission does not override the separate publication gate.
        self.remote_profile.published_at = None
        self.remote_profile.save(update_fields=["published_at"])
        assert self._payload_hidden(self.actor, instances=instances) is True
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is None

    def test_places_share_active_read_selection_without_scene_or_presence(self):
        hidden = PlaceFactory(room=self.profile, status=PlaceStatus.HIDDEN)
        removed = PlaceFactory(room=self.profile, status=PlaceStatus.REMOVED)
        remote = PlaceFactory(room=self.remote_profile)
        detached = PlaceFactory(room=None)
        assert list(active_places(room_id=self.profile.pk)) == [self.place]
        assert set(PlaceViewSet().get_queryset()) == set(active_places())
        scenes = Scene.objects.count()
        presences = PlacePresence.objects.count()
        result = self._resolve(MenuTargetKind.PLACES, self.place)
        assert result is not None
        assert result.place == self.place
        assert result.item is None
        assert result.game_object is None
        assert result.label == self.place.name
        for target in (hidden, removed, remote, detached):
            assert self._resolve(MenuTargetKind.PLACES, target) is None
        assert Scene.objects.count() == scenes
        assert PlacePresence.objects.count() == presences
        presence = PlacePresenceFactory(place=self.place)
        assert self._resolve(MenuTargetKind.PLACES, self.place) is not None
        presence.delete()
        assert self._resolve(MenuTargetKind.PLACES, self.place) is not None

    def test_place_changes_and_actor_changes_are_current(self):
        for status in (PlaceStatus.HIDDEN, PlaceStatus.REMOVED):
            self.place.status = status
            self.place.save(update_fields=["status"])
            assert self._resolve(MenuTargetKind.PLACES, self.place) is None
        self.place.status = PlaceStatus.ACTIVE
        self.place.room = self.remote_profile
        self.place.save(update_fields=["status", "room"])
        assert self._resolve(MenuTargetKind.PLACES, self.place) is None
        self.place.room = self.profile
        self.place.save(update_fields=["room"])
        for location in (self.remote, self.obj, None):
            self._move(self.actor, location)
            for kind, target in (
                (MenuTargetKind.OBJECTS, self.obj),
                (MenuTargetKind.EXITS, self.exit),
                (MenuTargetKind.PLACES, self.place),
            ):
                assert self._resolve(kind, target) is None
        self._move(self.actor, self.room)
        assert self._resolve(MenuTargetKind.PLACES, self.place) is not None

    def test_place_and_object_id_collision_does_not_change_domain(self):
        # Same integer intentionally names distinct rows with different scopes.
        collision = Place.objects.filter(pk=self.obj.pk).first()
        if collision is None:
            collision = PlaceFactory(pk=self.obj.pk, room=self.remote_profile)
        else:
            collision.room = self.remote_profile
            collision.save(update_fields=["room"])
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).game_object == self.obj
        assert self._resolve(MenuTargetKind.PLACES, collision) is None
        collision.room = self.profile
        collision.save(update_fields=["room"])
        result = self._resolve(MenuTargetKind.PLACES, collision)
        assert result.place == collision
        assert result.game_object is None
        assert result.item is None
        assert self._resolve(MenuTargetKind.EXITS, collision) is None

    def test_invalid_and_inapplicable_context_is_neutral(self):
        for kind, target in (
            (MenuTargetKind.OBJECTS, self.obj),
            (MenuTargetKind.EXITS, self.exit),
            (MenuTargetKind.PLACES, self.place),
        ):
            request = self._request(kind, target)
            for value in (True, "1", 0, -1, None, 999999999):
                with self.subTest(kind=kind, value=value):
                    assert resolve_menu_target(
                        self.actor, replace(request, target_id=value),
                    ) is None
            for context in (
                {"owner_persona_id": self.sheet.primary_persona.pk},
                {"container_item_id": ItemInstanceFactory(game_object=None).pk},
                {"owner_persona_id": True},
                {"container_item_id": "1"},
                {"owner_persona_id": 0, "container_item_id": -1},
            ):
                assert resolve_menu_target(self.actor, replace(request, **context)) is None
        assert resolve_menu_target(
            self.actor, MenuTargetRequest("objects", self.obj.pk),
        ) is None
        assert resolve_menu_target(
            self.actor, MenuTargetRequest("unknown", self.obj.pk),
        ) is None

    def test_labels_preserve_existing_viewer_specific_payload_names(self):
        context = SceneDataManager()
        self.room.scene_data = context
        actor_state = context.initialize_state_for_object(self.actor)
        other_state = context.initialize_state_for_object(self.other)
        for kind, target in (
            (MenuTargetKind.OBJECTS, self.obj), (MenuTargetKind.EXITS, self.exit),
        ):
            state = context.initialize_state_for_object(target)
            state.name = "A carved arch"
            state.fake_name = "A shadowed arch"
            state.real_name_viewers.add(self.actor.pk)
            state.name_prefix = "old "
            state.name_suffix = " (weathered)"
            state.name_prefix_map[self.actor.pk] = "familiar "
            state.name_suffix_map[self.other.pk] = " (unknown)"
            for actor, looker, expected in (
                (self.actor, actor_state, "familiar A carved arch (weathered)"),
                (self.other, other_state, "old A shadowed arch (unknown)"),
            ):
                with self.subTest(kind=kind, actor=actor.pk):
                    payload = ObjectStateSerializer(
                        context={"looker": looker},
                    ).to_representation(state)
                    assert payload["name"] == expected
                    with patch.object(
                        SceneDataManager, "get_state_by_pk",
                        side_effect=AssertionError("label must not lazily initialize"),
                    ):
                        assert self._resolve(kind, target, actor=actor).label == expected
            # A cached target does not require a cached viewer to honor viewer maps.
            context.states.pop(self.actor.pk)
            assert self._resolve(kind, target).label == "familiar A carved arch (weathered)"
            context.states[self.actor.pk] = actor_state
            state.name_prefix_map[self.actor.pk] = "new "
            assert self._resolve(kind, target).label == "new A carved arch (weathered)"

    def test_shared_projection_preserves_base_state_edge_semantics(self):
        context = SceneDataManager()
        self.room.scene_data = context
        state = context.initialize_state_for_object(self.obj)
        viewer = context.initialize_state_for_object(self.actor)
        # Exact expected outputs lock down old policy, not a second implementation.
        cases = (
            ("Real", "Fake", None, (), "Fake"),
            ("Real", "Fake", self.obj.pk, (), "Real"),
            ("Real", "Fake", self.actor.pk, (), "Fake"),
            ("Real", "Fake", self.actor.pk, [self.actor.pk], "Real"),
            ("Real", "", self.actor.pk, (), "Real"),
            ("", None, self.actor.pk, (), ""),
            (None, None, self.actor.pk, (), None),
            (None, "Fake", None, (), "Fake"),
        )
        for base, fake, viewer_id, viewers, selected in cases:
            with self.subTest(base=base, fake=fake, viewer_id=viewer_id):
                looker = None if viewer_id is None else (
                    state if viewer_id == self.obj.pk else viewer
                )
                state.name = base
                state.fake_name = fake
                state.real_name_viewers = viewers
                state.name_prefix = "["
                state.name_suffix = "]"
                state.name_prefix_map = {self.actor.pk: ""}
                state.name_suffix_map = {self.actor.pk: "!"}
                expected = f"{selected}!" if viewer_id == self.actor.pk else f"[{selected}]"
                assert select_display_name(
                    base, object_id=self.obj.pk, viewer_id=viewer_id,
                    fake_name=fake, real_name_viewers=viewers,
                ) == selected
                assert state._base_display_name(looker) == selected
                with patch(
                    "flows.object_states.base_state.project_display_name",
                    wraps=project_display_name,
                ) as projection:
                    assert state.get_display_name(looker) == expected
                    projection.assert_called_once()
                assert project_display_name(
                    base, object_id=self.obj.pk, viewer_id=viewer_id,
                    fake_name=fake, real_name_viewers=viewers,
                    name_prefix="[", name_suffix="]",
                    name_prefix_map={self.actor.pk: ""},
                    name_suffix_map={self.actor.pk: "!"},
                ) == expected
                # Resolver and state share the projection; no viewer state load.
                if viewer_id == self.actor.pk:
                    with patch.object(
                        SceneDataManager, "get_state_by_pk",
                        side_effect=AssertionError("projection must not load state"),
                    ), patch(
                        "actions.target_resolution.project_display_name",
                        wraps=project_display_name,
                    ) as projection:
                        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == expected
                        projection.assert_called_once()

        # Subclasses still select their own bare identity before decoration.
        class IdentityState(BaseState):
            def _base_display_name(self, looker_state):
                return "Presented identity"

        identity = IdentityState(self.obj, context)
        identity.fake_name = "Must not override subclass identity"
        identity.name_prefix = "<"
        identity.name_suffix = ">"
        assert identity.get_display_name(viewer) == "<Presented identity>"

    def test_flow_local_viewer_removal_after_initialization_is_immediate(self):
        context = SceneDataManager()
        self.room.scene_data = context
        actor_state = context.initialize_state_for_object(self.actor)
        for kind, target in (
            (MenuTargetKind.OBJECTS, self.obj), (MenuTargetKind.EXITS, self.exit),
        ):
            state = context.initialize_state_for_object(target)
            state.name = "A carved arch"
            state.fake_name = "A shadowed arch"
            # Use the actual flow writers, which replace the set with a list.
            context.add_to_context_list(target.pk, "real_name_viewers", self.actor.pk)
            assert self._resolve(kind, target).label == "A carved arch"
            context.remove_from_context_list(target.pk, "real_name_viewers", self.actor.pk)
            assert self.actor.pk not in state.real_name_viewers
            with patch.object(
                SceneDataManager, "get_state_by_pk",
                side_effect=AssertionError("read must not load state"),
            ):
                assert self._resolve(kind, target).label == "A shadowed arch"
                assert ObjectStateSerializer(
                    context={"looker": actor_state},
                ).to_representation(state)["name"] == "A shadowed arch"
        # Even an initialized character with naming exceptions is never eligible.
        other_state = context.initialize_state_for_object(self.other)
        other_state.name = "Protected character name"
        other_state.real_name_viewers.add(self.actor.pk)
        assert self._resolve(MenuTargetKind.OBJECTS, self.other) is None
        assert self._resolve(MenuTargetKind.EXITS, self.other) is None

    def test_item_base_is_consistent_cold_warm_and_after_rename(self):
        self.room.__dict__.pop("scene_data", None)
        item = ItemInstanceFactory(game_object=self.obj, custom_name="A silver cup")
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "A silver cup"
        context = SceneDataManager()
        self.room.scene_data = context
        state = context.initialize_state_for_object(self.obj)
        state.name = "Different flow-local ObjectDB name"
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "A silver cup"
        item.custom_name = "A golden cup"
        item.save(update_fields=["custom_name"])
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "A golden cup"
        state.name_prefix_map[self.actor.pk] = "familiar "
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "familiar A golden cup"
        state.fake_name = "A shadowed cup"
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "familiar A shadowed cup"
        context.add_to_context_list(self.obj.pk, "real_name_viewers", self.actor.pk)
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "familiar A golden cup"
        context.remove_from_context_list(self.obj.pk, "real_name_viewers", self.actor.pk)
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "familiar A shadowed cup"
        context.states.pop(self.obj.pk)
        assert self._resolve(MenuTargetKind.OBJECTS, self.obj).label == "A golden cup"

    def test_initialize_packages_are_real_but_never_run_during_resolution(self):
        definition = BehaviorPackageDefinition.objects.create(
            name="menu-read-write-control",
            service_function_path=f"{__name__}.initialize_with_place_write",
        )
        targets = (self.room, self.actor, self.obj, self.exit, self.remote)
        packages = [
            BehaviorPackageInstance.objects.create(
                definition=definition, obj=target, hook="initialize_state",
            )
            for target in targets
        ]
        # Positive control: the real loader imports this function and writes a row.
        for target, pkg in zip(targets, packages, strict=True):
            context = SceneDataManager()
            context.initialize_state_for_object(target)
            marker = Place.objects.get(name=f"initialize-write-{pkg.pk}")
            marker.delete()
        # The import callable is cached; clear it so the spy observes real dispatch.
        definition.__dict__.pop("service_function", None)
        self.room.__dict__.pop("scene_data", None)
        item = ItemInstanceFactory(game_object=self.obj, custom_name="A silver cup")
        with patch(
            f"{__name__}.initialize_with_place_write", wraps=initialize_with_place_write,
        ) as hook:
            for cached in (False, True):
                if cached:
                    # Existing presentation state was initialized before this read.
                    context = SceneDataManager()
                    self.room.scene_data = context
                    context.states[self.obj.pk] = self.obj.get_object_state(context)
                    context.states[self.obj.pk].name = "A public room fixture"
                    context.states[self.exit.pk] = self.exit.get_object_state(context)
                scenes = Scene.objects.count()
                presences = PlacePresence.objects.count()
                with patch.object(
                    SceneDataManager, "initialize_state_for_object",
                    side_effect=AssertionError("menu read must not initialize state"),
                ), CaptureQueriesContext(connection) as queries:
                    obj_result = self._resolve(MenuTargetKind.OBJECTS, self.obj)
                    # Cached state.name never supplants the attached item's public base.
                    assert obj_result.label == item.display_name
                    assert self._resolve(MenuTargetKind.EXITS, self.exit).label == self.exit.key
                    assert self._resolve(MenuTargetKind.PLACES, self.place).label == self.place.name
                    if cached:
                        context.states.pop(self.obj.pk)
                        missing_state_result = self._resolve(MenuTargetKind.OBJECTS, self.obj)
                        assert missing_state_result.label == item.display_name
                        assert set(context.states) == {self.exit.pk}
                hook.assert_not_called()
                writes = [
                    query["sql"] for query in queries.captured_queries
                    if query["sql"].lstrip().upper().startswith(
                        ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"),
                    )
                ]
                assert writes == []
                assert not Place.objects.filter(name__startswith="initialize-write-").exists()
                assert Scene.objects.count() == scenes
                assert PlacePresence.objects.count() == presences
                if not cached:
                    assert "scene_data" not in self.room.__dict__
                else:
                    assert set(context.states) == {self.exit.pk}

    def test_instance_exit_empty_batch_map_never_falls_back_to_admission(self):
        from behaviors.instance_entrance_package import entrance_refuses, instance_refuses

        instance = InstancedRoom.objects.create(
            room=self.remote_profile, owner=self.other_sheet,
        )
        # Actor is not admitted; published destination isolates the instance policy.
        assert entrance_refuses(self.remote, self.actor) is True
        assert instance_refuses(instance, self.actor) is True
        with patch(
            "behaviors.instance_entrance_package.entrance_refuses", wraps=entrance_refuses,
        ) as single, patch(
            "behaviors.instance_entrance_package.instance_refuses", wraps=instance_refuses,
        ) as batched:
            assert exit_hidden_from_viewer(self.exit, self.actor, {}) is False
            assert self._payload_hidden(self.actor, instances={}) is False
            single.assert_not_called()
            batched.assert_not_called()
            assert exit_hidden_from_viewer(self.exit, self.actor, None) is True
            single.assert_called_once_with(self.remote, self.actor)
            batched.assert_not_called()
            single.reset_mock()
            instances = {self.remote.pk: instance}
            assert exit_hidden_from_viewer(self.exit, self.actor, instances) is True
            batched.assert_called_once_with(instance, self.actor)
            single.assert_not_called()
            batched.reset_mock()
            assert self._payload_hidden(self.actor, instances=instances) is True
            batched.assert_called_once_with(instance, self.actor)
            single.assert_not_called()
        assert self._resolve(MenuTargetKind.EXITS, self.exit) is None

    def test_resolution_performs_no_sql_writes(self):
        with CaptureQueriesContext(connection) as queries:
            for kind, target in (
                (MenuTargetKind.OBJECTS, self.obj),
                (MenuTargetKind.EXITS, self.exit),
                (MenuTargetKind.PLACES, self.place),
            ):
                assert self._resolve(kind, target) is not None
        writes = [
            query["sql"] for query in queries.captured_queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"),
            )
        ]
        assert writes == []
