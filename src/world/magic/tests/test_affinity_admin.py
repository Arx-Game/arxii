"""The admin list of Affinities keeps every row on screen (#5295)."""

from django.test import TestCase, tag
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.factories import AffinityFactory

LONG = "Primal strength is what you feel, whoever is watching. " * 8


class AffinityAdminListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountDB.objects.create_superuser("affadmin", "aff@example.com", "pw-123456")
        AffinityFactory(name="Primal", description=LONG)

    @tag("regression")
    def test_list_shows_the_start_of_a_long_description_not_all_of_it(self):
        """Regression for #5295: the full description in an eleven-column list was a column a
        pixel wide, so the first row ran down several screens and hid the other rows."""
        self.client.force_login(self.staff)
        body = self.client.get(reverse("admin:arxii_affinity_changelist")).content.decode()
        assert "Primal strength is what you feel" in body
        assert LONG.strip() not in body
