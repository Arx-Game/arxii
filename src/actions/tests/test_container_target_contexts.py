"""Immediate container targets under current physical and containment scope."""

from dataclasses import replace

from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB

from actions.definitions.perception import LookAtItemAction
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory


class ContainerTargetContextTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.actor = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.actor)
        self.account = AccountFactory(is_staff=False)
        self.actor.db_account = self.account
        self.actor.save()
        self.other = CharacterFactory(location=self.room)
        self.other_sheet = CharacterSheetFactory(character=self.other)
        self.container = self._container(self.actor)
        self.child = self._child(self.container)
        self.request = MenuTargetRequest(
            MenuTargetKind.ITEMS,
            self.child.pk,
            container_item_id=self.container.pk,
        )

    def _container(self, location, *, physical=True):
        return ItemInstanceFactory(
            template=ItemTemplateFactory(is_container=True, supports_open_close=True),
            game_object=ObjectDBFactory(location=location) if physical else None,
            holder_character_sheet=self.sheet,
            is_open=True,
        )

    def _child(self, container, *, physical=True):
        return ItemInstanceFactory(
            game_object=(ObjectDBFactory(location=container.game_object) if physical else None),
            contained_in=container,
            holder_character_sheet=self.sheet,
            custom_name="A copper token",
        )

    def _resolve(self, **changes):
        return resolve_menu_target(self.actor, replace(self.request, **changes))

    def _set_location(self, obj, location):
        # Evennia's property setter saves db_location and updates contents caches.
        obj.location = location
        assert ObjectDB.objects.filter(pk=obj.pk, db_location=location).exists()

    def _conceal(self, obj):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(target=obj, condition=template)

    def test_carried_and_room_contents_resolve_exact_relation(self):
        for location in (self.actor, self.room):
            with self.subTest(location=location):
                self._set_location(self.container.game_object, location)
                result = self._resolve()
                assert result is not None
                assert result.item == self.child
                assert result.game_object == self.child.game_object
                assert result.label == self.child.display_name
                assert result.request == self.request

    def test_unasserted_contained_item_does_not_fall_back(self):
        assert self._resolve(container_item_id=None) is None

    def test_bad_context_and_other_kinds_are_neutral(self):
        for value in (True, "1", 0, -1, 999999999, self.child.pk):
            with self.subTest(value=value):
                assert self._resolve(container_item_id=value) is None
        for kind in (MenuTargetKind.OBJECTS, MenuTargetKind.EXITS, MenuTargetKind.PLACES):
            assert self._resolve(kind=kind) is None
        assert self._resolve(target_id=999999999) is None

    def test_wrong_container_does_not_fall_back_to_readable_item(self):
        wrong = self._container(self.actor)
        assert self._resolve(container_item_id=wrong.pk) is None

    def test_closed_remote_and_private_carried_container_are_neutral(self):
        self.container.is_open = False
        self.container.save(update_fields=["is_open"])
        assert self._resolve() is None
        self.container.is_open = True
        self.container.save(update_fields=["is_open"])
        for location in (self.remote, self.other, None):
            self._set_location(self.container.game_object, location)
            assert self._resolve() is None

    def test_no_room_cannot_authorize_an_unlocated_container(self):
        self._set_location(self.actor, None)
        self._set_location(self.container.game_object, None)
        assert self._resolve() is None

    def test_noncontainer_or_row_only_root_is_unavailable(self):
        template = self.container.template
        template.is_container = False
        template.save(update_fields=["is_container"])
        assert self._resolve() is None
        root = self._container(self.actor, physical=False)
        child = self._child(root, physical=False)
        assert self._resolve(target_id=child.pk, container_item_id=root.pk) is None

    def test_container_and_child_concealment_require_current_detection(self):
        self._conceal(self.container.game_object)
        assert self._resolve() is None
        register_detection(self.sheet, self.container.game_object)
        assert self._resolve() is not None
        self._conceal(self.child.game_object)
        assert self._resolve() is None
        register_detection(self.sheet, self.child.game_object)
        assert self._resolve() is not None

    def test_current_movement_and_containment_override_previous_resolution(self):
        assert self._resolve() is not None
        self._set_location(self.child.game_object, self.actor)
        assert self._resolve() is None
        self._set_location(self.child.game_object, self.container.game_object)
        assert self._resolve() is not None
        other_container = self._container(self.actor)
        self.child.contained_in = other_container
        self.child.save(update_fields=["contained_in"])
        assert self._resolve() is None
        self._set_location(self.child.game_object, other_container.game_object)
        assert self._resolve(container_item_id=other_container.pk) is not None
        self.child.contained_in = None
        self.child.save(update_fields=["contained_in"])
        self._set_location(self.child.game_object, self.actor)
        assert self._resolve(container_item_id=other_container.pk) is None
        assert self._resolve(container_item_id=None) is not None

    def test_root_movement_and_new_containment_are_rechecked(self):
        assert self._resolve() is not None
        self._set_location(self.actor, self.remote)
        assert self._resolve() is not None  # carried root follows actor
        self._set_location(self.container.game_object, self.room)
        assert self._resolve() is None
        self._set_location(self.actor, self.room)
        assert self._resolve() is not None
        outer = self._container(self.actor)
        self.container.contained_in = outer
        self.container.save(update_fields=["contained_in"])
        self._set_location(self.container.game_object, outer.game_object)
        assert self._resolve() is None

    def test_nested_child_never_expands_read_scope(self):
        inner = self._container(self.container.game_object)
        inner.contained_in = self.container
        inner.save(update_fields=["contained_in"])
        nested = self._child(inner)
        assert self._resolve(target_id=inner.pk) is not None
        assert self._resolve(target_id=nested.pk) is None
        assert self._resolve(target_id=nested.pk, container_item_id=inner.pk) is None

    def test_consumed_child_and_container_are_neutral(self):
        self.child.destroyed_at = timezone.now()
        self.child.save(update_fields=["destroyed_at"])
        assert self._resolve() is None
        self.child.destroyed_at = None
        self.child.save(update_fields=["destroyed_at"])
        self.container.destroyed_at = timezone.now()
        self.container.save(update_fields=["destroyed_at"])
        assert self._resolve() is None

    def test_combined_owner_and_container_are_neutral_without_fallback(self):
        for owner in (
            self.sheet.primary_persona.pk,
            self.other_sheet.primary_persona.pk,
            True,
            "1",
            0,
            -1,
            999999999,
        ):
            with self.subTest(owner=owner):
                assert self._resolve(owner_persona_id=owner) is None
        assert self._resolve() is not None

    def test_room_container_read_scope_does_not_depend_on_child_holder(self):
        self._set_location(self.container.game_object, self.room)
        self.child.holder_character_sheet = self.other_sheet
        self.child.save(update_fields=["holder_character_sheet"])
        self._set_location(self.other, self.remote)
        assert self._resolve() is not None
        assert self._resolve(owner_persona_id=self.other_sheet.primary_persona.pk) is None

    def test_read_does_not_mutate_or_materialize_row_only_child(self):
        child = self._child(self.container, physical=False)
        before = ObjectDB.objects.count()
        relation = child.contained_in_id
        result = self._resolve(target_id=child.pk)
        assert result is not None
        assert result.item == child
        assert result.game_object is None
        assert child.game_object_id is None
        assert child.contained_in_id == relation
        assert ObjectDB.objects.count() == before

    def test_existing_action_api_can_render_row_only_immediate_content(self):
        child = self._child(self.container, physical=False)
        child.custom_name = "Row-only keepsake"
        child.save(update_fields=["custom_name"])
        before = ObjectDB.objects.count()
        result = LookAtItemAction().run(
            self.actor,
            container_id=self.container.game_object.pk,
            item_name=child.display_name,
        )
        assert result.success
        assert child.display_name in result.message
        assert child.game_object_id is None
        assert ObjectDB.objects.count() == before
