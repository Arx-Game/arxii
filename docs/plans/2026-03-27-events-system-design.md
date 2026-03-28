# Events System Design

## Problem

Players need a way to schedule RP gatherings — balls, meetings, training sessions, coven
rituals — and have those events appear on a shared calendar. Currently there's no scheduling
system; Scene only handles active RP logging.

## Key Design Insight: Events Are Not Scenes

Events and Scenes serve different purposes and should be separate systems:

- **Event** — the planning/scheduling artifact. Who, what, when, where, is it public, who's
  invited, how is the room modified. An Event sets up the world state for RP to happen.
- **Scene** — the RP recording. Tracks interactions, personas, threading, privacy. A Scene
  logs what actually happened during the RP.

An Event spawns a Scene when RP begins. The Scene has an optional FK back to the Event.
One event, one scene. Multi-room GM sessions that span multiple scenes are a Stories/GM
concern, handled separately.

## Four Distinct Discovery Concerns

This design addresses only #3. The others are listed for clarity:

1. **Ephemeral scenes** — spontaneous, unlogged, never scheduled. Already built.
2. **GM sessions** — GM running narrative sessions for their table, potentially multi-room.
   Deferred to Stories/GM system.
3. **Events** — scheduled RP gatherings anyone can create, public or private. **This system.**
4. **Grid presence** — "who's where" on public rooms for organic RP. Future feature, likely
   a graphical map showing characters in public spaces.

## App Location

New Django app: `world/events`

Events are a cross-cutting coordination system touching scenes, rooms, game clock,
societies/reputation, and eventually economy. They don't belong in any existing app.

## Models

### Event

The central model. Represents a planned gathering with scheduling and access control.

```
Event
  name                 CharField(255)
  description          TextField(blank=True)
  location             FK(RoomProfile, on_delete=PROTECT)
  status               EventStatus: DRAFT / SCHEDULED / ACTIVE / COMPLETED / CANCELLED
  is_public            BooleanField — public events visible to all on calendar

  # Scheduling — real time is primary, IC time derived then adjustable
  scheduled_real_time  DateTimeField — the OOC date/time players schedule for
  scheduled_ic_time    DateTimeField — derived from game clock, player can modify
  time_phase           TimePhase: DAWN / DAY / DUSK / NIGHT (default DAY)

  # Lifecycle
  started_at           DateTimeField(nullable) — when event actually began
  ended_at             DateTimeField(nullable) — when event finished

  # Timestamps
  created_at           DateTimeField(auto_now_add)
  updated_at           DateTimeField(auto_now)
```

**Status transitions:** DRAFT → SCHEDULED → ACTIVE → COMPLETED, any → CANCELLED

**Constraints:**
- No two events at the same location within 6 real hours of each other
- If a running event overlaps with the next scheduled one, the running event ends
- `scheduled_ic_time` validated to be within ~2 IC weeks of the OOC scheduling date
- Scene time freezes at the designated `time_phase`

### EventHost

Multiple hosts per event. Hosts can modify the event. Staff has implicit host-level
access without needing a row.

```
EventHost
  event        FK(Event, on_delete=CASCADE)
  persona      FK(Persona, on_delete=SET_NULL, nullable)
  is_primary   BooleanField(default=False) — the "face" of the event on listings
  added_at     DateTimeField(auto_now_add)

  Unique: (event, persona)
```

At least one host must be `is_primary=True` (validated at service layer).

### EventInvitation

Polymorphic invitation supporting individual personas, organizations, and societies.
Many invitation rows per event.

```
EventInvitation
  event                FK(Event, on_delete=CASCADE)
  target_type          InvitationTargetType: PERSONA / ORGANIZATION / SOCIETY
  target_persona       FK(Persona, nullable, on_delete=SET_NULL)
  target_organization  FK(Organization, nullable, on_delete=SET_NULL)
  target_society       FK(Society, nullable, on_delete=SET_NULL)
  can_bring_guests     BooleanField(default=False) — future hook
  invited_at           DateTimeField(auto_now_add)
  invited_by           FK(Persona, nullable, on_delete=SET_NULL)

  Unique: (event, target_type, target_persona, target_organization, target_society)
```

