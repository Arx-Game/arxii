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
        # 1 session + 1 encounter + 2 prefetch (participants + opponents).
        with self.assertNumQueries(4):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class MyActionQueryCountTests(_SharedSetupMixin, TestCase):
    """``GET /api/combat/<pk>/my_action/`` — current-round action lookup."""

    def test_warm_my_action_query_count(self) -> None:
        url = f"/api/combat/{self.encounter.pk}/my_action/"
        self.client.get(url)  # warm-up
        # 4 queries on the second call:
        #   1. DRF session lookup
        #   2. CombatEncounter SELECT (get_object runs the .get(), even
        #      though SharedMemoryModel returns the identity-mapped row)
        #   3. RosterEntry.for_account(...).character_ids() — shared
        #      between IsEncounterParticipant and _get_participant via
        #      request._combat_viewer_character_ids
        #   4. CombatRoundAction.filter(participant, round_number)
        # The participants_cached + opponents_cached prefetches do NOT
        # fire on the warm call: they ran during warm-up and populated
        # attributes on the identity-mapped encounter, so the second
        # get_object hands back the same instance with those lists
        # already attached.
        with self.assertNumQueries(4):
            response = self.client.get(url)
        # 200 with None body when no action declared yet.
        self.assertEqual(response.status_code, 200)
