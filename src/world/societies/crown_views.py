"""The crown's read API (#4061 slice 2): who wears it, the open bid, your own vote.

One GET per city. While a bid is open the tally is hidden (the maintainer's
ruling: tallied only at the close), so the payload carries only the viewer's
own vote; the last closed bid shows its tally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.areas.models import Area
from world.societies.constants import CrownBidStatus
from world.societies.crown import current_crown, may_call_vote, vote_weight
from world.societies.models import CrownBid, CrownVote, OrganizationMembership

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from rest_framework.request import Request

    from world.character_sheets.models import CharacterSheet


class CrownSerializer(serializers.Serializer):
    organization = serializers.CharField()
    organization_id = serializers.IntegerField()
    recognized_at = serializers.DateTimeField()
    term_ends_at = serializers.DateTimeField()


class OpenBidSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    bidder = serializers.CharField()
    bidder_id = serializers.IntegerField()
    opened_at = serializers.DateTimeField()
    closes_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=CrownBidStatus.choices)


class ClosedBidSerializer(OpenBidSerializer):
    weight_for = serializers.IntegerField()
    weight_against = serializers.IntegerField()


class OwnVoteSerializer(serializers.Serializer):
    in_favor = serializers.BooleanField()
    weight = serializers.IntegerField()


class CrownPageSerializer(serializers.Serializer):
    city = serializers.CharField()
    crown = CrownSerializer(allow_null=True)
    bid = OpenBidSerializer(allow_null=True)
    last_bid = ClosedBidSerializer(allow_null=True)
    your_vote = OwnVoteSerializer(allow_null=True)
    your_weight = serializers.IntegerField()
    may_call = serializers.BooleanField()


def _viewer_sheet(request: Request) -> CharacterSheet | None:
    """The viewer's selected character, the durable selection the website shows."""
    account = cast("AccountDB", request.user)
    player_data = account.player_data
    entry = player_data.selected_entry if player_data is not None else None
    return entry.character_sheet if entry is not None else None


def _bid_payload(bid: CrownBid, *, with_tally: bool) -> dict:
    payload = {
        "id": bid.pk,
        "bidder": bid.bidder.name,
        "bidder_id": bid.bidder_id,
        "opened_at": bid.opened_at,
        "closes_at": bid.closes_at,
        "status": bid.status,
    }
    if with_tally:
        payload["weight_for"] = bid.weight_for
        payload["weight_against"] = bid.weight_against
    return payload


class CrownView(APIView):
    """GET ``/api/societies/crown/<city_id>/``."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, city_id: int) -> Response:
        try:
            city = Area.objects.get(pk=city_id)
        except Area.DoesNotExist:
            return Response({"detail": "No such city."}, status=404)
        crown = current_crown(city)
        open_bid = (
            CrownBid.objects.filter(city=city, status=CrownBidStatus.OPEN)
            .select_related("bidder")
            .first()
        )
        last_bid = (
            CrownBid.objects.filter(city=city)
            .exclude(status=CrownBidStatus.OPEN)
            .select_related("bidder")
            .first()
        )
        sheet = _viewer_sheet(request)
        own_vote = None
        weight = 0
        may_call = False
        if sheet is not None:
            weight = vote_weight(sheet)
            if open_bid is not None:
                vote = CrownVote.objects.filter(bid=open_bid, character_sheet=sheet).first()
                if vote is not None:
                    own_vote = {"in_favor": vote.in_favor, "weight": vote.weight}
            led = {
                m.organization
                for m in OrganizationMembership.objects.filter(
                    persona__character_sheet=sheet,
                    left_at__isnull=True,
                    exiled_at__isnull=True,
                    rank__can_manage_ranks=True,
                ).select_related("organization")
            }
            may_call = open_bid is None and any(may_call_vote(org, city) for org in led)
        payload = {
            "city": city.name,
            "crown": (
                {
                    "organization": crown.organization.name,
                    "organization_id": crown.organization_id,
                    "recognized_at": crown.recognized_at,
                    "term_ends_at": crown.term_ends_at,
                }
                if crown is not None
                else None
            ),
            "bid": _bid_payload(open_bid, with_tally=False) if open_bid is not None else None,
            "last_bid": _bid_payload(last_bid, with_tally=True) if last_bid is not None else None,
            "your_vote": own_vote,
            "your_weight": weight,
            "may_call": may_call,
        }
        return Response(CrownPageSerializer(payload).data)
