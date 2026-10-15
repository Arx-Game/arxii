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
- **`Header.tsx`**: Application header with navigation. Dropdown rows carry
  `requires: 'auth' | 'gm' | 'staff'` (#4188): `gm` is `account.is_gm`, which an
  assistant GM also has, so it is the whole GM gate. The **GMing** group (Dashboard,
  Story Builder, Tables, Lead GM Queue, plus a Staff section holding Story Workload)
  shows for `is_gm || is_staff`; its trigger carries one count, `total` from
  `useGMAttention` (`gm/queries.ts`, `GET /api/gm/attention/`), the same payload the
  Dashboard's "Waiting on you" strip reads, so badge and strip never disagree
  (ADR-4188). World is the lore shelf (Codex, Tidings, Journals, Realms); Crossover is
  reached from the Dashboard strip. The phone sheet mirrors the groups and shows the
  count in the group label.
- **`SelectedCharacterChip.tsx`**: The docked-portrait chip the header renders when the
  account has a selected character (#3412). Selection is not presence, and the chip
  shows both (#3859, #4321): presence comes from `roster/useCharacterPresence.ts`, which
  reads this tab's socket first (`sessions[name].isConnected`, the same fact
  `GatefoldPage`'s redirect and `GameTopBar`'s dot read) and the roster payload's
  `session_count`/`room_name` when the tab opened no socket, so a second tab or device
  tells the truth too (ADR-4321). In the world, the sub-line says "In the world" plus
  the room, the button is "Return to the world" (a second socket joins the same
  character), and "Disconnect Character" (`roster/useDisconnectCharacter.ts`) closes
  this tab's socket, or asks the disconnect endpoint to close every session when the
  tab has none, or offers "This connection" / "Every connection" when it has one and
  the character has another; not in the world, it offers "Enter the world" and says
  "Not in the world". Navigating away from `/game` keeps the socket open (ADR-0295),
  which is why the chip must never read the route. `Header` refetches the roster list
  every 30 s while a chip is up. Degraded lifecycle states show `dockedStateLabel`
  instead of a presence claim.
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
- **`ProfileDropdown.tsx`**: The account menu behind the header's far-right control, and
  `AccountMenuContent`, its items for any `DropdownMenu` trigger (#4321): the Who tab's
  Online list opens the same menu from the player's own name, so the game reaches the
  sheet, the Hall, the roster and settings in the same tab. Its last item is "Log Out
  Account" (ruled 2026-10-13: the account, never the character).
- **`SubmitButton.tsx`**: Form submission button

## Component Patterns

- **Functional components only** with TypeScript interfaces
- **Radix UI primitives** with custom Tailwind styling
- **Error boundaries** for graceful error handling
- **Context providers** for global state management
