"""E2E journey test for journals & goals telnet authoring (#1350).

Drives the authoring loop through the ``journal`` / ``goal`` commands — the
ADR-0001 convergence point (web+telnet share ``action.run()``). Mirrors the
``test_relationships_command.py`` structure: real Actions, real DB state,
``CharacterFactory`` + ``CharacterSheetFactory``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.goals import CmdGoal
from commands.journals import CmdJournal
from commands.parsing import parse_kv_and_flags
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.goals.factories import GoalDomainFactory
from world.goals.models import CharacterGoal, GoalJournal
from world.goals.services import MAX_GOAL_POINTS
from world.journals.models import JournalEntry, WeeklyJournalXP


def _make_journal_cmd(caller: Any, args: str = "") -> CmdJournal:
    cmd = CmdJournal()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"journal {args}".strip()
    cmd.cmdname = "journal"
    return cmd


def _make_goal_cmd(caller: Any, args: str = "") -> CmdGoal:
    cmd = CmdGoal()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"goal {args}".strip()
    cmd.cmdname = "goal"
    return cmd


def _capture(caller: Any) -> str:
    return "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)


class JournalGoalJourneyE2ETests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.writer = CharacterFactory()
        self.writer.db_account = AccountFactory()
        self.writer.save()
        self.writer_sheet = CharacterSheetFactory(character=self.writer)
        self.writer.msg = MagicMock()
        self.responder = CharacterFactory()
        self.responder.db_account = AccountFactory()
        self.responder.save()
        self.responder_sheet = CharacterSheetFactory(character=self.responder)
        self.responder.msg = MagicMock()

    def test_full_authoring_loop(self) -> None:
        # 1. Writer writes a public journal entry.
        _make_journal_cmd(
            self.writer,
            (
                "write title=A Courtly Observation "
                "body=The Duke was severe today. public tags=court,rumor"
            ),
        ).func()
        entry = JournalEntry.objects.get(author=self.writer_sheet, title="A Courtly Observation")
        self.assertTrue(entry.is_public)
        self.assertEqual({t.name for t in entry.tags.all()}, {"court", "rumor"})
        tracker = WeeklyJournalXP.objects.get(character_sheet=self.writer_sheet)
        self.assertEqual(tracker.posts_this_week, 1)

        # 2. Responder responds with praise.
        _make_journal_cmd(
            self.responder,
            f"respond {entry.pk} type=praise title=Well Said body=I quite agree.",
        ).func()
        response = JournalEntry.objects.get(parent=entry, response_type="praise")
        self.assertEqual(response.author, self.responder_sheet)

        # 3. Writer sets a character goal and logs progress.
        domain = GoalDomainFactory(name="Standing")
        _make_goal_cmd(self.writer, f"add domain={domain.pk} points=10 notes=Gain standing").func()
        self.assertTrue(
            CharacterGoal.objects.filter(
                character=self.writer.sheet_data, domain=domain, points=10
            ).exists()
        )

        _make_goal_cmd(
            self.writer, f"log domain={domain.pk} title=A step forward content=Curried favor today."
        ).func()
        self.assertTrue(
            GoalJournal.objects.filter(
                character=self.writer.sheet_data, domain=domain, title="A step forward"
            ).exists()
        )


class JournalCommandErrorTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterSheetFactory().character
        self.caller.db_account = AccountFactory()
        self.caller.save()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()

    def test_write_missing_body_reports_error(self) -> None:
        _make_journal_cmd(self.caller, "write title=Only a title").func()
        self.assertIn("body", _capture(self.caller).lower())

    def test_respond_unknown_entry_reports_error(self) -> None:
        _make_journal_cmd(self.caller, "respond 99999 type=praise title=x body=y").func()
        self.assertIn("not found", _capture(self.caller).lower())

    def test_unknown_subverb_shows_usage(self) -> None:
        _make_journal_cmd(self.caller, "frobnicate").func()
        self.assertIn("Usage", _capture(self.caller))

    def test_bare_journal_lists_entries(self) -> None:
        _make_journal_cmd(self.caller, "").func()
        self.assertIn("no journal entries", _capture(self.caller).lower())

    def test_respond_to_own_entry_reports_error(self) -> None:
        # Caller writes a public entry, then tries to respond to it themselves.
        _make_journal_cmd(
            self.caller,
            "write title=My Thoughts body=Some musings. public",
        ).func()
        entry = JournalEntry.objects.get(author=self.caller_sheet, title="My Thoughts")
        _make_journal_cmd(
            self.caller,
            f"respond {entry.pk} type=praise title=Self Praise body=I agree with me.",
        ).func()
        self.assertIn("your own", _capture(self.caller).lower())
        # No response row should have been created.
        self.assertFalse(JournalEntry.objects.filter(parent=entry, response_type="praise").exists())

    def test_respond_to_private_entry_reports_error(self) -> None:
        # Caller writes a private entry (no `public` flag), then tries to respond.
        _make_journal_cmd(
            self.caller,
            "write title=Secret Thoughts body=Hidden musings.",
        ).func()
        entry = JournalEntry.objects.get(author=self.caller_sheet, title="Secret Thoughts")
        self.assertFalse(entry.is_public)
        _make_journal_cmd(
            self.caller,
            f"respond {entry.pk} type=praise title=Intrusion body=I shouldn't see this.",
        ).func()
        self.assertIn("private", _capture(self.caller).lower())
        self.assertFalse(JournalEntry.objects.filter(parent=entry, response_type="praise").exists())


class GoalCommandErrorTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterSheetFactory().character
        self.caller.db_account = AccountFactory()
        self.caller.save()
        self.caller.msg = MagicMock()

    def test_unknown_domain_reports_error(self) -> None:
        _make_goal_cmd(self.caller, "add domain=Bogus points=5").func()
        self.assertIn("no goal domain", _capture(self.caller).lower())

    def test_over_cap_fails(self) -> None:
        domain = GoalDomainFactory(name="Wealth")
        _make_goal_cmd(self.caller, f"add domain={domain.pk} points=999").func()
        self.assertIn("exceed", _capture(self.caller).lower())

    def test_bare_goal_shows_budget(self) -> None:
        _make_goal_cmd(self.caller, "").func()
        self.assertIn(str(MAX_GOAL_POINTS), _capture(self.caller))

    def test_goal_set_revision_too_soon(self) -> None:
        # First `goal set` succeeds (no existing goals -> revision gate skipped).
        domain_a = GoalDomainFactory(name="Power")
        domain_b = GoalDomainFactory(name="Legacy")
        _make_goal_cmd(
            self.caller,
            f"set domain={domain_a.pk}:points=10,domain={domain_b.pk}:points=5",
        ).func()
        self.assertEqual(CharacterGoal.objects.filter(character=self.caller.sheet_data).count(), 2)

        # Second `goal set` within the revision window -> REVISION_TOO_SOON.
        _make_goal_cmd(
            self.caller,
            f"set domain={domain_a.pk}:points=20",
        ).func()
        self.assertIn("cannot revise", _capture(self.caller).lower())
        # Original allocations unchanged (the second set was rejected).
        self.assertEqual(CharacterGoal.objects.filter(character=self.caller.sheet_data).count(), 2)


_JOURNAL_MULTIWORD_KEYS = frozenset({"title", "body"})
_GOAL_MULTIWORD_KEYS = frozenset({"title", "content", "notes"})
_KNOWN_PUBLIC_FLAG = frozenset({"public"})


class JournalParserTests(TestCase):
    def test_multiword_body_runs_to_next_key(self) -> None:
        kwargs, flags = parse_kv_and_flags(
            "title=A Title body=Some long body. public",
            multiword_keys=_JOURNAL_MULTIWORD_KEYS,
            known_flags=_KNOWN_PUBLIC_FLAG,
        )
        self.assertEqual(kwargs["title"], "A Title")
        self.assertEqual(kwargs["body"], "Some long body.")
        self.assertIn("public", flags)

    def test_public_flag_parsed(self) -> None:
        _kw, flags = parse_kv_and_flags(
            "title=x body=y public",
            multiword_keys=_JOURNAL_MULTIWORD_KEYS,
            known_flags=_KNOWN_PUBLIC_FLAG,
        )
        self.assertEqual(flags, {"public"})


class GoalParserTests(TestCase):
    def test_notes_multiword(self) -> None:
        kwargs, _flags = parse_kv_and_flags(
            "domain=1 points=5 notes=A long winded note.",
            multiword_keys=_GOAL_MULTIWORD_KEYS,
            known_flags=_KNOWN_PUBLIC_FLAG,
        )
        self.assertEqual(kwargs["notes"], "A long winded note.")
