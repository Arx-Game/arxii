from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.constants import QuestionKind
from world.character_creation.factories import (
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.distinctions.factories import DistinctionFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory


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
            slot=cls.q1, name="Courier", grants_distinction=cls.kept, reputation_seed=200
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
                "gloss": "Shipping, tithe contracts.",
                "influence": 4,
            }
        ]
        choice = q1["choices"][0]
        assert choice["grants_distinction"] == {
            "id": self.kept.id,
            "name": "Kept Close",
            "cost_per_rank": 15,
            "secret_by_default": False,
        }
        assert "reputation_seed" not in choice
        q2 = slots[self.q2.id]
        assert q2["kind"] == "person"
        assert q2["same_anchor_as"] == self.q1.id
        assert q2["follow_up_to"] == self.q1.id
        assert q2["shown_for_choice_ids"] == [self.choice.id]
