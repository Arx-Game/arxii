"""Command-level tests: auto-fire + advancement-error handling in CmdRitual (#1700).

Covers:
  (a) Joining a site-convened Durance session auto-fires — level rises, session gone.
      The session is stamped with ``session_kwargs={"site_convened": "1"}`` (set by
      ``convene_durance_at_site``); ``DuranceAdapter.should_auto_fire`` keys on that
      marker, NOT on whether the initiator is a ``DuranceTrainingSite`` trainer.
  (b) ``_handle_fire`` on a Durance whose requirements are unmet surfaces the
      ``.failed`` reason instead of propagating the exception.
  (c) Overlap case: when an officiant IS a registered trainer but the session was drafted
      via plain ``ritual draft`` (no ``site_convened`` marker), ``should_auto_fire``
      returns False and ``ritual join`` falls through to the normal "joined" message.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.magic.factories import RitualOfTheDuranceFactory
from world.magic.models.sessions import RitualSession
from world.magic.services.sessions import accept_session, draft_session
from world.progression.factories import DuranceTrainingSiteFactory
from world.progression.models import CharacterPathHistory, ClassLevelAdvancement
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock
from world.scenes.factories import SceneFactory

# Patch target: the legend-gate function called inside advance_class_level_via_session.
_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Build a command instance ready to have .func() called."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


def _setup_durance_participants(path):
    """Return (officiant_char, officiant_sheet, inductee_char, inductee_sheet, inductee_class).

    Both the officiant and inductee are wired with the shared *path*; the officiant is at
    level 10 (passes the officiant eligibility guard), the inductee at level 2 (advances
    to 3 on a successful Durance fire).
    """
    officiant_char = CharacterFactory(db_key="DuranceOfficiant")
    officiant_sheet = CharacterSheetFactory(character=officiant_char)
    officiant_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=officiant_sheet,
        character_class=officiant_class,
        level=10,
        is_primary=True,
    )
    CharacterPathHistory.objects.create(character=officiant_sheet, path=path)

    inductee_char = CharacterFactory(db_key="DuranceInductee")
    inductee_sheet = CharacterSheetFactory(character=inductee_char)
    inductee_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=inductee_sheet,
        character_class=inductee_class,
        level=2,
        is_primary=True,
    )
    CharacterPathHistory.objects.create(character=inductee_sheet, path=path)

    return officiant_char, officiant_sheet, inductee_char, inductee_sheet, inductee_class


class DuranceAutoFireOnJoinTests(TestCase):
    """Joining a site-convened Durance session auto-fires without a manual 'ritual fire'.

    The session is stamped with ``session_kwargs={"site_convened": "1"}`` — the marker
    that ``convene_durance_at_site`` sets when drafting a session at a training site.
    ``DuranceAdapter.should_auto_fire`` keys on that marker alone; no ``DuranceTrainingSite``
    DB query is needed here.
    """

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        (
            self.officiant_char,
            self.officiant_sheet,
            self.inductee_char,
            self.inductee_sheet,
            self.inductee_class,
        ) = _setup_durance_participants(self.path)

        # Authored level unlock for the inductee's class at target level 3.
        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        CharacterUnlock.objects.create(
            character=self.inductee_char.sheet_data,
            character_class=self.inductee_class,
            target_level=3,
        )

        # Active scene at inductee's location so the testament POSE can be posted.
        SceneFactory(location=self.inductee_char.location, is_active=True)

        self.ritual = RitualOfTheDuranceFactory()

        # Stamp the session with the site_convened marker as convene_durance_at_site would.
        self.session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="",
            session_kwargs={"site_convened": "1"},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session_pk = self.session.pk

    def test_join_auto_fires_level_rises_session_deleted(self) -> None:
        """Inductee joins a site-convened session; auto-fire bumps level to 3, session gone."""
        with patch(_CHECK_PATH, return_value=(True, [])):
            cmd = _run(CmdRitual, self.inductee_char, f"join {self.session_pk}")
            cmd.func()

        # Session must be deleted after successful auto-fire.
        self.assertFalse(RitualSession.objects.filter(pk=self.session_pk).exists())

        # ClassLevelAdvancement receipt written with correct before/after.
        self.assertTrue(
            ClassLevelAdvancement.objects.filter(
                character_sheet=self.inductee_sheet,
                level_before=2,
                level_after=3,
            ).exists()
        )

        # Caller received a completion message (not the normal "joined" message).
        msg_text = self.inductee_char.msg.call_args[0][0]
        self.assertNotIn("You have joined", msg_text)
        self.assertIn(str(self.session_pk), msg_text)

    def test_join_auto_fire_unmet_requirements_surfaces_error(self) -> None:
        """Auto-fire with unmet requirements surfaces the failed reasons, not a traceback."""
        with patch(_CHECK_PATH, return_value=(False, ["Requires 50 Legend"])):
            cmd = _run(CmdRitual, self.inductee_char, f"join {self.session_pk}")
            cmd.func()

        msg_text = self.inductee_char.msg.call_args[0][0]
        self.assertIn("Requires 50 Legend", msg_text)


class NonSiteDuranceJoinFallsThrough(TestCase):
    """When the officiating sheet has no DuranceTrainingSite, join uses the normal path."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        (
            self.officiant_char,
            self.officiant_sheet,
            self.inductee_char,
            self.inductee_sheet,
            self.inductee_class,
        ) = _setup_durance_participants(self.path)
        ClassLevelUnlock.objects.create(character_class=self.inductee_class, target_level=3)
        # Deliberately NO DuranceTrainingSite → should_auto_fire returns False.
        self.ritual = RitualOfTheDuranceFactory()
        self.session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="",
            session_kwargs={},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    def test_non_site_join_sends_normal_joined_message(self) -> None:
        """Non-site Durance join ends with the normal 'You have joined' message; no auto-fire."""
        cmd = _run(CmdRitual, self.inductee_char, f"join {self.session.pk}")
        cmd.func()

        # Session still exists — no auto-fire fired it.
        self.assertTrue(RitualSession.objects.filter(pk=self.session.pk).exists())

        msg_text = self.inductee_char.msg.call_args[0][0]
        self.assertIn("joined", msg_text.lower())


