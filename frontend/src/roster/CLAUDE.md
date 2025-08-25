# Roster - Character Management Interface

Character roster management system with character sheets, applications, and media galleries.

## Key Directories

### `components/`

- **`GalleryManagement.tsx`**: Image/file gallery management interface
- **`MediaUploadForm.tsx`**: File upload component with privacy controls

### `pages/`

- **`RosterListPage.tsx`**: Browsable character roster with filtering
- **`CharacterSheetPage.tsx`**: Detailed character information display
- **`PlayerMediaPage.tsx`**: Media gallery management for players

## Key Files

### API Integration

- **`api.ts`**: REST API functions for roster operations
- **`queries.ts`**: React Query hooks for roster data
- **`types.ts`**: TypeScript definitions for roster data structures

## Key Features

- **Character Applications**: Apply for available roster characters
- **Character Sheets**: Detailed character information and demographics
- **Media Galleries**: Upload and manage character images with privacy controls
- **Tenure System**: Character ownership history tracking
- **Search and Filtering**: Advanced roster browsing capabilities

## Data Flow

- **REST API**: Full CRUD operations via `/api/roster/` endpoints
- **Pagination**: Large roster sets with efficient pagination
- **File Upload**: Direct integration with Cloudinary for media storage
- **Privacy Controls**: Gallery visibility and access management

## Integration Points

- **Backend Models**: Direct integration with world.roster Django models
- **Authentication**: Tenure-based permissions for character access
- **Media Storage**: Cloudinary integration for file uploads
