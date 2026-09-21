"""Tests for the ``relationship`` telnet command (#3957 / #1485).

Exercises the namespaced subverb router end-to-end: every write verb runs the
real tie Action (asserting DB state, not mocked dispatch), and the ``list`` /
``show`` read surfaces render real relationships. The error paths get focused
coverage too.

Mirrors the ``CmdMageScar`` test pattern (real ``_handle_*`` methods) and the
org-command ``caller.search`` mock pattern (returns a real character so
``target.sheet_data`` resolves for real).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.relationships import CmdRelationship
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import CharacterRelationship, RelationshipLabel


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


class CmdRelationshipDeclareTests(TestCase):
    """``relationship declare <name>=<type>[,awareness]`` runs DeclareLabelAction."""

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
        self.friend = RelationshipTypeFactory(name="Friend")

    def test_declare_defaults_private(self) -> None:
        _make_cmd(self.caller, f"declare {self.target.db_key}=Friend").func()
        label = RelationshipLabel.objects.get()
        self.assertEqual(label.awareness, LabelAwareness.PRIVATE)
        self.assertEqual(label.relationship.source_id, self.caller_sheet.pk)
        self.assertEqual(label.relationship.target_id, self.target_sheet.pk)

    def test_declare_with_awareness_creates_public(self) -> None:
        _make_cmd(self.caller, f"declare {self.target.db_key}=Friend,public").func()
        label = RelationshipLabel.objects.get()
        self.assertEqual(label.awareness, LabelAwareness.PUBLIC)

    def test_declare_unknown_type_refused(self) -> None:
        _make_cmd(self.caller, f"declare {self.target.db_key}=Nonexistent").func()
        self.assertIn("No relationship type", _capture(self.caller))
        self.assertEqual(RelationshipLabel.objects.count(), 0)

    def test_declare_requires_a_name(self) -> None:
        _make_cmd(self.caller, "declare =Friend").func()
        self.assertIn("Usage: relationship declare", _capture(self.caller))

    def test_declare_requires_an_equals(self) -> None:
        _make_cmd(self.caller, f"declare {self.target.db_key}").func()
        self.assertIn("Usage: relationship declare", _capture(self.caller))


class CmdRelationshipShiftEndTests(TestCase):
    """``relationship shift``/``end`` run ShiftLabelAction/EndLabelAction."""

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
        self.friend = RelationshipTypeFactory(name="Friend")
        self.lover = RelationshipTypeFactory(name="Lover")
        _make_cmd(self.caller, f"declare {self.target.db_key}=Friend").func()

    def test_shift_changes_label_type(self) -> None:
        _make_cmd(self.caller, f"shift {self.target.db_key}=Friend,Lover,at the gate").func()
        self.assertFalse(RelationshipLabel.objects.filter(ended_at__isnull=True, type=self.friend))
        new = RelationshipLabel.objects.get(ended_at__isnull=True)
        self.assertEqual(new.type_id, self.lover.pk)
        self.assertEqual(new.note, "at the gate")

    def test_shift_unknown_from_label_refused(self) -> None:
        _make_cmd(self.caller, f"shift {self.target.db_key}=Lover,Friend").func()
        self.assertIn("have not declared", _capture(self.caller))

    def test_end_ends_the_label(self) -> None:
        _make_cmd(self.caller, f"end {self.target.db_key}=Friend").func()
        label = RelationshipLabel.objects.get()
        self.assertIsNotNone(label.ended_at)


class CmdRelationshipRevealTests(TestCase):
    """``relationship reveal <name>=<type>,<awareness>`` runs AdvanceLabelAwarenessAction."""

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
        RelationshipTypeFactory(name="Friend")
        _make_cmd(self.caller, f"declare {self.target.db_key}=Friend").func()

    def test_reveal_advances_awareness(self) -> None:
        _make_cmd(self.caller, f"reveal {self.target.db_key}=Friend,public").func()
        label = RelationshipLabel.objects.get()
        self.assertEqual(label.awareness, LabelAwareness.PUBLIC)

    def test_reveal_backward_refused(self) -> None:
        _make_cmd(self.caller, f"reveal {self.target.db_key}=Friend,public").func()
        self.caller.msg.reset_mock()
        _make_cmd(self.caller, f"reveal {self.target.db_key}=Friend,private").func()
        self.assertIn("A label can be made known, never hidden again.", _capture(self.caller))


class CmdRelationshipApSummaryTests(TestCase):
    """``relationship ap``/``summary`` run SetTieAllocationAction/SetTieSummaryAction."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        from world.action_points.models import ActionPointPool

        flush_cache()
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock()
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.caller.search.side_effect = _search_returns(self.target)
        pool = ActionPointPool.get_or_create_for_character(self.caller)
        pool.current = 40
        pool.save(update_fields=["current"])

    def test_ap_sets_the_allocation(self) -> None:
        _make_cmd(self.caller, f"ap {self.target.db_key}=9").func()
        side = CharacterRelationship.objects.get(source=self.caller_sheet, target=self.target_sheet)
        self.assertEqual(side.allocation.ap_amount, 9)

    def test_ap_requires_a_number(self) -> None:
        _make_cmd(self.caller, f"ap {self.target.db_key}=nine").func()
        self.assertIn("must be a number", _capture(self.caller))

    def test_summary_sets_the_summary(self) -> None:
        _make_cmd(self.caller, f"summary {self.target.db_key}=A throat.").func()
        side = CharacterRelationship.objects.get(source=self.caller_sheet, target=self.target_sheet)
        self.assertEqual(side.summary, "A throat.")


