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

- **`SearchSelect.tsx`**: Searchable select component
- **`TenureSearch.tsx`**, **`TenureMultiSearch.tsx`**: Character search components
- **`WelcomePanel.tsx`**: First-login home-page card for an authenticated account — "Enter the
  game" CTA, pending-application status, draft-in-progress link, or the roster/create-character
  choice for a zero-character account (#2162)

### Message Bodies

- **`FormattedContent.tsx`**: Parses a message body's inline markup (bold, italic,
  strikethrough, colour, links) into segments and renders them in one `<span>`. Every
  reader that shows a pose, say, emit or whisper (`PoseUnit`, `ExplorationReader`,
  `SceneMessages`) renders the body through it. **The feed's word-wrap rule lives here,
  once** (#3862): the wrapper carries `[overflow-wrap:anywhere]`, so an unbroken run (a
  URL, a keyboard mash, a long invented word) breaks at the column's edge in every reader
  instead of widening the feed sideways. `anywhere` rather than `break-word` because only
  `anywhere` lets the run shrink a flex child's min-content width, and the feed column is
  a flex child. A new reader that renders a body through this component inherits the rule;
  one that bypasses it must carry the same class itself (see `EvenniaMessage`).

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
