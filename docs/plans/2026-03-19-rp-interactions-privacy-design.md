# RP Interactions, Privacy & Scene Recording Design

**Date:** 2026-03-19
**Status:** Design
**Depends on:** Scenes (existing), Relationships (existing), Roster (existing)

## Problem Statement

Arx II needs a system where RP interactions are automatically recorded so players can
reference them for relationship updates, without making players feel surveilled or requiring
explicit scene creation for organic grid RP. The system must handle three levels of privacy
while keeping the common case (just posing in a room) completely frictionless.

### Core Tension

- **Must record:** Interactions need to exist as referenceable records so relationship updates
  aren't purely honor-system
- **Must not feel recorded:** Players doing organic grid RP shouldn't think about logging, and
  intimate RP must never feel surveilled

### Design Philosophy

This is a **memory system**, not an audit trail. The primary purpose is letting players curate
their character's story — bookmarking meaningful moments, building a living history of
relationships. Staff validation is a side effect, not the goal.

## Key Concepts

### Interaction vs Scene

These are fundamentally different things:

- **Interaction** — An atomic RP action: one writer, one piece of content, one audience. Always
  created when someone poses, emits, says, whispers, shouts, or takes a mechanical action.
  Lightweight. The universal building block.
- **Scene** — An explicit container a player or GM starts. While active, it captures interactions
  in that location. Has structure, name, description, privacy mode. Manually started and ended.

**Why not auto-create scenes?** Consider a busy market room where hundreds of characters come
and go throughout the day. An auto-scene would never end, and a player trying to reference a
brief funny exchange would have to dig through thousands of irrelevant interactions. Scenes are
organizational tools; interactions are the atomic records.

### Conversational Threads

Threads are **emergent, not structural**. They form from target patterns in the interaction
stream:

- Character A poses targeting Character B → Character B replies targeting Character A → thread
- Untargeted poses stay in the main flow
- A targeted pose that's public is in the main flow AND groupable as a thread
- The frontend derives threads from target chains — no thread entity in the database

Threads are a UI/filtering concern: collapsible, expandable, ignorable. In a room with 30
people talking, players can follow just the threads they care about and filter out the rest.

## Data Models

### New: Interaction

The atomic RP record. Replaces the current approach of only logging to SceneMessage when a
scene is active.

```
Interaction
├── character: FK ObjectDB           — IC identity who wrote it
├── roster_entry: FK RosterEntry     — specific player (privacy binds here, not character)
├── persona: FK Persona (nullable)   — disguise/alt identity if active
├── location: FK ObjectDB            — where it happened
├── scene: FK Scene (nullable)       — scene container if one was active
├── target_personas: M2M Persona     — explicit IC targets (thread derivation)
├── content: TextField               — the actual written text
├── mode: TextChoices                — pose / emit / say / whisper / shout / action
├── visibility: TextChoices          — default / very_private
├── timestamp: DateTimeField
└── sequence_number: PositiveIntegerField
```

### New: InteractionAudience (through model)

Captures exactly who could see an interaction at creation time. This is the visibility ceiling —
it can only shrink, never expand.

```
InteractionAudience
├── interaction: FK Interaction
├── roster_entry: FK RosterEntry     — the specific player who saw it
└── persona: FK Persona              — the IC identity they were presenting as
```

**All player-facing surfaces use Persona, never Account or RosterEntry.** RosterEntry is an
internal field for permission checks. Players only ever see persona identities.

### New: InteractionFavorite

Private bookmark for cherished moments.

```
InteractionFavorite
├── interaction: FK Interaction
├── roster_entry: FK RosterEntry     — the player who bookmarked it
└── created_at: DateTimeField
```

Favorites are **purely private** — no other player sees what you bookmarked. Social feedback
(kudos, pose voting, reactions) is handled by separate systems.

### Modified: Scene

Add privacy mode to existing Scene model:

```
Scene (existing, modified)
├── ... existing fields ...
├── privacy_mode: TextChoices        — public / private / ephemeral (NEW)
├── summary: TextField (nullable)    — required for ephemeral, optional for others (NEW)
└── summary_status: TextChoices      — draft / pending_review / agreed (NEW)
```

