"""Tests for the ``relationship`` telnet command (#1485).

Exercises the namespaced subverb router end-to-end: the four write verbs run the
real relationship Actions (asserting DB state, not mocked dispatch), and the
``list`` / ``show`` read surfaces render real relationships. The parser's
multi-word ``key=value`` handling and the error paths get focused coverage too.

Mirrors the ``CmdMageScar`` test pattern (real ``_handle_*`` + ``patch.object``
on the action where needed) and the org-command ``caller.search`` mock pattern
(returns a real character so ``target.sheet_data`` resolves for real).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.relationships import CmdRelationship, _parse_name_and_kwargs
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign, UpdateVisibility
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipDevelopmentFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipDevelopment,
    RelationshipTrackProgress,
    RelationshipUpdate,
    WriteupComplaint,
    WriteupKudos,
)
from world.roster.factories import RosterTenureFactory


def _make_cmd(caller: Any, args: str = "") -> CmdRelationship:
    """Build a CmdRelationship wired to ``caller`` with the given arg string."""
    cmd = CmdRelationship()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"relationship {args}".strip()
    cmd.cmdname = "relationship"
    return cmd


def _capture(caller: Any) -> str:
    """Join all positional msg() args into one string for assertion."""
    return "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)


def _search_returns(target: Any):
    """A caller.search side_effect that returns ``target`` by its db_key, else None."""
    return lambda name: target if name == target.db_key else None


class CmdRelationshipWriteTests(TestCase):
    """The four write verbs run the real Action and mutate the DB."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock()
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Friendship")
        # Make caller.search return the real target character by name.
        self.caller.search.side_effect = _search_returns(self.target)

    def test_impression_creates_relationship(self) -> None:
        args = (
            f"impression {self.target.db_key} track={self.track.pk} points=3 "
            "title=A striking introduction writeup=They commanded the room."
        )
        _make_cmd(self.caller, args).func()
        relationship = CharacterRelationship.objects.get(
            source=self.caller_sheet, target=self.target_sheet
        )
        self.assertTrue(relationship.is_pending)
        self.assertTrue(
            RelationshipUpdate.objects.filter(
                relationship=relationship, is_first_impression=True
            ).exists()
        )
        self.assertIn("first impression", _capture(self.caller).lower())

    def test_impression_resolves_track_by_name(self) -> None:
        args = (
            f"impression {self.target.db_key} track=Friendship points=2 "
            "title=Hi writeup=Hello there."
        )
        _make_cmd(self.caller, args).func()
        relationship = CharacterRelationship.objects.get(
            source=self.caller_sheet, target=self.target_sheet
        )
        update = RelationshipUpdate.objects.get(relationship=relationship)
        self.assertEqual(update.track, self.track)

    def test_develop_adds_development(self) -> None:
        # Development adds permanent points up to track capacity, so seed
        # capacity directly on the progress record.
        relationship = CharacterRelationshipFactory(
            source=self.caller_sheet, target=self.target_sheet
        )
        RelationshipTrackProgress.objects.create(
            relationship=relationship, track=self.track, capacity=5, developed_points=0
        )
        args = (
            f"develop {self.target.db_key} track={self.track.pk} points=2 "
            "title=Growing respect writeup=They proved themselves. xp=5"
        )
        _make_cmd(self.caller, args).func()
        self.assertTrue(
            RelationshipDevelopment.objects.filter(
                author=self.caller_sheet, track=self.track
            ).exists()
        )

    def test_capstone_creates_capstone(self) -> None:
        args = (
            f"capstone {self.target.db_key} track={self.track.pk} points=10 "
            "title=A binding oath writeup=We swore an oath that day."
        )
        _make_cmd(self.caller, args).func()
        capstone = RelationshipCapstone.objects.get(author=self.caller_sheet, track=self.track)
        self.assertEqual(capstone.points, 10)
        # Capstone defaults to SHARED visibility.
        self.assertEqual(capstone.visibility, UpdateVisibility.SHARED)

    def test_redistribute_moves_points(self) -> None:
        relationship = CharacterRelationshipFactory(
            source=self.caller_sheet, target=self.target_sheet
        )
        target_track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Rivalry")
        RelationshipTrackProgress.objects.create(
            relationship=relationship,
            track=self.track,
            capacity=10,
            developed_points=5,
        )
        args = (
            f"redistribute {self.target.db_key} source={self.track.pk} "
            f"target={target_track.pk} points=3 title=A shift writeup=Respect waned."
        )
        _make_cmd(self.caller, args).func()
        change = RelationshipChange.objects.get(author=self.caller_sheet)
        self.assertEqual(change.points_moved, 3)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=target_track
        )
        self.assertEqual(progress.developed_points, 3)

    def test_impression_respects_visibility_and_coloring(self) -> None:
        args = (
            f"impression {self.target.db_key} track={self.track.pk} points=3 "
            "title=Hi writeup=Hello. coloring=positive visibility=public"
        )
        _make_cmd(self.caller, args).func()
        update = RelationshipUpdate.objects.get(author=self.caller_sheet)
        self.assertEqual(update.visibility, UpdateVisibility.PUBLIC)
        from world.relationships.constants import FirstImpressionColoring

        self.assertEqual(update.coloring, FirstImpressionColoring.POSITIVE)


