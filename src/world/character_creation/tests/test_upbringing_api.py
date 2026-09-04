"""CG API for Upbringings (#3617)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.constants import FamilyPath
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import CharacterDraft
from world.roster.factories import (
    FamilyFactory,
    FamilyKindFactory,
    KinSlotPoolFactory,
    KinspersonFactory,
)


class UpbringingListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user(username="upb", password="x")
        cls.template = OriginTemplateFactory(cg_point_cost=2, allows_claim_family=True)
        cls.slot = OriginTemplateSlotFactory(template=cls.template, allows_text=False)
        cls.choice = OriginTemplateSlotChoiceFactory(slot=cls.slot, cost_per_influence=3)
        cls.gated = OriginTemplateFactory(beginning=cls.template.beginning, trust_required=50)

    def test_list_carries_paths_prompts_and_choices_and_hides_trust_gated(self):
        client = APIClient()
        client.force_authenticate(self.account)
        res = client.get(
            f"/api/character-creation/origin-templates/?beginning={self.template.beginning_id}"
        )
        assert res.status_code == 200
        rows = res.json()
        assert [r["id"] for r in rows] == [self.template.id]
        row = rows[0]
        assert row["cg_point_cost"] == 2
        assert row["allows_claim_family"]
        assert row["allows_name_family"]
        assert not row["allows_no_family"]
        assert row["named_family_kind"] == self.template.named_family_kind_id
        slot = row["slots"][0]
        assert slot["applies_to"] == FamilyPath.ANY
        assert slot["allows_text"] is False
        assert slot["choices"][0] == {
            "id": self.choice.id,
            "name": self.choice.name,
            "description": "",
            "cg_point_cost": 0,
            "cost_per_influence": 3,
            "sort_order": self.choice.sort_order,
        }

    def test_claimable_kind_ids_query_count_does_not_grow_with_template_count(self):
        """claimable_kind_ids is one batched query per response, not one per row.

        Two independent beginnings (never touched before in this test, so
        SharedMemoryModel's identity map holds no warm state for either) isolate
        the comparison from cross-request cache effects: 1 template vs 3
        templates must cost the same number of queries.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        one_beginning = BeginningsFactory()
        one_template = OriginTemplateFactory(beginning=one_beginning)
        one_template.claimable_kinds.add(FamilyKindFactory())

        three_beginning = BeginningsFactory()
        for _ in range(3):
            template = OriginTemplateFactory(beginning=three_beginning)
            template.claimable_kinds.add(FamilyKindFactory())

        # Separate clients (no shared session) so both requests pay the same
        # one-time session-creation cost - the comparison isolates the
        # origin-templates query count, not Django's session bookkeeping.
        client_one = APIClient()
        client_one.force_authenticate(self.account)
        with CaptureQueriesContext(connection) as ctx_one:
            res_one = client_one.get(
                f"/api/character-creation/origin-templates/?beginning={one_beginning.id}"
            )
        assert res_one.status_code == 200
        assert len(res_one.json()) == 1

        client_three = APIClient()
        client_three.force_authenticate(self.account)
        with CaptureQueriesContext(connection) as ctx_three:
            res_three = client_three.get(
                f"/api/character-creation/origin-templates/?beginning={three_beginning.id}"
            )
        assert res_three.status_code == 200
        assert len(res_three.json()) == 3

        assert len(ctx_one.captured_queries) == len(ctx_three.captured_queries)


class DraftUpbringingPatchTest(TestCase):
    def setUp(self):
        self.account = AccountDB.objects.create_user(username="patcher", password="x")
        self.template = OriginTemplateFactory(allows_claim_family=True)
        self.draft = CharacterDraftFactory(
            account=self.account,
            selected_area=self.template.beginning.starting_area,
            selected_beginnings=self.template.beginning,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self.url = f"/api/character-creation/drafts/{self.draft.pk}/"

    def test_patch_selects_upbringing_and_path(self):
        res = self.client.patch(
            self.url, {"selected_origin_template_id": self.template.id}, format="json"
        )
        assert res.status_code == 200, res.json()
        assert res.json()["selected_origin_template"]["id"] == self.template.id
        res = self.client.patch(self.url, {"family_path": FamilyPath.NAMED}, format="json")
        assert res.status_code == 200
        res = self.client.patch(
            self.url,
            {"draft_data": {"new_family_name": "Vale", "origin_choices": {"1": None}}},
            format="json",
        )
        assert res.status_code == 200
        draft = CharacterDraft.objects.get(pk=self.draft.pk)
        assert draft.family_path == FamilyPath.NAMED
        assert draft.draft_data["new_family_name"] == "Vale"

    def test_patch_refuses_a_path_the_upbringing_lacks(self):
        self.client.patch(
            self.url, {"selected_origin_template_id": self.template.id}, format="json"
        )
        res = self.client.patch(self.url, {"family_path": FamilyPath.NONE}, format="json")
        assert res.status_code == 400

    def test_patch_refuses_a_foreign_upbringing(self):
        other = OriginTemplateFactory()
        res = self.client.patch(self.url, {"selected_origin_template_id": other.id}, format="json")
        assert res.status_code == 400

    def test_changing_upbringing_clears_downstream_keys(self):
        self.client.patch(
            self.url, {"selected_origin_template_id": self.template.id}, format="json"
        )
        self.client.patch(self.url, {"draft_data": {"new_family_name": "Vale"}}, format="json")
        second = OriginTemplateFactory(beginning=self.template.beginning, allows_no_family=True)
        self.client.patch(self.url, {"selected_origin_template_id": second.id}, format="json")
        draft = CharacterDraft.objects.get(pk=self.draft.pk)
        assert "new_family_name" not in draft.draft_data

    def test_switching_family_path_clears_claimed_family_and_kin_claims(self):
        """A PATCH that switches paths drops the old path's family/kin claims (#3617 review)."""
        self.client.patch(
            self.url, {"selected_origin_template_id": self.template.id}, format="json"
        )
        self.client.patch(self.url, {"family_path": FamilyPath.CLAIMED}, format="json")
        draft = CharacterDraft.objects.get(pk=self.draft.pk)
        draft.family = FamilyFactory()
        draft.claimed_kin_slot = KinspersonFactory()
        draft.claimed_kin_pool = KinSlotPoolFactory()
        draft.save(update_fields=["family", "claimed_kin_slot", "claimed_kin_pool"])

        res = self.client.patch(self.url, {"family_path": FamilyPath.NAMED}, format="json")
        assert res.status_code == 200

        draft.refresh_from_db()
        assert draft.family_path == FamilyPath.NAMED
        assert draft.family is None
        assert draft.claimed_kin_slot is None
        assert draft.claimed_kin_pool is None

    def test_patching_the_same_family_path_is_a_noop(self):
        self.client.patch(
            self.url, {"selected_origin_template_id": self.template.id}, format="json"
        )
        self.client.patch(self.url, {"family_path": FamilyPath.CLAIMED}, format="json")
        draft = CharacterDraft.objects.get(pk=self.draft.pk)
        family = FamilyFactory()
        draft.family = family
        draft.save(update_fields=["family"])

        res = self.client.patch(self.url, {"family_path": FamilyPath.CLAIMED}, format="json")
        assert res.status_code == 200

        draft.refresh_from_db()
        assert draft.family_path == FamilyPath.CLAIMED
        assert draft.family == family
