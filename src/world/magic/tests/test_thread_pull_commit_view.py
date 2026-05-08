"""Tests for ThreadPullCommitView (POST /api/magic/thread-pull-commit/).

Covers:
- Ephemeral happy path (no encounter, COVENANT_ROLE thread): balance decremented;
  no CombatPull row created; response carries resonance_spent, anima_spent,
  resolved_effects.
- Combat happy path (encounter + participant supplied): a CombatPull row exists
  for the participant/round.
- ProtagonismLockedError: locked sheet returns HTTP 400.
- ResonanceInsufficient: balance below cost returns HTTP 400.
- InvalidImbueAmount: empty thread list, ownership mismatch, or anchor-not-in-action
  returns HTTP 400.
- NoMatchingWornFacetItemsError: a FACET thread with no matching worn item returns
  HTTP 400 with the typed user_message.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatPull
from world.covenants.factories import CovenantRoleFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    FacetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    with_corruption_at_stage,
)
from world.magic.models import CharacterResonance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

_COMMIT_URL = "/api/magic/thread-pull-commit/"


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Also sets character.account so service functions that navigate
    character_sheet.character.account resolve correctly.
    Returns the created RosterTenure.  Reuses an existing PlayerData row if the
    account already has one.
    """
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


def _make_covenant_role_thread(sheet, resonance):
    """Create a COVENANT_ROLE Thread for ``sheet`` using the direct factory path.

    COVENANT_ROLE threads are always-in-action (they bypass _anchor_in_action),
    making them the simplest anchor for ephemeral-context happy-path tests.
    The ThreadFactory defaults to TRAIT kind, so we override the discriminator
    and typed FK directly.
    """
    role = CovenantRoleFactory()
    return ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.COVENANT_ROLE,
        target_trait=None,
        target_covenant_role=role,
    )


