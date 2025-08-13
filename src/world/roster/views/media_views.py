"""
PlayerMedia and gallery views.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from evennia_extensions.models import Artist, MediaType, PlayerMedia
from world.roster.models import RosterTenure, TenureMedia
from world.roster.permissions import IsOwnerOrStaff, ReadOnlyOrOwner
from world.roster.serializers import PlayerMediaSerializer
from world.roster.services import CloudinaryGalleryService


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
