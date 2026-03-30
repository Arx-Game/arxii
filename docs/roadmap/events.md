# Events

**Status:** MVP complete
**Depends on:** Scenes, Areas, Game Clock, Societies (for organization/society invitations)

## Overview
Scheduled RP gatherings — balls, meetings, training sessions, rituals. Players create events
with a time, location, and guest list. Events appear on a shared calendar, modify room state
while active, and spawn Scenes for RP logging. Distinct from Scenes (which only record RP)
and from GM sessions (which are narrative-driven, handled by Stories/GM system).

## Key Design Points
- **Events are not Scenes** — Events handle scheduling, access control, and room state. Scenes
  handle RP logging. An Event spawns a Scene when RP begins (Scene has optional FK back to Event)
- **Progressive disclosure** — Simple creation by default (name, location, time, public/private).
  Extra options expand to room modifications, organization invites, prestige investment
- **Persona-based identity** — All player-facing references use Persona to preserve IC/OOC boundary.
  Hosts are personas, invitations target personas
- **No RSVPs** — Low-pressure design. You're invited, show up or don't. Scene tracks who came
- **Polymorphic invitations** — Invite individual personas, entire organizations, or societies
- **Room modifications** — Events can temporarily alter room descriptions, and eventually security,
  decor/prestige, access permeability, and interactive objects

## What's Built

### Core Models (`world/events`)
- **Event** — name, description, location (FK RoomProfile), status lifecycle
  (DRAFT/SCHEDULED/ACTIVE/COMPLETED/CANCELLED), public/private, scheduling (real time primary,
  IC time derived then adjustable, TimePhase default DAY), 6-hour same-location gap constraint
- **EventHost** — multi-host via Persona, one primary host, staff has implicit access
- **EventInvitation** — polymorphic targets (persona/organization/society), SET_NULL on deletion.
  Invite/remove actions on EventViewSet
- **EventModification** — stub: room_description_overlay applied on start, reverted on complete
- **Scene.event FK** — nullable FK on existing Scene model

### Room Selection
- `is_public` flag on RoomProfile filters which rooms appear in public listings
- Area hierarchy drill-down API (RoomProfileViewSet) for browsing public rooms
- MVP: all public rooms hostable by anyone

### Calendar & Discovery API
- Calendar endpoint showing upcoming/active events with pagination
- Public events visible to all; private events visible to hosts, direct invitees, and members
  of invited organizations/societies (via FK join through OrganizationMembership)
- Filters: status, location/area, search by name/description
- GM permission: scene GMs can complete active events

### Event Lifecycle
- DRAFT → SCHEDULED (appears on calendar) → ACTIVE (room modified, scene created) → COMPLETED
- Room description overlay applied to room's temporary_description on ACTIVE, reverted on COMPLETED
- Scene created with privacy derived from event's public/private setting
- Atomic transactions with select_for_update to prevent duplicate scenes

### Frontend
- Event list page with status tabs (upcoming/active/past), search, pagination
- Event detail page with hosts, invitations, room modification, lifecycle actions
- Event create form with area drill-down location picker
- Event edit form for DRAFT/SCHEDULED events (hosts/staff only)
- Invitation management: persona search, invite, and remove from detail page
- Sidebar panel for quick event access
- Timezone-correct datetime inputs

## Future Work (not MVP)
- **IC permission to host** — society reputation checks, bribery/permission gameplay loops
- **IC costs** — currency/supplies for hosting, scaling with prestige
- **Full EventModification** — security levels, prestige/wealth investment, access permeability
  (open/guests/hard locked), interactive objects, guard NPCs. Needs dedicated brainstorm
- **Prestige/fame system** — noble politics reputation distinct from Legend, affected by event
  quality and noble house investment
- **Domain effects** — event quality affecting noble house domain strength
- **Guest access mechanics** — invitees bringing +1s, sneak mechanics for uninvited
- **Interactive event objects** — mini-games attached to events
- **GM events** — integration with Stories/GM table system
- **Running events auto-ended** when next scheduled event at same location begins

## Design Doc
- `docs/plans/2026-03-27-events-system-design.md`

## Notes
- EventModification is deliberately a stub. Do not expand its schema without a dedicated
  brainstorming session to get the full shape right
- The permission/cost system for hosting is groundwork only in MVP — the hooks exist but
  enforcement is deferred to future PRs
