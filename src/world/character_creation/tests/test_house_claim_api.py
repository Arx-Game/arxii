"""API tests for the CG house creator's aspect/feature/styling surface (#2079)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.areas.factories import AreaFactory
from world.character_creation.factories import CharacterDraftFactory
from world.roster.models import Family
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import (
    Domain,
    HouseAspectDefinition,
    HouseAspectOption,
    HouseFeature,
    HouseTemplate,
    SuccessionLaw,
    Title,
)


class HouseClaimApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crown = OrganizationFactory(name="The Crown API")
        cls.realm = cls.crown.society.realm
        cls.law = SuccessionLaw.objects.create(
            name="API Primogeniture", derivation="primogeniture_wedlock"
        )
        cls.template = HouseTemplate.objects.create(
            name="API Barony Charter",
            realm=cls.realm,
            family_type=Family.FamilyType.NOBLE,
            society=cls.crown.society,
            liege=cls.crown,
            default_succession_law=cls.law,
        )
        cls.virtue = HouseAspectDefinition.objects.create(
            name="House Virtue API", prompt="Which virtue rules the house?"
        )
        cls.fortitude = HouseAspectOption.objects.create(
            definition=cls.virtue, name="Fortitude API"
        )
        cls.inactive = HouseAspectOption.objects.create(
            definition=cls.virtue, name="Retired API", is_active=False
        )
        cls.template.aspect_definitions.add(cls.virtue)
        cls.hearth = HouseFeature.objects.create(
            name="Hearth Right API",
            slug="hearth-right-api",
            description="Guests are sacrosanct.",
        )
        cls.template.features.add(cls.hearth)
        cls.seat = Domain.objects.create(
            area=AreaFactory(), name="API Marches", owner_org=cls.crown
        )
        cls.title = Title.objects.create(
            name="Barony of API",
            tier=TitleTier.BARONY,
            realm=cls.realm,
            seat_domain=cls.seat,
            is_claimable=True,
        )
        cls.draft = CharacterDraftFactory()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.draft.account)

    def _payload(self, **overrides):
        payload = {
            "title": self.title.pk,
            "template": self.template.pk,
            "house_name": "Apiwood",
            "backstory": "An old line of the marches.",
            "words": "The Marches Hold",
            "colors": "grey and gold",
            "sigil_description": "A tower on a grey field.",
            "lands_writeup": "Border keeps and toll roads.",
            "aspects": [{"definition": self.virtue.pk, "options": [self.fortitude.pk]}],
            "mercy": 0,
            "method": 0,
            "status": 0,
            "change": 0,
            "allegiance": 0,
            "power": 0,
        }
        payload.update(overrides)
        return payload

    def test_house_titles_expose_definition_tree_and_features(self):
        response = self.client.get("/api/character-creation/house-titles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = response.data["results"] if isinstance(response.data, dict) else response.data
        title = next(t for t in titles if t["id"] == self.title.pk)
        template = next(t for t in title["templates"] if t["id"] == self.template.pk)
        definitions = template["aspect_definitions"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["name"], "House Virtue API")
        option_names = [o["name"] for o in definitions[0]["options"]]
        self.assertIn("Fortitude API", option_names)
        self.assertNotIn("Retired API", option_names)
        feature_slugs = [f["slug"] for f in template["features"]]
        self.assertEqual(feature_slugs, ["hearth-right-api"])

    def test_post_full_claim_persists_picks_and_stylings(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["words"], "The Marches Hold")
        self.assertEqual(
            response.data["aspects"],
            [{"definition": "House Virtue API", "option": "Fortitude API"}],
        )

    def test_post_missing_pick_is_refused_with_user_message(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(aspects=[]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("House Virtue API", response.data["detail"])

    def test_post_malformed_aspects_is_refused(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(aspects=[{"definition": "not-a-number", "options": ["x"]}]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