class DuranceSiteOfficiantPlainDraftNoAutoFireTests(TestCase):
    """Overlap case: officiant is a registered trainer, but the session was drafted via
    ``ritual draft`` (no site_convened marker) — should_auto_fire must return False.

    This guards the deliberate live-officiant ceremony: the trainer uses ``ritual draft``
    to open a witnessed ceremony, invites the inductee, and fires with ``ritual fire``
    at the moment of their choosing.  The auto-fire path must NOT trigger just because
    the officiant happens to be a trainer-of-record at a training site.
    """

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        (
            self.officiant_char,
            self.officiant_sheet,
            self.inductee_char,
            self.inductee_sheet,
            self.inductee_class,
        ) = _setup_durance_participants(self.path)
        ClassLevelUnlock.objects.create(character_class=self.inductee_class, target_level=3)

        # Officiant IS a registered trainer-of-record at a site — the bug condition.
        DuranceTrainingSiteFactory(officiant=self.officiant_sheet, is_active=True)

        self.ritual = RitualOfTheDuranceFactory()

        # Session drafted via plain ritual draft — NO site_convened marker.
        self.session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="",
            session_kwargs={},  # no site_convened → manual fire required
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    def test_should_auto_fire_is_false_without_site_convened_marker(self) -> None:
        """should_auto_fire returns False when the session has no site_convened key."""
        from commands.ritual_adapters import DuranceAdapter

        self.assertFalse(DuranceAdapter().should_auto_fire(session=self.session))

    def test_ritual_join_does_not_auto_fire(self) -> None:
        """``ritual join`` falls through to normal join message; session survives."""
        cmd = _run(CmdRitual, self.inductee_char, f"join {self.session.pk}")
        cmd.func()

        # Session must still exist (no auto-fire fired it).
        self.assertTrue(RitualSession.objects.filter(pk=self.session.pk).exists())

        msg_text = self.inductee_char.msg.call_args[0][0]
        self.assertIn("joined", msg_text.lower())

    def test_no_class_level_advancement_written_on_plain_join(self) -> None:
        """No ClassLevelAdvancement receipt is written when auto-fire is suppressed."""
        from world.progression.models import ClassLevelAdvancement

        cmd = _run(CmdRitual, self.inductee_char, f"join {self.session.pk}")
        cmd.func()

        self.assertFalse(
            ClassLevelAdvancement.objects.filter(character_sheet=self.inductee_sheet).exists()
        )


class DuranceHandleFireAdvancementErrorTests(TestCase):
    """_handle_fire catches ClassLevelAdvancementError and surfaces .failed reasons."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        (
            self.officiant_char,
            self.officiant_sheet,
            self.inductee_char,
            self.inductee_sheet,
            self.inductee_class,
        ) = _setup_durance_participants(self.path)

        # Unlock must EXIST for check_requirements_for_unlock to be reached.
        ClassLevelUnlock.objects.create(character_class=self.inductee_class, target_level=3)
        SceneFactory(location=self.inductee_char.location, is_active=True)

        self.ritual = RitualOfTheDuranceFactory()

        # Draft and accept via service so we can drive _handle_fire via command.
        session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="",
            session_kwargs={},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session_pk = session.pk
        inductee_participant = session.participants.get(character_sheet=self.inductee_sheet)
        accept_session(participant=inductee_participant, participant_kwargs={}, references=[])

    def test_fire_unmet_requirements_surfaces_failed_list(self) -> None:
        """Officiating character fires; unmet requirements show up as a caller message, not exc."""
        with patch(_CHECK_PATH, return_value=(False, ["Requires 50 Legend"])):
            cmd = _run(CmdRitual, self.officiant_char, f"fire {self.session_pk}")
            cmd.func()

        msg_text = self.officiant_char.msg.call_args[0][0]
        self.assertIn("Requires 50 Legend", msg_text)

    def test_fire_multiple_failed_reasons_joined_with_semicolon(self) -> None:
        """Multiple failed reasons are joined with '; ' in the surfaced message."""
        reasons = ["Requires 50 Legend", "Must complete training"]
        with patch(_CHECK_PATH, return_value=(False, reasons)):
            cmd = _run(CmdRitual, self.officiant_char, f"fire {self.session_pk}")
            cmd.func()

        msg_text = self.officiant_char.msg.call_args[0][0]
        self.assertIn("Requires 50 Legend", msg_text)
        self.assertIn("Must complete training", msg_text)
        self.assertIn(";", msg_text)
