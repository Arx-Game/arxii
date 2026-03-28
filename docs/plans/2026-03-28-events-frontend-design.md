# Events Frontend Design

## Problem

Players need to browse, create, and manage scheduled events from both the main site
and the in-game interface. The backend API exists (`/api/events/`) but there is no
frontend to interact with it.

## Two Contexts

Events are browsable content that works in two contexts:

1. **Site browsing** (not logged into a character) — full standalone pages at `/events`,
   `/events/:id`, `/events/new`. Standard site layout with header/footer.
2. **In-game** (logged into a character) — compact view in the right sidebar tab panel.
   The right sidebar is a multi-view context panel (Room / Events / Codex) where Room
   is the default. Events tab shows a scrollable list; clicking an event opens its
   detail page in a new tab.

Components are designed to work in both contexts via a `compact` prop that adapts
layout and interaction patterns.

## Routing

New routes in `App.tsx`:
- `/events` → `EventsListPage`
- `/events/new` → `ProtectedRoute` → `EventCreatePage`
- `/events/:id` → `EventDetailPage`

Header navigation: add `{ to: '/events', label: 'Events' }` to the links array.

URL helpers in `utils/urls.ts`:
```
EVENTS: '/events'
urls.event(id) → '/events/{id}'
urls.eventCreate() → '/events/new'
urls.eventsList() → '/events'
```

## Components

### Shared Components

#### EventCard

Single event summary. Used in both list page and sidebar.

**Props:** `event: EventListItem`, `compact?: boolean`

**Displays:**
- Event name (linked — same-tab in full mode, new-tab in compact/sidebar mode)
- Primary host persona name
- Scheduled real time (formatted date/time), IC time as tooltip
- Time phase icon (Lucide icons: `Sunrise` for DAWN, `Sun` for DAY, `Sunset` for DUSK,
  `Moon` for NIGHT)
- Location name
- `EventStatusBadge` — colored by status
- Public/Private badge (lock icon for private)

**Compact mode:** Tighter padding, single column, smaller text. Name links with
`target="_blank"`.

**Full mode:** More horizontal space, description excerpt shown, name links navigate
in same tab.

#### EventStatusBadge

Small colored badge component.

| Status | Color | Label |
|--------|-------|-------|
| draft | gray | Draft |
| scheduled | blue | Scheduled |
| active | green | Active |
| completed | muted | Completed |
| cancelled | red | Cancelled |

Uses the existing `Badge` UI component with variant styling.

#### TimePhaseBadge

Icon + label for time of day. Uses Lucide icons.

| Phase | Icon | Color |
|-------|------|-------|
| dawn | Sunrise | amber |
| day | Sun | yellow |
| dusk | Sunset | orange |
| night | Moon | indigo |

#### EventDetail

Full event information display. Used on the detail page and could be shown in
sidebar for quick preview.

**Props:** `event: EventDetailData`, `compact?: boolean`, `isHost?: boolean`,
`isStaff?: boolean`

**Sections:**

1. **Header** — name, status badge, public/private badge
2. **Info** — description, location name, scheduled time (real + IC), time phase,
   hosts list (primary marked)
3. **Invitations** (hosts/staff only) — list of invited personas, organizations,
   societies with counts
4. **Room modification** (if exists) — room description overlay text
5. **Host actions** (hosts/staff only, based on status):
   - Draft: "Schedule" button, "Edit" button
   - Scheduled: "Start Event", "Edit", "Cancel" buttons
   - Active: "Complete Event", "Cancel" buttons
   - Completed/Cancelled: no actions

Actions use `useMutation` calling the lifecycle endpoints. Confirmation dialog
before destructive actions (cancel, complete).

#### EventCreateForm

Form for creating a new event.

**Fields:**
- **Name** — text input, required
- **Description** — textarea, optional
- **Location** — `AreaDrilldownPicker` component OR "Use current room" button
  (when in-game, reads current room from game state)
- **Scheduled time** — date/time picker for real (OOC) time, must be in the future
- **IC time preview** — read-only field showing derived IC time, with option to
  adjust via separate date/time picker
