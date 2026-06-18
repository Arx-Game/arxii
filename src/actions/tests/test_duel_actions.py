"""Tests for the challenge action (Task 10).

Tests are built using setUp (not setUpTestData) because CharacterFactory creates
Evennia ObjectDB instances (DbHolder — not deepcopyable, which breaks setUpTestData).

Scenarios covered:
  (a) Consenting co-located target → PENDING DuelChallenge created, success result.
  (b) Target whose SocialConsentPreference blocks all social actions → blocked, no challenge.
  (c) Self-challenge → rejected, no challenge.
  (d) Target in a different room → rejected, no challenge.
  (e) Actor has no CharacterSheet → rejected, no challenge.
"""

from __future__ import annotations

import django.test

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import DuelChallengeStatus
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
