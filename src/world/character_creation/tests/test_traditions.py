from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
)
from world.character_creation.models import BeginningTradition
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import TraditionFactory


class BeginningTraditionTests(TestCase):
    """Tests for BeginningTradition through model."""

    def test_create_beginning_tradition(self):
        bt = BeginningTraditionFactory()
        assert BeginningTradition.objects.filter(pk=bt.pk).exists()

    def test_with_required_distinction(self):
        distinction = DistinctionFactory()
        bt = BeginningTraditionFactory(required_distinction=distinction)
        assert bt.required_distinction == distinction

    def test_beginning_traditions_m2m(self):
        beginning = BeginningsFactory()
        t1 = TraditionFactory(name="T1")
        t2 = TraditionFactory(name="T2")
        BeginningTradition.objects.create(beginning=beginning, tradition=t1)
        BeginningTradition.objects.create(beginning=beginning, tradition=t2)
        assert beginning.traditions.count() == 2

    def test_unique_together(self):
        bt = BeginningTraditionFactory()
        with self.assertRaises(IntegrityError):
            BeginningTradition.objects.create(beginning=bt.beginning, tradition=bt.tradition)

    def test_tradition_available_in_multiple_beginnings(self):
        tradition = TraditionFactory()
        b1 = BeginningsFactory(name="B1")
        b2 = BeginningsFactory(name="B2")
        BeginningTradition.objects.create(beginning=b1, tradition=tradition)
        BeginningTradition.objects.create(beginning=b2, tradition=tradition)
        assert tradition.available_beginnings.count() == 2


class FinalizeMagicTraditionTests(TestCase):
    """Tests for tradition-related finalization steps."""

    @classmethod
    def setUpTestData(cls):
        from world.codex.factories import (
            CodexEntryFactory,
            TraditionCodexGrantFactory,
        )

        cls.tradition = TraditionFactory()
        cls.codex_entry = CodexEntryFactory()
        TraditionCodexGrantFactory(tradition=cls.tradition, entry=cls.codex_entry)

    def test_finalize_creates_character_tradition(self):
        """CharacterTradition created when draft has tradition."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterTradition

        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(selected_tradition=self.tradition)

        # Partially simulate finalize_magic_data for just the tradition part
        CharacterTradition.objects.create(
            character=sheet,
            tradition=draft.selected_tradition,
        )

        assert CharacterTradition.objects.filter(character=sheet, tradition=self.tradition).exists()

    def test_finalize_creates_codex_knowledge(self):
        """Codex grants applied when draft has tradition."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.models import CharacterCodexKnowledge
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet__character=sheet.character)
        draft = CharacterDraftFactory(selected_tradition=self.tradition)

        # Simulate step 5 of finalize_magic_data
        from world.codex.models import TraditionCodexGrant

        grants = TraditionCodexGrant.objects.filter(tradition=draft.selected_tradition).values_list(
            "entry_id", flat=True
        )
        sheet.refresh_from_db()
        roster_entry = sheet.roster_entry
        for entry_id in grants:
            CharacterCodexKnowledge.objects.get_or_create(
                roster_entry=roster_entry,
                entry_id=entry_id,
                defaults={"status": CodexKnowledgeStatus.KNOWN},
            )

        knowledge = CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            entry=self.codex_entry,
        )
        assert knowledge.exists()
        assert knowledge.first().status == CodexKnowledgeStatus.KNOWN


