"""The CG beginnings API must not poison the Beginnings admin change page (Sentry ARX2-9).

The identity map hands back the same resident instance for a pk on every
later load and never refreshes its fields. A row first loaded through a
``.only(...)`` queryset is therefore resident with its other columns missing
for the whole process, and Django's deferred-attribute getter raises
``KeyError`` when the admin's inline formset asks for one of them.
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.character_creation.factories import BeginningsFactory
from world.codex.factories import BeginningsCodexGrantFactory
from world.codex.models import BeginningsCodexGrant


class BeginningsAdminAfterCgApiTests(TestCase):
    """The admin opens after a player has already listed beginnings in CG."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = AccountDB.objects.create_superuser(
            "rootadmin", "root@example.com", "pw-123456"
        )
        cls.beginning = BeginningsFactory()
        BeginningsCodexGrantFactory(beginnings=cls.beginning)

    def test_change_page_opens_after_cg_list_loaded_the_grants(self) -> None:
        # A fresh process has no grant rows resident: the CG list is their first load.
        BeginningsCodexGrant.flush_instance_cache(force=True)
        self.client.force_login(self.superuser)

        listed = self.client.get("/api/character-creation/beginnings/")
        self.assertEqual(listed.status_code, 200)

        change = self.client.get(reverse("admin:arxii_beginnings_change", args=[self.beginning.pk]))

        self.assertEqual(change.status_code, 200)