class CmdRelationshipAdvanceTests(TestCase):
    """``relationship advance <name>=<journal entry id>`` runs AdvanceRelationshipTierAction."""

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

    def test_advance_reports_the_gate(self) -> None:
        from world.journals.factories import JournalEntryFactory

        entry = JournalEntryFactory(author=self.caller_sheet, about=self.target_sheet)
        _make_cmd(self.caller, f"advance {self.target.db_key}={entry.pk}").func()
        self.assertIn(
            "The relationship is not deep enough for the next tier.", _capture(self.caller)
        )

    def test_advance_refuses_a_journal_entry_that_is_not_yours(self) -> None:
        from world.journals.factories import JournalEntryFactory

        other_sheet = CharacterSheetFactory()
        entry = JournalEntryFactory(author=other_sheet, about=self.target_sheet)
        _make_cmd(self.caller, f"advance {self.target.db_key}={entry.pk}").func()
        self.assertIn("No journal entry", _capture(self.caller))


class CmdRelationshipReadTests(TestCase):
    """``relationship list``/``show`` render the target name, a label, and depth."""

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
        RelationshipTypeFactory(name="Friend")
        _make_cmd(self.caller, f"declare {self.target.db_key}=Friend,public").func()
        self.caller.msg.reset_mock()

    def test_list_renders_target_label_and_depth(self) -> None:
        _make_cmd(self.caller, "list").func()
        out = _capture(self.caller)
        self.assertIn(self.target.db_key, out)
        self.assertIn("Friend", out)
        self.assertIn("depth", out)

    def test_bare_relationship_is_the_same_as_list(self) -> None:
        _make_cmd(self.caller, "").func()
        out = _capture(self.caller)
        self.assertIn(self.target.db_key, out)

    def test_show_renders_detail(self) -> None:
        _make_cmd(self.caller, f"show {self.target.db_key}").func()
        out = _capture(self.caller)
        self.assertIn(self.target.db_key, out)
        self.assertIn("Friend", out)
        self.assertIn("depth", out)
        self.assertIn("ap this week", out)

    def test_show_by_id(self) -> None:
        side = CharacterRelationship.objects.get()
        _make_cmd(self.caller, f"show {side.pk}").func()
        self.assertIn(self.target.db_key, _capture(self.caller))

    def test_list_empty(self) -> None:
        other_caller = CharacterFactory()
        CharacterSheetFactory(character=other_caller)
        other_caller.msg = MagicMock()
        _make_cmd(other_caller, "list").func()
        self.assertIn("no relationships", _capture(other_caller).lower())


