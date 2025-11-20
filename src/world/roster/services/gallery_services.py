"""Gallery and media services for the roster system.
Handles Cloudinary integration for tenure media storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
import uuid

import cloudinary
import cloudinary.api
import cloudinary.uploader
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from evennia_extensions.models import Artist, PlayerData, PlayerMedia
from world.roster.models import RosterTenure, TenureMedia
from world.roster.services.media_scan import MediaScanService

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from world.roster.models import TenureGallery


class CloudinaryGalleryService:
    """Service for managing Cloudinary uploads and tenure media."""

    @staticmethod
    def generate_tenure_folder(tenure: RosterTenure) -> str:
        """Generate a unique folder name for a tenure's media."""
        if tenure.photo_folder:
            return str(tenure.photo_folder)

        # Create folder name: character_pk/tenure_number_uuid for uniqueness
        folder_name = (
            f"char_{tenure.roster_entry.character.pk}/"
            f"{tenure.player_number}_{uuid.uuid4().hex[:8]}"
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
        gallery: TenureGallery | None = None,
        created_by: Artist | None = None,
    ) -> PlayerMedia:
        """Upload an image to Cloudinary and create media records.

        Args:
            player_data: Owner of the uploaded media
            image_file: The uploaded image file
            media_type: Type of media (photo, portrait, gallery)
            title: Optional title for the media
            description: Optional description
            tenure: Optional tenure to associate with the media
            gallery: Optional gallery to associate with the tenure media
            created_by: Optional artist who created the media

        Returns:
            PlayerMedia: The created media record

        Raises:
            ValidationError: If upload fails or file is invalid
        """
        if (
            not hasattr(settings, "CLOUDINARY_CLOUD_NAME")
            or not settings.CLOUDINARY_CLOUD_NAME
        ):
            msg = "Cloudinary is not configured"
            raise ValidationError(msg)

        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if (
            hasattr(image_file, "content_type")
            and image_file.content_type not in allowed_types
        ):
            msg = f"Unsupported file type: {image_file.content_type}"
            raise ValidationError(msg)

        MediaScanService.scan_image(image_file)

        if tenure:
            folder = cls.generate_tenure_folder(tenure)
        else:
            folder = f"player_{player_data.account.pk}"
        public_id = f"{folder}/{uuid.uuid4().hex}"

        try:
            result = cloudinary.uploader.upload(
                image_file,
                public_id=public_id,
                folder=folder,
                resource_type="image",
                quality="auto",
                fetch_format="auto",
                eager=[
                    {"width": 300, "height": 300, "crop": "fill"},
                    {"width": 150, "height": 150, "crop": "fill"},
                ],
            )

            media = PlayerMedia.objects.create(
                player_data=player_data,
                cloudinary_public_id=result["public_id"],
                cloudinary_url=result["secure_url"],
                media_type=media_type,
                title=title,
                description=description,
                created_by=created_by,
            )

            if tenure:
                TenureMedia.objects.create(tenure=tenure, media=media, gallery=gallery)

            return cast(PlayerMedia, media)

        except Exception as e:
            msg = f"Failed to upload image: {e!s}"
            raise ValidationError(msg) from e

    @classmethod
    def delete_media(cls, media: PlayerMedia) -> bool:
        """Delete media from Cloudinary and remove the database record.

        Args:
            media: The PlayerMedia to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cloudinary.uploader.destroy(media.cloudinary_public_id)
            media.delete()
            return True
        except Exception:  # noqa: BLE001
            media.delete()
            return False

    @classmethod
    def get_tenure_gallery(cls, tenure: RosterTenure) -> list[PlayerMedia]:
        """Get all media for a tenure, ordered by sort order and upload date."""
        return list(
            PlayerMedia.objects.filter(
                tenure_links__tenure=tenure,
                tenure_links__gallery__is_public=True,
            ).order_by("tenure_links__sort_order", "-uploaded_date"),
        )

    @classmethod
    def get_primary_image(cls, tenure: RosterTenure) -> PlayerMedia | None:
        """Get the primary image for a tenure from the character's roster entry."""
        if tenure.roster_entry.profile_picture:
            profile_pic = tenure.roster_entry.profile_picture
            if (
                profile_pic.tenure == tenure
                and profile_pic.gallery
                and profile_pic.gallery.is_public
            ):
                return cast(PlayerMedia, profile_pic.media)
        return None

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
                TenureMedia.objects.filter(id=media_id, tenure=tenure).update(
                    sort_order=index,
                )
            return True
        except Exception:  # noqa: BLE001
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
