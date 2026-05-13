"""Query-count regression tests for ``CombatEncounterViewSet``.

Locks in the query budgets for the combat hot path. The encounter list /
detail / action endpoints rely on a ``participants_cached`` +
``opponents_cached`` prefetch chain plus a pre-computed serializer context
(``viewer_character_ids`` + ``is_gm``). Once warmed, subsequent requests
should run a small constant number of queries — no per-row filters, no
re-walks of the roster join chain.

If the counts here climb, the prefetch discipline has been broken
somewhere — likely a new ``.filter()`` / ``.get()`` /  ``.values()``
call that should have walked a cached relation instead. Pin the count,
document each query, and only relax it if the new query is genuinely
necessary.

Mirrors the sibling ``world.items.tests.test_item_view_query_counts``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class _SharedSetupMixin:
    """Common setup: GM account, two player participants, two opponents.

    Multiple participants + opponents ensures any per-row query would
    multiply.
    """

    @classmethod
    def setUpTestData(cls) -> None:  # type: ignore[misc]
        cls.gm_account = AccountFactory(username="qc_gm")
        cls.gm_character = CharacterFactory(db_key="QCGmChar")
        cls.gm_sheet = CharacterSheetFactory(character=cls.gm_character)
        cls.gm_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.gm_character,
            player_data__account=cls.gm_account,
        )

        cls.player_account = AccountFactory(username="qc_player")
        cls.player_character = CharacterFactory(db_key="QCPlayerChar")
        cls.player_sheet = CharacterSheetFactory(character=cls.player_character)
        cls.player_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.player_character,
            player_data__account=cls.player_account,
        )

        # Second player participant — proves participants prefetch holds.
        cls.player2_account = AccountFactory(username="qc_player2")
        cls.player2_character = CharacterFactory(db_key="QCPlayer2Char")
        cls.player2_sheet = CharacterSheetFactory(character=cls.player2_character)
        cls.player2_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.player2_character,
            player_data__account=cls.player2_account,
        )

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.gm_account, is_gm=True)

    def setUp(self) -> None:
        # Fresh encounter per test (avoids CombatNPC identity-map contamination
        # — same reason GMLifecycleTest does this).
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.participant2 = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player2_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CombatOpponentFactory(encounter=self.encounter)
        CombatOpponentFactory(encounter=self.encounter)
        self.client = APIClient()
        self.client.force_authenticate(user=self.player_account)


class EncounterListQueryCountTests(_SharedSetupMixin, TestCase):
    """``GET /api/combat/`` — list endpoint."""

    def test_warm_list_query_count(self) -> None:
        url = "/api/combat/"
        self.client.get(url)  # warm-up
        # 1 session + 1 encounters queryset + 1 prefetch chain (participants
        # + opponents land in a single batched prefetch path).
        with self.assertNumQueries(3):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class EncounterRetrieveQueryCountTests(_SharedSetupMixin, TestCase):
    """``GET /api/combat/<pk>/`` — detail endpoint."""

    def test_warm_retrieve_query_count(self) -> None:
        url = f"/api/combat/{self.encounter.pk}/"
        self.client.get(url)  # warm-up
        # 3 queries on the warm call: session + encounter + the lone
        # remaining roster lookup the permission classes need. The
        # account-level ``played_character_sheet_ids`` cached_property
        # makes that lookup a single Account attribute read after the
        # first request fills the cache, but the cache itself wasn't
        # filled before this test class's warm-up call, so it still
        # fires once during warm-up. (After warm-up: zero roster
        # queries.) The participants/opponents prefetches do not fire
        # on the warm call — they ran during warm-up and the
        # identity-mapped encounter retains the attribute.
        with self.assertNumQueries(3):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class MyActionQueryCountTests(_SharedSetupMixin, TestCase):
    """``GET /api/combat/<pk>/my_action/`` — current-round action lookup."""

    def test_warm_my_action_query_count(self) -> None:
        url = f"/api/combat/{self.encounter.pk}/my_action/"
        self.client.get(url)  # warm-up
        # 3 queries observed on the second call (captured via
        # ``CaptureQueriesContext``):
        #   1. DRF session lookup
        #   2. CombatEncounter SELECT (``get_object`` re-evaluates the
        #      queryset; SharedMemoryModel returns the same Python
        #      instance for the row)
        #   3. CombatRoundAction filter for this participant/round
        # Notably absent from the warm call:
        #   - participants/opponents prefetches (fired during warm-up;
        #     identity-mapped encounter retains the attribute)
        #   - the RosterEntry character_ids query (now served by
        #     ``Account.played_character_sheet_ids`` — a cached_property
        #     filled on warm-up and read directly from the in-memory
        #     Account instance thereafter)
        # This assertion is a regression guard: if a new query slips into
        # the hot path (a new ``.filter`` / ``.get`` / ``.values``), this
        # test will catch it.
        with self.assertNumQueries(3):
            response = self.client.get(url)
        # 200 with None body when no action declared yet.
        self.assertEqual(response.status_code, 200)
