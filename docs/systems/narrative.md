# Narrative System

General-purpose IC message delivery. `NarrativeMessage` rows carry GM/staff/automated messages to characters; `NarrativeMessageDelivery` rows fan one message out to many recipients with per-recipient delivered/acknowledged state.

Used by the stories system for beat completions and episode resolutions, but not stories-specific — also available for atmosphere messages, visions, happenstance events, and any future IC-message use case.

**Source:** `src/world/narrative/`
**API Base:** `/api/narrative/`

---

## Enums

```python
from world.narrative.constants import NarrativeCategory

# TextChoices:
NarrativeCategory.STORY          # Beat completions, episode resolutions, story-driven informs
NarrativeCategory.ATMOSPHERE     # GM-authored ambient world messages
NarrativeCategory.VISIONS        # Dreams, visions, prophetic flashes
NarrativeCategory.HAPPENSTANCE   # Random incidents, unexpected arrivals
NarrativeCategory.SYSTEM         # System notifications
```

---

## Models

### NarrativeMessage

A single IC message. Immutable after send. Per-recipient state lives on `NarrativeMessageDelivery`.

| Field | Type | Notes |
|-------|------|-------|
| `body` | TextField | Player-facing IC content |
| `ooc_note` | TextField | Staff/GM-only OOC context; never shown to players |
| `category` | CharField | One of `NarrativeCategory` values |
| `sender_account` | FK to `accounts.AccountDB`, nullable | Null = automated/system-sourced |
| `related_story` | FK to `stories.Story`, nullable | Optional context for stories-emitted messages |
| `related_beat_completion` | FK to `stories.BeatCompletion`, nullable | Populated when this message informs of a beat completion |
| `related_episode_resolution` | FK to `stories.EpisodeResolution`, nullable | Populated when this message informs of an episode resolution |
| `sent_at` | DateTimeField | `auto_now_add` |

### NarrativeMessageDelivery

Per-recipient delivery state. Unique per `(message, recipient_character_sheet)`.

| Field | Type | Notes |
|-------|------|-------|
| `message` | FK to `NarrativeMessage` | Cascade delete |
| `recipient_character_sheet` | FK to `character_sheets.CharacterSheet` | Cascade delete |
| `delivered_at` | DateTimeField, nullable | Set when the message was pushed to the recipient's puppeted session; null until delivered |
| `acknowledged_at` | DateTimeField, nullable | Set when the player acknowledges the message via the API |

---

## Service Functions

### `send_narrative_message`

```python
def send_narrative_message(
    *,
    recipients: Iterable[CharacterSheet],
    body: str,
    category: str,
    sender_account: AccountDB | None = None,
    ooc_note: str = "",
    related_story: Story | None = None,
    related_beat_completion: BeatCompletion | None = None,
    related_episode_resolution: EpisodeResolution | None = None,
) -> NarrativeMessage
```

Creates a `NarrativeMessage` and one `NarrativeMessageDelivery` per recipient in a single transaction. After commit, real-time pushes the message to each recipient's puppeted session (if online) via `character.msg()` with the `|R[NARRATIVE]|n` color tag and `type="narrative"`. Offline recipients' delivery rows stay queued (`delivered_at=None`) until the next login triggers `deliver_queued_messages`.

One message can fan out to many recipients (GM sends covenant message to 5 of 8 members → one message, five delivery rows).

### `deliver_queued_messages`

```python
def deliver_queued_messages(character_sheet: CharacterSheet) -> int
```

Pushes all unread queued deliveries for a character and marks them `delivered_at=now`. Called from `Character.at_post_puppet` via `stories.services.login.catch_up_character_stories`. Returns the count of deliveries attempted.

---

## API Endpoints

### `GET /api/narrative/my-messages/`

Paginated list of the requesting account's character's deliveries, ordered by `-message__sent_at`.

Supports query params (via `NarrativeMessageDeliveryFilter`):
- `category` — filter by message category (one of `NarrativeCategory` values)
- `related_story` — filter by related story pk
- `acknowledged` — boolean; true to show only acknowledged deliveries, false for unacknowledged

Player payload excludes `ooc_note`. Staff/GM-facing rendering should use `NarrativeMessageWithOOCSerializer` in custom views.

### `POST /api/narrative/deliveries/{pk}/acknowledge/`

Marks a delivery `acknowledged_at=now` (idempotent — calling twice leaves the first timestamp unchanged).

Permission: recipient (via `IsDeliveryRecipientOrStaff`) or staff. Non-recipient accounts receive 403/404.

---

## Integration with Stories

The stories system emits narrative messages automatically at two points:

1. **BeatCompletion** — after `_evaluate_and_record_beat` (auto flip), `record_gm_marked_outcome`, or `record_aggregate_contribution` creates a BeatCompletion row, `stories.services.narrative.notify_beat_completion` fans out a `NarrativeMessage` with `category=STORY`, `related_beat_completion` populated, and `body=beat.player_resolution_text` (fallback to a minimal default).

2. **EpisodeResolution** — after `resolve_episode` commits an EpisodeResolution, `notify_episode_resolution` fans out a `NarrativeMessage` with `related_episode_resolution` populated and `body=transition.connection_summary` (fallback to `episode.summary`, then a minimal default).

Recipients resolve by story scope:
- CHARACTER → the story's owning `character_sheet`
- GROUP → active `GMTableMembership` personas' `character_sheet` values (`left_at__isnull=True`)
- GLOBAL → active `StoryParticipation` members' sheets

---

## Frontend Roadmap (Phase 4)

The React frontend will surface narrative messages in two places:

- **Inline main-text stream** — messages get a distinct `|R` (light red) color tag so the webclient can style them apart from normal scene messages
- **Messages section of character sheet** — paginated, filterable, searchable; unread counter from `acknowledged_at=null` rows

Both are frontend concerns; the backend exposes `/api/narrative/my-messages/` and `/api/narrative/deliveries/{id}/acknowledge/` as the minimum needed to drive them.
