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
- **`SelectedCharacterChip.tsx`**: The docked-portrait chip the header renders when the
  account has a selected character (#3412). Selection is not presence, and the chip
  shows both (#3859): it reads the character's live session from the store
  (`sessions[name].isConnected`, the same fact `GatefoldPage`'s redirect and
  `GameTopBar`'s dot read). With a live session the sub-line says "In the world" plus
  the room, the button is "Return to the world", and "Leave the world" calls
  `useGameSocket().disconnect(name)`, the world menu's own item, so the server unpuppets
  the character; without one it offers "Enter the world" and says "Not in the world".
  Navigating away from `/game` keeps the socket open (ADR-0295), which is why the chip
  must read the store and never the route. Degraded lifecycle states show
  `dockedStateLabel` instead of a presence claim.
- **`Footer.tsx`**: Application footer
- **`AuthProvider.tsx`**: Authentication context provider

### Specialized Components

- **`SearchSelect.tsx`**: Searchable select component
- **`TenureSearch.tsx`**, **`TenureMultiSearch.tsx`**: Character search components
- **`WelcomePanel.tsx`**: First-login home-page card for an authenticated account — "Enter the
  game" CTA, pending-application status, draft-in-progress link, or the roster/create-character
  choice for a zero-character account (#2162)

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
