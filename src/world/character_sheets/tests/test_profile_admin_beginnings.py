"""Adding an origin on the Profile admin grants that origin's entries (#3775)."""

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import BeginningsFactory
from world.character_sheets.admin import apply_new_origin_rows
from world.character_sheets.factories import ProfileBeginningsFactory
from world.character_sheets.models import ProfileBeginnings
from world.character_sheets.types import ProfileBeginningsSource
from world.codex.factories import CodexEntryFactory
from world.codex.models import BeginningsCodexGrant, CharacterCodexKnowledge
from world.roster.factories import RosterEntryFactory


class ProfileAdminBeginningsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer", is_staff=True, is_superuser=True)
        cls.holder = RosterEntryFactory()
        cls.profile = cls.holder.character_sheet.true_profile
        cls.first = BeginningsFactory(name="Peerage")
        cls.second = BeginningsFactory(name="Twilight Court")
        cls.first_entry = CodexEntryFactory(name="Arx, City of Heroes")
        cls.second_entry = CodexEntryFactory(name="The Twilight Court")
        BeginningsCodexGrant.objects.create(beginnings=cls.first, entry=cls.first_entry)
        BeginningsCodexGrant.objects.create(beginnings=cls.second, entry=cls.second_entry)
        ProfileBeginningsFactory(profile=cls.profile, beginnings=cls.first)

    def test_change_form_shows_the_origins_inline(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:arxii_profile_change", args=[self.profile.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "beginnings_rows")
        self.assertContains(response, "Where play began")

    def test_adding_a_recovered_origin_grants_its_entries(self):
        """``apply_new_origin_rows`` is the unit under test (#3775).

        ``ProfileAdmin.save_related`` is a two-liner that calls
        ``super().save_related`` then this helper, so the helper is where the
        behaviour lives and is tested directly with a stub formset rather than
        driving the whole admin change-form machinery with ``form=None``.
        """
        row = ProfileBeginnings(
            profile=self.profile,
            beginnings=self.second,
            source=ProfileBeginningsSource.RECOVERED_MEMORY,
            note="Woke under the Catacombs",
        )
        row.save()

        class _Formset:
            new_objects = [row]

        request = RequestFactory().post("/")
        request.user = self.staff
        request.session = {}
        request._messages = FallbackStorage(request)

        apply_new_origin_rows(request, [_Formset()])

        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.holder, entry=self.second_entry
            ).exists()
        )
        self.assertEqual(
            CharacterCodexKnowledge.objects.filter(roster_entry=self.holder).count(), 1
        )
