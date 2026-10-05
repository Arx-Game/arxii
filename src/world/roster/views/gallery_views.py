"""A character's Gallery (#4151): list, upload, edit, reorder, delete, hide and show.

Every write goes through ``world.roster.services.gallery``, which owns the rules that
keep the worn look showable; this layer resolves the request, checks who is asking and
turns a refused change into its ``user_message``.
"""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from http import HTTPMethod
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from world.roster.filters import GalleryPictureFilterSet
from world.roster.models import RosterEntry, TenureMedia
from world.roster.permissions import CanManageGallery
from world.roster.serializers.gallery import (
    GalleryDeleteResultSerializer,
    GalleryPictureSerializer,
    GalleryPictureUpdateSerializer,
    GalleryReorderSerializer,
    GalleryUploadSerializer,
    MediaUsageSerializer,
)
from world.roster.services.gallery import (
    UNSET,
    GalleryError,
    Unset,
    add_pictures,
    can_manage_gallery,
    clear_look,
    delete_picture,
    entry_of,
    hidden_ids,
    hide_character_art,
    media_usage,
    reorder_pictures,
    set_look,
    show_character_art,
    update_picture,
    wear_look,
)


def _refuse(exc: GalleryError) -> ValidationError:
    return ValidationError({"detail": exc.user_message})


class GalleryPictureViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """The pictures in one character's Gallery. ``?roster_entry=<id>`` is required."""

    serializer_class = GalleryPictureSerializer
    permission_classes = [CanManageGallery]
    filter_backends = [DjangoFilterBackend]
    filterset_class = GalleryPictureFilterSet
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[TenureMedia]:
        return TenureMedia.objects.select_related(
            "media__player_data",
            "look",
            "tenure__roster_entry",
            "roster_entry",
        )

    def filter_queryset(self, queryset: QuerySet[TenureMedia]) -> QuerySet[TenureMedia]:
        """Filter the list only. A single picture is addressed by its id alone."""
        if self.action != "list":
            return queryset
        return super().filter_queryset(queryset)

    def _account(self) -> AccountDB:
        """The requester. Every route here needs an account (``CanManageGallery``)."""
        return cast(AccountDB, self.request.user)

    # ------------------------------------------------------------ read

    def _context_for(self, entry: RosterEntry | None, links: Sequence[TenureMedia]) -> dict:
        """Serializer context for one character's pictures, in two queries at most."""
        context = self.get_serializer_context()
        context["account"] = self._account()
        if entry is None:
            return context
        context["worn_id"] = entry.profile_picture_id
        if can_manage_gallery(self._account(), entry):
            context["hidden_ids"] = hidden_ids(entry)
            context["also_on"] = self._also_on(entry, links)
        return context

    @staticmethod
    def _also_on(
        entry: RosterEntry, links: Sequence[TenureMedia]
    ) -> dict[int, MutableSequence[str]]:
        """For each file, the other characters whose gallery also holds it."""
        others = (
            TenureMedia.objects.filter(media_id__in=[link.media_id for link in links])
            .exclude(pk__in=[link.pk for link in links])
            .select_related(
                "tenure__roster_entry__character_sheet__character",
                "roster_entry__character_sheet__character",
            )
        )
        names: dict[int, MutableSequence[str]] = {}
        for other in others:
            other_entry = entry_of(other)
            if other_entry.pk != entry.pk:
                names.setdefault(other.media_id, []).append(
                    other_entry.character_sheet.character.db_key
                )
        return names

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        links = list(page if page is not None else queryset)
        entry = entry_of(links[0]) if links else None
        serializer = GalleryPictureSerializer(
            links, many=True, context=self._context_for(entry, links)
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def _one(self, link: TenureMedia) -> dict:
        link.refresh_from_db()
        entry = entry_of(link)
        entry.refresh_from_db(fields=["profile_picture"])
        return GalleryPictureSerializer(link, context=self._context_for(entry, [link])).data

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(self._one(self.get_object()))

    # ------------------------------------------------------------ write

    def _require_manager(self, entry: RosterEntry) -> None:
        if not can_manage_gallery(self._account(), entry):
            msg = "You can't change this character's gallery."
            raise PermissionDenied(msg)

    @extend_schema(
        request=GalleryUploadSerializer, responses={201: GalleryPictureSerializer(many=True)}
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Upload files into the Gallery (the player's own, or staff's character art)."""
        upload = GalleryUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        entry = upload.validated_data["roster_entry"]
        self._require_manager(entry)
        try:
            links = add_pictures(entry, upload.validated_data["images"], by=self._account())
        except GalleryError as exc:
            raise _refuse(exc) from exc
        data = GalleryPictureSerializer(
            links, many=True, context=self._context_for(entry, links)
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(request=GalleryPictureUpdateSerializer, responses=GalleryPictureSerializer)
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change a picture's words, NSFW flag, mood or crop (``crop: null`` un-looks it)."""
        link = self.get_object()
        change = GalleryPictureUpdateSerializer(data=request.data)
        change.is_valid(raise_exception=True)
        data = change.validated_data
        # UNSET, not None: a null mood or crop is a real request (clear it).
        mood = data.get("mood", UNSET)
        crop = data.get("crop", UNSET)
        try:
            with transaction.atomic():
                update_picture(
                    link,
                    title=data.get("title"),
                    caption=data.get("caption"),
                    is_nsfw=data.get("is_nsfw"),
                    mood=mood,
                )
                if crop is None:
                    clear_look(link)
                elif not isinstance(crop, Unset):
                    set_look(
                        link,
                        x=crop["x"],
                        y=crop["y"],
                        width=crop["width"],
                        mood=link.look if isinstance(mood, Unset) else mood,
                    )
                    if data.get("wear"):
                        wear_look(entry_of(link), link)
        except GalleryError as exc:
            raise _refuse(exc) from exc
        return Response(self._one(link))

    @extend_schema(responses=GalleryDeleteResultSerializer)
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The one Delete: the file goes, unless another character's gallery holds it."""
        link = self.get_object()
        try:
            outcome = delete_picture(link, by=self._account())
        except GalleryError as exc:
            raise PermissionDenied(exc.user_message) from exc
        return Response(GalleryDeleteResultSerializer({"outcome": outcome.value}).data)

    @extend_schema(request=GalleryReorderSerializer, responses={204: None})
    @action(detail=False, methods=[HTTPMethod.POST])
    def reorder(self, request: Request) -> Response:
        """Put the whole Gallery in a new order."""
        change = GalleryReorderSerializer(data=request.data)
        change.is_valid(raise_exception=True)
        entry = change.validated_data["roster_entry"]
        self._require_manager(entry)
        try:
            reorder_pictures(entry, change.validated_data["ids"])
        except GalleryError as exc:
            raise _refuse(exc) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _hide_target(self) -> tuple[TenureMedia, Any]:
        link = self.get_object()
        entry = entry_of(link)
        current = entry.current_tenure
        # Hiding is the current player's choice for their own time on the character.
        if current is None or current.player_data.account_id != self.request.user.pk:
            msg = "Only the character's player can hide its art."
            raise PermissionDenied(msg)
        if not link.is_character_art:
            msg = "Only character art can be hidden; delete your own pictures instead."
            raise ValidationError({"detail": msg})
        return link, current

    @extend_schema(request=None, responses=GalleryPictureSerializer)
    @action(detail=True, methods=[HTTPMethod.POST])
    def hide(self, request: Request, pk: str | None = None) -> Response:
        """Stop showing a piece of character art, for this player's time on the character."""
        link, tenure = self._hide_target()
        hide_character_art(link, tenure)
        return Response(self._one(link))

    @extend_schema(request=None, responses=GalleryPictureSerializer)
    @action(detail=True, methods=[HTTPMethod.POST])
    def show(self, request: Request, pk: str | None = None) -> Response:
        """Show hidden character art again."""
        link, tenure = self._hide_target()
        show_character_art(link, tenure)
        return Response(self._one(link))

    @extend_schema(responses=MediaUsageSerializer)
    @action(detail=False, methods=[HTTPMethod.GET], filter_backends=[], pagination_class=None)
    def usage(self, request: Request) -> Response:
        """The requester's storage: what their own files take, and their quota."""
        return Response(MediaUsageSerializer(media_usage(request.user.player_data)).data)