class CmdRelationshipReadTests(TestCase):
    """``list`` and ``show`` render real relationships."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock()
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.caller.search.side_effect = _search_returns(self.target)
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Friendship")

    def test_bare_lists_empty(self) -> None:
        _make_cmd(self.caller, "").func()
        self.assertIn("no relationships", _capture(self.caller).lower())

    def test_list_renders_relationship(self) -> None:
        relationship = CharacterRelationshipFactory(
            source=self.caller_sheet, target=self.target_sheet
        )
        RelationshipTrackProgressFactory(
            relationship=relationship,
            track=self.track,
            capacity=5,
            developed_points=3,
        )
        _make_cmd(self.caller, "list").func()
        text = _capture(self.caller)
        # The list row shows the target name, the relationship id, and affection.
        self.assertIn(self.target.db_key, text)
        self.assertIn(f"[#{relationship.pk}]", text)
        # Track names appear in the detail view, not the list row.
        self.assertIn("show", text.lower())

    def test_show_by_id_renders_detail(self) -> None:
        rel = CharacterRelationshipFactory(source=self.caller_sheet, target=self.target_sheet)
        _make_cmd(self.caller, f"show #{rel.pk}").func()
        text = _capture(self.caller)
        self.assertIn(self.target.db_key, text)
        self.assertIn(f"#{rel.pk}", text)

    def test_show_by_name_renders_detail(self) -> None:
        CharacterRelationshipFactory(source=self.caller_sheet, target=self.target_sheet)
        _make_cmd(self.caller, f"show {self.target.db_key}").func()
        text = _capture(self.caller)
        self.assertIn(self.target.db_key, text)


class CmdRelationshipErrorTests(TestCase):
    """Routing and argument-resolution error paths."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterFactory()
        CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=None)
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Friendship")

    def test_unknown_subverb_shows_usage(self) -> None:
        _make_cmd(self.caller, "frobnicate").func()
        self.assertIn("Usage", _capture(self.caller))

    def test_impression_missing_target_reports_usage(self) -> None:
        _make_cmd(self.caller, "impression").func()
        self.assertIn("Usage", _capture(self.caller))

    def test_impression_target_not_found_reports_error(self) -> None:
        _make_cmd(
            self.caller,
            f"impression Ghost track={self.track.pk} points=3 title=x writeup=y",
        ).func()
        text = _capture(self.caller).lower()
        self.assertIn("could not find", text)

    def test_impression_unknown_track_reports_error(self) -> None:
        self.caller.search.return_value = CharacterFactory()  # some real char, no sheet
        _make_cmd(
            self.caller,
            "impression Bob track=99999 points=3 title=x writeup=y",
        ).func()
        # Either the target has no sheet or the track is unknown; both are errors.
        text = _capture(self.caller).lower()
        self.assertTrue("no character sheet" in text or "no relationship track" in text)

    def test_impression_missing_points_reports_error(self) -> None:
        target = CharacterFactory()
        CharacterSheetFactory(character=target)
        self.caller.search.return_value = target
        _make_cmd(
            self.caller,
            f"impression {target.db_key} track={self.track.pk} title=x writeup=y",
        ).func()
        self.assertIn("points", _capture(self.caller).lower())

    def test_bad_visibility_reports_error(self) -> None:
        target = CharacterFactory()
        CharacterSheetFactory(character=target)
        self.caller.search.return_value = target
        _make_cmd(
            self.caller,
            f"impression {target.db_key} track={self.track.pk} points=3 "
            "title=x writeup=y visibility=banana",
        ).func()
        self.assertIn("visibility", _capture(self.caller).lower())


