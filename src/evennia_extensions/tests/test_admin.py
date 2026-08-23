"""Tests for evennia_extensions admin registrations (#3291)."""

from django.contrib import admin
from django.test import TestCase

from evennia_extensions.admin import RoomDescVariantInline, RoomProfileAdmin
from evennia_extensions.models import RoomDescVariant, RoomProfile


class RoomDescVariantAdminTests(TestCase):
    def test_room_profile_is_registered(self) -> None:
        assert RoomProfile in admin.site._registry

    def test_room_desc_variant_inline_is_present(self) -> None:
        registered = admin.site._registry[RoomProfile]
        assert isinstance(registered, RoomProfileAdmin)
        assert RoomDescVariantInline in registered.inlines

    def test_inline_targets_room_desc_variant_model(self) -> None:
        assert RoomDescVariantInline.model is RoomDescVariant
