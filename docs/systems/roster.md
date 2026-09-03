# Roster System

Character lifecycle management with web-first applications, player anonymity, and tenure-based ownership.

**Source:** `src/world/roster/`
**API Base:** `/api/roster/`

---

## Enums (models/choices.py)

```python
from world.roster.models import (
    ApplicationStatus,      # PENDING, APPROVED, DENIED, WITHDRAWN
    PlotInvolvement,        # HIGH, MEDIUM, LOW, NONE
    RosterType,             # ACTIVE, INACTIVE, AVAILABLE, RESTRICTED, FROZEN, PENDING, NPC
    CreationProvenance,     # STAFF, GM_TABLE, PLAYER (viewable quality/trust signal, #1506)
    ApprovalScope,          # ALL, HOUSE, STORY, NONE
    ValidationErrorCodes,   # Error code constants for DRF serializers
    ValidationMessages,     # User-friendly validation message constants
)
```

---

## Applying these migrations

`Roster.roster_type` (#2728) is `null=False` with no default — migration 0011
(`alter_roster_roster_type`) fails with `column "roster_type" contains null values`
on any database that already has `Roster` rows.

**Dev databases only, and only for a database still stranded before migration 0011.**
The delete-and-reseed below was written under ADR-0013, whose no-backfill premise
ADR-0237 has since superseded: production is durable, `RosterEntry` and its tenures
cascade off `Roster`, and this statement would take real characters with it. Never run
it against production; a production database in this state needs a `RunPython`
backfill, per ADR-0237.

```sql
DELETE FROM roster_roster;
```

then re-run `world.roster.seeds.ensure_rosters()` (e.g. via the roster or
character_creation seed cluster) — it creates all seven canonical shelves keyed by
`roster_type`.

---

## Activity, inactivity, and auto-release (#671, #2728)

Two orthogonal axes, both on `CharacterSheet`: `activity_state` is **OOC** (is the
player showing up), `lifecycle_state` is **IC** (what is true in the fiction). A
captured character and a lapsed player are different facts and neither implies the
other.

**`activity_requirement` is authored per character, on `RosterEntry`.** It follows
from the nature of the character and the stories it is tied to, so staff set and
change it by hand in the admin. It is deliberately *not* on `Roster`: approval moves
a character from Available onto the Active shelf, which would flatten every
character's requirement to whatever that one shelf carried.

It governs two things — **which signals count** (HIGH = any-persona IC action *plus*
account login; LOW = account login only) and **whether inactivity also releases the
character**. It does *not* decide whether a character is swept: every character is
flagged INACTIVE at 30 days so nothing accrues income or takes decay for someone
who isn't there.

### The sweep is demotion-only

`world.roster.services.activity.sweep_activity_states` (weekly cron) walks
characters on the **Active shelf** and demotes those past the 30-day bar. Story NPCs
sit on the NPC shelf and are excluded by construction rather than by a special case.

Promotion is **event-driven**: `mark_character_active` fires from `at_post_puppet`,
so a returning player is ACTIVE immediately instead of waiting up to a week. The
sweep therefore never examines a non-ACTIVE sheet to catch a return.

Hiatus expiry runs *after* demotion, deliberately. A player's decay clock keeps
running through a declared absence, so expiring and demoting in one tick would flag —
and for a roster character, release — someone the instant their vacation ended,
before they could log back in. Expiring last leaves them ACTIVE until the next run.

**A swept character costs writes only.** The sweep's population is the whole active
playerbase, so its per-character cost is the number that matters. Everything the loop
reads is fetched in bulk — the shelf and `true_profile` via `select_related`, the
tenures and their player account via `Prefetch(..., to_attr="cached_tenures")` —
because `decay_tier` otherwise walks `roster_entry → current_tenure → player_data →
account` once per sheet. `world.roster.tests.test_sweep_query_slope` pins this by
measuring two population sizes: reads must not grow at all, writes must be exactly
the four inherent row updates per released character.

**Bulk callers must clear up after themselves.** `RosterEntry.cached_tenures` is a
`cached_property`, so `to_attr="cached_tenures"` fills it directly (and leaves
`entry.tenures` a live relation for everyone else). But `SharedMemoryModel` hands the
same instance to the next reader in the process, so a fill left in place would answer
with a mid-sweep snapshot indefinitely. Call `RosterEntry.invalidate_tenure_cache()`
after any bulk fill and after any tenure mutation — the sweep does it for every
character it examines, including ones it decides not to demote.

### Account-level caches (#3597, ADR-0260)

`request.user` is the identity-mapped `Account` typeclass, so account facts are
`cached_property` entries on it, computed once per account per process and never
memoized on a view or a request: `cached_roster_entries` (current tenures),
`cached_persona_ids` (every persona type on those sheets), `cached_codex_knowledge`
(`roster_entry_id -> entry_id -> CharacterKnowledge`), `cached_covenant_memberships`
(`covenant_id -> own active membership`), beside the older `cached_primary_persona_ids`
and `played_character_sheet_ids`. Invalidation is `related_cache_fields`: any
`RosterTenure` save clears them all; `CharacterCodexKnowledge`, `Persona` and
`CharacterCovenantRole` each walk `... -> current_tenure -> player_data -> account` on
save/delete. "Available" (active roster, not retired) stays one definition:
`PlayerData.get_available_roster_entries()`, which `get_available_characters()` maps over.

### Release is narrower than the flag

| | Flagged INACTIVE at 30d | Auto-released |
|---|---|---|
| `activity_requirement` HIGH | yes | **yes** |
| `activity_requirement` LOW | yes | **yes** |
| `activity_requirement` NONE | yes | no |
| OCs (`is_oc=True`) | yes | **never** |
| NPCs (NPC shelf) | not swept | n/a |

The flag is broad because its job is to stop accrual for an absent player. The
release is narrow because taking a character away is only justified when someone
else is waiting for it. On release the tenure is **ended, never deleted** and the
entry moves back to Available.

**A returning player is re-seated, not renumbered.** Applications are staff-approved,
so approval — not application order — is the decision point, and losing applications
result in nothing. If the original player is the one approved,
`RosterApplication.approve` reopens their existing tenure rather than minting a
second one, which would otherwise announce them as "2nd player of X" when they are
the same person.

Consumers should ask the shared vocabulary on `CharacterSheet.objects`
(`.active()` / `.claimable()` / `.dormant()` / `.inactive_at_least(tier)`) rather
than deriving absence from timestamps. Mothballing (90d) reads
`inactive_at_least(LONG_INACTIVE)` — a *consequence* of inactivity, not a rival
definition of it.

---

## Models

### Core Roster

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Roster` | Character category groups (Active, Inactive, etc.) — keyed by `roster_type` (#2728); `name` is a display label only | `roster_type` (unique, `RosterType`, the key), `name` (unique, display label), `description`, `is_active`, `is_public`, `allow_applications`, `sort_order` |
| `RosterEntry` | Bridge linking characters to rosters (1:1 with CharacterSheet) | `character_sheet` (OneToOne CharacterSheet — retargeted from ObjectDB in #2608), `roster` (FK), `profile_picture` (FK TenureMedia), `joined_roster`, `previous_roster`, `last_puppeted`, `activity_requirement` (`ActivityRequirement`, #2728 — **authored per character**, not derived from the shelf), `gm_notes`, `creation_provenance` (`CreationProvenance`, #1506), `created_by_account` (FK AccountDB), `created_for_table` (FK gm.GMTable — set for GM_TABLE) |

### Tenures & Anonymity

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `RosterTenure` | Player-character relationship with anonymity — `Meta.ordering = ["-start_date"]` (#2728), so the lazy and prefetched fills of `RosterEntry.cached_tenures` agree on sort without either restating it | `player_data` (FK PlayerData), `roster_entry` (FK), `player_number`, `start_date`, `end_date` (null = current), `applied_date`, `approved_date`, `approved_by` (FK PlayerData), `photo_folder` |
| `RosterApplication` | Application workflow before tenures | `player_data` (FK PlayerData), `character` (FK CharacterSheet — retargeted from ObjectDB in #2608), `status` (TextChoices), `application_text`, `review_notes`, `reviewed_by` (FK PlayerData) |
| `PlayerData` (`evennia_extensions`) | Extends `AccountDB`; holds `selected_entry` (FK `RosterEntry`, `SET_NULL`, #3412) — the durable, offscreen "which character has this account taken up" fact (state 2.5 substrate). **Selection is not presence**: set only via `world.roster.services.selection.set_selected_entry`, which triggers zero lifecycle/session/puppeting writes. Must be one of `get_available_characters()`'s own-current population; a foreign entry is rejected. | `account` (OneToOne AccountDB, pk), `selected_entry` (FK RosterEntry, nullable), `display_name`, `karma`, `gm_notes`, ... |

### Settings & Media

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TenureDisplaySettings` | Per-tenure UI preferences (1:1) | `tenure` (OneToOne), `public_character_info`, `show_online_status`, `allow_pages`, `allow_tells`, `appear_offline` (quiet/hidden mode #1463 — drops off where/who + unpageable except allowlist; read via `world.scenes.presence.character_appears_offline`, written via `world.roster.services.display.set_appear_offline`), `rp_preferences`, `plot_involvement` |
| `TenureGallery` | Named collection of media for a tenure | `tenure` (FK), `name`, `is_public`, `allowed_viewers` (M2M RosterTenure) |
| `TenureMedia` | Bridge between player media and tenures | `tenure` (FK), `media` (FK Media, renamed from PlayerMedia #2408), `gallery` (FK TenureGallery, nullable), `sort_order` |

### Mail

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `PlayerMail` | Tenure-targeted mail with threading | `sender_tenure` (FK, nullable), `recipient_tenure` (FK), `subject`, `message`, `sent_date`, `read_date`, `archived`, `in_reply_to` (FK self) |

### Families

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Family` | Family/house definition (SharedMemoryModel) | `name` (unique), `family_type` (COMMONER/NOBLE), `description`, `is_playable`, `created_by_cg`, `created_by` (FK AccountDB), `origin_realm` (FK Realm) |
| `FamilyMember` | Individual member of a family tree | `family` (FK), `member_type` (CHARACTER/PLACEHOLDER/NPC), `character` (OneToOne ObjectDB, nullable), `name`, `description`, `age`, `mother` (FK self), `father` (FK self), `created_by` (FK AccountDB) |

---

## Key Methods

### RosterEntry

```python
from world.roster.models import RosterEntry

# Get current tenure (most recent without end_date)
entry.current_tenure  # Returns RosterTenure or None

# Check if character accepts applications
entry.accepts_applications  # True if roster allows apps AND no current tenure

# Move character to a different roster
entry.move_to_roster(new_roster)  # Saves previous_roster, updates joined_roster

# Cached tenures (ordered by -start_date)
entry.cached_tenures
```

### RosterTenure

```python
from world.roster.models import RosterTenure

# Anonymous display name
tenure.display_name  # "2nd player of Ariel"

# Check if tenure is current
tenure.is_current  # True if end_date is None

# Convenience character access
tenure.character  # roster_entry.character

# Cached media
tenure.cached_media  # list of TenureMedia
```

### RosterApplication

```python
from world.roster.models import RosterApplication

# Approve application (creates RosterTenure, sends email)
tenure = application.approve(staff_player_data)

# Deny application (sends denial email)
application.deny(staff_player_data, reason="Not suitable at this time")

# Player withdraws their own application
application.withdraw()

# Get policy review info for reviewer display
application.get_policy_review_info()  # Delegates to RosterPolicyService
```

### PlayerMail

```python
from world.roster.models import PlayerMail

mail.is_read       # True if read_date is not None
mail.mark_read()   # Sets read_date to now

# Get all messages in a thread (finds root, returns chronological)
mail.get_thread_messages()
```

---

## Telnet Surface (#2122)

Roster browsing and applying stay web-only, by design. The one telnet exception is
**own-status only** — a player checking on applications they've already submitted, which
needs no listing/browsing UI:

- `roster` / `roster status` (`commands/account/account_info.py`, `CmdRoster`, registered in
  `AccountCmdSet`) — reads `self.account.player_data.get_pending_applications()` (the same
  `PlayerData` method the web `/api/user/` payload's `pending_applications` field already
  calls). Scoped to the caller's own `PlayerData` — no id-based lookup exists on the command,
  so one account's applications can never surface another's.

The telnet front door itself (connection screen + the characterless post-login message,
`server/conf/connection_screens.py` / `typeclasses/accounts.py::at_post_login`) now points at
`settings.FRONTEND_URL` so a telnet-only player has a path to the web roster/application/chargen
flow in the first place.

### FamilyMember

```python
from world.roster.models.families import FamilyMember

member.get_display_name()  # Character key or placeholder name
member.parents             # [mother, father] (non-None only)
member.children            # Combined children_as_mother + children_as_father
member.siblings            # Members sharing at least one parent

# Ancestor traversal with depth limit
member.get_ancestors(max_depth=10)

# Derive relationship to another member
member.get_relationship_to(other)
# Returns: "parent", "child", "sibling", "grandparent", "grandchild",
#          "aunt/uncle", "niece/nephew", "cousin", "self", or None
```

### Custom Managers

```python
from world.roster.models import RosterEntry, RosterApplication, RosterTenure

# RosterEntry manager
RosterEntry.objects.active_rosters()                        # In active rosters
RosterEntry.objects.available_characters()                  # Accepting applications, no current player
RosterEntry.objects.exclude_frozen()                        # Not frozen
RosterEntry.objects.by_roster_type("Active")                # Filter by roster name
RosterEntry.objects.exclude_characters_for_player(player)   # Exclude player's current/pending chars

# RosterApplication manager
RosterApplication.objects.pending()                         # Status = pending
RosterApplication.objects.for_character(character)           # For specific character
RosterApplication.objects.for_player(player_data)            # By specific player
RosterApplication.objects.awaiting_review()                  # Pending, ordered by date
RosterApplication.objects.recently_reviewed(days=7)          # Reviewed in last N days

# RosterTenure manager
RosterTenure.objects.current()                              # end_date is null
RosterTenure.objects.ended()                                # end_date is not null
RosterTenure.objects.for_player(player_data)                 # For specific player
```

---

## API Endpoints

### Rosters (`/api/roster/rosters/`)
- `GET /api/roster/rosters/` - List active rosters (read-only). Staff see every
  active roster; everyone else is narrowed to `is_public=True`, so staff-only
  shelves (e.g. NPC) never surface to players (#2728).

### Entries (`/api/roster/entries/`)
- `GET /api/roster/entries/` - List roster entries with character data
- `GET /api/roster/entries/{id}/` - Entry detail
- `GET /api/roster/entries/mine/` - Current user's characters (authenticated).
  `MyRosterEntrySerializer` annotates `unread_narrative_count` (#3412 slice 2 — the
  Hall's per-character tidings badge) via one aggregated `Count(...filter=...)` JOIN
  over unacknowledged `NarrativeMessageDelivery` rows, not a per-row query. The same
  serializer backs the unannotated `select` response fragment
  (`selected_entry`/`SelectedEntryResultSerializer`), so the field is a
  `SerializerMethodField` reading the annotation off `obj.__dict__` when present and
  falling back to a direct count (one extra query, single-object path only) when not.
  Also exposes `lifecycle_state` (#3412 slice 3 — a plain read-only `CharField` mirror
  of `CharacterSheet.lifecycle_state`, no annotation, no migration) so the Hall's
  OffscreenActsPlate can branch on a degraded state (CAPTURED/DEAD/RETIRED/UNKNOWN)
  without a new endpoint. Deliberately does NOT expose the unconscious overlay (a
  conditions-system read, not a sheet column) — recorded as an open seam, not built.
- `POST /api/roster/entries/{id}/apply/` - Apply for a character (requires verified email)
- `POST /api/roster/entries/{id}/set_profile_picture/` - Set profile picture from tenure media
- `POST /api/roster/entries/select/` - Set/clear the account's durable character selection
  (`{entry_id}` or `null`) — the state 2.5 substrate (#3412). Mirrors the persona
  set-active endpoint's shape: the entry must be one of `mine`'s own-current-entries
  population, a foreign/unknown id is rejected uniformly, and `entry_id: null` always
  clears. **Selection is NOT presence** — no lifecycle/session/puppeting side effects
  fire. Sole mutator: `world.roster.services.selection.set_selected_entry`. Response
  mirrors the `/api/user/` payload fragment (`selected_entry_id` + `selected_entry`).

**Filters:** `RosterEntryFilterSet` via DjangoFilterBackend

### Tenures (`/api/roster/tenures/`)
- `GET /api/roster/tenures/` - List tenures with search by character name
- `GET /api/roster/tenures/mine/` - Current user's active tenures (for dropdown selection)

### Mail (`/api/roster/mail/`) — the OOC player-to-player mail surface (#2160, ADR-0226)
- `GET /api/roster/mail/` - List received mail (newest first)
- `POST /api/roster/mail/` - Send mail (validates sender_tenure ownership); fires
  `notify_mail_arrived(recipient_tenure, mail)` via `transaction.on_commit`, pushing a
  `WebsocketMessageType.MAIL_ARRIVED` payload (`mail_id`/`sender_display`/`subject` — no
  account identifiers) to the recipient's account. Fail-soft: an offline recipient's
  `account.msg` is a harmless no-op; a push failure never blocks the send.
- `POST /api/roster/mail/{id}/mark-read/` - Mark this mail read (idempotent; recipient-only,
  enforced by the scoped queryset in `get_object()`)
- `GET /api/roster/mail/unread-count/` - Count of unread, unarchived mail across the
  requester's tenures (`UnreadMailCountSerializer`)

Web-only surface: compose at `/profile/mail` or in-scene via `MessagePlayerDialog` (pre-fills
`ComposeMailForm` from the character card's "Message the player" quick action), unread badge
in the header (`UnreadMailBadge`), mark-read-on-open in `ReceivedMailList`. No telnet mail
command.

### Applications (`/api/roster/applications/`) - staff review queue (#3265)
- `GET /api/roster/applications/` - List applications; `?status=` filters by
  `ApplicationStatus` (`pending`/`approved`/`denied`/`withdrawn`), defaulting to
  pending-only when omitted (`RosterApplicationFilterSet.qs`) so the queue opens on
  what needs action
- `GET /api/roster/applications/{id}/` - Application detail (full text, `policy_review_info`)
- `POST /api/roster/applications/{id}/review/` - `{"action": "approve"|"deny",
  "review_notes"}` drives `RosterApplication.approve()`/`.deny()`
- `GET /api/roster/applications/pending-count/` - Count of pending applications, for
  the staff hub badge

All four routes are staff-only, gated by `CanApproveApplications`
(`PlayerData.can_approve_applications()` - staff today; trust-system integration is
future work). Distinct from `character_creation`'s DraftApplication review: this
queue is players applying for staff-authored characters already on the Available
shelf, not new player-made characters going through CG.

### Families (`/api/roster/families/`)
- `GET /api/roster/families/` - List playable families
- `GET /api/roster/families/{id}/` - Family detail
- `GET /api/roster/families/{id}/tree/` - Complete family tree with members

**Query Parameters:** `has_open_positions=true` (filter families with placeholder members)

### Family Members (`/api/roster/family-members/`)
- Full CRUD for family members (creator or staff only for write)

**Filters:** `family`, `member_type`

### Media (`/api/roster/media/`)
- `GET /api/roster/media/` - List user's media (staff sees all)
- `POST /api/roster/media/` - Upload image via Cloudinary
- `POST /api/roster/media/{id}/associate_tenure/` - Link media to a tenure/gallery
- `POST /api/roster/media/{id}/set_profile_picture/` - Set as account profile picture

### Galleries (`/api/roster/galleries/`)
- Full CRUD for tenure galleries

**Query Parameters:** `tenure` (filter by tenure ID)

---

## Permissions

| Permission Class | Used For | Rule |
|-----------------|----------|------|
| `IsOwnerOrStaff` | Media/gallery modification | `obj.player_data.account == request.user` or staff |
| `IsPlayerOrStaff` | Roster entry modifications | Active tenure for the entry or staff |
| `ReadOnlyOrOwner` | Media/gallery viewing | Safe methods for all; write requires ownership |
| `StaffOnlyWrite` | Roster management | Safe methods for all; write requires staff |
| `CanApproveApplications` | Application review queue (#3265) | `PlayerData.can_approve_applications()` (staff today) |

---

## Integration Points

- **PlayerData** (`evennia_extensions.PlayerData`): Extends AccountDB with `player_data` reverse relation; tenures link to PlayerData, not AccountDB directly
- **Media** (`evennia_extensions.Media`, renamed from `PlayerMedia` #2408): Actual media storage (player uploads and staff-authored art, derived by `player_data` nullability — see ADR-0146); TenureMedia bridges to character tenures
- **Scenes System**: Personas reference characters via ObjectDB, which have `roster_entry` for identity resolution
- **Character Creation**: `Family` and `FamilyMember` used during CG for family selection; families filtered by `origin_realm`

---

## Frontend: Selection Chrome (#3412 slice 1, ADR-0241)

Web-only; no telnet surface (selection is a web-first state substrate, not a
command). Client state mirrors the server; nothing here is a source of truth.

- **`gameSlice`** (`frontend/src/store/gameSlice.ts`) mirrors
  `PlayerData.selected_entry_id`/`selected_entry` alongside the existing
  `active`/`activeEntryId` puppeting fields — hydrated from `useAccountQuery`'s
  `GET /api/user/` response on every fetch, so a hard reload or a second device
  reproduces the same selection. **Known wart:** the slice keys by character
  *name*, not `RosterEntry` id, a pre-existing shape deliberately not refactored
  here (25-surface change, out of slice scope — see the #3412 roadmap entry's
  "known seams").
- **`SelectedCharacterChip`** (`frontend/src/components/SelectedCharacterChip.tsx`)
  — docked-portrait chip in `Header`, rendered app-wide (not just inside
  `/game`) whenever a selection exists. Shows portrait + name, reuses the same
  `PersonaSwitcher` `GameTopBar` mounts in-game (re-mounted here so
  identity-switching works before entering `/game`), an "Enter the world" link,
  and a "step away" control that clears the selection via
  `useSelectCharacterMutation`. PLACEHOLDER copy throughout — final wording is
  a separate pass; see the "Taken Up" glossary entry.
- **`RequireCharacter`** (`frontend/src/components/RequireCharacter.tsx`) — route
  guard gaining a second remedy (#3412 hygiene fold-in): offers both "Browse the
  roster" and "Create a character," mirroring `WelcomePanel`'s zero-character
  card instead of offering only one path.
- **Enter-the-world auto-start** — the one deliberate selection→presence
  crossing. `SelectedCharacterChip`'s "Enter the world" link never puppets
  anything itself; `GamePage`'s own mount-path effect (`frontend/src/game/GamePage.tsx`)
  auto-starts the session on arrival when a selection exists but no session is
  live yet, keeping the selection/puppeting distinction intact even at the one
  place they meet.
- **Degradation sweep (#3412 hygiene fold-in):** loading states for tidings and
  wardrobe panels, a mute-settings link, three message-tab fixes, notification
  badge routing corrections, nine feed-kind labels, and consent-notifier gating
  — all pre-existing gaps surfaced while wiring selection-aware chrome, fixed in
  the same slice rather than filed separately (repo convention: fold in, don't
  file).

## Admin

- `RosterAdmin` - List/filter by active status and application permission
- `RosterEntryAdmin` - Autocomplete for characters; fieldsets for status, history, notes, timestamps
- `RosterTenureAdmin` - Autocomplete for entry/player_data; date hierarchy on start_date; displays `is_current` boolean
- `RosterApplicationAdmin` - Bulk approve/deny actions; autocomplete for character/player_data; date hierarchy on applied_date. No longer the only review surface: staff also review from `/staff/roster-applications` via `RosterApplicationViewSet` (#3265)
- `TenureDisplaySettingsAdmin` - Grouped fieldsets for display, communication, and roleplay preferences
- `TenureGalleryAdmin` - Autocomplete for tenure and allowed_viewers
- `TenureMediaAdmin` - Autocomplete for tenure, media, and gallery
- `PlayerMailAdmin` - Search by sender/recipient character names; date hierarchy on sent_date; `is_read` boolean display
- `FamilyAdmin` - List/filter by family type, playability, CG-created status