Remove `is_public` (replaced by `privacy_mode`).

### New: SceneSummaryRevision

Collaborative summary editing for ephemeral scenes. All author references use Persona, never
Account — a player editing a summary sees "Revised by The Masked Baron", not "Revised by
steve_2847".

```
SceneSummaryRevision
├── scene: FK Scene
├── persona: FK Persona              — who submitted this revision (IC identity)
├── content: TextField               — the summary text
├── action: TextChoices              — submit / edit / agree
└── timestamp: DateTimeField
```

### Modified: RelationshipUpdate

The weekly relationship update adopts a "one update per week per relationship" structure,
referencing RP instead of being a standalone writeup. This replaces the current unlimited
updates + 7/week development split.

The `linked_scene` FK already exists. Add:

```
RelationshipUpdate (existing, modified)
├── ... existing fields ...
├── linked_interaction: FK Interaction (nullable, NEW)
│   — specific interaction that prompted this update
├── reference_mode: TextChoices (NEW)
│   — all_weekly / specific_interaction / specific_scene
└── feeling: FK RelationshipTrack (NEW, or reuse existing track field)
    — the emotional direction of this update
```

**Reference modes:**
- `all_weekly` — default. "We interacted this week." System confirms interactions exist between
  the characters.
- `specific_interaction` — player highlights a particular interaction and writes about why it
  mattered
- `specific_scene` — player references an entire scene

The player writes about how the interaction mattered and what changed. The reference is context
for their story, not proof for an audit.

**Browsable history:** Relationship updates and favorited interactions form a browsable
character history — a timeline of meaningful moments and how the character felt about them.

## Privacy Architecture

### Player-Facing Model: Four Tiers

Players think about privacy in four intuitive levels:

| Tier | What players understand | Who can see it |
|---|---|---|
| **Public** | "Open RP anyone can read" | Anyone in the game |
| **Private** | "Only people who were there" | Audience members + staff |
| **Very Private** | "Just us, nobody else ever" | Original roster entries only. Not staff, not future players |
| **Ephemeral** | "Never saved at all" | Nobody after the moment passes |

### Data Model: Two Fields

Internally, the four-tier player model maps to two fields:

- **Scene `privacy_mode`** (public / private / ephemeral) — sets the floor for all interactions
  within the scene. Interactions without a scene default based on audience scope.
- **Interaction `visibility`** (default / very_private) — per-interaction override that can
  only escalate privacy, never reduce it.

The public vs private distinction comes from the scene's `privacy_mode` and the audience scope,
not from the interaction itself. A "default" visibility interaction in a public scene is public;
the same in a private scene is private. This keeps the data model simple while the UX presents
the four-tier mental model players expect.

### Tier Details

**1. Public** — Content saved, globally viewable.
- Interactions in public scenes with room-wide audience
- This is the default for open tavern RP, market squares, public events
- The vast majority of all interactions

**2. Private** — Content saved, audience-scoped + staff.
- Interactions in private scenes → visible to scene participants + staff
- Whispers → only the audience members who received them
- Tabletalk → only the table participants
- Staff can see for GM purposes

**3. Very Private** — Content saved but locked to original roster entries in the audience
at time of creation.
- Not visible to staff
- Not visible to future players of the same characters (new roster entries)
- Any audience member can escalate an interaction or thread to very_private
- One person marking it applies to the whole exchange — hiding one side while exposing the
  other doesn't protect privacy
- Staff can see aggregate metadata (counts, timestamps, locations) but never content

**4. Ephemeral** — Content never stored. Declared at scene creation, cannot be changed after.
- Interactions are delivered in real-time but never written to the database
- No ledger metadata, no content, nothing persisted
- Only the Scene record exists: name, participants (as personas), and summary
- The summary goes through a collaborative edit/agree flow
- Any participant can close the scene at any time
- The scene is referenceable for relationship updates regardless of summary status
- Impossible to recover content by design — this is the trust guarantee

### Visibility Rules

Visibility follows a simple cascade and **never expands beyond the original audience**:

