"""
PlayerMedia and gallery views.
"""

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from evennia_extensions.models import Artist, MediaType, PlayerMedia
from world.roster.models import RosterTenure, TenureGallery, TenureMedia
from world.roster.permissions import IsOwnerOrStaff, ReadOnlyOrOwner
from world.roster.serializers import PlayerMediaSerializer, TenureGallerySerializer
from world.roster.services import CloudinaryGalleryService


class PlayerMediaViewSet(viewsets.ModelViewSet):
    """API viewset for managing player media."""

    serializer_class = PlayerMediaSerializer
    permission_classes = [ReadOnlyOrOwner]

    def get_queryset(self) -> QuerySet[PlayerMedia]:
        # For listing, show user's own media unless staff
        # For detail views, show all media (permissions will restrict modifications)
        if self.action == "list":
            if self.request.user.is_staff:
                return PlayerMedia.objects.all()
            try:
                return PlayerMedia.objects.filter(
                    player_data=self.request.user.player_data,
                )
            except AttributeError:
                # User has no player_data, return empty queryset
                return PlayerMedia.objects.none()
        else:
            # For detail views (retrieve, update, etc), show all media
            return PlayerMedia.objects.all()

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

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        image_file = request.FILES.get("image_file")
        media_type = request.data.get("media_type", MediaType.PHOTO)
        title = request.data.get("title", "")
        description = request.data.get("description", "")
        artist_id = request.data.get("created_by")
        artist = None
        if artist_id:
            artist = Artist.objects.get(pk=artist_id)
        media = CloudinaryGalleryService.upload_image(
            player_data=request.user.player_data,
            image_file=image_file,
            media_type=media_type,
            title=title,
            description=description,
            created_by=artist,
        )
        serializer = self.get_serializer(media)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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

    serializer_class = TenureGallerySerializer
    permission_classes = [ReadOnlyOrOwner]

    def get_queryset(self) -> QuerySet[TenureGallery]:
        if self.request.user.is_staff:
            queryset = TenureGallery.objects.all()
        else:
            queryset = TenureGallery.objects.filter(
                tenure__player_data=self.request.user.player_data,
            )
        tenure_id = self.request.query_params.get("tenure")
        if tenure_id:
            queryset = queryset.filter(tenure_id=tenure_id)
        return queryset

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
