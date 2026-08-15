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
- **Lightweight RSVP** — Persona invitations carry an optional Accept/Decline response (PENDING by
  default); org/society invitations have no per-member RSVP. Low-pressure: the response is a headcount
  aid, not a gate — the host sees who's coming, but attendance is still "show up or don't." Scene
  tracks who actually came (#1499)
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
  Persona invitations carry an `InvitationResponse` (PENDING/ACCEPTED/DECLINED) +
  `responded_at`; org/society invitations have no per-member RSVP. Invite/remove actions on
  EventViewSet; invitee RSVP via the `respond` endpoint (#1499)
- **EventModification** — stub: room_description_overlay applied on start, reverted on complete
- **Scene.event FK** — nullable FK on existing Scene model

### Action Convergence & Telnet (#1499)
- The web `EventViewSet` create/schedule/start/complete/cancel/invite `@action`s and the
  invitee `respond` (RSVP) all run through real `Action`s on `action.run()` (ADR-0001) —
  `actions/definitions/events.py` (`event_create` / `event_schedule` / `event_start` /
  `event_complete` / `event_cancel` / `event_invite` / `respond_invitation`), REGISTRY backend.
- Lifecycle + invite Actions are **account-authorized** (a staffer or scene GM can manage an
  event with no character): they take an `account` kwarg and pass `actor=None` through
  `action.run()`; the host/GM/staff gate mirrors the DRF permission classes (`IsEventHostOrStaff` /
  `IsEventHostGMOrStaff`). `create` and `respond` act *as* a persona (resolved character actor +
  `HasCharacterSheetPrerequisite`).
- Telnet: the `event <subverb>` namespace (`commands/events.py`, CmdEvent) routes
  `create` / `schedule` / `start` / `complete` / `cancel` / `invite` / `rsvp` write verbs plus
  `list` / `show` read surfaces — converging on the same Actions the web uses.

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
- Invitee RSVP (#3069): Accept/Decline on a viewer's own pending persona invitation, rendered
  inline in the same detail-page invitation list every viewer already sees
  (`EventInvitations.tsx`, matched against the viewer's own persona ids via
  `useMyRosterEntriesQuery`); already-responded rows show "You accepted"/"You declined" instead
  of the buttons. Calls the same `respond_invitation` Action/`respond` endpoint telnet's `event
  rsvp` uses
- Sidebar panel for quick event access
- Timezone-correct datetime inputs
- **Event grandeur (#2357):** `GrandeurPanel` on the event detail page — category
  picker (venue/entertainment/favors/decor), amount input, running contribution list
  + total spend. Post-completion score/tier display is a follow-up (score is visible
  today only via the minted deed).

### Event Grandeur (#2357)
Prestige/wealth investment for once-in-a-lifetime events (royal wedding, coronation,
grand ball) — the dedicated-brainstorm slot the Future Work bullet below used to
reserve. Catering-shaped sibling to `EventCatering`, NOT an `EventModification`
expansion (still gated on its own dedicated brainstorm — see below).
- **`EventGrandeurContribution`** (`world/events/models.py`) — event FK, `GrandeurCategory`
  (VENUE/ENTERTAINMENT/FAVORS/DECOR — food stays catering's lane), `contributed_by`
  Persona, `amount_spent`, audit FK to the `CurrencyTransfer` the spend rode.
  `contribute_grandeur` (`world/events/services.py`) resolves the currency sink via
  `world.currency.services.transfer` (null destination); multiple hosts/contributors
  can each add rows.
- **Completion hook** — `_award_grandeur_prestige`, called from `complete_event`
  alongside `_award_catering_prestige` (independent, both can fire on one event):
  `_grandeur_score` sums spend into a sqrt-diminishing-returns score (capped), then
  mints the primary host's "Grandeur" deed via `create_solo_deed` +
  `_apply_grand_display` — the same pipeline catering uses, so the org's existing 10%
  member-deed trickle (`Organization.accumulated_prestige`) feeds off it automatically.
- **Honoree cut** — when the completed event has a linked, **COMPLETED**
  `Ceremony` whose `ceremony_type.key` is WEDDING or CORONATION,
  `_award_grandeur_honoree_cut` mints an additive per-honoree deed (a flat
  percent of the host's deed value, mirroring
  `CeremonyConfig.officiant_cut_percent`'s shape) — on top of whatever
  `finish_ceremony`'s own branch already awarded them. No cut for a plain grand
  ball, and no cut for a ceremony that opened but never solemnized: an event can
  `complete_event` independently of its own ceremony's finish/abandon (two
  separate triggers, no ordering enforced between them), so an
  `abandon_ceremony`'d wedding — which awards its honorees nothing — must not
  still pay a grandeur cut for a marriage that never happened (review fix,
  2026-08-15).
- **Ratified 2026-08-15 (supersedes the original draft):** no `is_milestone` flag, no
  cooldown bookkeeping. For a ceremony-linked event the economic cost of the spend IS
  the gate (chain-marrying is allowed and priced; coronations are one-off per
  (honoree, title) by #2358's own constraint, not by grandeur bookkeeping); plain
  diminishing returns apply to every event alike.
- **Nonrefundable on cancellation (ruled by the controller 2026-08-15, spec silent —
  Apostate to confirm on tuning pass):** `contribute_grandeur` accepts contributions on
  a SCHEDULED or ACTIVE event, and `cancel_event` can cancel a SCHEDULED event with no
  grandeur-specific unwind — the spend already left the payer's purse/treasury through
  the real currency sink (null destination, non-recoverable) the instant it was made,
  and no prestige mints either (only `complete_event` runs the completion hook). A
  cancelled event's contributions stay spent, matching a nonrefundable-deposit reading
  of "throwing money at a wedding that falls through." Pinned by
  `test_grandeur.py::GrandeurCancellationTest`.
- **Action/telnet/web** — `event_invest_grandeur` (`ContributeGrandeurAction`,
  REGISTRY, treasury-sourced spends gated on `can_spend_treasury` at the Action
  layer); telnet `event grandeur <id> category=<...> amount=<n> [org=<name>]`; web
  `GrandeurPanel` on the event detail page (purse-sourced only for now — no
  "my organizations" picker exists yet for a treasury source).

## Future Work (not MVP)
- **IC permission to host** — society reputation checks, bribery/permission gameplay loops
- **IC costs** — currency/supplies for hosting, scaling with prestige
- **Full EventModification** — security levels, access permeability (open/guests/hard
  locked), interactive objects, guard NPCs. Still needs its own dedicated brainstorm
  before the schema expands — #2357 (event grandeur, above) deliberately did NOT use
  this slot; #2289's ceremony quality remains a planned multiplier input here
- **Prestige/fame system** — noble politics reputation distinct from Legend; #2357
  covers the once-in-a-lifetime-event slice via the Legend/deed pipeline, a general
  system is still open
- **Domain effects** — event quality affecting noble house domain strength (named in
  the original Future Work bullet #2357 grew from; not part of the ratified 2026-08-15
  direction — no domain-model hook exists to verify against, stays a separate future
  issue if wanted)
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
