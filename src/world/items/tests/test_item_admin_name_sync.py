"""A staff rename in the item admin reaches the name look shows (#4338)."""

from __future__ import annotations

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.items.admin import ItemInstanceAdmin
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object_in_room


class ItemAdminNameSyncTests(TestCase):
    def test_saving_a_custom_name_renames_the_game_object(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        instance = ItemInstanceFactory(template=ItemTemplateFactory(name="Plain cup"))
        cup = materialize_item_game_object_in_room(instance, room)
        instance.custom_name = "Heron cup"

        ItemInstanceAdmin(ItemInstance, site).save_model(
            RequestFactory().post("/"), instance, form=None, change=True
        )

        cup.refresh_from_db()
        assert cup.db_key == "Heron cup"
