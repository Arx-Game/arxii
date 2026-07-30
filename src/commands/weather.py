"""Telnet ``time`` command (#1522, celestial #2845) — the IC clock + local weather readout.

A glance at what time it is in the world (IC and server-clock), the moon at night, and what
the weather is doing where the character is standing. The weather half resolves the region's
current weather (most-specific-wins) and shows one season/phase-appropriate line — the same
atmospheric flavour the periodic echo pushes, but on demand. The frontend renders the same
`current_conditions` data as a widget.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from commands.command import ArxCommand

# Player-facing server-clock timezone (#2845): the game's scheduling anchor is US-Eastern
# (the weekly rollover anchors EST), so the `time` command reports it there. Display-only —
# Django's TIME_ZONE stays UTC; %Z renders EST/EDT correctly across daylight saving.
SERVER_DISPLAY_TIMEZONE = ZoneInfo("America/New_York")


class CmdTime(ArxCommand):
    """Check the IC time and the weather where you are.

    Usage:
      time
      weather
      weather squelch     - stop the periodic weather echo (still readable in its tab)
      weather unsquelch   - resume the periodic weather echo
    """

    key = "time"
    aliases = ["weather"]
    locks = "cmd:all()"
    help_category = "General"
    action = None
    SQUELCH = "squelch"
    UNSQUELCH = "unsquelch"

    def func(self) -> None:
        from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
        from world.narrative.services import is_category_muted, set_category_mute  # noqa: PLC0415
        from world.weather.services import current_conditions  # noqa: PLC0415

        arg = self.args.strip().lower()
        account = self.account
        if arg in (self.SQUELCH, self.UNSQUELCH) and account is not None:
            muted = arg == self.SQUELCH
            set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=muted)
            self.msg("Weather echoes squelched." if muted else "Weather echoes restored.")
            return

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere in particular.")
            return

        conditions = current_conditions(room)
        lines: list[str] = [
            self._time_line(conditions),
            self._server_time_line(),
            *self._moon_lines(conditions),
            *self._weather_lines(conditions),
        ]

        if account is not None and is_category_muted(
            account=account, category=NarrativeCategory.WEATHER
        ):
            lines.append("|x(weather echoes squelched — `weather unsquelch` to resume)|n")

        self.msg("\n".join(lines))

    @staticmethod
    def _time_line(conditions: Any) -> str:
        """One line for the IC clock (time/phase/season), or a not-running notice."""
        if conditions.ic_time is None:
            return "|xThe world's clock isn't running yet.|n"
        descriptor = conditions.phase.label if conditions.phase is not None else "an hour"
        if conditions.season is not None:
            descriptor = f"{descriptor} in {conditions.season.label}"
        stamp = conditions.ic_time.strftime("%H:%M, %B %d, %Y")
        return f"|wIt is {descriptor} — {stamp}.|n"

    @staticmethod
    def _server_time_line() -> str:
        """One line for the real server clock, in the game's US-Eastern anchor zone."""
        from django.utils import timezone  # noqa: PLC0415

        now = timezone.now().astimezone(SERVER_DISPLAY_TIMEZONE)
        return f"|xServer time: {now.strftime('%H:%M %Z, %B %d')}.|n"

    @staticmethod
    def _moon_lines(conditions: Any) -> list[str]:
        """The moon phase, shown at night only (#2845 — matches the web widget)."""
        from world.game_clock.constants import TimePhase  # noqa: PLC0415

        if conditions.phase != TimePhase.NIGHT or conditions.moon_phase is None:
            return []
        return [f"|wThe moon:|n {conditions.moon_phase.label}"]

    @staticmethod
    def _weather_lines(conditions: Any) -> list[str]:
        """The room's effective weather and its emit line, or an unremarkable notice."""
        if conditions.weather_type is None:
            return ["|xThe weather here is unremarkable.|n"]
        lines = [f"|wWeather here:|n {conditions.weather_type.name}"]
        if conditions.emit_text:
            lines.append(f"  |x{conditions.emit_text}|n")
        return lines
