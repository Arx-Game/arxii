"""Tests for the challenge / accept / decline / withdraw / yield actions (Tasks 10, 11, 12).

Tests are built using setUp (not setUpTestData) because CharacterFactory creates
Evennia ObjectDB instances (DbHolder — not deepcopyable, which breaks setUpTestData).

Scenarios covered (Task 10 — challenge):
  (a) Consenting co-located target → PENDING DuelChallenge created, success result.
  (b) Target whose SocialConsentPreference blocks all social actions → blocked, no challenge.
  (c) Self-challenge → rejected, no challenge.
  (d) Target in a different room → rejected, no challenge.
  (e) Actor has no CharacterSheet → rejected, no challenge.

Scenarios covered (Task 11 — accept / decline / withdraw):
  (f) Challenged PC accepts → ACCEPTED challenge, CombatEncounter created + linked.
  (g) Challenged PC declines → DECLINED challenge, no encounter.
  (h) Challenger withdraws → WITHDRAWN challenge, no encounter.
  (i) Only the challenged PC may accept/decline (challenger is rejected).
  (j) Only the challenger may withdraw (challenged is rejected).
  (k) Non-PENDING challenge cannot be accepted/declined/withdrawn.

Scenarios covered (Task 12 — yield):
  (l) Participant in active DUEL yields → encounter COMPLETED, other duelist is duel_winner.
  (m) Actor not in any duel → clean failure ("You are not in a duel.").
  (n) Actor has no CharacterSheet → clean failure.
"""

from __future__ import annotations

import django.test

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import DuelChallengeStatus, EncounterStatus
from world.combat.duels import create_pvp_duel
from world.combat.factories import DuelChallengeFactory
from world.combat.models import DuelChallenge
from world.consent.factories import SocialConsentPreferenceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _make_room(name: str = "TestRoom") -> object:
    """Create a Room ObjectDB instance."""
    return ObjectDBFactory(
        db_key=name,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_pc(name: str, room: object) -> tuple:
    """Return (actor ObjectDB, CharacterSheet) with an active RosterTenure.

    Wires: Character → CharacterSheet → RosterEntry → RosterTenure (active).
    The tenure chain is required for _tenure_blocks_actor to look up consent prefs.
    """
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry)
    return actor, sheet