1. Ephemeral scene → no interactions stored at all
2. Very private → only original roster entries in audience at creation time. Not staff.
3. Private scene → scene participants + staff
4. Default → audience-scoped:
   - Room-wide pose in public scene → globally viewable
   - Room-wide pose in private scene → scene participants + staff
   - Whisper → audience only
   - Tabletalk → table participants only

Scene `privacy_mode` sets the floor — interactions inside can be escalated more private, never
less. You cannot downgrade a private scene to public without all participants agreeing, since
that would expand visibility.

### Deletion

Three-tier deletion model, designed to normalize rewriting as part of the RP flow:

- **Immediate** (within minutes) — no questions asked, just gone. Handles wrong audience,
  typos, misclicks. Completely normal, not shameful.
- **Recent** (within 30 days) — still allowed, confirmation prompt. Handles "the RP took a
  turn I'm not comfortable having recorded."
- **After 30 days** — locked. Can still mark very_private but cannot delete. Prevents
  retroactive history erasure that could affect others' relationship records.

Deletion is **hard delete** — no soft delete, no tombstone. If a deleted interaction was
referenced by a relationship update, the reference becomes "deleted interaction" — the
relationship update itself still stands.

### Staff Access Summary

| Visibility | Staff can see content? | Staff can see metadata? |
|---|---|---|
| Default (public) | Yes | Yes |
| Default (audience-scoped) | Yes | Yes |
| Private scene | Yes | Yes |
| Very private | No | Aggregate only (counts, timestamps, location) |
| Ephemeral scene | No (never stored) | Scene record + summary only |

## Scene Lifecycle

### Creating a Scene

Any player can start a scene in their current location:
- Set name, optional description, privacy mode (public / private / ephemeral)
- Ephemeral is a one-time choice at creation — cannot be changed after
- Public ↔ private can be toggled while active (upgrading to private is fine; downgrading to
  public requires all participants to agree)

### During a Scene

- New interactions in that location automatically get the `scene` FK
- For ephemeral scenes, interactions are delivered to players in real-time but never written to
  the database
- Players join/leave freely
- Public/private scenes show their name to the room
- Ephemeral scenes show "Ephemeral scene in progress" with participants listed by persona

### Closing a Scene

- Any participant can close it at any time
- Public/private scenes: marked inactive, interactions remain per visibility rules
- Ephemeral scenes: closing triggers the summary flow

### Ephemeral Summary Flow

1. The player who closes writes an initial summary
2. Other participants are notified and can: **agree**, **submit an edit**, or **ignore**
3. Edits trigger another round — participants see the revision and can agree/edit
4. No hard deadline — summary can stay in "pending" indefinitely
5. Scene is referenceable for relationship updates regardless of summary status
6. All revisions display **persona** names, never accounts
7. If players can't agree, relationship updates referencing the scene still work — the
   summary is a courtesy, not a gate

## Scale Considerations

### Interaction Volume

Thousands of players generating hundreds of interactions per day = tens of millions of rows
within months. This will be one of the largest tables in the database.

### PostgreSQL Table Partitioning

Partition `Interaction` by date range (monthly or quarterly) using Postgres native declarative
partitioning:

- Keeps queries fast (most queries are recent data — "my interactions this week")
- Makes old data easy to archive or move to cold storage
- No application-level sharding needed
- Partition pruning means queries with timestamp filters only scan relevant partitions
- Compatible with Django via `django-postgres-extra` or raw partition DDL in migrations

### InteractionAudience Partitioning

The audience through table will be even larger (each interaction × number of audience members).
Partition in tandem with Interaction by the same date ranges, using the interaction's timestamp.

### Indexing Strategy

- `(character, timestamp)` — "my recent interactions"
- `(location, timestamp)` — "what happened in this room"
- `(scene, sequence_number)` — scene message ordering
- `(roster_entry, timestamp)` on InteractionAudience — "interactions I witnessed"
- Partial index on `visibility = 'very_private'` for efficient privacy filtering

## Relationship Integration

### Weekly Update Structure

The relationship update system adopts a once-per-week cadence per relationship:

