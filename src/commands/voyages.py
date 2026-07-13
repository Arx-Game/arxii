"""Telnet `voyage` command (#1855) — dispatches the four voyage actions.

Usage:
  voyage <destination>       - Start a voyage to a named hub
  voyage method <method>      - Set travel method
  voyage advance               - Advance to next hub (tempus fugit)
  voyage arrive                - Complete voyage (fast-forward to destination)
  voyage stop                  - Abandon voyage at current hub
  voyage status                - Show current voyage progress
"""

from __future__ import annotations

from commands.command import ArxCommand
from world.travel.models import TravelHub, TravelMethod

_ADVANCE = "advance"
_ARRIVE = "arrive"
_JOIN = "join"
_METHOD = "method"
_STATUS = "status"
_STOP = "stop"


class CmdVoyage(ArxCommand):
    """Overworld travel / voyages.

    Usage:
      voyage <destination>
      voyage method <method>
      voyage advance
      voyage arrive
      voyage stop
      voyage status
    """

    key = "voyage"
    aliases = ["voyages"]
    help_category = "Travel"

    def func(self) -> None:  # noqa: C901, PLR0911
        from actions.definitions.voyages import (  # noqa: PLC0415
            AbandonVoyageAction,
            AdvanceLegAction,
            CompleteVoyageAction,
            StartVoyageAction,
        )

        args = self.args.strip().split()
        if not args:
            self.msg("Usage: voyage <destination|method <m>|advance|arrive|stop|status>")
            return

        subcommand = args[0].lower()

        if subcommand == _ADVANCE:
            result = AdvanceLegAction().run(self.caller)
            self.msg(result.message)
            return

        if subcommand == _ARRIVE:
            result = CompleteVoyageAction().run(self.caller)
            self.msg(result.message)
            return

        if subcommand == _STOP:
            result = AbandonVoyageAction().run(self.caller)
            self.msg(result.message)
            return

        if subcommand == _STATUS:
            self._show_status()
            return

        if subcommand == _METHOD and len(args) > 1:
            method_name = " ".join(args[1:])
            method = TravelMethod.objects.filter(name__iexact=method_name).first()
            if method is None:
                self.msg(f"No travel method named '{method_name}'.")
                return
            self.caller.ndb.voyage_method = method
            self.msg(f"Travel method set to {method.name}.")
            return

        if subcommand == _JOIN:
            self.msg("Joining voyages is not yet implemented.")
            return

        # Default: treat as destination name
        dest_name = " ".join(args)
        hub = TravelHub.objects.filter(name__iexact=dest_name, is_active=True).first()
        if hub is None:
            self.msg(f"No travel hub named '{dest_name}'.")
            return

        method = self.caller.ndb.voyage_method
        if method is None:
            method = TravelMethod.objects.filter(is_default=True).first()
            if method is None:
                self.msg("No default travel method available. Set one with 'voyage method <name>'.")
                return

        result = StartVoyageAction().run(
            self.caller,
            destination_id=hub.room_profile_id,
            travel_method_id=method.pk,
        )
        self.msg(result.message)

    def _show_status(self) -> None:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.travel.constants import VoyageStatus  # noqa: PLC0415
        from world.travel.models import VoyageParticipant  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except AttributeError:
            sheet = None
        if sheet is None:
            self.msg("You have no active character.")
            return

        persona = active_persona_for_sheet(sheet)
        if persona is None:
            self.msg("You have no active persona.")
            return

        participant = (
            VoyageParticipant.objects.filter(
                persona=persona,
                left_at__isnull=True,
                voyage__status=VoyageStatus.IN_TRANSIT,
            )
            .select_related("voyage", "voyage__destination_hub", "voyage__travel_method")
            .first()
        )
        if participant is None:
            self.msg("You are not currently on a voyage.")
            return

        voyage = participant.voyage
        total_hubs = len(voyage.route_hubs)
        dest_name = voyage.destination_hub.name if voyage.destination_hub else "unknown"
        self.msg(
            f"Voyage to {dest_name} "
            f"(hub {voyage.current_leg_index + 1}/{total_hubs}) "
            f"via {voyage.travel_method.name}. "
            f"Legs traveled: {participant.legs_traveled}."
        )
