# Components - Reusable UI Components

Reusable React components and application shell components using TypeScript and Radix UI.

## Key Directories

### `ui/`

Radix-based UI components with Tailwind styling:

- **`button.tsx`**, **`card.tsx`**, **`input.tsx`**: Basic form components
- **`table.tsx`**, **`tabs.tsx`**, **`sheet.tsx`**: Layout components
- **`dropdown-menu.tsx`**, **`navigation-menu.tsx`**: Navigation components
- **`avatar.tsx`**, **`badge.tsx`**, **`skeleton.tsx`**: Display components
- **`accordion.tsx`**, **`separator.tsx`**: Structural components

### `character/`

Character-specific UI components:

- **`CharacterLink.tsx`**, **`CharacterAvatarLink.tsx`**: Character navigation
- **`CharacterPortrait.tsx`**: Character image display
- **`BackgroundSection.tsx`**, **`StatsSection.tsx`**: Character sheet sections
- **`RelationshipsSection.tsx`**, **`GalleriesSection.tsx`**: Character data sections
- **`CharacterApplicationForm.tsx`**: Character application interface

## Key Files

### Application Shell

- **`Layout.tsx`**: Main application layout wrapper
- **`Header.tsx`**: Application header with navigation
- **`Footer.tsx`**: Application footer
- **`AuthProvider.tsx`**: Authentication context provider

### Specialized Components

- **`SceneListCard.tsx`**: Scene display component
- **`ScenesSpotlight.tsx`**: Featured scenes display
- **`QuickActions.tsx`**: Quick action menu
- **`SearchSelect.tsx`**: Searchable select component
- **`TenureSearch.tsx`**, **`TenureMultiSearch.tsx`**: Character search components

### Utility Components

- **`ModeToggle.tsx`**: Dark/light mode toggle
- **`ErrorBoundary.tsx`**: Error handling wrapper
- **`ProfileDropdown.tsx`**: User profile menu
- **`SubmitButton.tsx`**: Form submission button

## Component Patterns

- **Functional components only** with TypeScript interfaces
- **Radix UI primitives** with custom Tailwind styling
- **Error boundaries** for graceful error handling
- **Context providers** for global state management