Only one target FK populated per row based on `target_type`. Invalid/deleted targets
become SET_NULL — the invitation becomes inert but never cascades to delete the event.

**No RSVPs.** Invitations are low-pressure — show up or don't. Obligation after
confirming creates cognitive burden that runs counter to the loose, low-pressure feel
we want for RP in a MUSH. The Scene tracks who actually participated.

### EventModification (stub)

One-to-one with Event. Currently only `room_description_overlay` is functional.
Full design of modification types (security, prestige/decor, access permeability,
interactive objects, guard levels) requires a dedicated brainstorming session before
implementation.

```
EventModification
  event                     OneToOne(Event, on_delete=CASCADE)
  room_description_overlay  TextField(blank=True) — augments room desc while ACTIVE
```

Future fields (to be designed): security level, prestige/wealth investment, access
permeability (open/guests allowed/hard locked), interactive objects, guard NPCs.

### Scene FK (existing model change)

Add to the existing Scene model:

```
Scene
  event  FK(Event, nullable, on_delete=SET_NULL, related_name="scene")
```

One scene per event. The event FK is how scenes know they were spawned from a
scheduled event.

## Room Selection

Players select a location for their event via:

1. **Area hierarchy drill-down** — browse public rooms: region → city → neighborhood →
   building → room. Uses existing Area model (8 levels), AreaClosure materialized view,
   and RoomProfile. Excludes rooms where `is_public=False` (new field on RoomProfile).
2. **Current room** — pick the room you're standing in.

After selection, a permission check determines whether the character can host an event
at that location. This permission is tied to EventModification — permission to modify
a room implies permission to host there. For MVP: all public rooms are hostable by
anyone. Future: gated by society reputation, IC costs, bribery/permission gameplay loops.

## Calendar & Discovery

- Public events appear on a shared calendar visible to all players
- Private events appear only to hosts and invitees (including organization/society members)
- Calendar shows events by OOC date with IC time and time phase
- Events display: name, description, location, primary host persona, time, public/private
- Filter by: upcoming/active/completed, location (area), host, organization/society

## Event Lifecycle

1. **Creation** — host creates event, picks location, sets time, invites guests
2. **DRAFT** — event is being set up, not yet on the calendar
3. **SCHEDULED** — event is confirmed and appears on the calendar
4. **ACTIVE** — event time arrives, room description overlay applies, scene is created
5. **COMPLETED** — event ends (manually or forced by next event at same location)
6. **CANCELLED** — host or staff cancels

When an event becomes ACTIVE:
- EventModification.room_description_overlay is applied to the room
- A Scene is created with `event` FK pointing back
- Scene privacy mode is set by the host (can be ephemeral for private events)

When an event COMPLETES:
- Room description reverts to normal
- Scene is finished (is_active=False, date_finished set)

## Design Decisions

### No RSVPs
Obligation after confirming creates cognitive burden. Show up or don't.

### No estimated duration
6 real-hour minimum gap between events at the same location prevents overlap.
Running events are ended when the next scheduled event begins.

### Persona-based, not account-based
All player-facing references use Persona to maintain IC/OOC privacy boundary.
Hosts are personas. Invitations target personas. Players cannot determine who
plays which character through the event system.

### Events don't modify Scene responsibilities
Scene continues to handle only RP logging. Events handle scheduling, room state,
access control. Clean separation of concerns.

### Progressive disclosure UX
Simple event creation by default (name, location, time, public/private, description).
"Extra options" expands to EventModification, detailed invitations, organization
invites, etc. A casual tavern meetup and a coronation ball use the same system
at different depth levels.

## Future Work (not in MVP)

- **IC permission to host** — society reputation checks, bribery gameplay loop
- **IC costs** — currency/supplies for hosting, scaling with prestige
- **Full EventModification design** — security, prestige, access permeability,
  interactive objects, guard NPCs (needs dedicated brainstorm)
- **Prestige/fame system** — noble politics reputation distinct from Legend,
  affected by event quality and investment
- **Domain effects** — event quality affecting noble house domain strength
- **Guest access** — invitees bringing +1s, sneak mechanics for uninvited
- **Interactive objects** — mini-games attached to events
- **GM events** — integration with Stories/GM table system for narrative sessions
