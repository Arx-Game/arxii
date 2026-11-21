"""Gallery and media services for the roster system.
Handles Cloudinary integration for tenure media storage."""

from __future__ import annotations

import logging
from typing import cast
import uuid

import cloudinary
import cloudinary.api
import cloudinary.exceptions
import cloudinary.uploader
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Sum
import urllib3.exceptions

from evennia_extensions.models import Artist, Media, PlayerData
from world.roster.models import RosterTenure, TenureMedia
from world.roster.services.media_scan import MediaScanService

logger = logging.getLogger(__name__)

# The one opaque Cloudinary folder a face portrait lives in (#4889). No player or character
# number appears in the path, so a mask's picture URL cannot be matched to the real face's.
FACE_PORTRAIT_FOLDER = "faces"

# What a Cloudinary call raises: its own API error, or the transport's failure to reach it.
_CLOUDINARY_FAILURES = (cloudinary.exceptions.Error, urllib3.exceptions.HTTPError, OSError)

_ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
_CLOUDINARY_EAGER = [
    {"width": 300, "height": 300, "crop": "fill"},
    {"width": 150, "height": 150, "crop": "fill"},
]


def media_bytes_used(player_data: PlayerData) -> int:
    """Bytes the player's own files take.

    The quota counts the files the player uploaded (``Media.player_data``), wherever
    they are used: character art a staff member uploaded costs whoever plays the
    character nothing (#4151). The upload check and the Gallery's storage line both
    read this, so the two cannot disagree.
    """
    total = Media.objects.filter(player_data=player_data).aggregate(
        total=Sum("file_size_bytes"),
    )["total"]
    return total or 0


def enforce_player_media_limits(player_data: PlayerData, *, incoming_bytes: int) -> None:
    """Refuse a file that passes the per-file limit or would pass the player's quota (#3164).

    The one check every stored file goes through: a new upload and a copy of an existing
    picture (#4889). Staff accounts are exempt from both limits. The quota is the sum of the
    player's own ``Media`` rows, so a caller that must hold the quota under simultaneous
    requests calls this inside ``lock_player_media`` (see ``upload_image``).

    Raises:
        ValidationError: With the fixed per-file or quota message the Gallery shows.
    """
    if player_data.account.is_staff:
        return
    if incoming_bytes > settings.MAX_PLAYER_MEDIA_FILE_BYTES:
        msg = "This file is larger than the per-file limit."
        raise ValidationError(msg)
    if media_bytes_used(player_data) + incoming_bytes > player_data.media_quota_bytes:
        msg = "This upload would exceed your media quota."
        raise ValidationError(msg)


def lock_player_media(player_data: PlayerData) -> None:
    """Hold the player's row until the surrounding transaction ends (#4889).

    Uploads by one player then run one after another, so the second sees the first's
    bytes and two simultaneous uploads cannot both pass the quota. The lock is a filtered
    query rather than ``get(pk=...)``: the identity map answers a pk ``get`` from memory
    and would never reach the database. Must be called inside ``transaction.atomic()``.
    """
    list(PlayerData.objects.select_for_update().filter(pk=player_data.pk).values_list("pk"))


def _require_cloudinary() -> None:
    if not hasattr(settings, "CLOUDINARY_CLOUD_NAME") or not settings.CLOUDINARY_CLOUD_NAME:
        msg = "Cloudinary is not configured"
        raise ValidationError(msg)