- **Time phase** — select: Dawn / Day / Dusk / Night (default Day)
- **Public/Private** — toggle switch

**On submit:** POST to `/api/events/`, redirect to `/events/:id` on success where
the host can add invitations and schedule. Toast notification on success/error.

**Validation:** Name required, scheduled time must be future, location required.
Server-side validation handles location gap constraint (6-hour rule) — display
the error message from the API response.

#### AreaDrilldownPicker

Reusable cascading location selector. Browses the area hierarchy from top level
down to individual rooms.

**Props:** `value: number | null`, `onChange: (roomProfileId: number) => void`

**Behavior:**
1. On mount, fetches top-level areas: `GET /api/areas/` (no parent param)
2. Displays areas as a selectable list with level labels
3. Clicking an area fetches children: `GET /api/areas/?parent={id}`
4. Breadcrumb trail at top: "Arvum > Arx > The Docks" — click any level to
   navigate back
5. At leaf level (BUILDING or areas with no children), fetches rooms:
   `GET /api/areas/{id}/rooms/`
6. Selecting a room calls `onChange` with the RoomProfile ID
7. Selected room shown with full breadcrumb path

**Each level shows:** area name, level label (City, Ward, Neighborhood, etc.),
count of children or rooms.

**Loading states:** Skeleton loaders while fetching each level.

This component is reusable for any future room selection need.

### Standalone Pages

#### EventsListPage (`/events`)

Full-page event browser.

**Layout:**
- Page title "Events" with "Create Event" button (if authenticated)
- Search bar — text input with debounced search
- Status tabs — Upcoming / Active / Past (default: Upcoming)
- Event list — `EventCard` components in full mode
- Pagination — standard page-based

**Data fetching:**
```typescript
useQuery({
  queryKey: ['events', { status, search, page }],
  queryFn: () => fetchEvents({ status, search, page }),
})
```

**Empty states:** "No upcoming events" / "No active events" / "No past events found"
with appropriate messaging.

#### EventDetailPage (`/events/:id`)

Full-page event detail.

**Layout:**
- Back link to `/events`
- `EventDetail` component in full mode
- Host/staff see action buttons and invitation management
- If event is in DRAFT or SCHEDULED status and user is host, show "Edit" which
  toggles inline editing of name/description/time/phase/public

**Data fetching:**
```typescript
useQuery({
  queryKey: ['event', id],
  queryFn: () => fetchEvent(id),
})
```

