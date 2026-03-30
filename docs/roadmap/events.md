# Events

**Status:** in-progress
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

## What Exists
- **Area hierarchy** — 8-level spatial hierarchy (PLANE → BUILDING) with AreaClosure materialized
  view for efficient drill-down queries. Used for room selection in event creation
- **RoomProfile** — Links Evennia rooms to area hierarchy. Will gain `is_public` flag for
  filtering room selection
- **Game Clock** — IC/OOC time conversion for scheduling. TimePhase enum (DAWN/DAY/DUSK/NIGHT)
  reused for event time-of-day
- **Scene system** — Ready to accept optional `event` FK
- **Societies/Organizations** — Ready for invitation targeting

## What's Needed for MVP

### Core Models (`world/events`)
- **Event** — name, description, location (FK RoomProfile), status lifecycle
  (DRAFT/SCHEDULED/ACTIVE/COMPLETED/CANCELLED), public/private, scheduling (real time primary,
  IC time derived then adjustable, TimePhase default DAY), 6-hour same-location gap constraint
- **EventHost** — multi-host via Persona, one primary host, staff has implicit access
- **EventInvitation** — polymorphic targets (persona/organization/society), SET_NULL on deletion
- **EventModification** — stub: just room_description_overlay for MVP. Full design (security,
  prestige, access permeability, interactive objects) needs dedicated brainstorm session
- **Scene.event FK** — nullable FK on existing Scene model

### Room Selection
- `is_public` flag on RoomProfile for filtering
- Area hierarchy drill-down API for browsing public rooms
- Current-room selection option
- Permission check: can this character host here? (tied to EventModification permissions)
- MVP: all public rooms hostable by anyone

### Calendar & Discovery API
- Calendar endpoint showing upcoming/active events
- Public events visible to all, private events visible to hosts + invitees
- Filters: status, location/area, host, organization/society

### Event Lifecycle
- DRAFT → SCHEDULED (appears on calendar) → ACTIVE (room modified, scene created) → COMPLETED
- Room description overlay applied/reverted on ACTIVE/COMPLETED transitions
- Scene created with privacy derived from event's public/private setting
- Running events ended when next scheduled event at same location begins

### Frontend
- Event creation form with progressive disclosure
- Calendar view of upcoming events
- Event detail page (description, hosts, location, time)

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

## Design Doc
- `docs/plans/2026-03-27-events-system-design.md`

## Notes
- EventModification is deliberately a stub. Do not expand its schema without a dedicated
  brainstorming session to get the full shape right
- The permission/cost system for hosting is groundwork only in MVP — the hooks exist but
  enforcement is deferred to future PRs
