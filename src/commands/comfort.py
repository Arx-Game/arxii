"""Telnet ``comfort`` command (#1514) — the in-room comfort/weather readout.

The subtle *mechanical* surface for the climate→comfort loop: a player can glance at how
liveable the room they're standing in actually is — its 1–10 comfort level and which exposures
(cold, heat, wet, wind) are biting after the building's enclosure, style, and decorations.

This is deliberately separate from the room's *description*: the desc is the player's trusted
flavour, the comfort readout is the mechanical arbiter (you can't write away the cold). A web
build-HUD + the comfort→AP-regen effect are follow-ups; this is the always-available glance.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdComfort(ArxCommand):
    """Check how comfortable the room you're in is.

    Shows the room's comfort level (1–10) and any environmental exposures still biting after
    its construction and furnishings.

    Usage:
      comfort
    """

    key = "comfort"
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from world.locations.constants import COMFORT_LEVEL_LABELS, StatKey  # noqa: PLC0415
        from world.locations.services import comfort_summary  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere in particular.")
            return

        summary = comfort_summary(room)
        label = COMFORT_LEVEL_LABELS.get(summary.level, "")
        lines = [f"|wComfort here:|n {label} ({summary.level}/10)"]
        if summary.felt_exposures:
            biting = ", ".join(
                f"{StatKey(key).label.split()[0].lower()} {value}"
                for key, value in summary.felt_exposures.items()
            )
            lines.append(f"  |xBiting:|n {biting}")
        if summary.amenity:
            lines.append(f"  |xComforts:|n {summary.amenity}")
        self.msg("\n".join(lines))
