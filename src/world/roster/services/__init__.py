"""
Roster system services.

This module is organized into logical groups:
- gallery_services: Cloudinary and media management services
"""

# Import all services for backward compatibility
from world.roster.services.gallery_services import CloudinaryGalleryService

__all__ = [
    "CloudinaryGalleryService",
]