class CmdRelationshipErrorTests(TestCase):
    """No active character / unresolved target / unknown subverb error paths."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.caller = CharacterFactory()
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock(return_value=None)

    def test_no_active_character(self) -> None:
        _make_cmd(self.caller, "list").func()
        self.assertIn("No active character", _capture(self.caller))

    def test_unresolved_target(self) -> None:
        CharacterSheetFactory(character=self.caller)
        RelationshipTypeFactory(name="Friend")
        _make_cmd(self.caller, "declare Nobody=Friend").func()
        self.assertIn("Could not find", _capture(self.caller))

    def test_unknown_subverb_shows_usage(self) -> None:
        CharacterSheetFactory(character=self.caller)
        _make_cmd(self.caller, "bogus").func()
        self.assertIn("Usage:", _capture(self.caller))


class CmdRelationshipBumpTests(TestCase):
    """``relationship plus|neg <name>`` (+ switch form) runs the bump Action (#1699)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        flush_cache()
        self.room = ObjectDBFactory(db_key="BumpRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.caller = CharacterFactory()
        self.caller.location = self.room
        self.caller.save()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller_tenure = RosterTenureFactory(roster_entry__character_sheet=self.caller_sheet)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock()
        self.target = CharacterFactory()
        self.target.location = self.room
        self.target.save()
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.target_tenure = RosterTenureFactory(roster_entry__character_sheet=self.target_sheet)
        SceneParticipationFactory(scene=self.scene, account=self.caller_tenure.player_data.account)
        SceneParticipationFactory(scene=self.scene, account=self.target_tenure.player_data.account)
        self.caller.search.side_effect = _search_returns(self.target)

    def _target_pose(self):
        from world.scenes.constants import InteractionMode
        from world.scenes.factories import InteractionFactory

        return InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
        )

    def test_plus_subverb_bumps_regard(self) -> None:
        from world.relationships.models import RelationshipBump

        pose = self._target_pose()
        _make_cmd(self.caller, f"plus {self.target.db_key}").func()
        bump = RelationshipBump.objects.get()
        self.assertEqual(bump.interaction_id, pose.pk)
        self.assertEqual(bump.valence, 1)
        relationship = CharacterRelationship.objects.get(
            source=self.caller_sheet, target=self.target_sheet
        )
        self.assertEqual(relationship.affection, 1)
        self.assertIn("warms", _capture(self.caller))

    def test_neg_switch_form_bumps_friction(self) -> None:
        from world.relationships.models import RelationshipBump

        self._target_pose()
        cmd = _make_cmd(self.caller, self.target.db_key)
        cmd.switches = ["neg"]
        cmd.func()
        bump = RelationshipBump.objects.get()
        self.assertEqual(bump.valence, -1)
        self.assertIn("cools", _capture(self.caller))

    def test_budget_exhaustion_reports_cleanly(self) -> None:
        self._target_pose()
        _make_cmd(self.caller, f"plus {self.target.db_key}").func()
        _make_cmd(self.caller, f"plus {self.target.db_key}").func()
        self.assertIn("already acknowledged", _capture(self.caller))

    def test_plus_requires_a_name(self) -> None:
        _make_cmd(self.caller, "plus").func()
        self.assertIn("Usage: relationship plus", _capture(self.caller))


class CmdRelationshipCompanionTargetTests(TestCase):
    """``relationship declare <companion>=...`` resolves the room-present companion (#3575)."""

    def setUp(self) -> None:
        from evennia.utils.create import create_object
        from evennia.utils.idmapper.models import flush_cache

        from typeclasses.companions import CompanionObject
        from world.companions.factories import CompanionFactory

        flush_cache()
        self.caller = CharacterFactory()
        self.caller_sheet = CharacterSheetFactory(character=self.caller)
        self.caller.msg = MagicMock()
        self.caller.search = MagicMock()
        self.companion = CompanionFactory(owner=self.caller_sheet, name="Ash")
        self.companion_obj = create_object(CompanionObject, key="Ash", nohome=True)
        self.companion.objectdb = self.companion_obj
        self.companion.save(update_fields=["objectdb"])
        self.caller.search.side_effect = _search_returns(self.companion_obj)
        RelationshipTypeFactory(name="Loyalty")

    def test_declare_toward_companion(self) -> None:
        _make_cmd(self.caller, "declare Ash=Loyalty").func()
        rel = CharacterRelationship.objects.get(
            source=self.caller_sheet, target_companion=self.companion
        )
        self.assertEqual(RelationshipLabel.objects.filter(relationship=rel).count(), 1)
        self.assertIn("Ash", _capture(self.caller))

    def test_list_and_show_render_the_companion_row(self) -> None:
        _make_cmd(self.caller, "declare Ash=Loyalty").func()
        self.caller.msg.reset_mock()
        _make_cmd(self.caller, "list").func()
        self.assertIn("Ash", _capture(self.caller))
        self.caller.msg.reset_mock()
        _make_cmd(self.caller, "show Ash").func()
        self.assertIn("Ash", _capture(self.caller))
