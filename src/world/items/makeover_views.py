"""``/api/items/makeover-requests/``: a character's pending makeover asks and the answer (#4187).

The web face of the ask (the telnet face is ``world.items.offer_handlers``). The list is
the caller's own personas as target, after the lazy lapse check, so a stale card never
shows; ``respond`` grants or declines through the one service the telnet handler uses,
with the optional ``remember`` shortcut (``MakeoverRemember``) written in the same motion.
"""

from __future__ import annotations

from http import HTTPMethod

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.items.constants import MakeoverRemember
from world.items.exceptions import ItemError, MakeoverRequestLapsed, MakeoverRequestResolved
from world.items.makeover_models import MakeoverConsentRequest
from world.items.services.makeover_requests import (
    describe_offer,
    expire_if_lapsed,
    respond_to_makeover_request,
)
from world.scenes.action_constants import ActionRequestStatus


class MakeoverConsentRequestSerializer(serializers.ModelSerializer):
    """One pending ask as the target's card shows it."""

    stylist_name = serializers.CharField(source="stylist_persona.name", read_only=True)
    item_name = serializers.CharField(source="item_instance.display_name", read_only=True)
    trait_name = serializers.SerializerMethodField()
    option_name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    target_character_id = serializers.SerializerMethodField()

    class Meta:
        model = MakeoverConsentRequest
        fields = (
            "id",
            "stylist_name",
            "item_name",
            "trait_name",
            "option_name",
            "blend",
            "descriptor",
            "description",
            "target_character_id",
            "requested_at",
        )
        read_only_fields = fields

    def get_trait_name(self, obj: MakeoverConsentRequest) -> str | None:
        return obj.option.trait.display_name if obj.option is not None else None

    def get_option_name(self, obj: MakeoverConsentRequest) -> str | None:
        return obj.option.display_name if obj.option is not None else None

    def get_description(self, obj: MakeoverConsentRequest) -> str:
        return describe_offer(obj)

    def get_target_character_id(self, obj: MakeoverConsentRequest) -> int:
        """The ObjectDB pk of the asked character, so the notifier can switch to them."""
        return obj.target_persona.character_sheet_id


class RespondMakeoverRequestSerializer(serializers.Serializer):
    GRANT = "grant"
    DECLINE = "decline"

    decision = serializers.ChoiceField(choices=[GRANT, DECLINE])
    remember = serializers.ChoiceField(
        choices=MakeoverRemember.choices, required=False, allow_null=True
    )

    def validate(self, attrs: dict) -> dict:
        """ALWAYS rides a grant and NEVER a decline; the other pairs are consent footguns."""
        remember = attrs.get("remember")
        decision = attrs["decision"]
        if (remember == MakeoverRemember.ALWAYS and decision != self.GRANT) or (
            remember == MakeoverRemember.NEVER and decision != self.DECLINE
        ):
            raise serializers.ValidationError(
                {"remember": "Always let goes with a grant; never from goes with a decline."}
            )
        return attrs


class MakeoverConsentRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """The requesting account's own pending makeover asks (as target)."""

    serializer_class = MakeoverConsentRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post"]

    def get_queryset(self) -> QuerySet[MakeoverConsentRequest]:
        return (
            MakeoverConsentRequest.objects.filter(
                target_persona_id__in=self.request.user.cached_persona_ids,
                status=ActionRequestStatus.PENDING,
            )
            .select_related(
                "stylist_persona__character_sheet",
                "target_persona__character_sheet",
                "item_instance",
                "option__trait",
            )
            .order_by("requested_at")
        )

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Pending asks, after expiring any whose stylist has left the room."""
        rows = [row for row in self.get_queryset() if not expire_if_lapsed(row)]
        return Response(self.get_serializer(rows, many=True).data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def respond(self, request: Request, pk: int | None = None) -> Response:
        """Grant or decline this ask; ``remember`` writes the always / never shortcut.

        Looks up by (pk, own personas) rather than through ``get_queryset`` (PENDING-only)
        so a double-submit lands on the "already answered" 400 instead of a bare 404; a
        row addressed to someone else's persona is a 404 either way.
        """
        consent_request = get_object_or_404(
            MakeoverConsentRequest,
            pk=pk,
            target_persona_id__in=request.user.cached_persona_ids,
        )
        serializer = RespondMakeoverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accept = serializer.validated_data["decision"] == RespondMakeoverRequestSerializer.GRANT
        try:
            respond_to_makeover_request(
                consent_request,
                accept=accept,
                remember=serializer.validated_data.get("remember"),
            )
        except MakeoverRequestResolved as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        except MakeoverRequestLapsed as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_409_CONFLICT)
        except ItemError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": consent_request.status})