1. Player navigates to a relationship and starts a weekly update
2. System shows reference options:
   - **All interactions this week** (default) — confirmed by the interaction ledger
   - **A specific interaction** — browsable list filtered to interactions with this character
   - **A specific scene** — scenes involving both characters
3. Favorited interactions surface first in the browse list
4. Player selects a feeling/track direction and writes about how it mattered
5. System awards points based on the update (exact formula TBD, preserving existing
   temporary + capacity mechanics)

### Browsable History

Each relationship has a timeline view combining:
- Relationship updates (the weekly writeups with references)
- Favorited interactions between the two characters
- Scenes they shared

This is the "living history" — why these characters feel the way they do.

## Migration from Existing Models

### SceneMessage → Interaction

The existing `SceneMessage` model captures messages within scenes. The new `Interaction` model
is broader — it captures all RP regardless of whether a scene is active.

**Migration strategy:**
- Introduce `Interaction` as the new universal record
- `SceneMessage` becomes a lightweight view or is deprecated — interactions with a non-null
  `scene` FK serve the same purpose
- Existing SceneMessage data can be migrated to Interaction records
- The `message_location()` flow service function creates Interactions instead of (or in
  addition to) SceneMessages
- Scene detail views query Interactions filtered by scene FK

### RelationshipUpdate Changes

- Add `linked_interaction` FK and `reference_mode` field
- Existing `linked_scene` FK remains
- Weekly cadence enforced at the service layer (one update per relationship per cron week)
- Existing unlimited updates can be grandfathered or the old data isn't a concern since there's
  no production data

## Constants

### InteractionMode

```python
class InteractionMode(TextChoices):
    POSE = "pose", "Pose"
    EMIT = "emit", "Emit"
    SAY = "say", "Say"
    WHISPER = "whisper", "Whisper"
    SHOUT = "shout", "Shout"
    ACTION = "action", "Action"  # mechanical actions: checks, spells, etc.
```

No OOC mode — interactions are purely IC records.

### InteractionVisibility

```python
class InteractionVisibility(TextChoices):
    DEFAULT = "default", "Default"
    VERY_PRIVATE = "very_private", "Very Private"
```

### ScenePrivacyMode

```python
class ScenePrivacyMode(TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
    EPHEMERAL = "ephemeral", "Ephemeral"
```

### SummaryAction

```python
class SummaryAction(TextChoices):
    SUBMIT = "submit", "Submit"
    EDIT = "edit", "Edit"
    AGREE = "agree", "Agree"
```

### ReferenceMode

```python
class ReferenceMode(TextChoices):
    ALL_WEEKLY = "all_weekly", "All Interactions This Week"
    SPECIFIC_INTERACTION = "specific_interaction", "Specific Interaction"
    SPECIFIC_SCENE = "specific_scene", "Specific Scene"
```

## What This Design Does NOT Cover

These are related but separate concerns to be designed later:

- **Smart input composer** — MMO-style mode selector UX for the frontend
- **Check integration** — embedding mechanical checks into the interaction flow
- **Social check consent flow** — target player setting difficulty for social checks
- **Pose reactions / kudos** — social feedback on interactions (separate system)
- **Aura farming** — resonance feeding from scene perception (depends on magic integration)
- **Rich text editor** — replacing plain text input with modern compose experience
- **Scene scheduling** — finding and joining active scenes

## Open Questions

1. **Interaction partitioning granularity** — Monthly vs quarterly partitions? Depends on
   expected volume at launch. Monthly is safer for a game expecting thousands of players.
2. **Exact weekly update point formula** — How does the reference mode affect points earned?
   Does highlighting a specific meaningful interaction earn more than "we interacted"?
3. **Very private aggregate visibility** — Staff sees counts/timestamps/locations. Should this
   be an explicit admin view, or just available in standard queries?
4. **Ephemeral scene real-time delivery** — Technical approach for delivering interactions that
   are never persisted. WebSocket messages that bypass the ORM entirely? Needs implementation
   design.
5. **Interaction mode extensibility** — As more mechanical actions are added (spells, crafting,
   combat), do they all fall under `ACTION` mode, or do we add specific modes? Probably stay
   with `ACTION` and use supplemental data for specifics.
