"""Telnet ``sphinx`` command (#2640) — the Sphinx of Black Quartz's vow-suitability verdict.

Diegetic Shroudwatch Academy fixture, invoked *"Sphinx of Black Quartz, judge my vow:
<vow>."* Read-only telnet parity for the REST endpoint (``CovenantRoleViewSet.sphinx``)
— both call the same ``world.covenants.sphinx.judge_vow``, no parallel logic. v1
judgment call: invocable anywhere (the Academy-room gating is presentation/content,
not mechanics; flagged for review — #2640 spec). Soft gate: the Sphinx informs, it
never blocks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole
    from world.covenants.sphinx import SphinxVerdict

_NO_IDENTITY = "You have no active character for the Sphinx to judge."
_USAGE = "Usage: sphinx <vow name>"


class CmdSphinx(ArxCommand):
    """Ask the Sphinx of Black Quartz to judge a vow.

    Usage:
        sphinx <vow name>   — the Sphinx's three-tier verdict on your known
                               techniques against that vow's authored demands

    Soft gate: the Sphinx informs, it never blocks — you may still swear a
    vow it warns about.
    """

    key = "sphinx"
    locks = "cmd:all()"
    help_category = "Covenants"
    action = None

    def func(self) -> None:
        sheet = self.caller.character_sheet
        if sheet is None:
            self.caller.msg(_NO_IDENTITY)
            return

        vow_name = (self.args or "").strip()
        if not vow_name:
            self.caller.msg(_USAGE)
            return

        from world.covenants.models import CovenantRole  # noqa: PLC0415

        role = CovenantRole.objects.filter(name__iexact=vow_name).first()
        if role is None:
            self.caller.msg(f"The Sphinx does not know of a vow named '{vow_name}'.")
            return

        self.caller.msg(self._render_verdict(sheet, role))

    def _render_verdict(self, sheet: CharacterSheet, role: CovenantRole) -> str:
        from world.covenants.constants import SphinxTier  # noqa: PLC0415
        from world.covenants.sphinx import judge_vow  # noqa: PLC0415

        verdict = judge_vow(sheet, role)
        lines = [f"|wSphinx of Black Quartz, judge my vow: {role.name}.|n"]

        if verdict.tier == SphinxTier.TAKES:
            lines.append("The vow will take.")
            lines.extend(self._answered_lines(verdict))
        elif verdict.tier == SphinxTier.DORMANT:
            lines.append("The vow would lie dormant in places:")
            lines.extend(self._uncovered_lines(verdict))
        else:
            lines.append("The vow will not take — yet.")
            lines.extend(self._uncovered_lines(verdict))
            lines.extend(self._shopping_lines(verdict))

        return "\n".join(lines)

    @staticmethod
    def _answered_lines(verdict: SphinxVerdict) -> list[str]:
        names = sorted(
            {
                name
                for demand in verdict.demands
                if demand.covered
                for name in demand.qualifying_technique_names
            }
        )
        if not names:
            return []
        return [f"  Answered by: {', '.join(names)}."]

    @staticmethod
    def _uncovered_lines(verdict: SphinxVerdict) -> list[str]:
        uncovered = [demand for demand in verdict.demands if not demand.covered]
        if not uncovered:
            return []
        return [f"  {demand.function} ({demand.source}) — unanswered." for demand in uncovered]

    @staticmethod
    def _shopping_lines(verdict: SphinxVerdict) -> list[str]:
        if not verdict.shopping_list:
            return ["  No learnable technique would change this today."]
        lines = ["  Seek:"]
        lines.extend(
            f"    {item.technique_name} ({item.gift_name}) — answers {item.function}."
            for item in verdict.shopping_list
        )
        return lines