class ParseNameAndKwargsTests(TestCase):
    """The multi-word ``key=value`` parser (focused unit coverage)."""

    def test_name_only(self) -> None:
        name, kwargs = _parse_name_and_kwargs("Alice")
        self.assertEqual(name, "Alice")
        self.assertEqual(kwargs, {})

    def test_multiword_name_until_first_key(self) -> None:
        name, kwargs = _parse_name_and_kwargs("Alice Bob track=5 points=3")
        self.assertEqual(name, "Alice Bob")
        self.assertEqual(kwargs, {"track": "5", "points": "3"})

    def test_multiword_value_runs_to_next_key(self) -> None:
        name, kwargs = _parse_name_and_kwargs(
            "Alice title=A striking day writeup=They were great. points=3"
        )
        self.assertEqual(name, "Alice")
        self.assertEqual(kwargs["title"], "A striking day")
        self.assertEqual(kwargs["writeup"], "They were great.")
        self.assertEqual(kwargs["points"], "3")

    def test_empty_value(self) -> None:
        _name, kwargs = _parse_name_and_kwargs("Alice title= writeup=text")
        self.assertEqual(kwargs["title"], "")
        self.assertEqual(kwargs["writeup"], "text")

    def test_empty_rest(self) -> None:
        self.assertEqual(_parse_name_and_kwargs(""), ("", {}))

    def test_leading_token_without_key_raises(self) -> None:
        # A bare token after a key=value pair with no key context is malformed.
        from commands.exceptions import CommandError

        with self.assertRaises(CommandError):
            _parse_name_and_kwargs("Alice track=5 strayword points=3")


