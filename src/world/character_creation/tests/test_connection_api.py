from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.constants import (
    AnchorSource,
    OfferArrival,
    OfferChapter,
    QuestionKind,
)
from world.character_creation.factories import (
    DistinctionOfferFactory,
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.distinctions.factories import DistinctionFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory


class OriginTemplateConnectionReadTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user("reader", "r@example.com", "pw-123456")
        cls.template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        cls.org = OrganizationFactory(
            name="House Orisant",
            description="Shipping, tithe contracts. A very good cellar.",
            family=FamilyFactory(influence=4),
        )
        cls.q1 = GroupPromptFactory(template=cls.template, sort_order=0)
        cls.q1.anchor_orgs.add(cls.org)
        cls.kept = DistinctionFactory(name="Kept Close", cost_per_rank=15)
        cls.choice = OriginTemplateSlotChoiceFactory(
            slot=cls.q1, name="Courier", reputation_seed=200
        )
        cls.offer = DistinctionOfferFactory(
            distinction=cls.kept,
            chapter=OfferChapter.LINEAGE,
            origin_choice=cls.choice,
            arrives_as=OfferArrival.BUNDLED,
        )
        cls.q2 = OriginTemplateSlotFactory(
            template=cls.template,
            sort_order=1,
            kind=QuestionKind.PERSON,
            same_anchor_as=cls.q1,
            follow_up_to=cls.q1,
        )
        cls.q2.shown_for_choices.add(cls.choice)

    def test_slots_carry_kind_source_groups_show_when_and_grant(self):
        client = APIClient()
        client.force_authenticate(self.account)
        url = f"/api/character-creation/origin-templates/?beginning={self.template.beginning_id}"
        resp = client.get(url)
        assert resp.status_code == 200
        slots = {s["id"]: s for s in resp.json()[0]["slots"]}
        q1 = slots[self.q1.id]
        assert q1["kind"] == "group"
        assert q1["anchor_source"] == "listed"
        assert q1["groups"] == [
            {
                "id": self.org.id,
                "name": "House Orisant",
                "gloss": "Shipping, tithe contracts. A very good cellar.",
                "influence": 4,
            }
        ]
        choice = q1["choices"][0]
        assert choice["offers"] == [
            {
                "offer_id": self.offer.id,
                "distinction_id": self.kept.id,
                "name": "Kept Close",
                "player_line": "",
                "arrives_as": "bundled",
                "cost_per_rank": 15,
                "max_rank": self.kept.max_rank,
            }
        ]
        assert "reputation_seed" not in choice
        q2 = slots[self.q2.id]
        assert q2["kind"] == "person"
        assert q2["same_anchor_as"] == self.q1.id
        assert q2["follow_up_to"] == self.q1.id
        assert q2["shown_for_choice_ids"] == [self.choice.id]


class OriginTemplateGroupGlossTest(TestCase):
    """Gloss is the first LINE of the description, not the first sentence (#3660 ruling C)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user("glossreader", "gr@example.com", "pw-123456")
        cls.template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)

    def _gloss_for(self, org):
        client = APIClient()
        client.force_authenticate(self.account)
        url = f"/api/character-creation/origin-templates/?beginning={self.template.beginning_id}"
        resp = client.get(url)
        assert resp.status_code == 200
        row = next(r for r in resp.json() if r["id"] == self.template.id)
        group = next(g for s in row["slots"] for g in s["groups"] if g["id"] == org.id)
        return group["gloss"]

    def test_gloss_does_not_break_on_a_mid_sentence_abbreviation(self):
        """ "St." used to be mistaken for a sentence end (split on '. ') (#3660)."""
        org = OrganizationFactory(
            name="St. Orisant Trading Co",
            description="St. Orisant handles trade in salt and spice. A minor house.",
        )
        slot = GroupPromptFactory(template=self.template, sort_order=10)
        slot.anchor_orgs.add(org)
        assert self._gloss_for(org) == (
            "St. Orisant handles trade in salt and spice. A minor house."
        )

    def test_gloss_stops_at_the_first_newline(self):
        org = OrganizationFactory(
            name="Hollowmere Guild",
            description="A guild of glassblowers and lens-grinders.\nFounded in the old quarter.",
        )
        slot = GroupPromptFactory(template=self.template, sort_order=11)
        slot.anchor_orgs.add(org)
        assert self._gloss_for(org) == "A guild of glassblowers and lens-grinders."

    def test_gloss_is_empty_for_an_empty_description(self):
        org = OrganizationFactory(name="The Bare Guild", description="")
        slot = GroupPromptFactory(template=self.template, sort_order=12)
        slot.anchor_orgs.add(org)
        assert self._gloss_for(org) == ""

    def test_gloss_cuts_a_long_first_line_at_a_word_boundary(self):
        long_line = " ".join(["word"] * 40)  # 200 chars, well past the 160-char cap
        org = OrganizationFactory(name="The Verbose Guild", description=long_line)
        slot = GroupPromptFactory(template=self.template, sort_order=13)
        slot.anchor_orgs.add(org)
        gloss = self._gloss_for(org)
        assert len(gloss) <= 160
        assert not gloss.endswith("...")
        assert long_line.startswith(gloss)
        assert long_line[len(gloss)] == " "  # cut fell exactly on a word boundary


class OriginTemplateGroupQueryCountTest(TestCase):
    """groups_by_slot batches POOL and LISTED, so the count doesn't grow (#3660 ruling D)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user("qcount", "qc@example.com", "pw-123456")

    def _build_template(self, *, listed_count: int, pool_count: int, org_type):
        template = OriginTemplateFactory(allows_name_family=False, allows_no_family=True)
        for i in range(listed_count):
            slot = GroupPromptFactory(
                template=template, sort_order=i, anchor_source=AnchorSource.LISTED
            )
            slot.anchor_orgs.add(OrganizationFactory())
        for i in range(pool_count):
            GroupPromptFactory(
                template=template,
                sort_order=listed_count + i,
                anchor_source=AnchorSource.POOL,
                anchor_org_type=org_type,
            )
        return template

    def _query_count(self, template) -> int:
        # A fresh, never-touched-before client and beginning isolate the
        # comparison from cross-request cache effects (mirrors
        # test_upbringing_api's claimable_kind_ids query-count test).
        client = APIClient()
        client.force_authenticate(self.account)
        url = f"/api/character-creation/origin-templates/?beginning={template.beginning_id}"
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url)
        assert resp.status_code == 200
        return len(ctx.captured_queries)

    def test_group_query_count_does_not_grow_with_group_question_count(self):
        org_type = OrganizationTypeFactory()
        one_of_each = self._build_template(listed_count=1, pool_count=1, org_type=org_type)
        two_of_each = self._build_template(listed_count=2, pool_count=2, org_type=org_type)

        assert self._query_count(one_of_each) == self._query_count(two_of_each)