class ChallengeActionConsentingTargetTests(django.test.TestCase):
    """challenge at a consenting co-located target → PENDING DuelChallenge."""

    def setUp(self) -> None:
        self.room = _make_room("Arena")
        self.actor, self.actor_sheet = _make_pc("Challenger", self.room)
        self.target, self.target_sheet = _make_pc("Target", self.room)

    def test_challenge_creates_pending_duel_challenge(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertTrue(result.success, msg=result.message)
        challenge = DuelChallenge.objects.filter(
            challenger_sheet=self.actor_sheet,
            challenged_sheet=self.target_sheet,
            status=DuelChallengeStatus.PENDING,
        ).first()
        self.assertIsNotNone(challenge, "Expected a PENDING DuelChallenge to be created")

    def test_challenge_result_includes_challenge_id(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertTrue(result.success, msg=result.message)
        self.assertIn("challenge_id", result.data)


class ChallengeActionConsentBlockedTests(django.test.TestCase):
    """challenge at a target who has opted out of social actions → blocked."""

    def setUp(self) -> None:
        self.room = _make_room("BlockedArena")
        self.actor, self.actor_sheet = _make_pc("BlockedChallenger", self.room)
        self.target, self.target_sheet = _make_pc("BlockingTarget", self.room)
        # Give the target a tenure so _tenure_blocks_actor can find it
        tenure = self.target_sheet.roster_entry.current_tenure
        # Opt out of all social actions
        SocialConsentPreferenceFactory(tenure=tenure, allow_social_actions=False)

    def test_challenge_blocked_by_target_consent_preference(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertFalse(
            result.success,
            msg="Expected challenge to be blocked by consent preference",
        )
        self.assertFalse(
            DuelChallenge.objects.filter(
                challenger_sheet=self.actor_sheet,
                challenged_sheet=self.target_sheet,
            ).exists(),
            "No DuelChallenge should be created when consent is blocked",
        )


class ChallengeActionSelfChallengeTests(django.test.TestCase):
    """challenge at self → rejected."""

    def setUp(self) -> None:
        self.room = _make_room("SelfRoom")
        self.actor, self.actor_sheet = _make_pc("SelfChallenger", self.room)

    def test_self_challenge_rejected(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.actor)

        self.assertFalse(result.success, msg="Expected self-challenge to be rejected")
        self.assertFalse(
            DuelChallenge.objects.filter(challenger_sheet=self.actor_sheet).exists(),
            "No DuelChallenge should be created for self-challenge",
        )


class ChallengeActionDifferentRoomTests(django.test.TestCase):
    """challenge at target in a different room → rejected."""

    def setUp(self) -> None:
        self.room_a = _make_room("RoomA")
        self.room_b = _make_room("RoomB")
        self.actor, self.actor_sheet = _make_pc("FarChallenger", self.room_a)
        self.target, self.target_sheet = _make_pc("FarTarget", self.room_b)

    def test_challenge_cross_room_rejected(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertFalse(result.success, msg="Expected cross-room challenge to be rejected")
        self.assertFalse(
            DuelChallenge.objects.filter(
                challenger_sheet=self.actor_sheet,
                challenged_sheet=self.target_sheet,
            ).exists(),
        )


class ChallengeActionNoSheetTests(django.test.TestCase):
    """challenge when actor has no CharacterSheet → rejected."""

    def setUp(self) -> None:
        self.room = _make_room("NoSheetRoom")
        # Actor has no CharacterSheet
        self.actor = CharacterFactory(db_key="NoSheetActor", location=self.room)
        self.target, _ = _make_pc("NoSheetTarget", self.room)

    def test_challenge_no_sheet_rejected(self) -> None:
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertFalse(
            result.success,
            msg="Expected challenge to fail without actor CharacterSheet",
        )


class ChallengeActionNoActiveTenureTests(django.test.TestCase):
    """challenge at a target with a CharacterSheet+RosterEntry but NO active tenure.

    Regression guard for the crash where ``_consent_blocked`` called
    ``_tenure_blocks_actor(None, ...)`` → ``AttributeError: 'NoneType' object
    has no attribute 'social_consent_preference'``.

    Expected: the action succeeds (no tenure → no preference → allow) and a
    PENDING DuelChallenge is created.
    """

    def setUp(self) -> None:
        self.room = _make_room("TenurelessArena")
        self.actor, self.actor_sheet = _make_pc("TenureActor", self.room)

        # Target has a sheet + RosterEntry but no RosterTenure at all.
        target_char = CharacterFactory(db_key="TenurelessTarget", location=self.room)
        self.target_sheet = CharacterSheetFactory(character=target_char)
        RosterEntryFactory(character_sheet=self.target_sheet)
        # Deliberately skip RosterTenureFactory — entry.current_tenure is None.
        self.target = target_char

    def test_challenge_target_no_tenure_does_not_crash(self) -> None:
        """No active tenure must not raise AttributeError — should succeed."""
        from actions.registry import get_action

        result = get_action("challenge").run(self.actor, target=self.target)

        self.assertTrue(
            result.success,
            msg=(
                f"Expected challenge to succeed when target has no active tenure; "
                f"got: {result.message}"
            ),
        )
        self.assertTrue(
            DuelChallenge.objects.filter(
                challenger_sheet=self.actor_sheet,
                challenged_sheet=self.target_sheet,
                status=DuelChallengeStatus.PENDING,
            ).exists(),
            "Expected a PENDING DuelChallenge to be created",
        )


# ---------------------------------------------------------------------------
# Task 11: accept / decline / withdraw
# ---------------------------------------------------------------------------


class AcceptChallengeActionTests(django.test.TestCase):
    """accept action: challenged PC accepts → ACCEPTED challenge + CombatEncounter."""

    def setUp(self) -> None:
        self.room = _make_room("AcceptArena")
        self.challenger, self.challenger_sheet = _make_pc("Challenger", self.room)
        self.challenged, self.challenged_sheet = _make_pc("Challenged", self.room)
        self.challenge = DuelChallengeFactory(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=self.challenged_sheet,
            room=self.room,
        )

    def test_accept_sets_status_accepted(self) -> None:
        from actions.registry import get_action

        result = get_action("accept").run(self.challenged)

        self.assertTrue(result.success, msg=result.message)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.ACCEPTED)

    def test_accept_sets_resolved_at(self) -> None:
        from actions.registry import get_action

        get_action("accept").run(self.challenged)

        self.challenge.refresh_from_db()
        self.assertIsNotNone(self.challenge.resolved_at)

    def test_accept_creates_and_links_encounter(self) -> None:
        from actions.registry import get_action
        from world.combat.constants import EncounterType

        result = get_action("accept").run(self.challenged)

        self.assertTrue(result.success, msg=result.message)
        self.challenge.refresh_from_db()
        self.assertIsNotNone(self.challenge.resulting_encounter_id)
        enc = self.challenge.resulting_encounter
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertIn("encounter_id", result.data)

    def test_only_challenged_may_accept(self) -> None:
        """The challenger cannot accept their own challenge."""
        from actions.registry import get_action

        result = get_action("accept").run(self.challenger)

        self.assertFalse(result.success)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.PENDING)

    def test_non_pending_challenge_cannot_be_accepted(self) -> None:
        """Accepting an already-DECLINED challenge fails."""
        from actions.registry import get_action

        self.challenge.status = DuelChallengeStatus.DECLINED
        self.challenge.save(update_fields=["status"])

        result = get_action("accept").run(self.challenged)

        self.assertFalse(result.success)


class DeclineChallengeActionTests(django.test.TestCase):
    """decline action: challenged PC declines → DECLINED challenge, no encounter."""

    def setUp(self) -> None:
        self.room = _make_room("DeclineArena")
        self.challenger, self.challenger_sheet = _make_pc("Decliner_C", self.room)
        self.challenged, self.challenged_sheet = _make_pc("Decliner_D", self.room)
        self.challenge = DuelChallengeFactory(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=self.challenged_sheet,
            room=self.room,
        )

    def test_decline_sets_status_declined(self) -> None:
        from actions.registry import get_action

        result = get_action("decline").run(self.challenged)

        self.assertTrue(result.success, msg=result.message)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.DECLINED)

    def test_decline_sets_resolved_at(self) -> None:
        from actions.registry import get_action

        get_action("decline").run(self.challenged)

        self.challenge.refresh_from_db()
        self.assertIsNotNone(self.challenge.resolved_at)

    def test_decline_creates_no_encounter(self) -> None:
        from actions.registry import get_action

        get_action("decline").run(self.challenged)

        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.resulting_encounter_id)

    def test_only_challenged_may_decline(self) -> None:
        """The challenger cannot decline their own challenge."""
        from actions.registry import get_action

        result = get_action("decline").run(self.challenger)

        self.assertFalse(result.success)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.PENDING)

    def test_non_pending_challenge_cannot_be_declined(self) -> None:
        from actions.registry import get_action

        self.challenge.status = DuelChallengeStatus.ACCEPTED
        self.challenge.save(update_fields=["status"])

        result = get_action("decline").run(self.challenged)

        self.assertFalse(result.success)


