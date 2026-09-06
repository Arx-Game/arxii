"""The Upbringing Builder: one page for an Upbringing, its questions and answers (#3660)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import AnchorSource, QuestionKind
from world.character_creation.factories import (
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
)
from world.character_creation.models import (
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionFactory
from world.societies.factories import OrganizationFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class BuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("builderauthor")
        cls.writer = ContentContributorFactory(name="Builder Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("builderunlinked")
        cls.template = OriginTemplateFactory(
            name="Born to a Household", allows_name_family=False, allows_no_family=True
        )
        cls.q1 = GroupPromptFactory(template=cls.template, sort_order=0, name="House")
        cls.q1.anchor_orgs.add(OrganizationFactory(name="House Orisant"))
        cls.livery = OriginTemplateSlotChoiceFactory(slot=cls.q1, name="Livery at table")


class BuilderGetTest(BuilderTestCase):
    def test_renders_upbringing_questions_and_answers(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Born to a Household" in body
        assert "Pick a group" in body
        assert "Livery at table" in body
        assert "Matches 1 group today" in body  # live line for the LISTED source
        assert "House Orisant" in body

    def test_unlinked_contributor_sees_setup_guidance(self):
        self.client.force_login(self.unlinked)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert "link a contributor" in resp.content.decode().lower()


class BuilderSaveTest(BuilderTestCase):
    def _post_data(self, **overrides):
        data = {
            "beginning": self.template.beginning_id,
            "name": "Born to a Household",
            "frame_narrative": "You stood through dinners.",
            "cg_point_cost": "0",
            "trust_required": "0",
            "allows_no_family": "on",
            "is_active": "on",
            "sort_order": "1",
            # question formset: one existing question
            "q-TOTAL_FORMS": "1",
            "q-INITIAL_FORMS": "1",
            "q-MIN_NUM_FORMS": "0",
            "q-MAX_NUM_FORMS": "1000",
            "q-0-id": str(self.q1.pk),
            "q-0-name": "House",
            "q-0-prompt": "Which Humble house kept you",
            "q-0-example": "",
            "q-0-sort_order": "0",
            "q-0-is_required": "on",
            "q-0-applies_to": "any",
            "q-0-kind": QuestionKind.GROUP,
            "q-0-connection_kind": "served",
            "q-0-life_stage": "childhood",
            "q-0-anchor_source": AnchorSource.LISTED,
            "q-0-exclude_covert": "on",
            "q-0-anchor_orgs": [str(self.q1.anchor_orgs.first().pk)],
            # answers formset for q1
            f"a{self.q1.pk}-TOTAL_FORMS": "1",
            f"a{self.q1.pk}-INITIAL_FORMS": "1",
            f"a{self.q1.pk}-MIN_NUM_FORMS": "0",
            f"a{self.q1.pk}-MAX_NUM_FORMS": "1000",
            f"a{self.q1.pk}-0-id": str(self.livery.pk),
            f"a{self.q1.pk}-0-name": "Livery at table",
            f"a{self.q1.pk}-0-description": "You stood through the dinners.",
            f"a{self.q1.pk}-0-cg_point_cost": "5",
            f"a{self.q1.pk}-0-cost_per_influence": "1",
            f"a{self.q1.pk}-0-reputation_seed": "100",
            f"a{self.q1.pk}-0-trust_required": "0",
            f"a{self.q1.pk}-0-is_active": "on",
            f"a{self.q1.pk}-0-sort_order": "0",
        }
        data.update(overrides)
        return data

    def test_save_writes_rows_and_credits_the_operator(self):
        self.client.force_login(self.author)
        kept = DistinctionFactory(name="Kept Close")
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]),
            self._post_data(**{f"a{self.q1.pk}-0-grants_distinction": str(kept.pk)}),
        )
        assert resp.status_code == 302
        self.template.refresh_from_db()
        assert self.template.written_by == self.writer
        choice = OriginTemplateSlotChoice.objects.get(pk=self.livery.pk)
        assert choice.cg_point_cost == 5
        assert choice.grants_distinction == kept
        assert choice.written_by == self.writer
        assert OriginTemplateSlot.objects.get(pk=self.q1.pk).written_by == self.writer

    def test_review_stamps_review_only(self):
        self.client.force_login(self.author)
        resp = self.client.post(reverse("admin_upbringing_builder_review", args=[self.template.pk]))
        assert resp.status_code == 302
        template = OriginTemplate.objects.get(pk=self.template.pk)
        assert template.reviewed_by == self.writer
        assert template.written_by is None

    def test_unlinked_contributor_cannot_save(self):
        self.client.force_login(self.unlinked)
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]), self._post_data()
        )
        assert resp.status_code == 200  # re-rendered with the setup guidance
        assert OriginTemplateSlotChoice.objects.get(pk=self.livery.pk).cg_point_cost == 0
