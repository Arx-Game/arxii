"""API tests for the CG house creator's nested claim surface (#2079, #3983 Plan B)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import CharacterDraftFactory, OriginTemplateFactory
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import batch_unclaimed, name_rung, plant_rung
from world.societies.houses.constants import ClaimKinRelation, TitleTier
from world.societies.houses.models import (
    Domain,
    HouseCharterOption,
    HouseCharterQuestion,
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
            kind=FamilyKindFactory(name=NOBLE_KIND_NAME),
            society=cls.crown.society,
            org_type=cls.crown.org_type,
            liege=cls.crown,
            default_succession_law=cls.law,
        )
        cls.virtue = HouseCharterQuestion.objects.create(
            name="House Virtue API", prompt="Which virtue rules the house?"
        )
        cls.fortitude = HouseCharterOption.objects.create(
            definition=cls.virtue, name="Fortitude API"
        )
        cls.inactive = HouseCharterOption.objects.create(
            definition=cls.virtue, name="Retired API", is_active=False
        )
        cls.template.charter_questions.add(cls.virtue)
        cls.hearth = HouseFeature.objects.create(
            name="Hearth Right API",
            slug="hearth-right-api",
            description="Guests are sacrosanct.",
        )
        cls.template.features.add(cls.hearth)
        cls.seat = Domain.objects.create(
            area=AreaFactory(level=AreaLevel.BARONY), name="API Marches", owner_org=cls.crown
        )
        cls.title = Title.objects.create(
            name="Barony of API",
            tier=TitleTier.BARONY,
            realm=cls.realm,
            seat_domain=cls.seat,
            is_claimable=True,
        )
        cls.draft = CharacterDraftFactory()

        # A real seat chain for the nested kin/lands round-trip (#3983 Plan
        # B): a duchy claim grants the duchy + its own county + its own seat
        # barony (one chain, three titles), plus a loose barony batch-minted
        # under the county — mirrors test_house_creator.py's journey fixture.
        cls.duchy = plant_rung(realm=cls.realm, tier=TitleTier.DUCHY, name="Journey Duchy")
        cls.county = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=cls.duchy.seat_domain)
        cls.seat_barony = Title.objects.get(
            tier=TitleTier.BARONY, seat_domain=cls.duchy.seat_domain
        )
        name_rung(cls.county, "Journey County")
        name_rung(cls.seat_barony, "Journey Barony")
        cls.loose_barony = batch_unclaimed(parent_title=cls.county, tier=TitleTier.BARONY, count=1)[
            0
        ]
        cls.solano_family = FamilyFactory(name="API Solano")

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
            "facets": [{"definition": self.virtue.pk, "options": [self.fortitude.pk]}],
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
        definitions = template["charter_questions"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["name"], "House Virtue API")
        option_names = [o["name"] for o in definitions[0]["options"]]
        self.assertIn("Fortitude API", option_names)
        self.assertNotIn("Retired API", option_names)
        feature_slugs = [f["slug"] for f in template["features"]]
        self.assertEqual(feature_slugs, ["hearth-right-api"])
        # #4205: a plain option names no being and opens nothing.
        fortitude = next(o for o in definitions[0]["options"] if o["name"] == "Fortitude API")
        self.assertIsNone(fortitude["being_id"])
        self.assertEqual(fortitude["being_name"], "")
        self.assertIsNone(fortitude["target_entry_id"])

    def test_house_titles_drop_crowns_titular_and_chain_internal(self):
        """#4983: no kingdom, no titular or potential rung and no seat chain's inner
        rung is ever an undefined house a player may define; the duchy itself is."""
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import plant_rung
        from world.societies.houses.constants import TitleStation, TitleTier
        from world.societies.houses.models import Title

        realm = RealmFactory(name="Picker Realm")
        kingdom = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Picker Crown")
        kingdom.is_claimable = True  # forced by hand: the filter must still drop it
        kingdom.save(update_fields=["is_claimable"])
        duchy = plant_rung(
            realm=realm, tier=TitleTier.DUCHY, name="Picker Duchy", parent_title=kingdom
        )
        titular = plant_rung(
            realm=realm,
            tier=TitleTier.DUCHY,
            name="Old Duchy",
            parent_title=kingdom,
            station=TitleStation.TITULAR,
        )
        inner = Title.objects.get(seat_domain=duchy.seat_domain, tier=TitleTier.COUNTY)
        self.assertTrue(inner.is_claimable, "plant_rung marks the inner county claimable")
        response = self.client.get("/api/character-creation/house-titles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = response.data["results"] if isinstance(response.data, dict) else response.data
        ids = {t["id"] for t in titles}
        self.assertIn(duchy.pk, ids)
        self.assertNotIn(kingdom.pk, ids)
        self.assertNotIn(titular.pk, ids)
        self.assertNotIn(inner.pk, ids)

    def test_house_titles_query_count_does_not_grow_with_the_catalogue(self):
        """#4983: one realm graph per realm, never a liege walk per title."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import plant_rung
        from world.societies.houses.constants import TitleTier

        realm = RealmFactory(name="Count Realm")
        kingdom = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Count Crown")
        plant_rung(realm=realm, tier=TitleTier.DUCHY, name="Duchy 0", parent_title=kingdom)
        with CaptureQueriesContext(connection) as one:
            self.client.get("/api/character-creation/house-titles/")
        for i in range(1, 7):
            plant_rung(realm=realm, tier=TitleTier.DUCHY, name=f"Duchy {i}", parent_title=kingdom)
        with CaptureQueriesContext(connection) as seven:
            response = self.client.get("/api/character-creation/house-titles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len([t for t in titles if t["name"].startswith("Duchy")]), 7)
        # the identity map may spare a query on the second read; it never adds one per title
        self.assertLessEqual(len(seven), len(one))

    def _patron_question(self):
        """A patron question on the template, with one public liturgy god and one
        the question must not offer (its page is not public)."""
        from world.codex.factories import CodexEntryFactory
        from world.worship.factories import WorshippedBeingFactory, WorshipTraditionFactory

        liturgy = WorshipTraditionFactory(name="Church Liturgy API")
        entry = CodexEntryFactory(name="Calyx API", is_public=True)
        calyx = WorshippedBeingFactory(
            name="Calyx API", tradition=liturgy, codex_entry=entry, domains="Honorable combat"
        )
        hidden = WorshippedBeingFactory(
            name="Hidden API",
            tradition=liturgy,
            codex_entry=CodexEntryFactory(name="Hidden API", is_public=False),
        )
        patron = HouseCharterQuestion.objects.create(
            name="Patron API",
            prompt="Whom does the house serve?",
            sets_patron=True,
            patron_tradition=liturgy,
        )
        self.template.charter_questions.add(patron)
        return patron, calyx, hidden, entry

    def test_house_titles_offer_the_gods_of_the_patron_questions_worship(self):
        """#5110: the patron question's choices are the active, public gods of its
        worship, each carrying the god and opening its page; a hidden god is absent."""
        _patron, calyx, _hidden, entry = self._patron_question()

        response = self.client.get("/api/character-creation/house-titles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = response.data["results"] if isinstance(response.data, dict) else response.data
        title = next(t for t in titles if t["id"] == self.title.pk)
        template = next(t for t in title["templates"] if t["id"] == self.template.pk)
        definition = next(d for d in template["charter_questions"] if d["name"] == "Patron API")
        self.assertTrue(definition["sets_patron"])
        self.assertEqual([option["name"] for option in definition["options"]], ["Calyx API"])
        option = definition["options"][0]
        self.assertEqual(option["id"], calyx.pk)
        self.assertEqual(option["being_id"], calyx.pk)
        self.assertEqual(option["description"], "Honorable combat")
        self.assertEqual(option["target_entry_id"], entry.pk)

    def test_post_claim_carries_the_patron_and_refuses_a_god_not_offered(self):
        """#5110: the claim is refused without a patron and with a god the question
        does not offer; with one it offers, the claim holds the god."""
        _patron, calyx, hidden, _entry = self._patron_question()
        url = f"/api/character-creation/drafts/{self.draft.pk}/house-claim/"

        missing = self.client.post(url, self._payload(), format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST, missing.data)
        refused = self.client.post(url, self._payload(patron_being_id=hidden.pk), format="json")
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.data)

        response = self.client.post(url, self._payload(patron_being_id=calyx.pk), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["patron_being_id"], calyx.pk)
        self.assertEqual(response.data["patron_name"], "Calyx API")

    def test_post_full_claim_persists_picks_and_stylings(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["words"], "The Marches Hold")
        self.assertEqual(
            response.data["facets"],
            [{"definition": "House Virtue API", "option": "Fortitude API"}],
        )

    def test_post_missing_pick_is_refused_with_user_message(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(facets=[]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("House Virtue API", response.data["detail"])

    def test_post_malformed_aspects_is_refused(self):
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(facets=[{"definition": "not-a-number", "options": ["x"]}]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_observances_persist_and_get_echoes_them(self):
        """#4206: the founder's days of remembrance ride the nested submit body
        and come back on the status GET; a bad row is refused with the gate's
        own user message."""
        bad = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(observances=[{"ic_month": 13, "ic_day": 1, "name": "Nowhen"}]),
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST, bad.data)
        self.assertIn("month", bad.data["detail"])

        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(
                observances=[
                    {"ic_month": 10, "ic_day": 18, "name": "Founding Night", "lore": "Fire."},
                    {"ic_month": 1, "ic_day": 2, "name": "The Vigil"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        expected = [
            {
                "ic_month": 10,
                "ic_day": 18,
                "name": "Founding Night",
                "lore": "Fire.",
                "sort_order": 0,
            },
            {"ic_month": 1, "ic_day": 2, "name": "The Vigil", "lore": "", "sort_order": 1},
        ]
        self.assertEqual(response.data["observances"], expected)
        get_response = self.client.get(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/"
        )
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["observances"], expected)

    def test_post_nested_claim_persists_kin_and_lands_and_get_echoes_them(self):
        """#3983 Plan B: the founder's whole kin tree + per-rung land writing
        round-trip through the nested submit body and the status GET."""
        payload = self._payload(
            title=self.duchy.pk,
            house_name="Journeywood",
            facets=[{"definition": self.virtue.pk, "options": [self.fortitude.pk]}],
            founder_relation=ClaimKinRelation.CHILD,
            founder_is_heir=True,
            kin=[
                {"name": "Estuosa", "relation": ClaimKinRelation.HEAD},
                {"name": "Fiamma", "relation": ClaimKinRelation.MOTHER, "is_deceased": True},
                {
                    "name": "Dario",
                    "relation": ClaimKinRelation.SPOUSE,
                    "born_into": self.solano_family.pk,
                },
                {"name": "", "relation": ClaimKinRelation.CHILD},
                {"name": "Captain", "relation": ClaimKinRelation.POSITION, "is_household": True},
            ],
            lands=[
                {"title": self.duchy.pk, "description": "the duchy"},
                {"title": self.seat_barony.pk, "hall_name": "the Torre Accesa"},
                {"title": self.loose_barony.pk, "land_name": "Brasa", "description": "named"},
            ],
        )
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data["kin"]), 5)
        self.assertEqual(len(response.data["lands"]), 3)
        self.assertEqual(response.data["founder_relation"], ClaimKinRelation.CHILD)
        self.assertTrue(response.data["founder_is_heir"])

        get_response = self.client.get(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/"
        )
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_response.data["kin"]), 5)
        self.assertEqual(len(get_response.data["lands"]), 3)
        land_by_title = {row["title_id"]: row for row in get_response.data["lands"]}
        self.assertEqual(land_by_title[self.loose_barony.pk]["land_name"], "Brasa")
        spouse = next(
            row for row in get_response.data["kin"] if row["relation"] == ClaimKinRelation.SPOUSE
        )
        self.assertEqual(spouse["born_into_id"], self.solano_family.pk)

    def test_post_land_outside_the_grant_is_refused(self):
        elsewhere = Title.objects.create(
            name="Barony Elsewhere",
            tier=TitleTier.BARONY,
            realm=self.realm,
            is_claimable=False,
        )
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(lands=[{"title": elsewhere.pk, "description": "not mine"}]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_post_above_the_upbringings_max_claim_tier_is_refused(self):
        self.draft.selected_origin_template = OriginTemplateFactory(max_claim_tier=TitleTier.BARONY)
        self.draft.save(update_fields=["selected_origin_template"])
        response = self.client.post(
            f"/api/character-creation/drafts/{self.draft.pk}/house-claim/",
            self._payload(title=self.duchy.pk, house_name="Overreach"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
