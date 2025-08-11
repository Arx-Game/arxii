"""
API views for roster system.
"""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from evennia_extensions.models import Artist, MediaType, PlayerMedia
from world.roster.filters import RosterEntryFilterSet
from world.roster.models import Roster, RosterEntry, RosterTenure, TenureMedia
from world.roster.permissions import (
    IsOwnerOrStaff,
    IsPlayerOrStaff,
    ReadOnlyOrOwner,
    StaffOnlyWrite,
)
from world.roster.serializers import (
    MyRosterEntrySerializer,
    PlayerMediaSerializer,
    RosterApplicationSerializer,
    RosterEntrySerializer,
    RosterListSerializer,
)
from world.roster.services import CloudinaryGalleryService


class RosterEntryPagination(PageNumberPagination):
    """Default pagination for roster entries."""

    page_size = 20


class RosterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Expose roster entries and related actions."""

    serializer_class = RosterEntrySerializer
    permission_classes = [
        AllowAny
    ]  # Read-only viewset, so AllowAny is fine for listing/viewing
    filter_backends = [DjangoFilterBackend]
    filterset_class = RosterEntryFilterSet
    pagination_class = RosterEntryPagination

    def get_queryset(self):
        """Return a queryset of roster entries."""

        return (
            RosterEntry.objects.select_related("character")
            .prefetch_related(
                Prefetch(
                    "tenures",
                    queryset=RosterTenure.objects.all().prefetch_related(
                        Prefetch(
                            "media",
                            queryset=TenureMedia.objects.select_related("media"),
                            to_attr="cached_media",
                        )
                    ),
                )
            )
            .order_by("character__db_key")
        )

    def get_serializer_class(self):
        if self.action == "mine":
            return MyRosterEntrySerializer
        if self.action == "apply":
            return RosterApplicationSerializer
        return super().get_serializer_class()

    @action(
        detail=False,
        permission_classes=[IsAuthenticated],
        serializer_class=MyRosterEntrySerializer,
    )
    def mine(self, request):
        """Return roster entries for characters owned by the account."""

        # Get characters through PlayerData model
        try:
            player_data = request.user.player_data
            available_characters = player_data.get_available_characters()
        except AttributeError:
            available_characters = []

        entries = RosterEntry.objects.filter(character__in=available_characters)
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsPlayerOrStaff],
    )
    def set_profile_picture(self, request, pk=None):
        """Set the profile picture for this roster entry."""
        roster_entry = self.get_object()
        media_id = request.data.get("tenure_media_id")

        # Staff can access any tenure media, non-staff only their own
        if request.user.is_staff:
            media = TenureMedia.objects.get(
                pk=media_id,
                tenure__roster_entry=roster_entry,
            )
        else:
            media = TenureMedia.objects.get(
                pk=media_id,
                tenure__roster_entry=roster_entry,
                tenure__player_data=request.user.player_data,
            )

        roster_entry.profile_picture = media
        roster_entry.full_clean()
        roster_entry.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        serializer_class=RosterApplicationSerializer,
    )
    def apply(self, request, pk=None):
        """Accept a play application for a roster entry's character."""

        self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RosterViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for listing rosters."""

    queryset = Roster.objects.filter(is_active=True).order_by("sort_order", "name")
    serializer_class = RosterListSerializer
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            # Allow anyone to list/retrieve rosters
            permission_classes = [AllowAny]
        else:
            permission_classes = [StaffOnlyWrite]
        return [permission() for permission in permission_classes]


class PlayerMediaViewSet(viewsets.ModelViewSet):
    """API viewset for managing player media."""

    serializer_class = PlayerMediaSerializer
    permission_classes = [ReadOnlyOrOwner]

    def get_queryset(self):
        # For listing, show user's own media unless staff
        # For detail views, show all media (permissions will restrict modifications)
        if self.action == "list":
            if self.request.user.is_staff:
                return PlayerMedia.objects.all()
            try:
                return PlayerMedia.objects.filter(
                    player_data=self.request.user.player_data
                )
            except AttributeError:
                # User has no player_data, return empty queryset
                return PlayerMedia.objects.none()
        else:
            # For detail views (retrieve, update, etc), show all media
            return PlayerMedia.objects.all()

    def get_permissions(self):
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

    def create(self, request, *args, **kwargs):
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

    @action(detail=True, methods=["post"], permission_classes=[IsOwnerOrStaff])
    def associate_tenure(self, request, pk=None):
        tenure_id = request.data.get("tenure_id")

        # Staff can associate with any tenure, non-staff only their own
        if request.user.is_staff:
            tenure = RosterTenure.objects.get(pk=tenure_id)
        else:
            tenure = RosterTenure.objects.get(
                pk=tenure_id, player_data=request.user.player_data
            )

        media = self.get_object()
        TenureMedia.objects.create(tenure=tenure, media=media)
        return Response(status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[IsOwnerOrStaff])
    def set_profile_picture(self, request, pk=None):
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