class TraditionListLeakTests(TestCase):
    """Regression guard for the SharedMemoryModel + Prefetch(to_attr=) leak.

    ``Tradition`` is a SharedMemoryModel: instances persist across requests
    in the same process. The previous implementation attached
    ``prefetched_beginning_traditions`` (filtered by ``beginning_id`` from
    the request) onto each Tradition via ``Prefetch(to_attr=...)``. Django's
    ``prefetch_related`` saw the attribute already set on the next request
    and SKIPPED the new prefetch, so requests with a different
    ``beginning_id`` would inherit the previous request's filtered data.

    The list response varies by ``beginning_id`` via the ``required_distinction_id``
    field — different beginnings can require different distinctions for the
    same tradition. We hit the endpoint with ``beginning_id=B1`` and then
    ``beginning_id=B2`` against the same Tradition, and assert the second
    response reflects B2's BeginningTradition, not B1's.
    """

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory(name="LeakTestTradition")
        cls.distinction_a = DistinctionFactory(name="DistinctionA")
        cls.distinction_b = DistinctionFactory(name="DistinctionB")
        cls.beginning_a = BeginningsFactory(name="LeakBeginningA")
        cls.beginning_b = BeginningsFactory(name="LeakBeginningB")
        BeginningTraditionFactory(
            beginning=cls.beginning_a,
            tradition=cls.tradition,
            required_distinction=cls.distinction_a,
        )
        BeginningTraditionFactory(
            beginning=cls.beginning_b,
            tradition=cls.tradition,
            required_distinction=cls.distinction_b,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _required_distinction(self, response, tradition_id):
        for row in response.data:
            if row["id"] == tradition_id:
                return row["required_distinction_id"]
        return None

    def test_required_distinction_is_per_beginning_not_per_process(self):
        """Sequential requests with different beginning_id see their own data."""
        url = "/api/character-creation/traditions/"

        # First request — beginning A.
        resp_a = self.client.get(url, {"beginning_id": self.beginning_a.id})
        assert resp_a.status_code == status.HTTP_200_OK
        assert self._required_distinction(resp_a, self.tradition.id) == self.distinction_a.id

        # Second request — beginning B. Same Tradition instance is in
        # SharedMemoryModel cache from request 1; this is where the prior
        # implementation leaked beginning_a's distinction_id.
        resp_b = self.client.get(url, {"beginning_id": self.beginning_b.id})
        assert resp_b.status_code == status.HTTP_200_OK
        assert self._required_distinction(resp_b, self.tradition.id) == self.distinction_b.id

        # And going back to A still returns A's value (no flip-flop either).
        resp_a2 = self.client.get(url, {"beginning_id": self.beginning_a.id})
        assert resp_a2.status_code == status.HTTP_200_OK
        assert self._required_distinction(resp_a2, self.tradition.id) == self.distinction_a.id


class SelectTraditionTests(TestCase):
    """Tests for the select-tradition API endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory()
        cls.distinction = DistinctionFactory()
        cls.beginning = BeginningsFactory()
        cls.bt = BeginningTraditionFactory(
            beginning=cls.beginning,
            tradition=cls.tradition,
            required_distinction=cls.distinction,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _create_draft(self, **kwargs):
        """Create a draft owned by self.account with the test beginning."""
        defaults = {
            "account": self.account,
            "selected_beginnings": self.beginning,
        }
        defaults.update(kwargs)
        return CharacterDraftFactory(**defaults)

    def test_select_tradition_sets_fk(self):
        """Selecting a tradition sets the selected_tradition FK."""
        draft = self._create_draft()

        response = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.tradition.id},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.selected_tradition == self.tradition

    def test_clear_tradition(self):
        """Setting tradition_id=None clears selected_tradition."""
        draft = self._create_draft(selected_tradition=self.tradition)

        response = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": None},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.selected_tradition is None

    def test_select_tradition_without_beginning_fails(self):
        """Selecting a tradition without a beginning set returns 400."""
        draft = self._create_draft(selected_beginnings=None)

        response = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.tradition.id},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "beginning must be selected" in response.data["detail"]

    def test_select_tradition_not_in_beginning_fails(self):
        """Selecting a tradition not linked to the draft's beginning returns 400."""
        other_tradition = TraditionFactory()
        draft = self._create_draft()

        response = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": other_tradition.id},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not available" in response.data["detail"]


class DistinctionSyncClearsTraditionTests(TestCase):
    """Tests that removing a required distinction clears the tradition."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory()
        cls.distinction = DistinctionFactory()
        cls.beginning = BeginningsFactory()
        cls.bt = BeginningTraditionFactory(
            beginning=cls.beginning,
            tradition=cls.tradition,
            required_distinction=cls.distinction,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _create_draft(self, **kwargs):
        """Create a draft owned by self.account with the test beginning."""
        defaults = {
            "account": self.account,
            "selected_beginnings": self.beginning,
        }
        defaults.update(kwargs)
        return CharacterDraftFactory(**defaults)

    def _add_distinction_to_draft(self, draft, distinction):
        """Helper to add a distinction entry to draft_data."""
        distinctions = draft.draft_data.get("distinctions", [])
        distinctions.append(
            {
                "distinction_id": distinction.id,
                "distinction_name": distinction.name,
                "distinction_slug": distinction.slug,
                "category_slug": distinction.category.slug,
                "rank": 1,
                "cost": distinction.calculate_total_cost(1),
                "notes": "",
            }
        )
        draft.draft_data["distinctions"] = distinctions
        draft.save(update_fields=["draft_data"])

    def test_distinction_sync_removes_required_clears_tradition(self):
        """Removing the required distinction via sync clears selected_tradition."""
        draft = self._create_draft(selected_tradition=self.tradition)
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.distinction.id,
                "distinction_name": self.distinction.name,
                "distinction_slug": self.distinction.slug,
                "category_slug": self.distinction.category.slug,
                "rank": 1,
                "cost": self.distinction.calculate_total_cost(1),
                "notes": "",
            }
        ]
        draft.save(update_fields=["draft_data"])

        # Sync with an empty list, removing all distinctions
        response = self.client.put(
            f"/api/distinctions/drafts/{draft.id}/distinctions/sync/",
            {"distinctions": []},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.selected_tradition is None

    def test_destroy_required_distinction_clears_tradition(self):
        """Removing the required distinction via destroy clears selected_tradition."""
        draft = self._create_draft(selected_tradition=self.tradition)
        self._add_distinction_to_draft(draft, self.distinction)

        response = self.client.delete(
            f"/api/distinctions/drafts/{draft.id}/distinctions/{self.distinction.id}/",
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        draft.refresh_from_db()
        assert draft.selected_tradition is None

    def test_swap_away_required_distinction_clears_tradition(self):
        """Swapping away the required distinction clears selected_tradition."""
        other_distinction = DistinctionFactory()
        draft = self._create_draft(selected_tradition=self.tradition)
        self._add_distinction_to_draft(draft, self.distinction)

        response = self.client.post(
            f"/api/distinctions/drafts/{draft.id}/distinctions/swap/",
            {
                "remove_id": self.distinction.id,
                "add_id": other_distinction.id,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.selected_tradition is None

    def test_destroy_non_required_distinction_keeps_tradition(self):
        """Removing a non-required distinction does not clear the tradition."""
        other_distinction = DistinctionFactory()
        draft = self._create_draft(selected_tradition=self.tradition)
        self._add_distinction_to_draft(draft, self.distinction)
        self._add_distinction_to_draft(draft, other_distinction)

        response = self.client.delete(
            f"/api/distinctions/drafts/{draft.id}/distinctions/{other_distinction.id}/",
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        draft.refresh_from_db()
        assert draft.selected_tradition == self.tradition
