"""Current-scope typed item resolution, independent of action dispatch."""

from dataclasses import FrozenInstanceError

from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance


class MenuItemResolutionTests(TestCase):
    """Identify visible items without guessing ID domains or granting actions."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.actor = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.actor)
        self.other = CharacterFactory(location=self.room)
        self.other_sheet = CharacterSheetFactory(character=self.other)

    def _request(self, item: ItemInstance, **context: int) -> MenuTargetRequest:
        return MenuTargetRequest(MenuTargetKind.ITEMS, item.pk, **context)

    def _physical_item(self, location: ObjectDB | None, **kwargs: object) -> ItemInstance:
        obj = ObjectDBFactory(location=location)
        return ItemInstanceFactory(game_object=obj, **kwargs)

    def _conceal(self, item: ItemInstance) -> None:
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(condition=template, target=item.game_object)

    def test_request_is_frozen(self) -> None:
        request = MenuTargetRequest(MenuTargetKind.ITEMS, 1)
        with self.assertRaises(FrozenInstanceError):
            request.target_id = 2  # type: ignore[misc]

    def test_carried_physical_item_does_not_require_ownership(self) -> None:
        item = self._physical_item(self.actor, custom_name="Carried token")
        result = resolve_menu_target(self.actor, self._request(item))
        self.assertIsNotNone(result)
        assert result is not None
        assert result.item is not None
        assert result.game_object is not None
        self.assertEqual(result.item.pk, item.pk)
        self.assertEqual(result.game_object.pk, item.game_object_id)
        self.assertEqual(result.label, "Carried token")
        self.assertIsNone(result.place)
        with self.assertRaises(FrozenInstanceError):
            result.label = "Client label"  # type: ignore[misc]

    def test_room_item_ownership_is_not_a_visibility_gate(self) -> None:
        item = self._physical_item(self.room, holder_character_sheet=self.other_sheet)
        self.assertIsNotNone(resolve_menu_target(self.actor, self._request(item)))

    def test_owned_row_only_item_stays_row_only(self) -> None:
        item = ItemInstanceFactory(game_object=None, holder_character_sheet=self.sheet)
        before = ObjectDB.objects.count()
        result = resolve_menu_target(self.actor, self._request(item))
        self.assertIsNotNone(result)
        assert result is not None
        assert result.item is not None
        self.assertEqual(result.item.pk, item.pk)
        self.assertIsNone(result.game_object)
        self.assertIsNone(result.place)
        self.assertIsNone(item.game_object_id)
        self.assertEqual(ObjectDB.objects.count(), before)

    def test_other_or_unowned_row_only_items_are_unavailable(self) -> None:
        for holder in (self.other_sheet, None):
            with self.subTest(holder=holder):
                item = ItemInstanceFactory(game_object=None, holder_character_sheet=holder)
                self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_ownership_does_not_reveal_remote_physical_item(self) -> None:
        remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        item = self._physical_item(remote, holder_character_sheet=self.sheet)
        self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_private_carried_item_on_same_room_character_is_unavailable(self) -> None:
        item = self._physical_item(self.other, holder_character_sheet=self.other_sheet)
        self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_contained_items_are_unavailable_even_with_inconsistent_location(self) -> None:
        container = self._physical_item(self.actor)
        for location in (self.actor, self.room, None):
            with self.subTest(location=location):
                item = ItemInstanceFactory(
                    game_object=None if location is None else ObjectDBFactory(location=location),
                    holder_character_sheet=self.sheet,
                    contained_in=container,
                )
                self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_asserted_context_never_grants_scope_or_is_silently_ignored(self) -> None:
        item = self._physical_item(self.actor)
        for context in (
            {"owner_persona_id": 1},
            {"container_item_id": item.pk},
            {"owner_persona_id": 1, "container_item_id": item.pk},
        ):
            with self.subTest(context=context):
                self.assertIsNone(resolve_menu_target(self.actor, self._request(item, **context)))

    def test_hidden_and_absent_items_have_identical_unavailable_result(self) -> None:
        item = self._physical_item(self.room)
        self._conceal(item)
        self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))
        self.assertIsNone(
            resolve_menu_target(
                self.actor, MenuTargetRequest(MenuTargetKind.ITEMS, item.pk + 100000)
            )
        )

    def test_detected_concealment_uses_existing_perception_service(self) -> None:
        item = self._physical_item(self.room)
        self._conceal(item)
        register_detection(self.sheet, item.game_object)
        self.assertIsNotNone(resolve_menu_target(self.actor, self._request(item)))

    def test_concealed_carried_physical_item_is_unavailable(self) -> None:
        item = self._physical_item(self.actor)
        self._conceal(item)
        self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_reresolution_rejects_item_moved_to_other_character(self) -> None:
        item = self._physical_item(self.actor, holder_character_sheet=self.sheet)
        request = self._request(item)
        self.assertIsNotNone(resolve_menu_target(self.actor, request))
        item.game_object.location = self.other
        item.game_object.save()
        self.assertIsNone(resolve_menu_target(self.actor, request))

    def test_reresolution_rejects_item_after_actor_leaves_room(self) -> None:
        item = self._physical_item(self.room)
        request = self._request(item)
        self.assertIsNotNone(resolve_menu_target(self.actor, request))
        self.actor.location = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.actor.save()
        self.assertIsNone(resolve_menu_target(self.actor, request))

    def test_reresolution_rejects_destroyed_item(self) -> None:
        item = self._physical_item(self.actor)
        request = self._request(item)
        self.assertIsNotNone(resolve_menu_target(self.actor, request))
        item.destroyed_at = timezone.now()
        item.save()
        self.assertIsNone(resolve_menu_target(self.actor, request))

    def test_nowhere_actor_does_not_see_nowhere_physical_object(self) -> None:
        self.actor.location = None
        self.actor.save()
        item = self._physical_item(None, holder_character_sheet=self.sheet)
        self.assertIsNone(resolve_menu_target(self.actor, self._request(item)))

    def test_item_and_object_ids_are_not_interchangeable(self) -> None:
        obj = ObjectDBFactory(location=self.actor)
        item = ItemInstanceFactory(id=obj.pk + 100000, game_object=obj)
        ItemInstanceFactory(id=obj.pk, holder_character_sheet=self.other_sheet)
        result = resolve_menu_target(self.actor, self._request(item))
        self.assertIsNotNone(result)
        assert result is not None
        assert result.item is not None
        assert result.game_object is not None
        self.assertEqual(result.item.pk, item.pk)
        self.assertEqual(result.game_object.pk, obj.pk)
        self.assertNotEqual(item.pk, obj.pk)
        self.assertIsNone(
            resolve_menu_target(self.actor, MenuTargetRequest(MenuTargetKind.ITEMS, obj.pk))
        )
        self.assertIsNone(
            resolve_menu_target(self.actor, MenuTargetRequest(MenuTargetKind.OBJECTS, item.pk))
        )

    def test_unsupported_kinds_fail_closed_even_for_carried_item_id(self) -> None:
        item = self._physical_item(self.actor)
        for kind in (MenuTargetKind.OBJECTS, MenuTargetKind.EXITS, MenuTargetKind.PLACES):
            with self.subTest(kind=kind):
                self.assertIsNone(resolve_menu_target(self.actor, MenuTargetRequest(kind, item.pk)))

    def test_invalid_ids_and_unparsed_kind_fail_closed(self) -> None:
        for target_id in (True, False, 0, -1, "1", None):
            with self.subTest(target_id=target_id):
                self.assertIsNone(
                    resolve_menu_target(
                        self.actor,
                        MenuTargetRequest(MenuTargetKind.ITEMS, target_id),  # type: ignore[arg-type]
                    )
                )
        item = self._physical_item(self.actor)
        self.assertIsNone(
            resolve_menu_target(
                self.actor,
                MenuTargetRequest("items", item.pk),  # type: ignore[arg-type]
            )
        )

    def test_repeated_resolution_does_not_change_item_state(self) -> None:
        item = self._physical_item(self.actor, holder_character_sheet=self.sheet, charges=3)
        before = (
            item.game_object_id,
            item.game_object.location.pk,
            item.holder_character_sheet_id,
            item.contained_in_id,
            item.charges,
            item.destroyed_at,
            ItemInstance.objects.count(),
        )
        for _ in range(2):
            self.assertIsNotNone(resolve_menu_target(self.actor, self._request(item)))
        after = (
            item.game_object_id,
            item.game_object.location.pk,
            item.holder_character_sheet_id,
            item.contained_in_id,
            item.charges,
            item.destroyed_at,
            ItemInstance.objects.count(),
        )
        self.assertEqual(after, before)
