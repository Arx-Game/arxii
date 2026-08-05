from django.test import TestCase

from evennia_extensions.models import PlayerData
from world.contributors.factories import ContentContributorFactory
from world.contributors.models import ContentContributor, CreditedContent


class ContentContributorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.contributor = ContentContributorFactory(name="Tehom")

    def test_resolves_by_natural_key(self):
        found = ContentContributor.objects.get_by_natural_key("Tehom")
        self.assertEqual(found, self.contributor)

    def test_natural_key_is_the_name(self):
        self.assertEqual(ContentContributor.identity_fields(), ["name"])

    def test_str_is_the_name(self):
        self.assertEqual(str(self.contributor), "Tehom")


class CreditedContentTests(TestCase):
    def test_is_abstract(self):
        self.assertTrue(CreditedContent._meta.abstract)

    def test_every_credit_field_is_nullable(self):
        for name in ("written_by", "written_on", "reviewed_by", "reviewed_on"):
            with self.subTest(field=name):
                self.assertTrue(CreditedContent._meta.get_field(name).null)

    def test_credit_fields_create_no_reverse_accessor(self):
        # related_name="+" - 83 inheriting models would otherwise need 166
        # distinct reverse names on ContentContributor.
        contributor = ContentContributorFactory(name="Reverse Check")
        self.assertFalse(hasattr(contributor, "trait_set"))


class PlayerDataContributorLinkTests(TestCase):
    def test_link_is_optional_and_lives_on_the_account_side(self):
        field = PlayerData._meta.get_field("contributor")
        self.assertTrue(field.null)
        self.assertIs(field.related_model, ContentContributor)