class WithdrawChallengeActionTests(django.test.TestCase):
    """withdraw action: challenger rescinds → WITHDRAWN challenge, no encounter."""

    def setUp(self) -> None:
        self.room = _make_room("WithdrawArena")
        self.challenger, self.challenger_sheet = _make_pc("Withdrawer_C", self.room)
        self.challenged, self.challenged_sheet = _make_pc("Withdrawer_D", self.room)
        self.challenge = DuelChallengeFactory(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=self.challenged_sheet,
            room=self.room,
        )

    def test_withdraw_sets_status_withdrawn(self) -> None:
        from actions.registry import get_action

        result = get_action("withdraw").run(self.challenger)

        self.assertTrue(result.success, msg=result.message)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.WITHDRAWN)

    def test_withdraw_sets_resolved_at(self) -> None:
        from actions.registry import get_action

        get_action("withdraw").run(self.challenger)

        self.challenge.refresh_from_db()
        self.assertIsNotNone(self.challenge.resolved_at)

    def test_withdraw_creates_no_encounter(self) -> None:
        from actions.registry import get_action

        get_action("withdraw").run(self.challenger)

        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.resulting_encounter_id)

    def test_only_challenger_may_withdraw(self) -> None:
        """The challenged PC cannot withdraw a challenge they received."""
        from actions.registry import get_action

        result = get_action("withdraw").run(self.challenged)

        self.assertFalse(result.success)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.PENDING)

    def test_non_pending_challenge_cannot_be_withdrawn(self) -> None:
        from actions.registry import get_action

        self.challenge.status = DuelChallengeStatus.DECLINED
        self.challenge.save(update_fields=["status"])

        result = get_action("withdraw").run(self.challenger)

        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# Task 12: yield
