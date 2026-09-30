"""Telnet face of the underworld crown (#4061 slice 2).

Usage:
  crown                      who wears the city's crown, the open bid, your vote
  crown bid <family name>    call the vote in your family's name (leaders only)
  crown vote for|against     cast your vote on the open bid

The web is the primary face; this is the compatibility surface over the same
actions (``call_crown_vote``, ``cast_crown_vote``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from actions.definitions.crown import CallCrownVoteAction, CastCrownVoteAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.areas.models import Area

_VERB_BID = "bid"
_VERB_VOTE = "vote"
_SIDE_FOR = "for"
_SIDE_AGAINST = "against"


class CmdCrown(ArxCommand):
    """See who wears the city's crown, bid for it, or vote on an open bid.

    Usage:
      crown
      crown bid <family name>
      crown vote for
      crown vote against
    """

    key = "crown"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = None  # routes to an action only on bid / vote

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _city(self) -> Area | None:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.areas.constants import AreaLevel  # noqa: PLC0415

        room = self.caller.location
        try:
            node = room.room_profile.area
        except (AttributeError, ObjectDoesNotExist):
            return None
        seen = 0
        while node is not None and seen < 10:  # noqa: PLR2004 - defensive walk cap
            if node.level == AreaLevel.BARONY:
                return node
            node = node.parent
            seen += 1
        return None

    def _dispatch(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_status()
            return
        parts = raw.split(maxsplit=1)
        verb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if verb == _VERB_BID:
            self._bid(rest)
        elif verb == _VERB_VOTE:
            self._vote(rest)
        else:
            msg = "Usage: crown | crown bid <family name> | crown vote for|against"
            raise CommandError(msg)

    def _show_status(self) -> None:
        from world.societies.constants import CrownBidStatus  # noqa: PLC0415
        from world.societies.crown import current_crown, vote_weight  # noqa: PLC0415
        from world.societies.models import CrownBid, CrownVote  # noqa: PLC0415

        city = self._city()
        if city is None:
            self.msg("No city claims this ground.")
            return
        crown = current_crown(city)
        if crown is None:
            self.msg(f"Nobody wears the crown of |w{city.name}|n.")
        else:
            self.msg(
                f"|c{crown.organization.name}|n wears the crown of |w{city.name}|n "
                f"(since {crown.recognized_at:%Y-%m-%d}, term to {crown.term_ends_at:%Y-%m-%d})."
            )
        bid = (
            CrownBid.objects.filter(city=city, status=CrownBidStatus.OPEN)
            .select_related("bidder")
            .first()
        )
        if bid is None:
            self.msg("No vote is open.")
            return
        self.msg(
            f"|c{bid.bidder.name}|n bids for the crown; the vote closes {bid.closes_at:%Y-%m-%d}."
        )
        sheet = self.caller.character_sheet
        if sheet is None:
            return
        vote = CrownVote.objects.filter(bid=bid, character_sheet=sheet).first()
        weight = vote_weight(sheet)
        if vote is not None:
            side = "for" if vote.in_favor else "against"
            self.msg(f"You have voted {side} ({vote.weight}).")
        elif weight > 0:
            self.msg(f"Your word would carry {weight}. 'crown vote for' or 'crown vote against'.")

    def _bid(self, family_name: str) -> None:
        from world.societies.models import Organization  # noqa: PLC0415

        if not family_name:
            msg = "Bid in whose name? 'crown bid <family name>'."
            raise CommandError(msg)
        city = self._city()
        if city is None:
            msg = "No city claims this ground."
            raise CommandError(msg)
        organization = Organization.objects.filter(name__iexact=family_name).first()
        if organization is None:
            organization = Organization.objects.filter(name__icontains=family_name).first()
        if organization is None:
            msg = f"No family called '{family_name}'."
            raise CommandError(msg)
        result = CallCrownVoteAction().run(
            self.caller, organization_id=organization.pk, city_id=city.pk
        )
        self.msg(result.message)

    def _vote(self, side: str) -> None:
        from world.societies.constants import CrownBidStatus  # noqa: PLC0415
        from world.societies.models import CrownBid  # noqa: PLC0415

        side = side.lower()
        if side not in (_SIDE_FOR, _SIDE_AGAINST):
            msg = "'crown vote for' or 'crown vote against'."
            raise CommandError(msg)
        city = self._city()
        if city is None:
            msg = "No city claims this ground."
            raise CommandError(msg)
        bid = CrownBid.objects.filter(city=city, status=CrownBidStatus.OPEN).first()
        if bid is None:
            msg = "No vote is open."
            raise CommandError(msg)
        result = CastCrownVoteAction().run(self.caller, bid_id=bid.pk, in_favor=side == _SIDE_FOR)
        self.msg(result.message)
