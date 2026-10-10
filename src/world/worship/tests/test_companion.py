"""The deity's companion (#4198): every group from the editor's rows, empty groups
left out, calendar order, "reversed" on a reversed link, this god's side of a story
only, and a relationship drawn only when the reader may open the other god's entry."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.codex.types import CompanionReader
from world.magic.factories import FacetFactory, ResonanceFactory
from world.roster.factories import RosterTenureFactory
from world.tarot.factories import TarotCardFactory
from world.worship.companion import being_companion
from world.worship.constants import BeingRelationshipValence, BeingResonanceTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingNicknameFactory,
    BeingResonanceFactory,
    WorshipFeastDayFactory,
    WorshippedBeingFactory,
)
from world.worship.models import BeingRelationship, BeingTarotCard


class BeingCompanionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="The Fleshreaper", is_public=True)
        cls.being = WorshippedBeingFactory(
            name="The Fleshreaper", domains="Carnage, Hunters", codex_entry=cls.entry
        )
        cls.calyx_entry = CodexEntryFactory(name="Calyx", is_public=False)
        cls.calyx = WorshippedBeingFactory(name="Calyx", codex_entry=cls.calyx_entry)
        cls.unwritten = WorshippedBeingFactory(name="The Unwritten", codex_entry=None)
        BeingNicknameFactory(being=cls.being, name="The Gory Goddess")
        BeingNicknameFactory(being=cls.being, name="Mother of Hunters")
        WorshipFeastDayFactory(
            being=cls.being, ic_month=10, ic_day=18, name="The Reaping Festival", lore="Masks."
        )
        WorshipFeastDayFactory(being=cls.being, ic_month=3, ic_day=1, name="First Blood", lore="")
        cls.tower = TarotCardFactory(name="The Tower")
        cls.death = TarotCardFactory(name="Death")
        BeingTarotCard.objects.create(being=cls.being, card=cls.tower, is_reversed=True)
        BeingTarotCard.objects.create(being=cls.being, card=cls.death)
        BeingResonanceFactory(
            being=cls.being,
            resonance=ResonanceFactory(name="Saevus"),
            tier=BeingResonanceTier.FAVORED,
        )
        BeingResonanceFactory(
            being=cls.being,
            resonance=ResonanceFactory(name="Ferox"),
            tier=BeingResonanceTier.ASSOCIATED,
        )
        BeingFacetFactory(being=cls.being, facet=FacetFactory(name="Scythe"))
        feud = BeingRelationship(
            being_a=cls.being, being_b=cls.calyx, valence=BeingRelationshipValence.FEUD
        )
        feud.set_story_from(cls.being.pk, "She stole the first harvest.")
        feud.set_story_from(cls.calyx.pk, "The Reaper takes what was never hers.")
        feud.save()
        BeingRelationship.objects.create(
            being_a=cls.being, being_b=cls.unwritten, valence=BeingRelationshipValence.ALLY
        )
        cls.staff = AccountFactory(username="staffer", is_staff=True)
        cls.player = AccountFactory(username="player")
        cls.roster_entry = RosterTenureFactory(player_data__account=cls.player).roster_entry

    def _retrieve(self, entry, account=None):
        client = APIClient()
        if account is not None:
            client.force_authenticate(user=account)
        response = client.get(f"/api/codex/entries/{entry.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["companion"]

    def test_every_group_in_order_and_nothing_the_reader_may_not_see(self):
        companion = self._retrieve(self.entry)
        rail = {
            group["label"]: [item["text"] for item in group["items"]] for group in companion["rail"]
        }
        self.assertEqual(
            [group["label"] for group in companion["rail"]],
            ["Domains", "Also called", "Feast days", "Cards", "Favored", "Associated", "Facets"],
        )
        self.assertEqual(rail["Domains"], ["Carnage, Hunters"])
        self.assertEqual(rail["Also called"], ["The Gory Goddess", "Mother of Hunters"])
        self.assertEqual(
            rail["Feast days"],
            ["First Blood · Thawing 1 (3/1)", "The Reaping Festival · Masquing 18 (10/18)"],
        )
        self.assertEqual(rail["Cards"], ["Death", "The Tower reversed"])
        self.assertEqual(rail["Favored"], ["Saevus"])
        self.assertEqual(rail["Associated"], ["Ferox"])
        self.assertEqual(rail["Facets"], ["Scythe"])
        feast_items = next(g for g in companion["rail"] if g["label"] == "Feast days")["items"]
        self.assertIsNone(feast_items[0]["anchor"])
        self.assertEqual(feast_items[1]["anchor"], "feast-10-18")
        self.assertEqual(
            companion["sections"],
            [
                {
                    "anchor": "feast-10-18",
                    "label": "Feast day",
                    "name": "The Reaping Festival",
                    "when": "Masquing 18 (10/18)",
                    "entry_id": None,
                    "body": "Masks.",
                }
            ],
        )

    def test_staff_read_the_feud_but_never_a_god_without_a_page(self):
        companion = self._retrieve(self.entry, self.staff)
        labels = [group["label"] for group in companion["rail"]]
        self.assertIn("Feud", labels)
        self.assertNotIn("Ally", labels)
        feud = next(g for g in companion["rail"] if g["label"] == "Feud")
        self.assertEqual(
            feud["items"],
            [
                {
                    "text": "Calyx",
                    "entry_id": self.calyx_entry.pk,
                    "anchor": f"relationship-{self.calyx.pk}",
                    "href": None,
                }
            ],
        )
        self.assertEqual(
            [(s["label"], s["name"], s["body"]) for s in companion["sections"]],
            [
                ("Feast day", "The Reaping Festival", "Masks."),
                ("Feud", "Calyx", "She stole the first harvest."),
            ],
        )

    def test_sworn_houses_list_the_published_houses_whose_patron_this_is(self):
        """#4205: a published house whose patron_nickname names this god is on the rail,
        linked to its page by site path; an unpublished one, or one sworn to another
        god, is not; and the group is absent when there is nobody."""
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.almanach import publish_house

        before = self._retrieve(self.entry)
        self.assertNotIn("Sworn houses", [g["label"] for g in before["rail"]])

        gory = self.being.nicknames.get(name="The Gory Goddess")
        piropa = publish_house(OrganizationFactory(name="House Piropa", patron_nickname=gory))
        OrganizationFactory(name="House Unpublished", patron_nickname=gory)
        other_name = BeingNicknameFactory(being=self.calyx, name="The Knight")
        publish_house(OrganizationFactory(name="House Elsewhere", patron_nickname=other_name))

        companion = self._retrieve(self.entry)
        sworn = next(g for g in companion["rail"] if g["label"] == "Sworn houses")
        self.assertEqual(
            sworn["items"],
            [
                {
                    "text": "House Piropa",
                    "entry_id": None,
                    "anchor": None,
                    "href": f"/orgs/{piropa.pk}",
                }
            ],
        )
        # The group comes last on the rail, after the relationships.
        self.assertEqual(companion["rail"][-1]["label"], "Sworn houses")

    def test_the_other_god_tells_its_own_side(self):
        companion = self._retrieve(self.calyx_entry, self.staff)
        self.assertEqual(
            [(s["label"], s["name"], s["entry_id"], s["body"]) for s in companion["sections"]],
            [("Feud", "The Fleshreaper", self.entry.pk, "The Reaper takes what was never hers.")],
        )

    def test_a_player_whose_character_knows_calyx_reads_the_feud(self):
        # The anonymous reading above shows the feud absent without the knowledge; the
        # account's knowledge cache would otherwise hold a reading from before this row.
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.calyx_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        companion = self._retrieve(self.entry, self.player)
        self.assertIn("Feud", [g["label"] for g in companion["rail"]])

    def test_an_entry_no_being_owns_is_not_claimed(self):
        reader = CompanionReader(visible_entry_ids=frozenset(), is_staff=True)
        self.assertIsNone(being_companion(CodexEntryFactory(is_public=True), reader))
