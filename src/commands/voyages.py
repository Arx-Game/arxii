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

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from world.travel.models import TravelHub, TravelMethod

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.travel.models import Voyage, VoyageParticipant

_ACCEPT = "accept"
_ADVANCE = "advance"
_ARRIVE = "arrive"
_DECLINE = "decline"
_DEPART = "depart"
_INVITE = "invite"
_METHOD = "method"
_STATUS = "status"
_STOP = "stop"

#: Subverbs that take no argument and map 1:1 onto a voyage action.
_BARE_SUBCOMMANDS = frozenset({_ADVANCE, _ARRIVE, _STOP, _DEPART})


def _hub_name(voyage: Voyage) -> str:
    return voyage.destination_hub.name if voyage.destination_hub else "unknown"


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

    def func(self) -> None:
        args = self.args.strip().split()
        if not args:
            self.msg(
                "Usage: voyage <destination|method <m>|invite <name>|accept <id>|"
                "decline <id>|depart|advance|arrive|stop|status>"
            )
            return

        subcommand = args[0].lower()
        rest = args[1:]

        if subcommand in _BARE_SUBCOMMANDS:
            self._run_bare_action(subcommand)
        elif subcommand == _STATUS:
            self._show_status()
        elif subcommand == _METHOD and rest:
            self._set_travel_method(rest)
        elif subcommand == _INVITE and rest:
            self._invite(rest)
        elif subcommand in (_ACCEPT, _DECLINE) and rest:
            self._respond_to_invite(subcommand, rest)
        else:
            # Default: treat the whole argument as a destination hub name.
            self._start_voyage(args)

    def _run_bare_action(self, subcommand: str) -> None:
        """Dispatch the argument-free subverbs (advance/arrive/stop/depart)."""
        from actions.definitions.voyages import (  # noqa: PLC0415
            AbandonVoyageAction,
            AdvanceLegAction,
            CompleteVoyageAction,
            DepartVoyageAction,
        )

        action_class = {
            _ADVANCE: AdvanceLegAction,
            _ARRIVE: CompleteVoyageAction,
            _STOP: AbandonVoyageAction,
            _DEPART: DepartVoyageAction,
        }[subcommand]
        self.msg(action_class().run(self.caller).message)

    def _set_travel_method(self, rest: list[str]) -> None:
        method_name = " ".join(rest)
        method = TravelMethod.objects.filter(name__iexact=method_name).first()
        if method is None:
            self.msg(f"No travel method named '{method_name}'.")
            return
        self.caller.ndb.voyage_method = method
        self.msg(f"Travel method set to {method.name}.")

    def _invite(self, rest: list[str]) -> None:
        from actions.definitions.voyages import InviteToVoyageAction  # noqa: PLC0415

        target = self.caller.search(" ".join(rest))
        if target is None:
            return  # search already sent a "not found" message
        try:
            target_persona_id = target.sheet_data.primary_persona_id
        except AttributeError:
            self.msg("That character has no persona.")
            return
        result = InviteToVoyageAction().run(self.caller, target_persona_id=target_persona_id)
        self.msg(result.message)

    def _respond_to_invite(self, subcommand: str, rest: list[str]) -> None:
        from actions.definitions.voyages import RespondVoyageInviteAction  # noqa: PLC0415

        try:
            invite_id = int(rest[0])
        except ValueError:
            self.msg(f"Usage: voyage {subcommand} <invite-id>")
            return
        result = RespondVoyageInviteAction().run(
            self.caller, invite_id=invite_id, accept=subcommand == _ACCEPT
        )
        self.msg(result.message)

    def _start_voyage(self, args: list[str]) -> None:
        from actions.definitions.voyages import StartVoyageAction  # noqa: PLC0415

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

    def _active_persona(self) -> Persona | None:
        """The caller's active persona, or None after messaging why not."""
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except AttributeError:
            sheet = None
        if sheet is None:
            self.msg("You have no active character.")
            return None

        persona = active_persona_for_sheet(sheet)
        if persona is None:
            self.msg("You have no active persona.")
        return persona

    def _show_status(self) -> None:
        from world.travel.constants import VoyageStatus  # noqa: PLC0415
        from world.travel.models import VoyageParticipant  # noqa: PLC0415

        persona = self._active_persona()
        if persona is None:
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
            self._show_pending_invites(persona)
        elif participant.voyage.status == VoyageStatus.DRAFT:
            self._show_draft_voyage(participant.voyage)
        else:
            self._show_voyage_in_transit(participant)

    def _show_pending_invites(self, persona: Persona) -> None:
        from world.travel.models import VoyageInvite  # noqa: PLC0415

        invites = VoyageInvite.objects.filter(
            target_persona=persona,
            response=VoyageInvite.Response.PENDING,
        ).select_related("voyage", "voyage__destination_hub")
        if not invites:
            self.msg("You are not currently on a voyage.")
            return
        self.msg("You have pending voyage invitations:")
        for inv in invites:
            self.msg(
                f"  #{inv.pk}: Voyage to {_hub_name(inv.voyage)} (invited by {inv.invited_by})"
            )
        self.msg("Use 'voyage accept <id>' or 'voyage decline <id>'.")

    def _show_draft_voyage(self, voyage: Voyage) -> None:
        from world.travel.models import VoyageInvite  # noqa: PLC0415

        self.msg(f"DRAFT voyage to {_hub_name(voyage)} via {voyage.travel_method.name}.")
        self.msg(f"  Participants: {voyage.participants.filter(left_at__isnull=True).count()}")
        for label, response in (
            ("Accepted", VoyageInvite.Response.ACCEPTED),
            ("Pending", VoyageInvite.Response.PENDING),
            ("Declined", VoyageInvite.Response.DECLINED),
        ):
            invites = voyage.invites.filter(response=response)
            if invites:
                self.msg(f"  {label}: " + ", ".join(str(i.target_persona) for i in invites))
        self.msg("Use 'voyage depart' to set out, or 'voyage stop' to cancel.")

    def _show_voyage_in_transit(self, participant: VoyageParticipant) -> None:
        voyage = participant.voyage
        total_hubs = len(voyage.route_hubs)
        self.msg(
            f"Voyage to {_hub_name(voyage)} "
            f"(hub {voyage.current_leg_index + 1}/{total_hubs}) "
            f"via {voyage.travel_method.name}. "
            f"Legs traveled: {participant.legs_traveled}."
        )
