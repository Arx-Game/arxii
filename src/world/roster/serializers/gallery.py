"""Gallery serializers (#4151): a character's pictures, and the changes a player makes.

The read shape carries everything a viewer's Gallery needs and nothing it must not see:
``is_hidden`` and ``also_on`` are only ever filled for the character's own player (and
staff), and the NSFW veil is the client's to draw from ``is_nsfw`` plus the sheet's
``viewer_is_friend``; any logged-in account may see any picture (#3904), so the URL is
not withheld.
"""

from __future__ import annotations

from typing import ClassVar

from django.core.validators import FileExtensionValidator
from rest_framework import serializers

from world.character_sheets.models import MoodOption
from world.roster.models import RosterEntry, TenureMedia
from world.roster.serializers.media import ACCEPTED_IMAGE_EXTENSIONS
from world.roster.services.gallery import look_url, may_delete_picture


class CropSerializer(serializers.Serializer):
    """A look's 4:5 frame in the file's own pixels; height is width x 5/4."""

    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1)


class GalleryPictureSerializer(serializers.ModelSerializer):
    """One picture as a viewer's Gallery shows it.

    Context: ``account`` (the requester), ``hidden_ids`` and ``also_on`` (filled only
    for the character's own player or staff), ``worn_id``.
    """

    url = serializers.CharField(source="media.cloudinary_url", read_only=True)
    look_url = serializers.SerializerMethodField()
    title = serializers.CharField(source="media.title", read_only=True)
    caption = serializers.CharField(source="media.description", read_only=True)
    is_nsfw = serializers.BooleanField(source="media.is_nsfw", read_only=True)
    width = serializers.IntegerField(source="media.width", read_only=True, allow_null=True)
    height = serializers.IntegerField(source="media.height", read_only=True, allow_null=True)
    file_size_bytes = serializers.IntegerField(
        source="media.file_size_bytes", read_only=True, allow_null=True
    )
    mood = serializers.SerializerMethodField()
    crop = serializers.SerializerMethodField()
    is_look = serializers.BooleanField(read_only=True)
    is_character_art = serializers.BooleanField(read_only=True)
    is_worn = serializers.SerializerMethodField()
    is_hidden = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    also_on = serializers.SerializerMethodField()

    class Meta:
        model = TenureMedia
        fields: ClassVar[tuple[str, ...]] = (
            "id",
            "url",
            "look_url",
            "title",
            "caption",
            "is_nsfw",
            "width",
            "height",
            "file_size_bytes",
            "mood",
            "crop",
            "sort_order",
            "is_look",
            "is_character_art",
            "is_worn",
            "is_hidden",
            "can_delete",
            "also_on",
        )
        read_only_fields = fields

    def get_look_url(self, obj: TenureMedia) -> str | None:
        return look_url(obj)

    def get_mood(self, obj: TenureMedia) -> str:
        return obj.look.name if obj.look is not None else ""

    def get_crop(self, obj: TenureMedia) -> dict[str, int] | None:
        if not obj.is_look:
            return None
        return {"x": obj.crop_x, "y": obj.crop_y, "width": obj.crop_width}

    def get_is_worn(self, obj: TenureMedia) -> bool:
        return obj.pk == self.context.get("worn_id")

    def get_is_hidden(self, obj: TenureMedia) -> bool:
        return obj.pk in self.context.get("hidden_ids", set())

    def get_can_delete(self, obj: TenureMedia) -> bool:
        account = self.context.get("account")
        return account is not None and account.is_authenticated and may_delete_picture(obj, account)

    def get_also_on(self, obj: TenureMedia) -> list[str]:
        return self.context.get("also_on", {}).get(obj.media_id, [])


class GalleryUploadSerializer(serializers.Serializer):
    """Files dropped onto a character's Gallery."""

    roster_entry = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())
    images = serializers.ListField(
        child=serializers.FileField(
            validators=[FileExtensionValidator(allowed_extensions=ACCEPTED_IMAGE_EXTENSIONS)],
        ),
        allow_empty=False,
        max_length=50,
    )


class GalleryPictureUpdateSerializer(serializers.Serializer):
    """What the owner changes on one picture. Every field is optional.

    ``crop`` set makes (or re-frames) a look; ``crop`` null makes it a plain picture.
    ``mood`` is a ``MoodOption`` id, or null for none.
    """

    title = serializers.CharField(max_length=200, allow_blank=True, required=False)
    caption = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    is_nsfw = serializers.BooleanField(required=False)
    mood = serializers.PrimaryKeyRelatedField(
        queryset=MoodOption.objects.filter(is_active=True), allow_null=True, required=False
    )
    crop = CropSerializer(allow_null=True, required=False)
    wear = serializers.BooleanField(
        required=False,
        help_text="With a crop: also make this the worn look.",
    )


class GalleryReorderSerializer(serializers.Serializer):
    """The gallery's pictures, in their new order."""

    roster_entry = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class GalleryDeleteResultSerializer(serializers.Serializer):
    """What a Delete did: ``deleted`` (file gone) or ``unlinked`` (only off this one)."""

    outcome = serializers.CharField()


class MediaUsageSerializer(serializers.Serializer):
    """The requester's storage: bytes their own files take, and their quota."""

    used_bytes = serializers.IntegerField()
    quota_bytes = serializers.IntegerField()
