"""Media scanning service for uploaded images."""

from typing import List

from django.core.files.uploadedfile import UploadedFile


class MediaScanError(Exception):
    """Raised when media fails a content scan."""


class MediaScanService:
    """Placeholder service for scanning uploaded media.

    This service should integrate with third-party APIs to detect
    NSFW or illegal content such as CSAM. For now it returns an empty
    list of tags.
    """

    @staticmethod
    def scan_image(image_file: UploadedFile) -> List[str]:
        """Scan an uploaded image for inappropriate content.

        Args:
            image_file: The image file to scan.

        Returns:
            list[str]: Tags describing detected content.

        Raises:
            MediaScanError: If prohibited content is detected or the scan fails.
        """
        # TODO: Implement actual scanning via third-party service.
        return []