# ---------------------------------------------------------------------------


class YieldActionActiveDuelTests(django.test.TestCase):
    """yield action: participant in an active DUEL concedes → COMPLETED, other wins."""

    def setUp(self) -> None:
        self.room = _make_room("YieldArena")
        self.challenger, self.challenger_sheet = _make_pc("YieldChallenger", self.room)
        self.challenged, self.challenged_sheet = _make_pc("YieldChallenged", self.room)
        # Create an active DUEL encounter using the real service.
        self.encounter = create_pvp_duel(self.challenger_sheet, self.challenged_sheet, self.room)

    def test_yield_completes_duel_encounter(self) -> None:
        from actions.registry import get_action

        result = get_action("yield").run(self.challenger)

        self.assertTrue(result.success, msg=result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, EncounterStatus.COMPLETED)

    def test_yield_makes_other_duelist_duel_winner(self) -> None:
        from actions.registry import get_action

        result = get_action("yield").run(self.challenger)

        self.assertTrue(result.success, msg=result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.duel_winner_id, self.challenged_sheet.pk)

    def test_yield_result_includes_encounter_id(self) -> None:
        from actions.registry import get_action

        result = get_action("yield").run(self.challenger)

        self.assertTrue(result.success, msg=result.message)
        self.assertIn("encounter_id", result.data)


class YieldActionNotInDuelTests(django.test.TestCase):
    """yield action: actor not in any active duel → clean failure."""

    def setUp(self) -> None:
        self.room = _make_room("NoYieldRoom")
        self.actor, self.actor_sheet = _make_pc("NotInDuel", self.room)

    def test_yield_not_in_duel_fails_cleanly(self) -> None:
        from actions.registry import get_action

        result = get_action("yield").run(self.actor)

        self.assertFalse(result.success)
        self.assertIn("not in a duel", result.message.lower())


class YieldActionNoSheetTests(django.test.TestCase):
    """yield action: actor has no CharacterSheet → clean failure."""

    def setUp(self) -> None:
        self.room = _make_room("NoSheetYieldRoom")
        self.actor = CharacterFactory(db_key="NoSheetYielder", location=self.room)

    def test_yield_no_sheet_fails_cleanly(self) -> None:
        from actions.registry import get_action

        result = get_action("yield").run(self.actor)

        self.assertFalse(result.success)