**404 handling:** If the event is not found (private event user can't see, or
doesn't exist), show "Event not found" page.

#### EventCreatePage (`/events/new`)

Protected route — requires authentication.

**Layout:**
- Page title "Create Event"
- `EventCreateForm` component
- Cancel button returns to `/events`

### Game Sidebar Integration

#### Right Sidebar Tab Bar

The existing `RoomPanel` in the game view becomes one tab in a multi-tab sidebar.

**Tab bar:** sits at the top of the right sidebar column.

| Tab | Icon | Label |
|-----|------|-------|
| Room | `MapPin` | Room |
| Events | `Calendar` | Events |
| Codex | `BookOpen` | Codex |

Room is the default active tab. Tab state is local to the game session (not
persisted).

**Implementation:** New `SidebarTabPanel` wrapper component that renders the tab
bar and conditionally shows `RoomPanel`, `EventsSidebarPanel`, or a Codex panel
(placeholder for now).

#### EventsSidebarPanel

Compact event browser for the right sidebar.

**Layout:**
- Status filter tabs (small): Upcoming / Active / Past
- No search bar (search is for full page only)
- Scrollable list of `EventCard` in compact mode
- Each event name links to `/events/:id` with `target="_blank"` (new tab)
- "View All Events" link at bottom opens `/events` in new tab

**Data fetching:** Same `fetchEvents` query function as the list page, just
filtered to compact display.

## API Layer

### New file: `frontend/src/events/queries.ts`

```typescript
// List events with filters
fetchEvents({ status?, search?, page? }) → GET /api/events/

// Single event detail
fetchEvent(id) → GET /api/events/{id}/

// Create event
createEvent(data) → POST /api/events/

// Update event
updateEvent(id, data) → PATCH /api/events/{id}/

// Lifecycle actions
scheduleEvent(id) → POST /api/events/{id}/schedule/
startEvent(id) → POST /api/events/{id}/start/
completeEvent(id) → POST /api/events/{id}/complete/
cancelEvent(id) → POST /api/events/{id}/cancel/
```

### New file: `frontend/src/events/types.ts`

TypeScript interfaces matching the API serializers:

```typescript
interface EventListItem {
  id: number
  name: string
  description: string
  location: number
  location_name: string
  status: EventStatus
  is_public: boolean
  scheduled_real_time: string
  scheduled_ic_time: string
  time_phase: TimePhase
  primary_host_name: string | null
}

interface EventDetailData extends EventListItem {
  started_at: string | null
  ended_at: string | null
  created_at: string
  updated_at: string
  hosts: EventHost[]
  invitations: EventInvitation[]
  modification: EventModification | null
}

// ... plus EventHost, EventInvitation, EventModification, enums
```

### Backend addition: Area browsing endpoints

New endpoints needed in `world/areas` (no ViewSet exists yet):

```
GET /api/areas/                → top-level areas (parent=null)
GET /api/areas/?parent={id}    → child areas of a parent
GET /api/areas/{id}/rooms/     → public rooms in an area
```

Serializer returns: `id`, `name`, `level` (display), `children_count`,
`rooms_count` (at leaf level).

Rooms endpoint returns: `id` (RoomProfile PK), `name` (room db_key),
`area_breadcrumb` (string like "The Docks, Arx").

## Backend Changes Required

1. **Area ViewSet** — new read-only ViewSet in `world/areas/` with list and
   rooms action. Filter by parent. Include children/room counts.
2. **RoomProfile.is_public** — new boolean field on RoomProfile (default True).
   The design doc mentions this but it hasn't been added yet. Needed for
   filtering the room list in the area drill-down.

## File Structure

```
frontend/src/events/
  pages/
    EventsListPage.tsx
    EventDetailPage.tsx
    EventCreatePage.tsx
  components/
    EventCard.tsx
    EventDetail.tsx
    EventCreateForm.tsx
    EventStatusBadge.tsx
    TimePhaseBadge.tsx
    AreaDrilldownPicker.tsx
    EventsSidebarPanel.tsx
  queries.ts
  types.ts

frontend/src/game/components/
  SidebarTabPanel.tsx       (new — wraps tab bar + panel content)
  RoomPanel.tsx             (existing — becomes a tab)
  EventsSidebarPanel.tsx    (or import from events/)
```

## Design Decisions

### No search in sidebar
Search is for deliberate browsing on the full page. The sidebar is for quick
glancing at upcoming/active events while RPing.

### New tab for sidebar event clicks
Players in the middle of RP shouldn't lose their game context. Opening event
details in a new tab keeps the game view intact.

### Compact prop pattern
Same components render in both page and sidebar contexts. The `compact` prop
controls padding, text size, link behavior (same-tab vs new-tab), and layout
density. No separate component trees.

### Status tabs not full calendar
A calendar grid (monthly view) is visually appealing but complex to build and
most useful when there are many events. Status tabs (Upcoming/Active/Past) are
simpler, work well for any event count, and match the existing scenes list pattern.
A calendar view can be added later as an alternative visualization.

### Area drill-down over flat room search
Prevents exposing the full room list (spoiler concern), gives players natural
spatial browsing, and the backend infrastructure (Area model, AreaClosure) already
supports it.

## Future Work

- Calendar grid view as alternative to list
- "My events" filter (events I hosted or attended)
- Participant search on past events (via Scene participation data)
- Invitation management UI (add/remove invitations from detail page)
- Event editing form (inline on detail page for hosts)
- Codex sidebar panel content
- Room drill-down in sidebar context (for the Room tab)
