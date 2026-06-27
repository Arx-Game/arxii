"""Telnet journey: missions — resolve beat, abandon, group pick + vote (#1349).

Drives the mission play loop end-to-end through the `mission` telnet command
(`CmdMission`), proving the same `world.missions.services.play` seam the web
`MissionJournalViewSet` uses is fully reachable from pure backend input. The
command is a thin layer over the services; the engine itself is covered by
`world/missions/tests/test_play_surface.py` (solo) and
`test_1036_group_play.py` (group).

Graphs use BRANCH options (no dice) so routing is deterministic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.missions import CmdMission
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import ConflictMode, MissionStatus, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRecord, MissionGroupBallot
from world.missions.services.run import share_mission, staff_assign_mission


def _run(caller: object, args: str = "") -> CmdMission:
    """Build and execute a `mission` command instance; return it for assertions."""
    cmd = CmdMission()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"mission {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _said(caller: object) -> str:
    """Concatenate every positional string the command sent to the caller."""
    chunks: list[str] = []
    for call in caller.msg.call_args_list:
        chunks.extend(arg for arg in call.args if isinstance(arg, str))
    return "\n".join(chunks)


def _pc(db_key: str | None = None) -> object:
    character = CharacterFactory(db_key=db_key) if db_key else CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


def _solo_graph(name: str):
    """Entry node (one BRANCH option) → second node (terminal BRANCH option).

    Solo: a single-participant run, so the GROUP_VOTE factory default on the
    node is inert (group flow needs >1 participant).
    """
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    MissionOptionFactory(
        node=entry,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER take the first step",
        branch_target=second,
    )
    MissionOptionFactory(
        node=second,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER finish it",
        branch_target=None,  # terminal
    )
    return template, entry, second


def _group_graph(name: str):
    """A 2-participant GROUP_VOTE entry node with two BRANCH options."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(
        template=template,
        key="entry",
        is_entry=True,
        conflict_mode=ConflictMode.GROUP_VOTE,
    )
    dest_a = MissionNodeFactory(template=template, key="dest-a")
    dest_b = MissionNodeFactory(template=template, key="dest-b")
    MissionOptionFactory(
        node=entry,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Path A",
        branch_target=dest_a,
    )
    MissionOptionFactory(
        node=entry,
        order=1,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Path B",
        branch_target=dest_b,
    )
    return template, entry, dest_a, dest_b


class SoloMissionTelnetTests(TestCase):
    def setUp(self) -> None:
        self.pc = _pc("Solo")
        self.template, self.entry, self.second = _solo_graph("solo-journey")
        self.instance = staff_assign_mission(self.template, self.pc)

    def test_journal_lists_the_run(self) -> None:
        _run(self.pc)
        out = _said(self.pc)
        self.assertIn(str(self.instance.pk), out)
        self.assertIn("solo-journey", out)

    def test_beat_shows_numbered_options(self) -> None:
        _run(self.pc, f"beat {self.instance.pk}")
        out = _said(self.pc)
        self.assertIn("1)", out)
        self.assertIn("take the first step", out)

    def test_resolve_advances_the_node_and_records_a_deed(self) -> None:
        _run(self.pc, f"resolve {self.instance.pk} 1")
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node_id, self.second.pk)
        self.assertTrue(MissionDeedRecord.objects.filter(instance=self.instance).exists())

    def test_abandon_marks_the_run_abandoned(self) -> None:
        _run(self.pc, f"abandon {self.instance.pk}")
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.ABANDONED)

    def test_resolve_out_of_range_ordinal_is_a_friendly_error(self) -> None:
        _run(self.pc, f"resolve {self.instance.pk} 9")
        self.assertIn("option", _said(self.pc).lower())
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node_id, self.entry.pk)  # unchanged

    def test_non_participant_cannot_inspect_the_beat(self) -> None:
        intruder = _pc("Nosy")
        _run(intruder, f"beat {self.instance.pk}")
        self.assertIn("not part of that mission", _said(intruder).lower())

    def test_pick_on_a_solo_beat_steers_to_resolve(self) -> None:
        _run(self.pc, f"pick {self.instance.pk} 1")
        self.assertIn("resolve", _said(self.pc).lower())


class GroupMissionTelnetTests(TestCase):
    def setUp(self) -> None:
        self.holder = _pc("Holder")
        self.p2 = _pc("Second")
        self.template, self.entry, self.dest_a, self.dest_b = _group_graph("group-journey")
        self.instance = staff_assign_mission(self.template, self.holder)
        share_mission(self.instance, self.p2)

    def test_pick_then_vote_resolves_to_the_chosen_branch(self) -> None:
        # Stage 1: both pick option 1 (Path A).
        _run(self.holder, f"pick {self.instance.pk} 1")
        _run(self.p2, f"pick {self.instance.pk} 1")
        self.assertTrue(MissionGroupBallot.objects.filter(instance=self.instance).count() == 2)
        # Stage 2: both vote option 1 → Path A wins → resolves to dest-a.
        _run(self.holder, f"vote {self.instance.pk} 1")
        _run(self.p2, f"vote {self.instance.pk} 1")
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node_id, self.dest_a.pk)
        self.assertFalse(MissionGroupBallot.objects.filter(instance=self.instance).exists())

    def test_resolve_on_a_group_beat_steers_to_pick(self) -> None:
        _run(self.holder, f"resolve {self.instance.pk} 1")
        self.assertIn("pick", _said(self.holder).lower())
        # Nothing resolved.
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node_id, self.entry.pk)

    def test_beat_shows_the_group_decision(self) -> None:
        _run(self.holder, f"beat {self.instance.pk}")
        out = _said(self.holder)
        self.assertIn("Path A", out)
        self.assertIn("1)", out)