class ThreadPullCommitViewEphemeralHappyPathTests(APITestCase):
    """Ephemeral (no encounter) pull commit — balance debited, no CombatPull row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="pull_commit_ephemeral")
        cls.character = CharacterFactory(db_key="PullCommitEphemeral")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

        # Per-tier cost row.
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

        # COVENANT_ROLE thread — always-in-action, simplest case.
        cls.thread = _make_covenant_role_thread(cls.sheet, cls.resonance)
        # Authored pull effect so resolved_effects is non-empty.
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=3,
        )

    def test_ephemeral_pull_decrements_balance(self) -> None:
        """POST commit → CharacterResonance.balance decremented by resonance_cost."""
        self.client.force_authenticate(user=self.account)

        before = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance

        resp = self.client.post(
            _COMMIT_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        after = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance
        self.assertEqual(before - after, 2)

    def test_ephemeral_pull_no_combat_pull_row(self) -> None:
        """Ephemeral pull must NOT create a CombatPull row."""
        self.client.force_authenticate(user=self.account)
        pre = CombatPull.objects.count()

        resp = self.client.post(
            _COMMIT_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(CombatPull.objects.count(), pre)

    def test_ephemeral_pull_response_shape(self) -> None:
        """Response must contain resonance_spent, anima_spent, resolved_effects."""
        self.client.force_authenticate(user=self.account)

        resp = self.client.post(
            _COMMIT_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        data = resp.data
        self.assertIn("resonance_spent", data)
        self.assertIn("anima_spent", data)
        self.assertIn("resolved_effects", data)
        self.assertEqual(data["resonance_spent"], 2)
        self.assertIsInstance(data["resolved_effects"], list)
        self.assertGreater(len(data["resolved_effects"]), 0)


class ThreadPullCommitViewCombatHappyPathTests(APITestCase):
    """Combat-context pull commit — CombatPull row persisted."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="pull_commit_combat")
        cls.character = CharacterFactory(db_key="PullCommitCombat")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

        # COVENANT_ROLE thread — always-in-action in combat too.
        cls.thread = _make_covenant_role_thread(cls.sheet, cls.resonance)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=3,
        )

        # Combat context
        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )

    def test_combat_pull_creates_combat_pull_row(self) -> None:
        """POST commit with combat context → CombatPull row for the participant/round."""
        self.client.force_authenticate(user=self.account)
        pre = CombatPull.objects.count()

        resp = self.client.post(
            _COMMIT_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
                "action_context": {
                    "combat_encounter_id": self.encounter.pk,
                    "combat_participant_id": self.participant.pk,
                },
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(CombatPull.objects.count() - pre, 1)
        pull = CombatPull.objects.filter(
            participant=self.participant,
            encounter=self.encounter,
            round_number=1,
        ).first()
        self.assertIsNotNone(pull)


class ThreadPullCommitViewErrorTests(APITestCase):
    """Error path tests for ThreadPullCommitView."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Owner account
        cls.account = AccountFactory(username="pull_commit_errors")
        cls.character = CharacterFactory(db_key="PullCommitErrors")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        # Non-owner account + sheet
        cls.other_account = AccountFactory(username="pull_commit_other")
        cls.other_character = CharacterFactory(db_key="PullCommitOther")
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)
        _link_account_to_sheet(cls.other_account, cls.other_character, cls.other_sheet)

        cls.resonance = ResonanceFactory()
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

        ThreadPullCostFactory(tier=1, resonance_cost=5, anima_per_thread=1)

        # Thread for the owner
        cls.thread = _make_covenant_role_thread(cls.sheet, cls.resonance)
        # Thread for the other sheet (ownership mismatch)
        cls.other_thread = _make_covenant_role_thread(cls.other_sheet, cls.resonance)

    def _post(self, payload: dict) -> object:
        self.client.force_authenticate(user=self.account)
        return self.client.post(_COMMIT_URL, payload, format="json")

    def test_protagonism_locked_returns_400(self) -> None:
        """ProtagonismLockedError → HTTP 400.

        Set stage-5 corruption (the only current source of protagonism lock).
        Use a separate resonance so the corruption resonance row doesn't
        conflict with any row the other tests create on self.resonance.
        """
        # Give enough balance on the pull resonance so the only gate is the lock.
        lock_resonance = ResonanceFactory()
        cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=lock_resonance,
            balance=20,
            lifetime_earned=20,
        )
        # Lock the sheet by installing stage-5 corruption (any resonance works).
        with_corruption_at_stage(self.sheet, lock_resonance, stage=5)
        # Reload to clear cached_property.
        from world.character_sheets.models import CharacterSheet

        fresh = CharacterSheet.objects.get(pk=self.sheet.pk)

        # Need a thread on the locked sheet using lock_resonance.
        lock_thread = _make_covenant_role_thread(fresh, lock_resonance)

        try:
            self.client.force_authenticate(user=self.account)
            resp = self.client.post(
                _COMMIT_URL,
                {
                    "character_sheet_id": fresh.pk,
                    "resonance_id": lock_resonance.pk,
                    "tier": 1,
                    "thread_ids": [lock_thread.pk],
                },
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        finally:
            lock_thread.delete()
            cr.delete()

    def test_resonance_insufficient_returns_400(self) -> None:
        """ResonanceInsufficient (balance 0 < cost 5) → HTTP 400."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        try:
            resp = self._post(
                {
                    "character_sheet_id": self.sheet.pk,
                    "resonance_id": self.resonance.pk,
                    "tier": 1,
                    "thread_ids": [self.thread.pk],
                }
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        finally:
            CharacterResonance.objects.filter(
                character_sheet=self.sheet, resonance=self.resonance
            ).delete()

    def test_empty_thread_list_returns_400(self) -> None:
        """Empty thread_ids list fails DRF allow_empty=False validation → HTTP 400."""
        resp = self._post(
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [],
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_thread_not_owned_returns_400(self) -> None:
        """Passing a thread belonging to another sheet → HTTP 400 (InvalidImbueAmount)."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=20,
            lifetime_earned=20,
        )
        try:
            # The thread belongs to other_sheet, not self.sheet.
            resp = self._post(
                {
                    "character_sheet_id": self.sheet.pk,
                    "resonance_id": self.resonance.pk,
                    "tier": 1,
                    "thread_ids": [self.other_thread.pk],
                }
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        finally:
            CharacterResonance.objects.filter(
                character_sheet=self.sheet, resonance=self.resonance
            ).delete()

    def test_combat_encounter_without_participant_returns_400(self) -> None:
        """combat_encounter_id set but combat_participant_id absent → HTTP 400."""
        encounter = CombatEncounterFactory(round_number=1)
        resp = self._post(
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
                "action_context": {
                    "combat_encounter_id": encounter.pk,
                },
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ThreadPullCommitViewFacetErrorTests(APITestCase):
    """NoMatchingWornFacetItemsError → HTTP 400 with typed user_message."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="pull_commit_facet")
        cls.character = CharacterFactory(db_key="PullCommitFacet")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

        # FACET thread — error fires when no worn item bears this facet.
        facet = FacetFactory()
        cls.facet_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_trait=None,
            target_facet=facet,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=2,
        )

    def test_facet_no_worn_items_returns_400(self) -> None:
        """FACET thread with no worn item bearing the facet → HTTP 400 with user_message."""
        self.client.force_authenticate(user=self.account)

        resp = self.client.post(
            _COMMIT_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.facet_thread.pk],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        from world.magic.exceptions import NoMatchingWornFacetItemsError

        # The response should carry the typed exception's user_message.
        err_str = str(resp.data)
        self.assertIn(NoMatchingWornFacetItemsError.user_message, err_str)
