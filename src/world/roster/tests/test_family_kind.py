"""Family kinds are authored rows; influence prices CG standing (#3617)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.roster.constants import COMMONER_KIND_NAME, CRIME_KIND_NAME, NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory
from world.roster.models import Family, FamilyKind
from world.roster.seeds import ensure_family_kinds


class FamilyKindRowsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Migration 0219 backfills these three rows on a real deploy; the fast/parity
        # test tiers build schema straight from model state and never replay migration
        # RunPython (server/conf/sqlite_test_settings.py's data-seeding caveat), so
        # seed them explicitly here via the same idempotent helper production seeding
        # (world.seeds.clusters) uses.
        ensure_family_kinds()

    def test_migration_created_the_three_canonical_kinds(self):
        names = set(FamilyKind.objects.values_list("name", flat=True))
        assert {COMMONER_KIND_NAME, NOBLE_KIND_NAME, CRIME_KIND_NAME} <= names
        assert FamilyKind.objects.get(name=NOBLE_KIND_NAME).styles_as_house is True
        assert FamilyKind.objects.get(name=COMMONER_KIND_NAME).styles_as_house is False

    def test_staff_can_add_a_new_kind_without_code(self):
        humble = FamilyKind.objects.create(name="Humble", description="Stripped-titles gentry.")
        family = FamilyFactory(kind=humble, influence=3)
        assert Family.objects.get(pk=family.pk).kind == humble
        assert family.influence == 3

    def test_influence_defaults_to_zero(self):
        assert FamilyFactory().influence == 0


class FamilyKindFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user(username="kindfilter", password="x")
        kinds = ensure_family_kinds()
        cls.crime = kinds[CRIME_KIND_NAME]
        cls.noble = kinds[NOBLE_KIND_NAME]
        cls.crime_family = FamilyFactory(kind=cls.crime, influence=4)
        cls.noble_family = FamilyFactory(kind=cls.noble)

    def test_kind_filter_narrows_the_list(self):
        client = APIClient()
        client.force_authenticate(self.account)
        res = client.get(f"/api/character-creation/families/?kind={self.crime.pk}")
        assert res.status_code == 200
        ids = {row["id"] for row in res.json()}
        assert ids == {self.crime_family.pk}
        row = res.json()[0]
        assert row["kind"] == {
            "id": self.crime.pk,
            "name": CRIME_KIND_NAME,
            "styles_as_house": False,
        }
        assert row["influence"] == 4
