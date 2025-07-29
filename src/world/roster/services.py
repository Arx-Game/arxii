"""
Gallery and media services for the roster system.
Handles Cloudinary integration for tenure media storage.
"""

from typing import List, Optional
import uuid

import cloudinary
import cloudinary.api
import cloudinary.uploader
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from world.roster.models import MediaType, RosterTenure, TenureMedia


class CloudinaryGalleryService:
    """Service for managing Cloudinary uploads and tenure media."""

    @staticmethod
    def generate_tenure_folder(tenure: RosterTenure) -> str:
        """Generate a unique folder name for a tenure's media."""
        if tenure.photo_folder:
            return tenure.photo_folder

        # Create folder name: character_pk/tenure_number_uuid for uniqueness
        folder_name = (
            f"char_{tenure.character.pk}/{tenure.player_number}_{uuid.uuid4().hex[:8]}"
        )
        tenure.photo_folder = folder_name
        tenure.save()
        return folder_name

    @classmethod
    def upload_image(
        cls,
        tenure: RosterTenure,
        image_file: UploadedFile,
        media_type: str = MediaType.PHOTO,
        title: str = "",
        description: str = "",
        is_primary: bool = False,
    ) -> TenureMedia:
        """
        Upload an image to Cloudinary and create a TenureMedia record.

        Args:
            tenure: The RosterTenure this media belongs to
            image_file: The uploaded image file
            media_type: Type of media (photo, portrait, gallery)
            title: Optional title for the media
            description: Optional description
            is_primary: Whether this should be the primary photo

        Returns:
            TenureMedia: The created media record

        Raises:
            ValidationError: If upload fails or file is invalid
        """
        if (
            not hasattr(settings, "CLOUDINARY_CLOUD_NAME")
            or not settings.CLOUDINARY_CLOUD_NAME
        ):
            raise ValidationError("Cloudinary is not configured")

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if (
            hasattr(image_file, "content_type")
            and image_file.content_type not in allowed_types
        ):
            raise ValidationError(f"Unsupported file type: {image_file.content_type}")

        # Generate folder and public_id
        folder = cls.generate_tenure_folder(tenure)
        public_id = f"{folder}/{uuid.uuid4().hex}"

        try:
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                image_file,
                public_id=public_id,
                folder=folder,
                resource_type="image",
                quality="auto",
                fetch_format="auto",
                # Add transformation for thumbnails
                eager=[
                    {"width": 300, "height": 300, "crop": "fill"},
                    {"width": 150, "height": 150, "crop": "fill"},
                ],
            )

            # If this is marked as primary, clear other primary flags
            if is_primary:
                TenureMedia.objects.filter(tenure=tenure, is_primary=True).update(
                    is_primary=False
                )

            # Create TenureMedia record
            media = TenureMedia.objects.create(
                tenure=tenure,
                cloudinary_public_id=result["public_id"],
                cloudinary_url=result["secure_url"],
                media_type=media_type,
                title=title,
                description=description,
                is_primary=is_primary,
            )

            return media

        except Exception as e:
            raise ValidationError(f"Failed to upload image: {str(e)}")

    @classmethod
    def delete_media(cls, media: TenureMedia) -> bool:
        """
        Delete media from Cloudinary and remove the database record.

        Args:
            media: The TenureMedia to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Delete from Cloudinary
            cloudinary.uploader.destroy(media.cloudinary_public_id)

            # Delete database record
            media.delete()
            return True

        except Exception:
            # Log the error but still delete the database record
            media.delete()
            return False

    @classmethod
    def get_tenure_gallery(cls, tenure: RosterTenure) -> List[TenureMedia]:
        """Get all media for a tenure, ordered by sort_order and upload date."""
        return list(
            tenure.media.filter(is_public=True).order_by("sort_order", "-uploaded_date")
        )

    @classmethod
    def get_primary_image(cls, tenure: RosterTenure) -> Optional[TenureMedia]:
        """Get the primary image for a tenure."""
        return tenure.media.filter(is_primary=True, is_public=True).first()

    @classmethod
    def update_media_order(cls, tenure: RosterTenure, media_ids: List[int]) -> bool:
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
                    sort_order=index
                )
            return True
        except Exception:
            return False

    @classmethod
    def get_cloudinary_url_with_transformation(
        cls, public_id: str, width: int = None, height: int = None, crop: str = "fill"
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
        transformation = {}
        if width:
            transformation["width"] = width
        if height:
            transformation["height"] = height
        if crop:
            transformation["crop"] = crop

        return cloudinary.CloudinaryImage(public_id).build_url(**transformation)
