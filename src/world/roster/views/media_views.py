"""
Media and gallery views.
"""

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import Media
from world.roster.filters import TenureGalleryFilterSet
from world.roster.models import RosterTenure, TenureGallery, TenureMedia
from world.roster.permissions import IsOwnerOrStaff, ReadOnlyOrOwner
from world.roster.serializers import MediaSerializer, MediaUploadSerializer, TenureGallerySerializer


class MediaViewSet(viewsets.ModelViewSet):
    """API viewset for managing player media."""

    # Paginated via the project default (ADR-0138): a player's whole uploaded
    # image library grows over time. Media.Meta.ordering (-uploaded_date)
    # gives stable page boundaries; the frontend gallery loads every page via
    # fetchAllPages since the grid shows the full set.
    serializer_class = MediaSerializer
    permission_classes = [ReadOnlyOrOwner]
    # The project default is JSON-only (see REST_FRAMEWORK settings); create's
    # image_file goes over the wire as a real upload, so this viewset also
    # accepts multipart/form-data (#3164). Content-Type on the request picks
    # the parser, so this doesn't loosen the other JSON-only actions.
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self) -> QuerySet[Media]:
        # For listing, show user's own media unless staff
        # For detail views, show all media (permissions will restrict modifications)
        if self.action == "list":
            if self.request.user.is_staff:
                return Media.objects.all()
            try:
                return Media.objects.filter(
                    player_data=self.request.user.player_data,
                )
            except AttributeError:
                # User has no player_data, return empty queryset
                return Media.objects.none()
        else:
            # For detail views (retrieve, update, etc), show all media
            return Media.objects.all()

    def get_permissions(self) -> list[BasePermission]:
        """
        Instantiate and return the list of permissions required for this view.
        """
        if self.action in ["update", "partial_update", "destroy"]:
            # Only media owner or staff can modify/delete media
            permission_classes = [IsOwnerOrStaff]
        else:
            # Default permissions for list, retrieve, create
            permission_classes = self.permission_classes

        return [permission() for permission in permission_classes]

    @extend_schema(request=MediaUploadSerializer, responses={201: MediaSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        upload_serializer = MediaUploadSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        upload_serializer.is_valid(raise_exception=True)
        media = upload_serializer.save()
        response_serializer = self.get_serializer(media)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[IsOwnerOrStaff])
    def associate_tenure(self, request: Request, pk: int | None = None) -> Response:
        tenure_id = request.data.get("tenure_id")
        gallery_id = request.data.get("gallery_id")

        # Staff can associate with any tenure, non-staff only their own
        if request.user.is_staff:
            tenure = RosterTenure.objects.get(pk=tenure_id)
        else:
            tenure = RosterTenure.objects.get(
                pk=tenure_id,
                player_data=request.user.player_data,
            )

        gallery = None
        if gallery_id:
            gallery = TenureGallery.objects.get(pk=gallery_id, tenure=tenure)

        media = self.get_object()
        TenureMedia.objects.create(tenure=tenure, media=media, gallery=gallery)
        return Response(status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[IsOwnerOrStaff])
    def set_profile_picture(self, request: Request, pk: int | None = None) -> Response:
        media = self.get_object()

        # For staff, set profile picture for the media owner; for users, set their own
        if request.user.is_staff:
            # Staff can set profile picture for the media owner
            player_data = media.player_data
        else:
            # Regular user sets their own profile picture
            player_data = request.user.player_data

        player_data.profile_picture = media
        player_data.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenureGalleryViewSet(viewsets.ModelViewSet):
    """API viewset for managing tenure galleries."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = TenureGallerySerializer
    permission_classes = [ReadOnlyOrOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TenureGalleryFilterSet

    def get_queryset(self) -> QuerySet[TenureGallery]:
        if self.request.user.is_staff:
            return TenureGallery.objects.all()
        return TenureGallery.objects.filter(
            tenure__player_data=self.request.user.player_data,
        )

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [IsOwnerOrStaff]
        else:
            permission_classes = self.permission_classes
        return [permission() for permission in permission_classes]

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        tenure_id = request.data.get("tenure_id")
        if request.user.is_staff:
            tenure = RosterTenure.objects.get(pk=tenure_id)
        else:
            tenure = RosterTenure.objects.get(
                pk=tenure_id,
                player_data=request.user.player_data,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gallery = serializer.save(tenure=tenure)
        read_serializer = self.get_serializer(gallery)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)
