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
    RosterType,             # ACTIVE, INACTIVE, AVAILABLE, RESTRICTED, FROZEN
    ApprovalScope,          # ALL, HOUSE, STORY, NONE
    ValidationErrorCodes,   # Error code constants for DRF serializers
    ValidationMessages,     # User-friendly validation message constants
)
```

---

## Models

### Core Roster

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Roster` | Character category groups (Active, Inactive, etc.) | `name` (unique), `description`, `is_active`, `is_public`, `allow_applications`, `sort_order` |
| `RosterEntry` | Bridge linking characters to rosters (1:1 with ObjectDB) | `character` (OneToOne ObjectDB), `roster` (FK), `profile_picture` (FK TenureMedia), `joined_roster`, `previous_roster`, `last_puppeted`, `frozen`, `gm_notes` |

### Tenures & Anonymity

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `RosterTenure` | Player-character relationship with anonymity | `player_data` (FK PlayerData), `roster_entry` (FK), `player_number`, `start_date`, `end_date` (null = current), `applied_date`, `approved_date`, `approved_by` (FK PlayerData), `photo_folder` |
| `RosterApplication` | Application workflow before tenures | `player_data` (FK PlayerData), `character` (FK ObjectDB), `status` (TextChoices), `application_text`, `review_notes`, `reviewed_by` (FK PlayerData) |

### Settings & Media

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TenureDisplaySettings` | Per-tenure UI preferences (1:1) | `tenure` (OneToOne), `public_character_info`, `show_online_status`, `allow_pages`, `allow_tells`, `rp_preferences`, `plot_involvement` |
| `TenureGallery` | Named collection of media for a tenure | `tenure` (FK), `name`, `is_public`, `allowed_viewers` (M2M RosterTenure) |
| `TenureMedia` | Bridge between player media and tenures | `tenure` (FK), `media` (FK PlayerMedia), `gallery` (FK TenureGallery, nullable), `sort_order` |

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
- `GET /api/roster/rosters/` - List active rosters (public, read-only)

### Entries (`/api/roster/entries/`)
- `GET /api/roster/entries/` - List roster entries with character data
- `GET /api/roster/entries/{id}/` - Entry detail
- `GET /api/roster/entries/mine/` - Current user's characters (authenticated)
- `POST /api/roster/entries/{id}/apply/` - Apply for a character (requires verified email)
- `POST /api/roster/entries/{id}/set_profile_picture/` - Set profile picture from tenure media

**Filters:** `RosterEntryFilterSet` via DjangoFilterBackend

### Tenures (`/api/roster/tenures/`)
- `GET /api/roster/tenures/` - List tenures with search by character name
- `GET /api/roster/tenures/mine/` - Current user's active tenures (for dropdown selection)

### Mail (`/api/roster/mail/`)
- `GET /api/roster/mail/` - List received mail (newest first)
- `POST /api/roster/mail/` - Send mail (validates sender_tenure ownership)

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

---

## Integration Points

- **PlayerData** (`evennia_extensions.PlayerData`): Extends AccountDB with `player_data` reverse relation; tenures link to PlayerData, not AccountDB directly
- **PlayerMedia** (`evennia_extensions.PlayerMedia`): Actual media storage; TenureMedia bridges to character tenures
- **Scenes System**: Personas reference characters via ObjectDB, which have `roster_entry` for identity resolution
- **Character Creation**: `Family` and `FamilyMember` used during CG for family selection; families filtered by `origin_realm`

---

## Admin

- `RosterAdmin` - List/filter by active status and application permission
- `RosterEntryAdmin` - Autocomplete for characters; fieldsets for status, history, notes, timestamps
- `RosterTenureAdmin` - Autocomplete for entry/player_data; date hierarchy on start_date; displays `is_current` boolean
- `RosterApplicationAdmin` - Bulk approve/deny actions; autocomplete for character/player_data; date hierarchy on applied_date
- `TenureDisplaySettingsAdmin` - Grouped fieldsets for display, communication, and roleplay preferences
- `TenureGalleryAdmin` - Autocomplete for tenure and allowed_viewers
- `TenureMediaAdmin` - Autocomplete for tenure, media, and gallery
- `PlayerMailAdmin` - Search by sender/recipient character names; date hierarchy on sent_date; `is_read` boolean display
- `FamilyAdmin` - List/filter by family type, playability, CG-created status
