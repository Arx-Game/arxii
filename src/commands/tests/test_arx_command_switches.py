"""``ArxCommand.parse`` splits ``/switches`` off the arguments (#4232 fix-on-sight).

Evennia hands ``ceremony/wedding a,b`` to the command keyed ``ceremony`` with
``args`` of ``/wedding a,b``; the base command never parsed that, so every
subclass reading ``self.switches`` raised on a real telnet line.
"""

from django.test import SimpleTestCase

from commands.account.sheet import CmdSheet
from commands.ceremonies import CmdCeremony
from commands.command import ArxCommand


class _Probe(ArxCommand):
    key = "probe"


def _parsed(args: str) -> ArxCommand:
    cmd = _Probe()
    cmd.args = args
    cmd.parse()
    return cmd


class ArxCommandSwitchParseTests(SimpleTestCase):
    def test_a_slash_form_line_yields_switches_and_bare_args(self) -> None:
        cmd = _parsed("/wedding Rowan Ashby,Lisbet Crane")
        self.assertEqual(cmd.switches, ["wedding"])
        self.assertEqual(cmd.args, "Rowan Ashby,Lisbet Crane")

    def test_several_switches_and_no_args(self) -> None:
        cmd = _parsed("/finish")
        self.assertEqual(cmd.switches, ["finish"])
        self.assertEqual(cmd.args, "")
        cmd = _parsed("/a/b rest")
        self.assertEqual(cmd.switches, ["a", "b"])
        self.assertEqual(cmd.args, "rest")

    def test_a_plain_line_has_no_switches(self) -> None:
        cmd = _parsed("wedding Rowan Ashby,Lisbet Crane")
        self.assertEqual(cmd.switches, [])
        self.assertEqual(cmd.args, "wedding Rowan Ashby,Lisbet Crane")
        cmd = _parsed("")
        self.assertEqual(cmd.switches, [])
        self.assertEqual(cmd.args, "")

    def test_the_ceremony_command_parses_its_slash_form(self) -> None:
        cmd = CmdCeremony()
        cmd.args = "/wedding Rowan Ashby,Lisbet Crane"
        cmd.parse()
        self.assertEqual(cmd.switches, ["wedding"])
        self.assertEqual(cmd.args, "Rowan Ashby,Lisbet Crane")

    def test_the_sheet_command_parses_its_section_switch(self) -> None:
        cmd = CmdSheet()
        cmd.args = "/family"
        cmd.parse()
        self.assertEqual(cmd.switches, ["family"])
        self.assertEqual(cmd.args, "")
