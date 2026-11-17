"""Tests for evennia_extensions admin registrations (#3291)."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from evennia_extensions.admin import PlacePrimumInline, RoomDescVariantInline, RoomProfileAdmin
from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import RoomDescVariant, RoomProfile
from world.magic.factories import PlacePrimumFactory
from world.magic.models import PlacePrimum


class RoomDescVariantAdminTests(TestCase):
    def test_room_profile_is_registered(self) -> None:
        assert RoomProfile in admin.site._registry

    def test_room_desc_variant_inline_is_present(self) -> None:
        registered = admin.site._registry[RoomProfile]
        assert isinstance(registered, RoomProfileAdmin)
        assert RoomDescVariantInline in registered.inlines

    def test_inline_targets_room_desc_variant_model(self) -> None:
        assert RoomDescVariantInline.model is RoomDescVariant


class PlacePrimumInlineTests(TestCase):
    """A staff edit of a lair's Primum starts its refill count again (#5125)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            username="lair-staff", email="lair-staff@example.com", password="x"
        )
        cls.profile = RoomProfileFactory()
        cls.long_ago = timezone.now() - timedelta(days=5)
        cls.lair = PlacePrimumFactory(
            room_profile=cls.profile,
            capacity=20,
            stored_amount=10,
            refill_per_day=2,
            stamped_at=cls.long_ago,
        )

    def submit(self, **changes: object) -> bool:
        """Post the inline as the lair's admin page would, with ``changes`` to the row."""
        request = RequestFactory().post("/admin/")
        request.user = self.staff
        inline = PlacePrimumInline(RoomProfile, admin.site)
        formset_class = inline.get_formset(request, self.profile)
        row = {
            "id": self.lair.pk,
            "room_profile": self.profile.pk,
            "substance": self.lair.substance_id,
            "capacity": 20,
            "stored_amount": 10,
            "refill_per_day": 2,
            "is_finite": "",
        } | changes
        data = {"primum-TOTAL_FORMS": 1, "primum-INITIAL_FORMS": 1, "primum-MIN_NUM_FORMS": 0}
        data |= {f"primum-0-{name}": value for name, value in row.items()}
        formset = formset_class(data, instance=self.profile, prefix="primum")
        valid = formset.is_valid()
        if valid:
            formset.save()
        return valid

    def stamped_at(self):
        return (
            PlacePrimum.objects.filter(pk=self.lair.pk).values_list("stamped_at", flat=True).get()
        )

    def test_editing_the_stock_restarts_the_refill_clock_and_an_untouched_row_keeps_it(
        self,
    ) -> None:
        self.assertTrue(self.submit())
        self.assertEqual(self.stamped_at(), self.long_ago)

        self.assertTrue(self.submit(stored_amount=4))

        self.assertGreater(self.stamped_at(), timezone.now() - timedelta(minutes=1))
        self.assertEqual(
            PlacePrimum.objects.filter(pk=self.lair.pk)
            .values_list("stored_amount", flat=True)
            .get(),
            4,
        )
