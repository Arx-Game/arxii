"""Telnet ``comfort`` command (#1514/#1522) — how comfortable *you* are, and why.

Leads with the player's **personal** comfort: the room's exposure (climate + weather + style)
after their worn clothing mitigates it — a named band (Comfortable → Extremely uncomfortable)
with the biting reasons (cold, heat, wet, injured…). Clothing — especially resonance-imbued
clothing — is what counteracts it, so a well-dressed character is comfortable where a scantily
clad one isn't. The room's own comfort level follows as context.

This is deliberately separate from the room's *description*: the desc is the player's trusted
flavour, the comfort readout is the mechanical arbiter (you can't write away the cold).
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdComfort(ArxCommand):
    """Check how comfortable you are where you're standing.

    Shows your personal comfort band and what's biting (after your clothing), then the room's own
    comfort level.

    Usage:
      comfort
    """

    key = "comfort"
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from world.locations.character_comfort import character_comfort_summary  # noqa: PLC0415
        from world.locations.constants import COMFORT_LEVEL_LABELS  # noqa: PLC0415
        from world.locations.services import comfort_summary  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere in particular.")
            return

        me = character_comfort_summary(self.caller)
        lines = [f"|wYou feel {me.band.lower()}.|n"]
        if me.reasons:
            lines.append(f"  |x({', '.join(me.reasons)})|n")

        room_summary = comfort_summary(room)
        room_label = COMFORT_LEVEL_LABELS.get(room_summary.level, "")
        lines.append(f"|xThe room itself:|n {room_label} ({room_summary.level}/10)")
        self.msg("\n".join(lines))
