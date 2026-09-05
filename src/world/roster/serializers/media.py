"""
Media and gallery serializers for the roster system.
"""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import FileExtensionValidator
from rest_framework import serializers

from evennia_extensions.models import Artist, Media, MediaType
from world.roster.models import TenureGallery, TenureMedia
from world.roster.services import CloudinaryGalleryService

# Extensions matching the content types CloudinaryGalleryService.upload_image accepts
# (image/jpeg, image/png, image/gif, image/webp). Kept next to the serializer that
# enforces them at the cheap layer, ahead of the service's content-type check (#3164).
ACCEPTED_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")


class ArtistSerializer(serializers.ModelSerializer):
    """Serialize artist information."""

    class Meta:
        model = Artist
        fields = (
            "id",
            "name",
            "description",
            "commission_notes",
            "accepting_commissions",
        )
        read_only_fields = fields


class MediaSerializer(serializers.ModelSerializer):
    """Serialize media uploaded by a player."""

    created_by = serializers.SerializerMethodField()

    def get_created_by(self, obj: Media):
        """Return serialized artist information if present."""
        artist = obj.created_by
        if not artist:
            return None
        return ArtistSerializer(artist).data

    class Meta:
        model = Media
        fields = (
            "id",
            "cloudinary_public_id",
            "cloudinary_url",
            "media_type",
            "title",
            "description",
            "created_by",
            "uploaded_date",
            "updated_date",
        )
        read_only_fields = fields


class MediaUploadSerializer(serializers.Serializer):
    """Validate a player's media upload before it reaches CloudinaryGalleryService.

    The per-file size check here mirrors the service's own check (#3164) with the
    same fixed message, so an oversized upload is rejected before the network call
    instead of after; the quota check stays service-only since it needs a DB
    aggregate over the player's existing media. Staff bypass the per-file check
    here too, matching the service's staff bypass.
    """

    image_file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=ACCEPTED_IMAGE_EXTENSIONS)],
    )
    media_type = serializers.ChoiceField(
        choices=MediaType.choices,
        default=MediaType.PHOTO,
    )
    title = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    created_by = serializers.PrimaryKeyRelatedField(
        queryset=Artist.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    def validate_image_file(self, value: serializers.FileField) -> serializers.FileField:
        """Reject an oversized file for non-staff before it ever reaches the service."""
        request = self.context.get("request")
        is_staff = bool(request and request.user.is_staff)
        if not is_staff:
            size = value.size or 0
            if size > settings.MAX_PLAYER_MEDIA_FILE_BYTES:
                msg = "This file is larger than the per-file limit."
                raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data: dict) -> Media:
        """Upload through the service, translating its ValidationError to a 4xx."""
        request = self.context["request"]
        try:
            return CloudinaryGalleryService.upload_image(
                player_data=request.user.player_data,
                image_file=validated_data["image_file"],
                media_type=validated_data["media_type"],
                title=validated_data["title"],
                description=validated_data["description"],
                created_by=validated_data["created_by"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def update(self, instance: Media, validated_data: dict) -> Media:
        """Not used: media uploads are create-only through this serializer."""
        raise NotImplementedError


class TenureMediaSerializer(serializers.ModelSerializer):
    """Serialize media associated with a roster tenure."""

    media = MediaSerializer(read_only=True)

    class Meta:
        model = TenureMedia
        fields = ("id", "media", "gallery", "sort_order")
        read_only_fields = ("id", "media", "gallery")


class TenureGallerySerializer(serializers.ModelSerializer):
    """Serialize tenure galleries."""

    class Meta:
        model = TenureGallery
        fields = ("id", "tenure", "name", "is_public", "allowed_viewers")
        read_only_fields = ("id", "tenure")
