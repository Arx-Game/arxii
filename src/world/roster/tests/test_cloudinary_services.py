"""
Tests for roster CloudinaryGalleryService.
"""

from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
import pytest

from evennia_extensions.models import MediaType, PlayerMedia
from world.roster.factories import (
    ArtistFactory,
    CharacterFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
    TenureGalleryFactory,
    TenureMediaFactory,
)
from world.roster.models import TenureMedia
from world.roster.services import CloudinaryGalleryService


class TestCloudinaryGalleryService(TestCase):
    """Tests for CloudinaryGalleryService."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.roster = RosterFactory(is_active=True)
        self.roster_entry = RosterEntryFactory(
            character=self.character,
            roster=self.roster,
        )
        self.tenure = RosterTenureFactory(
            roster_entry=self.roster_entry,
            player_number=1,
        )

    def test_generate_tenure_folder_existing_folder(self):
        """Test that existing folder is returned."""
        self.tenure.photo_folder = "existing/folder"
        self.tenure.save()

        folder = CloudinaryGalleryService.generate_tenure_folder(self.tenure)

        assert folder == "existing/folder"

    @patch("uuid.uuid4")
    def test_generate_tenure_folder_creates_new_folder(self, mock_uuid):
        """Test that new folder is created and saved."""
        mock_uuid.return_value.hex = "abcd1234abcd1234"  # Full hex string

        folder = CloudinaryGalleryService.generate_tenure_folder(self.tenure)

        expected = f"char_{self.character.pk}/{self.tenure.player_number}_abcd1234"
        assert folder == expected

        # Verify it was saved to the tenure
        self.tenure.refresh_from_db()
        assert self.tenure.photo_folder == expected

    @override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
    @patch("cloudinary.uploader.upload")
    def test_upload_image_success(self, mock_upload):
        """Test successful image upload."""
        # Mock successful Cloudinary response
        mock_upload.return_value = {
            "public_id": "test/image123",
            "secure_url": "https://res.cloudinary.com/test/image/upload/test/image123.jpg",
        }

        # Create test image file
        image_file = SimpleUploadedFile(
            "test.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        media = CloudinaryGalleryService.upload_image(
            player_data=self.tenure.player_data,
            image_file=image_file,
            media_type=MediaType.PHOTO,
            title="Test Image",
            description="Test description",
            tenure=self.tenure,
        )

        assert isinstance(media, PlayerMedia)
        assert media.player_data == self.tenure.player_data
        assert media.cloudinary_public_id == "test/image123"
        assert (
            media.cloudinary_url == "https://res.cloudinary.com/test/image/upload/test/image123.jpg"
        )
        assert media.media_type == MediaType.PHOTO
        assert media.title == "Test Image"
        assert media.description == "Test description"
        assert TenureMedia.objects.filter(tenure=self.tenure, media=media).exists()

        # Verify upload was called correctly
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        assert call_args[0][0] == image_file
        assert "public_id" in call_args[1]
        assert "folder" in call_args[1]
        assert call_args[1]["resource_type"] == "image"

    @override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
    @patch("cloudinary.uploader.upload")
    def test_upload_image_with_artist(self, mock_upload):
        """Test uploading image with artist attribution."""
        mock_upload.return_value = {
            "public_id": "test/image_artist",
            "secure_url": "https://res.cloudinary.com/test/image/upload/test/image_artist.jpg",
        }
        image_file = SimpleUploadedFile(
            "test.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )
        artist = ArtistFactory()
        media = CloudinaryGalleryService.upload_image(
            player_data=self.tenure.player_data,
            image_file=image_file,
            created_by=artist,
        )
        assert media.created_by == artist

    def test_upload_image_no_cloudinary_config(self):
        """Test upload fails when Cloudinary is not configured."""
        with override_settings(CLOUDINARY_CLOUD_NAME=""):
            image_file = SimpleUploadedFile(
                "test.jpg",
                b"fake content",
                content_type="image/jpeg",
            )

            with pytest.raises(ValidationError) as cm:
                CloudinaryGalleryService.upload_image(
                    player_data=self.tenure.player_data,
                    image_file=image_file,
                    tenure=self.tenure,
                )

            assert "Cloudinary is not configured" in str(cm.value)

    @override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
    def test_upload_image_invalid_file_type(self):
        """Test upload fails with invalid file type."""
        image_file = SimpleUploadedFile(
            "test.txt",
            b"not an image",
            content_type="text/plain",
        )

        with pytest.raises(ValidationError) as cm:
            CloudinaryGalleryService.upload_image(
                player_data=self.tenure.player_data,
                image_file=image_file,
                tenure=self.tenure,
            )

        assert "Unsupported file type: text/plain" in str(cm.value)

    @override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
    def test_upload_image_valid_file_types(self):
        """Test that valid file types are accepted."""
        valid_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]

        with patch("cloudinary.uploader.upload") as mock_upload:
            mock_upload.return_value = {
                "public_id": "test/image",
                "secure_url": "https://test.url",
            }

            for content_type in valid_types:
                image_file = SimpleUploadedFile(
                    "test.jpg",
                    b"fake content",
                    content_type=content_type,
                )

                # Should not raise ValidationError
                try:
                    CloudinaryGalleryService.upload_image(
                        player_data=self.tenure.player_data,
                        image_file=image_file,
                    )
                except ValidationError:
                    self.fail(f"Valid content type {content_type} was rejected")

    @override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
    @patch("cloudinary.uploader.upload")
    def test_upload_image_cloudinary_error(self, mock_upload):
        """Test upload handles Cloudinary errors."""
        mock_upload.side_effect = Exception("Cloudinary error")

        image_file = SimpleUploadedFile(
            "test.jpg",
            b"fake content",
            content_type="image/jpeg",
        )

        with pytest.raises(ValidationError) as cm:
            CloudinaryGalleryService.upload_image(
                player_data=self.tenure.player_data,
                image_file=image_file,
            )

        assert "Failed to upload image: Cloudinary error" in str(cm.value)

    @patch("cloudinary.uploader.destroy")
    def test_delete_media_success(self, mock_destroy):
        """Test successful media deletion."""
        tm = TenureMediaFactory(tenure=self.tenure)
        media = tm.media

        result = CloudinaryGalleryService.delete_media(media)

        assert result is True
        mock_destroy.assert_called_once_with(media.cloudinary_public_id)

        assert not PlayerMedia.objects.filter(id=media.id).exists()

    @patch("cloudinary.uploader.destroy")
    def test_delete_media_cloudinary_error(self, mock_destroy):
        """Test media deletion when Cloudinary fails."""
        mock_destroy.side_effect = Exception("Cloudinary error")
        tm = TenureMediaFactory(tenure=self.tenure)
        media = tm.media
        media_id = media.id

        result = CloudinaryGalleryService.delete_media(media)

        assert result is False
        assert not PlayerMedia.objects.filter(id=media_id).exists()

    def test_get_tenure_gallery(self):
        """Test getting tenure gallery media."""
        # Create galleries
        public_gallery = TenureGalleryFactory(tenure=self.tenure, is_public=True)
        private_gallery = TenureGalleryFactory(tenure=self.tenure, is_public=False)

        # Create media
        public_media1 = TenureMediaFactory(
            tenure=self.tenure,
            gallery=public_gallery,
            sort_order=2,
        )
        public_media2 = TenureMediaFactory(
            tenure=self.tenure,
            gallery=public_gallery,
            sort_order=1,
        )

        TenureMediaFactory(tenure=self.tenure, gallery=private_gallery)

        other_tenure = RosterTenureFactory(
            roster_entry=self.roster_entry,
            player_number=2,
        )
        other_gallery = TenureGalleryFactory(tenure=other_tenure, is_public=True)
        TenureMediaFactory(tenure=other_tenure, gallery=other_gallery)

        gallery = CloudinaryGalleryService.get_tenure_gallery(self.tenure)

        assert len(gallery) == 2
        assert gallery[0] == public_media2.media
        assert gallery[1] == public_media1.media

    def test_get_primary_image_with_profile_picture(self):
        """Test getting primary image when tenure has profile picture."""
        gallery = TenureGalleryFactory(tenure=self.tenure, is_public=True)
        media_link = TenureMediaFactory(tenure=self.tenure, gallery=gallery)
        self.roster_entry.profile_picture = media_link
        self.roster_entry.save()

        primary = CloudinaryGalleryService.get_primary_image(self.tenure)

        assert primary == media_link.media

    def test_get_primary_image_different_tenure(self):
        """
        Test primary image returns None if profile pic belongs to different tenure.
        """
        other_tenure = RosterTenureFactory(
            roster_entry=self.roster_entry,
            player_number=2,
        )
        gallery = TenureGalleryFactory(tenure=other_tenure, is_public=True)
        media_link = TenureMediaFactory(tenure=other_tenure, gallery=gallery)
        self.roster_entry.profile_picture = media_link
        self.roster_entry.save()

        primary = CloudinaryGalleryService.get_primary_image(self.tenure)

        assert primary is None

    def test_get_primary_image_private_media(self):
        """Test primary image returns None if profile pic is private."""
        gallery = TenureGalleryFactory(tenure=self.tenure, is_public=False)
        media_link = TenureMediaFactory(tenure=self.tenure, gallery=gallery)
        self.roster_entry.profile_picture = media_link
        self.roster_entry.save()

        primary = CloudinaryGalleryService.get_primary_image(self.tenure)

        assert primary is None

    def test_get_primary_image_no_profile_picture(self):
        """Test primary image returns None when no profile picture."""
        primary = CloudinaryGalleryService.get_primary_image(self.tenure)

        assert primary is None

    def test_update_media_order_success(self):
        """Test successful media reordering."""
        media1 = TenureMediaFactory(tenure=self.tenure, sort_order=0)
        media2 = TenureMediaFactory(tenure=self.tenure, sort_order=1)
        media3 = TenureMediaFactory(tenure=self.tenure, sort_order=2)

        # Reorder: media3, media1, media2
        result = CloudinaryGalleryService.update_media_order(
            self.tenure,
            [media3.id, media1.id, media2.id],
        )

        assert result is True

        # Verify new order
        media1.refresh_from_db()
        media2.refresh_from_db()
        media3.refresh_from_db()

        assert media3.sort_order == 0
        assert media1.sort_order == 1
        assert media2.sort_order == 2

    def test_update_media_order_filters_by_tenure(self):
        """Test that reordering only affects media for the specified tenure."""
        other_tenure = RosterTenureFactory(
            roster_entry=self.roster_entry,
            player_number=2,
        )

        media1 = TenureMediaFactory(tenure=self.tenure, sort_order=0)
        other_media = TenureMediaFactory(tenure=other_tenure, sort_order=0)

        # Try to reorder including media from different tenure
        result = CloudinaryGalleryService.update_media_order(
            self.tenure,
            [other_media.id, media1.id],
        )

        assert result is True

        # Other tenure's media should be unchanged
        other_media.refresh_from_db()
        assert other_media.sort_order == 0

        # Only our tenure's media should be reordered
        media1.refresh_from_db()
        assert media1.sort_order == 1  # Only media1 gets updated to position 1

    def test_update_media_order_exception(self):
        """Test media reordering handles exceptions."""
        with patch("world.roster.models.TenureMedia.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            result = CloudinaryGalleryService.update_media_order(self.tenure, [1, 2, 3])

            assert result is False

    @patch("cloudinary.CloudinaryImage")
    def test_get_cloudinary_url_with_transformation(self, mock_cloudinary_image):
        """Test generating Cloudinary URL with transformations."""
        mock_image = Mock()
        mock_image.build_url.return_value = "https://transformed.url"
        mock_cloudinary_image.return_value = mock_image

        url = CloudinaryGalleryService.get_cloudinary_url_with_transformation(
            "test/image",
            width=300,
            height=200,
            crop="fill",
        )

        assert url == "https://transformed.url"
        mock_cloudinary_image.assert_called_once_with("test/image")
        mock_image.build_url.assert_called_once_with(width=300, height=200, crop="fill")

    @patch("cloudinary.CloudinaryImage")
    def test_get_cloudinary_url_minimal_params(self, mock_cloudinary_image):
        """Test URL generation with minimal parameters."""
        mock_image = Mock()
        mock_image.build_url.return_value = "https://basic.url"
        mock_cloudinary_image.return_value = mock_image

        url = CloudinaryGalleryService.get_cloudinary_url_with_transformation(
            "test/image",
        )

        assert url == "https://basic.url"
        mock_image.build_url.assert_called_once_with(crop="fill")

    @patch("cloudinary.CloudinaryImage")
    def test_get_cloudinary_url_no_crop(self, mock_cloudinary_image):
        """Test URL generation without crop parameter."""
        mock_image = Mock()
        mock_image.build_url.return_value = "https://no-crop.url"
        mock_cloudinary_image.return_value = mock_image

        url = CloudinaryGalleryService.get_cloudinary_url_with_transformation(
            "test/image",
            width=100,
            crop=None,
        )

        assert url == "https://no-crop.url"
        mock_image.build_url.assert_called_once_with(width=100)