class CmdRelationshipKudosComplainTests(TestCase):
    """``kudos`` and ``complain`` subverbs create feedback rows and surface errors.

    Setup: caller is the SUBJECT of a SHARED update (relationship.target = caller_sheet).
    caller has an account via RosterTenureFactory — required by give_writeup_kudos.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        # Author writes the writeup.
        self.author = CharacterFactory()
        self.author_sheet = CharacterSheetFactory(character=self.author)
        # Caller is the subject (relationship.target).
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=None)
        # Link caller to an account so get_account_for_character resolves.
        tenure = RosterTenureFactory(roster_entry__character_sheet=self.caller_sheet)
        self.caller_account = tenure.player_data.account
        # Relationship: author → caller (caller is target/subject).
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Friendship")
        self.rel = CharacterRelationshipFactory(source=self.author_sheet, target=self.caller_sheet)
        # A SHARED update authored by the author about the caller.
        self.update = RelationshipUpdateFactory(
            relationship=self.rel,
            author=self.author_sheet,
            track=self.track,
            visibility=UpdateVisibility.SHARED,
        )

    def test_kudos_creates_writeupkudos_row(self) -> None:
        """``relationship kudos u<pk>`` creates a WriteupKudos row for the update."""
        _make_cmd(self.caller, f"kudos u{self.update.pk}").func()
        self.assertTrue(
            WriteupKudos.objects.filter(update=self.update, account=self.caller_account).exists()
        )

    def test_kudos_shows_success_message(self) -> None:
        """``relationship kudos`` surfaces the action's success message."""
        _make_cmd(self.caller, f"kudos u{self.update.pk}").func()
        self.assertIn("commend", _capture(self.caller).lower())

    def test_kudos_missing_ref_reports_error(self) -> None:
        """``relationship kudos`` with no ref shows a usage error."""
        _make_cmd(self.caller, "kudos").func()
        self.assertIn("usage", _capture(self.caller).lower())

    def test_kudos_bad_ref_reports_error(self) -> None:
        """An unrecognised writeup ref (e.g. ``xyz``) shows a clear error."""
        _make_cmd(self.caller, "kudos xyz").func()
        text = _capture(self.caller).lower()
        self.assertTrue("invalid" in text or "u<id>" in text or "ref" in text)

    def test_kudos_nonexistent_writeup_reports_error(self) -> None:
        """A well-formed ref to a non-existent pk surfaces the action error."""
        _make_cmd(self.caller, "kudos u99999").func()
        text = _capture(self.caller).lower()
        self.assertTrue("not found" in text or "writeup" in text)

    def test_complain_creates_writeupcomplaint_row(self) -> None:
        """``relationship complain u<pk>=<reason>`` creates a WriteupComplaint row."""
        _make_cmd(self.caller, f"complain u{self.update.pk}=This RP was in bad faith.").func()
        self.assertTrue(
            WriteupComplaint.objects.filter(
                update=self.update, complainant=self.caller_account
            ).exists()
        )

    def test_complain_shows_success_message(self) -> None:
        """``relationship complain`` surfaces the action's success message."""
        _make_cmd(self.caller, f"complain u{self.update.pk}=Bad faith.").func()
        self.assertIn("complaint", _capture(self.caller).lower())

    def test_complain_missing_reason_reports_error(self) -> None:
        """``relationship complain <ref>`` without ``=<reason>`` shows a usage error."""
        _make_cmd(self.caller, f"complain u{self.update.pk}").func()
        self.assertIn("usage", _capture(self.caller).lower())

    def test_complain_bad_ref_reports_error(self) -> None:
        """An unrecognised writeup ref in complain shows a clear error."""
        _make_cmd(self.caller, "complain xyz=reason").func()
        text = _capture(self.caller).lower()
        self.assertTrue("invalid" in text or "u<id>" in text or "ref" in text)


class CmdRelationshipShowWriteupsTests(TestCase):
    """``relationship show`` includes writeup labels so users know what to pass to kudos/complain.

    Ref notation: ``u<pk>`` = update, ``d<pk>`` = development, ``c<pk>`` = capstone.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=None)
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.caller.search.side_effect = _search_returns(self.target)
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE, name="Friendship")
        # Relationship source=caller → target.
        self.rel = CharacterRelationshipFactory(source=self.caller_sheet, target=self.target_sheet)
        # Seed one update so the writeup list appears.
        self.update = RelationshipUpdateFactory(
            relationship=self.rel,
            author=self.caller_sheet,
            track=self.track,
            visibility=UpdateVisibility.SHARED,
        )

    def test_show_displays_update_writeup_label(self) -> None:
        """``relationship show <#>`` lists updates with ``[u<pk>]`` labels."""
        _make_cmd(self.caller, f"show #{self.rel.pk}").func()
        text = _capture(self.caller)
        self.assertIn(f"[u{self.update.pk}]", text)

    def test_show_displays_development_writeup_label(self) -> None:
        """``relationship show <#>`` lists developments with ``[d<pk>]`` labels."""
        RelationshipTrackProgressFactory(
            relationship=self.rel, track=self.track, capacity=10, developed_points=0
        )
        dev = RelationshipDevelopmentFactory(
            relationship=self.rel,
            author=self.caller_sheet,
            track=self.track,
            points_earned=3,
        )
        _make_cmd(self.caller, f"show #{self.rel.pk}").func()
        text = _capture(self.caller)
        self.assertIn(f"[d{dev.pk}]", text)

    def test_show_displays_capstone_writeup_label(self) -> None:
        """``relationship show <#>`` lists capstones with ``[c<pk>]`` labels."""
        capstone = RelationshipCapstoneFactory(
            relationship=self.rel,
            author=self.caller_sheet,
            track=self.track,
        )
        _make_cmd(self.caller, f"show #{self.rel.pk}").func()
        text = _capture(self.caller)
        self.assertIn(f"[c{capstone.pk}]", text)
