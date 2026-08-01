"""Telnet face of the turf war (#2862 gap close).

``start_gang_turf`` shipped with no telnet, no REST, and no frontend — the
opening move of the whole turf war was reachable only through the generic
dispatch seam. This is the missing surface, plus the read that makes the
system legible from inside the fiction: standing on a corner should tell you
whose corner it is.

Usage:
  turf                    — who holds this neighborhood, and how firmly
  turf push <crew>        — open a turf project for your crew against here
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from actions.definitions.turf import StartGangTurfAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.areas.models import Area

_SUBVERB_PUSH = "push"
_USAGE = "Usage: turf | turf push <crew name>"

# Grip bands, purely descriptive (#2862 — no mechanical meaning of their own).
_GRIP_BANDS = (
    (0, "barely a foothold"),
    (25, "a loose hold"),
    (50, "a firm grip"),
    (75, "an iron grip"),
)


class CmdTurf(ArxCommand):
    """See who runs this neighborhood, or push your crew's claim on it.

    Usage:
      turf
      turf push <crew name>

    A push opens a turf project against the neighborhood you are standing
    in; feed it (and run turf jobs) and the corners change hands. Pushing
    against a crew that already holds ground will be noticed by them.
    """

    key = "turf"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = None  # routes to the action only on `push`

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_status()
            return
        parts = raw.split(maxsplit=1)
        crew_name = parts[1].strip() if len(parts) > 1 else ""
        if parts[0].lower() != _SUBVERB_PUSH or not crew_name:
            raise CommandError(_USAGE)
        self._push(crew_name)

    def _area(self) -> Area | None:
        """The area the caller is standing in, or None."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            return None
        try:
            profile = room.room_profile
        except (AttributeError, ObjectDoesNotExist):
            return None
        return profile.area if profile is not None else None

    def _show_status(self) -> None:
        from world.societies.models import NeighborhoodTurf  # noqa: PLC0415

        area = self._area()
        if area is None:
            self.msg("You are nowhere that anyone would fight over.")
            return
        turf = (
            NeighborhoodTurf.objects.filter(area=area)
            .select_related("controlling_org", "area")
            .first()
        )
        if turf is None or turf.controlling_org is None:
            self.msg(f"|w{area.name}|n is contested ground — nobody runs it.")
            return
        self.msg(
            f"|w{area.name}|n is run by |c{turf.controlling_org.name}|n "
            f"({self._grip_phrase(turf.grip)})."
        )

    @staticmethod
    def _grip_phrase(grip: int) -> str:
        phrase = _GRIP_BANDS[0][1]
        for floor, label in _GRIP_BANDS:
            if grip >= floor:
                phrase = label
        return phrase

    def _push(self, crew_name: str) -> None:
        from world.societies.models import Organization  # noqa: PLC0415

        area = self._area()
        if area is None:
            msg = "There is no ground here worth taking."
            raise CommandError(msg)
        organization = Organization.objects.filter(name__iexact=crew_name).first()
        if organization is None:
            organization = Organization.objects.filter(name__icontains=crew_name).first()
        if organization is None:
            msg = f"No crew called '{crew_name}'."
            raise CommandError(msg)
        result = StartGangTurfAction().run(
            actor=self.caller,
            organization_id=organization.pk,
            area_id=area.pk,
        )
        self.msg(result.message)

    def resolve_action_args(self) -> dict[str, Any]:  # pragma: no cover - unused
        return {}
