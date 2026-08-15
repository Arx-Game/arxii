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

```python
from world.narrative.constants import GemitReach

# TextChoices — how wide a gemit broadcasts (#1450):
GemitReach.GAME_WIDE      # every online session (the classic gemit)
GemitReach.SPECIFIED      # members of any mix of the linked societies and/or organizations
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

### Gemit (#1450)

A staff/GM real-time broadcast, persisted for retroactive (reach-scoped) viewing. Does **not** fan out into `NarrativeMessageDelivery` rows — gemit is broadcast, not per-recipient. The body is **hand-authored verbatim** (colour codes and all); nothing is generated.

| Field | Type | Notes |
|-------|------|-------|
| `body` | TextField | Verbatim broadcast text |
| `reach` | CharField (`GemitReach`) | Audience scope; default `GAME_WIDE` |
| `reach_societies` | M2M to `societies.Society` | Targets when `reach=SPECIFIED` (combinable with orgs) |
| `reach_organizations` | M2M to `societies.Organization` | Targets when `reach=SPECIFIED` (combinable with societies) |
| `sender_account` | FK to `accounts.AccountDB`, nullable | Null = system-generated |
| `related_era` / `related_story` | FK, nullable | Optional context links |
| `sent_at` | DateTimeField | `auto_now_add` |

### AmbientEmit (#2988)

A periodic room-linger flavor line — plain roaming atmosphere or a room-state risk telegraph,
distinguished only by whether `gate_stat_key` is set (one model, no second mechanism). Sibling
of `AmbientEmoteLine` (entry-triggered) but fires while occupants *remain* in a room, driven by
`world.narrative.ambient_texture.roll_and_echo_ambient_texture` on the `game_clock` scheduler.
See "Ambient Room Texture" below for the full mechanism.

| Field | Type | Notes |
|-------|------|-------|
| `key` | CharField, nullable, unique | Stable identity (`<pool-slug>-<nnn>`), #2980 convention |
| `text` | TextField | The line shown. PLACEHOLDER pending the content pass |
| `weight` | PositiveIntegerField | Weighted-random selection within its scope pool |
| `cooldown_minutes` | PositiveIntegerField | Per-row re-fire throttle |
| `last_fired_at` | DateTimeField, nullable | Runtime only — never exported |
| `area` / `room_profile` | FK, nullable | Plain nullable scope (not a `DiscriminatorMixin` pair) — neither set = generic pool |
| `gate_stat_key` | CharField (`StatKey`), blank | The `world.locations` axis this row telegraphs; blank = ungated |
| `gate_min` / `gate_max` | SmallIntegerField, nullable | Single-axis threshold band |
| `in_spring`…`in_winter`, `at_dawn`…`at_night` | BooleanField | Season/phase gates, `WeatherEmit`'s exact shape |

Inherits `NaturalKeyMixin` + `CreditedContent` + `SharedMemoryModel` (mirrors `WeatherEmit`).

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

### `broadcast_gemit` (#1450)

```python
def broadcast_gemit(
    *,
    body: str,
    sender_account: AccountDB,
    reach: str = GemitReach.GAME_WIDE,
    societies: Iterable[Society] | None = None,
    organizations: Iterable[Organization] | None = None,
    related_era: Era | None = None,
    related_story: Story | None = None,
) -> Gemit
```

Creates a `Gemit`, records its reach + targets, and pushes the green `|G[GEMIT]|n` broadcast. `GAME_WIDE` reaches every connected session; `SPECIFIED` reaches only sessions whose **active persona** is a member of any target society **or** organization (the two combine freely — one gemit can target a House and a Society together), resolved once via `OrganizationMembership`, then matched per session — a TEMPORARY mask holds no membership, so the disguised fall out of scope by design. Push failures are swallowed so a broadcast error never rolls back the record. Faces: telnet `gemit` (`CmdGemit`, staff `perm(Admin)`) and web `POST /api/narrative/gemits/`; the gemit history list (`GemitViewSet`) is reach-scoped so a scoped gemit never leaks to non-members (staff see all).

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

## Frontend (shipped)

The React surface lives in `frontend/src/narrative/`: `MessagesSection.tsx` +
`MessageRow.tsx` (paginated message list off `/api/narrative/my-messages/`),
`UnreadNarrativeBadge.tsx` (unread counter from `acknowledged_at=null` rows),
`SendGemitDialog.tsx`, and per-category muting via `CategoryMuteToggles.tsx` /
`MuteSettingsPage.tsx`. Acknowledge goes through
`/api/narrative/deliveries/{id}/acknowledge/`.

---

## Ambient Room Texture (#2988)

Two design-tenet promises off one substrate: roaming flavor for streets/markets/taverns
(silent between poses, previously) and a room-state risk telegraph off the same
`world.locations` crime/order stats — both are `AmbientEmit` rows, distinguished only by
whether `gate_stat_key` is set. **Text only** — no NPC/encounter spawning (that's #2378's job,
consuming the same telegraphed state).

**Selection** (`world.narrative.ambient_texture.select_ambient_emit(room, *, season=None,
phase=None, now=None)`): resolves the room's most-specific **non-empty scope pool** — a
room-scoped row set shadows an area-scoped set, which shadows the generic (scope-free) pool,
mirroring the `world.locations` cascade's most-specific-wins convention without reusing its
walk (this is pool selection, not a stat/resonance axis). Within the chosen pool: filters to
rows flagged for the current IC season *and* phase, excludes rows still in
`cooldown_minutes`, excludes rows whose `gate_stat_key` doesn't clear against
`world.locations.services.effective_value(room, stat_key=...)`, then weighted-random picks
(`world.checks.outcome_utils.select_weighted`, the same helper `deliver_ambient_group` uses).

**Driver** (`roll_and_echo_ambient_texture`, registered on the `game_clock` scheduler exactly
like `roll_and_echo_weather`): checked every tick, no-ops unless the IC time-of-day phase
transitioned since the task's last stamped run (shared guard,
`game_clock.task_registry.phase_transitioned_since_last_run` — extracted #2988 so weather and
ambient texture share the exact guard shape against their own task keys). On fire: derives the
candidate room set from **currently-connected sessions' locations** (`evennia.SESSION_HANDLER`,
deduped to distinct rooms) — never a grid-wide room scan, so per-tick cost is bounded by
online-player count, not map size. For each such room, selects and delivers one `AmbientEmit`
via `send_narrative_message` (durable, squelchable — never `message_location`, which is
ephemeral actor-driven scene text) under `NarrativeCategory.ATMOSPHERE`, the same category
`AmbientEmoteLine` delivers under. Frequency variance between a sleepy alley and a bustling
market is authored per-row via `weight` + `cooldown_minutes`, not a second cron interval.

**Risk telegraph is just a gated row.** An author writes "the crowd here thins fast when
trouble starts" with `gate_stat_key=CRIME, gate_min=60` — no separate mechanism, model, or
delivery path.

**Content round-trip splits by scope** (mirrors `AmbientEmoteLine`/`WeatherEmit` exactly):
room/area-scoped rows ride the grid-import bundle (tied to concrete grid rooms); scope-free
gated-pool rows ride `content_export.py`'s natural-key round trip
(`CONTENT_MODELS` entry `narrative.ambientemit`, row-filtered via `EXPORT_FILTERS` to
`area`/`room_profile` both null). **Grid-import wiring for scoped rows is not yet built** — an
`AmbientEmit` with a room/area scope today is admin-authored only; the bundle-side install step
(mirroring `_install_ambient_triggers`'s sibling pass) is a follow-up, not a structural gap in
the model.

---

## Player Tales (#2047)

A mission run's mechanical outcome is the player's to narrate. Every participant
of a resolved, completed, or abandoned run can write a **tale** — free-text
prose describing what their character did — via `mission tale <id> <text>`
(telnet) or `POST /api/missions/journal/{id}/tale/` (web). The policy is
**permissive canonicity**:

- **Canon by default.** A player's narration of a mechanical success is
  canon unless it contradicts what the dice/mechanics established.
- **Braggadocio rule.** Elaborations exceeding the character's demonstrated
  capability are *non-canonical fabrications* — in-world braggadocio — not
  moderation cases. The character told a taller tale than the truth; the
  world reacts accordingly.
- **Never parsed for mechanics.** Tales are never read by the engine for
  mechanical effects. They are narrative flavor only (see the
  `docs/roadmap/missions.md` invariant).
- **Staff never pre-approve.** There is no content gate, no review queue.
  The policy IS the mechanism — the same precedent as `save_deed_story`.

On a legend-minting run, saving a tale seeds the author's `LegendDeedStory`
for any unstoried `LegendEntry` linked to the run's deeds (seed, never
overwrite). See ADR-0105 for the rationale and the rejected staff-curation
alternative.