class CloudinaryGalleryService:
    """Service for managing Cloudinary uploads and tenure media."""

    @staticmethod
    def generate_tenure_folder(tenure: RosterTenure) -> str:
        """Generate a unique folder name for a tenure's media."""
        if tenure.photo_folder:
            return str(tenure.photo_folder)

        # Create folder name: character_pk/tenure_number_uuid for uniqueness
        folder_name = (
            f"char_{tenure.roster_entry.character_sheet_id}"
            f"/{tenure.player_number}_{uuid.uuid4().hex[:8]}"
        )
        tenure.photo_folder = folder_name
        tenure.save()
        return folder_name

    @classmethod
    def upload_image(  # noqa: PLR0913 - Upload API mirrors Cloudinary needs
        cls,
        player_data: PlayerData,
        image_file: UploadedFile,
        media_type: str = "photo",
        title: str = "",
        description: str = "",
        tenure: RosterTenure | None = None,
        created_by: Artist | None = None,
        folder: str | None = None,
    ) -> Media:
        """Upload an image to Cloudinary and create media records.

        Args:
            player_data: Owner of the uploaded media
            image_file: The uploaded image file
            media_type: Type of media (photo, portrait, gallery)
            title: Optional title for the media
            description: Optional description
            tenure: Optional tenure to associate with the media
            created_by: Optional artist who created the media
            folder: Optional Cloudinary folder. When given, the public id is
                ``<folder>/<uuid>`` and no player or tenure number appears in it (#4889).

        Returns:
            Media: The created media record

        Raises:
            ValidationError: If upload fails or file is invalid
        """
        _require_cloudinary()

        if hasattr(image_file, "content_type") and image_file.content_type not in (
            _ALLOWED_IMAGE_TYPES
        ):
            logger.warning("Unsupported file type: %s", image_file.content_type)
            msg = "Unsupported file type."
            raise ValidationError(msg)

        # UploadedFile.size is typed as int | None upstream (a File wrapping a
        # sizeless stream); an actual upload always reports a size, so treat a
        # missing one as empty rather than widening every arithmetic use below.
        incoming = image_file.size or 0
        MediaScanService.scan_image(image_file)

        # The check, the upload and the row run under the player's row lock, so two
        # simultaneous uploads cannot both pass the quota (#4889).
        with transaction.atomic():
            lock_player_media(player_data)
            enforce_player_media_limits(player_data, incoming_bytes=incoming)

            if folder is None:
                folder = (
                    cls.generate_tenure_folder(tenure)
                    if tenure
                    else f"player_{player_data.account.pk}"
                )
            public_id = f"{folder}/{uuid.uuid4().hex}"

            try:
                result = cloudinary.uploader.upload(
                    image_file,
                    public_id=public_id,
                    folder=folder,
                    resource_type="image",
                    quality="auto",
                    fetch_format="auto",
                    eager=_CLOUDINARY_EAGER,
                )

                media = Media.objects.create(
                    player_data=player_data,
                    cloudinary_public_id=result["public_id"],
                    cloudinary_url=result["secure_url"],
                    file_size_bytes=result.get("bytes"),
                    width=result.get("width"),
                    height=result.get("height"),
                    media_type=media_type,
                    title=title,
                    description=description,
                    created_by=created_by,
                )

                if tenure:
                    TenureMedia.objects.create(tenure=tenure, media=media)

                return cast(Media, media)

            except Exception as e:
                logger.exception("Failed to upload image to Cloudinary")
                msg = "Failed to upload image."
                raise ValidationError(msg) from e

    @classmethod
    def copy_image(
        cls,
        player_data: PlayerData,
        source: Media,
        *,
        folder: str,
        media_type: str = "portrait",
    ) -> Media:
        """Store a new copy of one of the player's pictures under an opaque folder (#4889).

        The copy has its own file, its own delivery URL and a blank title, description and
        artist, so it cannot be matched to ``source`` or to the player. It counts against
        the player's storage like any upload: the source's size is checked first, and the
        size Cloudinary reports is checked again (the asset is destroyed and the copy
        refused if that passes the quota).

        Raises:
            ValidationError: With the Gallery's per-file or quota message, or a fixed
                failure message.
        """
        _require_cloudinary()
        with transaction.atomic():
            lock_player_media(player_data)
            enforce_player_media_limits(player_data, incoming_bytes=source.file_size_bytes or 0)
            public_id = f"{folder}/{uuid.uuid4().hex}"
            try:
                result = cloudinary.uploader.upload(
                    source.cloudinary_url,
                    public_id=public_id,
                    folder=folder,
                    resource_type="image",
                    quality="auto",
                    fetch_format="auto",
                    eager=_CLOUDINARY_EAGER,
                )
            except _CLOUDINARY_FAILURES as e:
                logger.exception("Failed to copy image on Cloudinary")
                msg = "Failed to upload image."
                raise ValidationError(msg) from e
            try:
                enforce_player_media_limits(player_data, incoming_bytes=result.get("bytes") or 0)
            except ValidationError:
                cls._destroy_remote(result["public_id"])
                raise
            return cast(
                Media,
                Media.objects.create(
                    player_data=player_data,
                    cloudinary_public_id=result["public_id"],
                    cloudinary_url=result["secure_url"],
                    file_size_bytes=result.get("bytes"),
                    width=result.get("width"),
                    height=result.get("height"),
                    media_type=media_type,
                ),
            )

    @staticmethod
    def _destroy_remote(public_id: str) -> None:
        try:
            cloudinary.uploader.destroy(public_id)
        except _CLOUDINARY_FAILURES:
            logger.exception("Cloudinary destroy failed for %s; remote asset orphaned", public_id)

    @classmethod
    def delete_media(cls, media: Media) -> bool:
        """Delete media from Cloudinary and remove the database record.

        Args:
            media: The Media to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cloudinary.uploader.destroy(media.cloudinary_public_id)
            media.delete()
            return True
        except Exception:
            logger.exception(
                "Cloudinary destroy failed for %s; DB row removed, remote asset orphaned",
                media.cloudinary_public_id,
            )
            media.delete()
            return False

    @classmethod
    def update_media_order(cls, tenure: RosterTenure, media_ids: list[int]) -> bool:
        """
        Update the sort order of media items.

        Args:
            tenure: The tenure whose media to reorder
            media_ids: List of media IDs in the desired order

        Returns:
            bool: True if successful
        """
        try:
            for index, media_id in enumerate(media_ids):
                TenureMedia.objects.filter(id=media_id, tenure=tenure).update_with_reason(
                    reason="issue #3817: intentional atomic write",
                    sort_order=index,
                )
            return True
        except Exception:
            logger.exception("Media reorder failed for tenure %s", tenure.pk)
            return False

    @classmethod
    def get_cloudinary_url_with_transformation(
        cls,
        public_id: str,
        width: int | None = None,
        height: int | None = None,
        crop: str = "fill",
    ) -> str:
        """
        Generate a Cloudinary URL with transformations.

        Args:
            public_id: The Cloudinary public ID
            width: Desired width
            height: Desired height
            crop: Crop mode (fill, scale, fit, etc.)

        Returns:
            str: Transformed Cloudinary URL
        """
        transformation: dict[str, int | str] = {}
        if width:
            transformation["width"] = width
        if height:
            transformation["height"] = height
        if crop:
            transformation["crop"] = crop

        return str(cloudinary.CloudinaryImage(public_id).build_url(**transformation))
