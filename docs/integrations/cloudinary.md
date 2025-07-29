# Cloudinary Integration

Arx II uses [Cloudinary](https://cloudinary.com/) for image hosting and management, primarily for the roster system's character galleries.

## Overview

Cloudinary provides cloud-based image and video management services. We use it to:

- Store character gallery images tied to player tenures
- Automatically optimize images (quality, format conversion)
- Generate thumbnails and responsive images
- Organize media in tenure-specific folders for privacy

## Configuration

Required environment variables in `src/.env`:

```env
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

## Implementation Details

### Service Layer
- **Location**: `src/world/roster/services.py`
- **Class**: `CloudinaryGalleryService`
- **Key Methods**:
  - `upload_image()` - Upload with automatic transformations
  - `delete_media()` - Clean removal from cloud and database
  - `generate_tenure_folder()` - Unique folder structure per tenure

### Folder Structure
Images are organized by character and tenure:
```
char_{character_pk}/{tenure_number}_{uuid}/image_files
```

This ensures:
- Player anonymity (no usernames in paths)
- Tenure separation (images persist when characters change hands)
- Uniqueness (prevents collisions)

### Automatic Transformations
On upload, Cloudinary generates:
- Original image
- 300x300 thumbnail (crop: fill)
- 150x150 small thumbnail (crop: fill)
- Auto-optimized quality and format

### Database Integration
- **Model**: `TenureMedia` (`src/world/roster/models.py`)
- **Fields**: `cloudinary_public_id`, `cloudinary_url`, `media_type`
- **Relationships**: Tied to `RosterTenure`, not characters directly

## Security Considerations

- Images are public by default but organized in non-guessable folder structures
- Player identities are not exposed in URLs or folder names
- Image deletion removes both cloud storage and database records
- File type validation prevents non-image uploads

## Usage in Views

Character gallery views use the service layer:
- `gallery_view()` - Display tenure's gallery
- `upload_image()` - Handle new uploads with permission checks
- `delete_image()` - Remove images with ownership verification

## Future Enhancements

- Private/restricted image access controls
- Batch upload functionality
- Image moderation and approval workflows
- Integration with character approval process
