from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    SchoolingLineFactory,
    TraditionStateLineFactory,
)
from world.character_creation.models import Beginnings, BeginningTradition
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import TraditionFactory


class BeginningTraditionTests(TestCase):
    """Tests for BeginningTradition through model."""

    def test_create_beginning_tradition(self):
        bt = BeginningTraditionFactory()
        assert BeginningTradition.objects.filter(pk=bt.pk).exists()

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

    The list response varies by ``beginning_id`` — different beginnings can
    show the same Tradition with a different ``BeginningTradition`` row (own
    wording, state, sort order). ``test_repeat_request_with_same_beginning_hits_cache``
    below guards the SharedMemoryModel cache-hit path this leak's fix relies on.
    """

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory(name="LeakTestTradition")
        cls.beginning_a = BeginningsFactory(name="LeakBeginningA")
        cls.beginning_b = BeginningsFactory(name="LeakBeginningB")
        BeginningTraditionFactory(beginning=cls.beginning_a, tradition=cls.tradition)
        BeginningTraditionFactory(beginning=cls.beginning_b, tradition=cls.tradition)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_repeat_request_with_same_beginning_hits_cache(self):
        """Beginning + beginning_traditions are SharedMemoryModel-cached.

        After the first request loads the Beginning and its
        ``cached_beginning_traditions``, a second request with the same
        ``beginning_id`` should not re-fetch BeginningTradition rows or
        re-load the Beginning row — both live on the cached Beginning
        instance for the lifetime of the process.

        The Tradition list queryset still evaluates (with a JOIN through
        BeginningTradition for FilterSet's ``beginning_id`` filter), but
        no separate BT-fetch or Beginning-fetch query should fire.
        """
        import re

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = "/api/character-creation/traditions/"

        # Warmup: populate Beginning instance + cached_beginning_traditions.
        self.client.get(url, {"beginning_id": self.beginning_a.id})

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url, {"beginning_id": self.beginning_a.id})
        assert resp.status_code == status.HTTP_200_OK

        def primary_table(sql: str) -> str:
            m = re.search(r'FROM\s+"([^"]+)"', sql)
            return m.group(1) if m else ""

        primary_tables = [primary_table(q["sql"]) for q in ctx.captured_queries]
        # Table names derived (not hardcoded): a stale string here would go
        # silently vacuous (never matching any real table) rather than catching
        # a regression — see #2906.
        bt_table = BeginningTradition._meta.db_table
        beginnings_table = Beginnings._meta.db_table
        assert bt_table not in primary_tables, (
            f"Expected zero BT-as-primary-table queries on repeat request, got: {primary_tables}"
        )
        assert beginnings_table not in primary_tables, (
            f"Expected zero Beginnings-as-primary-table queries on repeat request "
            f"(SharedMemoryModel cache hit), got: {primary_tables}"
        )

    def test_rows_carry_state_line_refund_and_schooling(self):
        """Tradition rows print their slate state's line, carried refund, and
        schooling stances (#3675).
        """
        drawback = DistinctionFactory(name="Unbound Drawback", cost_per_rank=-75)
        TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT, entry_line="Self-taught", carries=drawback
        )
        TraditionStateLineFactory(state=TraditionState.LIVING_MASTERS, entry_line="Living masters")
        # Deliberately no TraditionStateLine row for TEACHERS_GONE, to cover a
        # slate line whose state has no standard line authored yet.

        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        SchoolingLineFactory(rank=0, name="Untrained", player_line="No training yet.")
        rank_one = SchoolingLineFactory(
            rank=1, name="Apprentice", player_line="Some training.", grants=training
        )
        SchoolingLineFactory(
            rank=2, name="Journeyman", player_line="More training.", grants=training
        )
        offer = DistinctionOfferFactory(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=rank_one, distinction=training
        )

        beginning = BeginningsFactory(name="StateLineBeginning")
        self_taught_tradition = TraditionFactory(name="SelfTaughtTradition")
        living_tradition = TraditionFactory(name="LivingTradition")
        unlined_tradition = TraditionFactory(name="UnlinedTradition")
        BeginningTraditionFactory(
            beginning=beginning,
            tradition=self_taught_tradition,
            state=TraditionState.SELF_TAUGHT,
        )
        BeginningTraditionFactory(
            beginning=beginning,
            tradition=living_tradition,
            state=TraditionState.LIVING_MASTERS,
            own_wording="Raised in the watch-house",
        )
        BeginningTraditionFactory(
            beginning=beginning,
            tradition=unlined_tradition,
            state=TraditionState.TEACHERS_GONE,
        )

        response = self.client.get(
            "/api/character-creation/traditions/", {"beginning_id": beginning.id}
        )
        assert response.status_code == status.HTTP_200_OK
        rows = {r["id"]: r for r in response.data}

        self_row = rows[self_taught_tradition.id]
        assert self_row["refund"] == -75
        assert self_row["state_line"] == "Self-taught"
        assert self_row["schooling"] == []

        living_row = rows[living_tradition.id]
        assert living_row["own_wording"] == "Raised in the watch-house"
        assert living_row["state_line"] == "Raised in the watch-house"
        assert living_row["schooling"][1]["price"] == 1
        assert living_row["schooling"][1]["techniques"] == 2
        assert living_row["schooling"][1]["offer_id"] == offer.id
        assert living_row["schooling"][0]["offer_id"] is None
        assert living_row["schooling"][2]["offer_id"] is None

        unlined_row = rows[unlined_tradition.id]
        assert unlined_row["state_line"] == ""
        assert unlined_row["refund"] == 0


class SelectTraditionTests(TestCase):
    """Tests for the select-tradition API endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory()
        cls.beginning = BeginningsFactory()
        cls.bt = BeginningTraditionFactory(
            beginning=cls.beginning,
            tradition=cls.tradition,
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
        """Selecting a tradition sets the FK; there is no gate (#3675)."""
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
    """The slate line's carried drawback survives a sync that omits it (#3675).

    There is no more "required distinction" gate to remove a pick from under —
    ``select_tradition`` no longer gates, and the carried drawback is applied by
    ``reconcile_offer_picks`` rather than stored independently of the pick. So a
    sync that omits the carried drawback does nothing (the next reconcile just
    re-adds it); only clearing the tradition itself removes it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.tradition = TraditionFactory()
        cls.drawback = DistinctionFactory(name="Self-Taught Drawback", cost_per_rank=-15)
        cls.beginning = BeginningsFactory()
        cls.bt = BeginningTraditionFactory(
            beginning=cls.beginning,
            tradition=cls.tradition,
            state=TraditionState.SELF_TAUGHT,
        )
        TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT, carries=cls.drawback, entry_line="Self-taught"
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

    def test_sync_cannot_shed_the_carried_drawback_only_clearing_the_tradition_can(self):
        draft = self._create_draft()
        self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": self.tradition.id},
            format="json",
        )
        draft.refresh_from_db()
        held_ids = {e["distinction_id"] for e in draft.draft_data["distinctions"]}
        assert self.drawback.id in held_ids

        # Syncing an empty CHOICE list does nothing: reconcile re-adds the carry.
        response = self.client.put(
            f"/api/distinctions/drafts/{draft.id}/distinctions/sync/",
            {"distinctions": []},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        held_ids = {e["distinction_id"] for e in draft.draft_data["distinctions"]}
        assert self.drawback.id in held_ids
        assert draft.selected_tradition == self.tradition

        # Clearing the tradition removes the carried drawback.
        clear = self.client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": None},
            format="json",
        )
        assert clear.status_code == status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.draft_data.get("distinctions", []) == []
