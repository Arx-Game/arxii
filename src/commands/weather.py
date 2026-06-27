"""Telnet ``time`` command (#1522) — the IC clock + local weather readout.

A glance at what time it is in the world and what the weather is doing where the character is
standing. The weather half resolves the region's current weather (most-specific-wins) and shows
one season/phase-appropriate line — the same atmospheric flavour the periodic echo pushes, but
on demand. The frontend renders the same `current_conditions` data as a widget.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdTime(ArxCommand):
    """Check the IC time and the weather where you are.

    Usage:
      time
      weather
    """

    key = "time"
    aliases = ["weather"]
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from world.weather.services import current_conditions  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere in particular.")
            return

        conditions = current_conditions(room)
        lines: list[str] = []
        if conditions.ic_time is None:
            lines.append("|xThe world's clock isn't running yet.|n")
        else:
            descriptor = conditions.phase.label if conditions.phase is not None else "an hour"
            if conditions.season is not None:
                descriptor = f"{descriptor} in {conditions.season.label}"
            stamp = conditions.ic_time.strftime("%H:%M, %B %d, %Y")
            lines.append(f"|wIt is {descriptor} — {stamp}.|n")

        if conditions.weather_type is not None:
            lines.append(f"|wWeather here:|n {conditions.weather_type.name}")
            if conditions.emit_text:
                lines.append(f"  |x{conditions.emit_text}|n")
        else:
            lines.append("|xThe weather here is unremarkable.|n")

        self.msg("\n".join(lines))
