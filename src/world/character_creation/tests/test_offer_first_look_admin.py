"""The first-look pin's admin changelist shows and filters the suggested-life flag (#4865)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.factories import BeginningsFactory, DistinctionOfferFactory
from world.character_creation.models import OfferFirstLook
from world.distinctions.factories import DistinctionFactory


class OfferFirstLookChangelistTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("pins", "p@example.com", "pw-123456")
        cls.beginning = BeginningsFactory(name="Born to a Household")
        starred = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Spoiled"),
            chapter=OfferChapter.ACTORS_SHEET,
            arrives_as=OfferArrival.CHOICE,
            prompt="never_do",
        )
        plain = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Patient"),
            chapter=OfferChapter.ACTORS_SHEET,
            arrives_as=OfferArrival.CHOICE,
            prompt="protect",
        )
        OfferFirstLook.objects.create(offer=starred, beginning=cls.beginning, preselected=True)
        OfferFirstLook.objects.create(offer=plain, beginning=cls.beginning, preselected=False)
        cls.url = reverse("admin:arxii_offerfirstlook_changelist")

    def test_the_changelist_lists_the_flag_and_filters_on_it(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["cl"].result_list), 2)
        self.assertIn("preselected", response.context["cl"].list_display)
        self.assertContains(response, "By preselected")
        starred_only = self.client.get(self.url, {"preselected__exact": "1"})
        self.assertEqual(starred_only.status_code, 200)
        rows = list(starred_only.context["cl"].result_list)
        self.assertEqual([row.offer.distinction.name for row in rows], ["Spoiled"])
        plain_only = self.client.get(self.url, {"preselected__exact": "0"})
        rows = list(plain_only.context["cl"].result_list)
        self.assertEqual([row.offer.distinction.name for row in rows], ["Patient"])
