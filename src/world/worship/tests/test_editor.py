"""The Deity Editor (#3780): one page writes a being, its Codex tier and its satellite rows."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from world.codex.factories import CodexEntryFactory
from world.codex.models import OrganizationCodexGrant
from world.magic.factories import FacetFactory, ResonanceFactory
from world.roster.factories import grant_test_tenure
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory
from world.societies.membership_services import join_organization
from world.tarot.factories import TarotCardFactory
from world.worship.constants import (
    BeingRelationshipValence,
    BeingResonanceTier,
    BeingVisibility,
)
from world.worship.editor_services import (
    BeingPage,
    FeastDayLine,
    RelationshipLine,
    ResonanceLine,
    obscure_organization_of,
    save_being,
    visibility_of,
)
from world.worship.factories import (
    BeingNicknameFactory,
    PrayerFactory,
    VisionFactory,
    WorshippedBeingFactory,
    WorshipTraditionFactory,
)
from world.worship.models import BeingFacet, BeingRelationship, WorshippedBeing


def _page(tradition, **overrides) -> BeingPage:
    base = {
        "name": "Fleshreaper",
        "description": "Goddess of carnage.",
        "domains": "Carnage, bloodshed",
        "tradition_id": tradition.pk,
        "is_active": True,
        "quote": "",
    }
    base.update(overrides)
    return BeingPage(**base)


class SaveBeingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tradition = WorshipTraditionFactory()
        cls.other = WorshippedBeingFactory()
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory()
        cls.card = TarotCardFactory()
        cls.organization = OrganizationFactory()

    def test_a_new_secret_being_gets_no_codex_page(self) -> None:
        being = save_being(_page(self.tradition))

        self.assertIsNone(being.codex_entry)
        self.assertEqual(visibility_of(being), BeingVisibility.SECRET)

    def test_the_page_writes_every_satellite_row_and_replaces_them_on_the_next_save(self) -> None:
        being = save_being(
            _page(
                self.tradition,
                nicknames=["the Crimson", "  ", "the Crimson"],
                resonances=[ResonanceLine(self.resonance.pk, BeingResonanceTier.FAVORED)],
                facet_ids=[self.facet.pk],
                feast_days=[FeastDayLine(3, 14, "The Long Bleeding", "A night of it.")],
                tarot_card_ids=[self.card.pk],
                relationships=[
                    RelationshipLine(self.other.pk, BeingRelationshipValence.ALLY, "Old friends.")
                ],
                gm_notes="Was a warlord in Arx 1.",
            )
        )

        self.assertEqual(list(being.nicknames.values_list("name", flat=True)), ["the Crimson"])
        self.assertEqual(being.resonances.get().tier, BeingResonanceTier.FAVORED)
        self.assertEqual(BeingFacet.objects.get(being=being).facet, self.facet)
        self.assertEqual(being.feast_days.get().name, "The Long Bleeding")
        self.assertEqual(list(being.tarot_cards.all()), [self.card])
        relationship = BeingRelationship.objects.get()
        self.assertEqual({relationship.being_a, relationship.being_b}, {being, self.other})
        self.assertEqual(relationship.public_story, "Old friends.")
        self.assertEqual(being.gm_notes, "Was a warlord in Arx 1.")

        save_being(
            _page(
                self.tradition,
                nicknames=["the Red"],
                resonances=[ResonanceLine(self.resonance.pk, BeingResonanceTier.ASSOCIATED)],
                feast_days=[FeastDayLine(3, 14, "The Long Bleeding", "Retold.")],
                relationships=[
                    RelationshipLine(self.other.pk, BeingRelationshipValence.FEUD, "Fell out.")
                ],
            ),
            being=being,
        )

        self.assertEqual(list(being.nicknames.values_list("name", flat=True)), ["the Red"])
        self.assertEqual(being.resonances.get().tier, BeingResonanceTier.ASSOCIATED)
        self.assertFalse(BeingFacet.objects.filter(being=being).exists())
        self.assertEqual(being.feast_days.get().lore, "Retold.")
        self.assertEqual(list(being.tarot_cards.all()), [])
        relationship = BeingRelationship.objects.get()
        self.assertEqual(relationship.valence, BeingRelationshipValence.FEUD)

    def test_a_public_being_gets_a_codex_page_with_its_quote(self) -> None:
        being = save_being(
            _page(self.tradition, quote="Never once mercy.", visibility=BeingVisibility.PUBLIC)
        )

        entry = being.codex_entry
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_public)
        self.assertEqual(entry.quote, "Never once mercy.")
        self.assertEqual(entry.name, "Fleshreaper")
        self.assertEqual(entry.subject.name, "The Pantheon")
        self.assertEqual(visibility_of(being), BeingVisibility.PUBLIC)

    def test_an_obscure_being_is_granted_to_an_organizations_members(self) -> None:
        persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        grant_test_tenure(persona.character_sheet)
        join_organization(self.organization, persona)

        being = save_being(
            _page(
                self.tradition,
                visibility=BeingVisibility.OBSCURE,
                organization_id=self.organization.pk,
            )
        )

        self.assertEqual(visibility_of(being), BeingVisibility.OBSCURE)
        self.assertEqual(obscure_organization_of(being), self.organization)
        self.assertFalse(being.codex_entry.is_public)
        roster_entry = persona.character_sheet.roster_entry
        self.assertTrue(roster_entry.codex_knowledge.filter(entry=being.codex_entry).exists())

        # Back to secret: the grant goes, the page stays.
        save_being(_page(self.tradition, visibility=BeingVisibility.SECRET), being=being)
        self.assertFalse(OrganizationCodexGrant.objects.exists())
        self.assertIsNotNone(being.codex_entry)
        self.assertEqual(visibility_of(being), BeingVisibility.SECRET)

    def test_a_new_member_learns_what_the_organization_grants(self) -> None:
        entry = CodexEntryFactory(is_public=False)
        OrganizationCodexGrant.objects.create(organization=self.organization, entry=entry)
        persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        grant_test_tenure(persona.character_sheet)

        join_organization(self.organization, persona)

        roster_entry = persona.character_sheet.roster_entry
        self.assertTrue(roster_entry.codex_knowledge.filter(entry=entry).exists())


class StaffBeingAPITests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        User = get_user_model()
        cls.staff = User.objects.create_user(username="staff-3780", password="x", is_staff=True)
        cls.player = User.objects.create_user(username="player-3780", password="x")
        cls.tradition = WorshipTraditionFactory()
        cls.rich = WorshippedBeingFactory(tradition=cls.tradition, resonance_pool=500)
        cls.poor = WorshippedBeingFactory(tradition=cls.tradition, resonance_pool=5)
        BeingNicknameFactory(being=cls.poor, name="the Quiet")
        cls.rich.codex_entry = CodexEntryFactory(is_public=True)
        cls.rich.save(update_fields=["codex_entry"])
        PrayerFactory(being=cls.rich)
        VisionFactory(being=cls.rich)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_players_are_refused(self) -> None:
        self.assertEqual(
            self._client(self.player).get("/api/worship/admin/beings/").status_code, 403
        )

    def test_the_list_sorts_by_pool_and_filters_by_visibility_and_searches_nicknames(self) -> None:
        client = self._client(self.staff)

        rows = client.get("/api/worship/admin/beings/").json()["results"]
        public = client.get("/api/worship/admin/beings/?visibility=public").json()["results"]
        secret = client.get("/api/worship/admin/beings/?visibility=secret").json()["results"]
        quiet = client.get("/api/worship/admin/beings/?search=quiet").json()["results"]

        self.assertEqual([row["id"] for row in rows], [self.rich.pk, self.poor.pk])
        self.assertEqual(rows[0]["visibility"], BeingVisibility.PUBLIC)
        self.assertEqual(rows[1]["nickname"], "the Quiet")
        self.assertEqual([row["id"] for row in public], [self.rich.pk])
        self.assertEqual([row["id"] for row in secret], [self.poor.pk])
        self.assertEqual([row["id"] for row in quiet], [self.poor.pk])

    def test_create_and_update_go_through_the_page(self) -> None:
        client = self._client(self.staff)
        resonance = ResonanceFactory()

        created = client.post(
            "/api/worship/admin/beings/",
            {
                "name": "Lady of the Loom",
                "description": "Fate and weaving.",
                "domains": "Fate, weaving",
                "tradition": self.tradition.pk,
                "quote": "Every thread ends.",
                "nicknames": ["the Patient Weaver"],
                "resonances": [{"resonance": resonance.pk, "tier": "favored"}],
                "feast_days": [{"ic_month": 1, "ic_day": 2, "name": "First Thread"}],
                "relationships": [
                    {"other_being": self.rich.pk, "valence": "rival", "public_story": "Old."}
                ],
                "visibility": "public",
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201, created.content)
        being = WorshippedBeing.objects.get(name="Lady of the Loom")
        page = created.json()
        self.assertEqual(page["quote"], "Every thread ends.")
        self.assertEqual(page["nicknames"], ["the Patient Weaver"])
        self.assertEqual(page["relationships"][0]["other_being_name"], self.rich.name)
        self.assertEqual(page["visibility"], "public")

        updated = client.put(
            f"/api/worship/admin/beings/{being.pk}/",
            {
                **{
                    k: v
                    for k, v in page.items()
                    if k not in {"id", "resonance_pool", "codex_entry"}
                },
                "relationships": [],
                "visibility": "secret",
                "gm_notes": "Keep her patient.",
            },
            format="json",
        )

        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["gm_notes"], "Keep her patient.")
        self.assertEqual(updated.json()["visibility"], "secret")
        self.assertFalse(BeingRelationship.objects.exists())

    def test_obscure_needs_an_organization(self) -> None:
        response = self._client(self.staff).post(
            "/api/worship/admin/beings/",
            {"name": "Nobody", "tradition": self.tradition.pk, "visibility": "obscure"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("organization", response.json())

    def test_options_and_the_dashboard_answer(self) -> None:
        client = self._client(self.staff)
        base = f"/api/worship/admin/beings/{self.rich.pk}"

        options = client.get("/api/worship/admin/beings/options/").json()
        overview = client.get(f"{base}/overview/").json()
        worship = client.get(f"{base}/worship/").json()
        prayers = client.get(f"{base}/prayers/").json()
        visions = client.get(f"{base}/visions/").json()
        codex = client.get(f"{base}/codex/").json()

        self.assertIn(self.tradition.pk, [row["id"] for row in options["traditions"]])
        self.assertEqual(overview["resonance_pool"], 500)
        self.assertEqual(len(overview["recent_activity"]), 2)
        self.assertEqual(worship["most_devoted"], [])
        self.assertEqual(prayers["count"], 1)
        self.assertEqual(visions["count"], 1)
        self.assertEqual(codex[0]["relation"], "the being's page")
        self.assertTrue(codex[0]["is_public"])
        self.assertEqual(client.get(f"{base}/sites/").json(), [])
        self.assertEqual(client.get(f"{base}/relics/").json(), [])
