"""Telnet `voyage` command (#1855) — dispatches the voyage actions.

Usage:
  voyage <destination>       - Start a voyage to a named hub
  voyage method <method>     - Set travel method
  voyage invite <name>       - Invite a co-located character (#2352)
  voyage accept <id>         - Accept a voyage invitation (#2352)
  voyage decline <id>        - Decline a voyage invitation (#2352)
  voyage depart              - Depart with accepted party (#2352)
  voyage advance             - Advance to next hub (tempus fugit)
  voyage arrive              - Complete voyage (fast-forward to destination)
  voyage stop                - Abandon voyage at current hub
  voyage status              - Show current voyage progress
"""

from __future__ import annotations

from commands.command import ArxCommand
from world.travel.models import TravelHub, TravelMethod

_ACCEPT = "accept"
_ADVANCE = "advance"
_ARRIVE = "arrive"
_DECLINE = "decline"
_DEPART = "depart"
_INVITE = "invite"
_METHOD = "method"
_STATUS = "status"
_STOP = "stop"


class CmdVoyage(ArxCommand):
    """Overworld travel / voyages.

    Usage:
      voyage <destination>
      voyage method <method>
      voyage invite <name>
      voyage accept <id>
      voyage decline <id>
      voyage depart
      voyage advance
      voyage arrive
      voyage stop
      voyage status
    """

    key = "voyage"
    aliases = ["voyages"]
    help_category = "Travel"

    def func(self) -> None:  # noqa: C901, PLR0911, PLR0912, PLR0915
        from actions.definitions.voyages import (  # noqa: PLC0415
            AbandonVoyageAction,
            AdvanceLegAction,
            CompleteVoyageAction,
            DepartVoyageAction,
            InviteToVoyageAction,
            RespondVoyageInviteAction,
            StartVoyageAction,
        )

        args = self.args.strip().split()
        if not args:
            self.msg(
                "Usage: voyage <destination|method <m>|invite <name>|accept <id>|"
                "decline <id>|depart|advance|arrive|stop|status>"
            )
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

        if subcommand == _INVITE and len(args) > 1:
            target_name = " ".join(args[1:])
            target = self.caller.search(target_name)
            if target is None:
                return  # search already sent a "not found" message
            try:
                target_persona_id = target.sheet_data.primary_persona_id
            except AttributeError:
                self.msg("That character has no persona.")
                return
            result = InviteToVoyageAction().run(self.caller, target_persona_id=target_persona_id)
            self.msg(result.message)
            return

        if subcommand == _ACCEPT and len(args) > 1:
            try:
                invite_id = int(args[1])
            except ValueError:
                self.msg("Usage: voyage accept <invite-id>")
                return
            result = RespondVoyageInviteAction().run(self.caller, invite_id=invite_id, accept=True)
            self.msg(result.message)
            return

        if subcommand == _DECLINE and len(args) > 1:
            try:
                invite_id = int(args[1])
            except ValueError:
                self.msg("Usage: voyage decline <invite-id>")
                return
            result = RespondVoyageInviteAction().run(self.caller, invite_id=invite_id, accept=False)
            self.msg(result.message)
            return

        if subcommand == _DEPART:
            result = DepartVoyageAction().run(self.caller)
            self.msg(result.message)
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

    def _show_status(self) -> None:  # noqa: C901
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.travel.constants import VoyageStatus  # noqa: PLC0415
        from world.travel.models import VoyageInvite, VoyageParticipant  # noqa: PLC0415

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
                voyage__status__in=[VoyageStatus.DRAFT, VoyageStatus.IN_TRANSIT],
            )
            .select_related("voyage", "voyage__destination_hub", "voyage__travel_method")
            .first()
        )
        if participant is None:
            # Check for pending invites
            invites = VoyageInvite.objects.filter(
                target_persona=persona,
                response=VoyageInvite.Response.PENDING,
            ).select_related("voyage", "voyage__destination_hub")
            if invites:
                self.msg("You have pending voyage invitations:")
                for inv in invites:
                    dest = (
                        inv.voyage.destination_hub.name if inv.voyage.destination_hub else "unknown"
                    )
                    self.msg(f"  #{inv.pk}: Voyage to {dest} (invited by {inv.invited_by})")
                self.msg("Use 'voyage accept <id>' or 'voyage decline <id>'.")
            else:
                self.msg("You are not currently on a voyage.")
            return

        voyage = participant.voyage
        dest_name = voyage.destination_hub.name if voyage.destination_hub else "unknown"

        if voyage.status == VoyageStatus.DRAFT:
            self.msg(f"DRAFT voyage to {dest_name} via {voyage.travel_method.name}.")
            # Show party roster
            accepted = voyage.invites.filter(response=VoyageInvite.Response.ACCEPTED)
            pending = voyage.invites.filter(response=VoyageInvite.Response.PENDING)
            declined = voyage.invites.filter(response=VoyageInvite.Response.DECLINED)
            self.msg(f"  Participants: {voyage.participants.filter(left_at__isnull=True).count()}")
            if accepted:
                self.msg("  Accepted: " + ", ".join(str(i.target_persona) for i in accepted))
            if pending:
                self.msg("  Pending: " + ", ".join(str(i.target_persona) for i in pending))
            if declined:
                self.msg("  Declined: " + ", ".join(str(i.target_persona) for i in declined))
            self.msg("Use 'voyage depart' to set out, or 'voyage stop' to cancel.")
        else:
            total_hubs = len(voyage.route_hubs)
            self.msg(
                f"Voyage to {dest_name} "
                f"(hub {voyage.current_leg_index + 1}/{total_hubs}) "
                f"via {voyage.travel_method.name}. "
                f"Legs traveled: {participant.legs_traveled}."
            )
