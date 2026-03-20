# Identity Hierarchy & Persona Refactor Design

**Date:** 2026-03-20
**Status:** Design
**Depends on:** Scenes (existing), Character Sheets (existing), Interactions (in progress)
**Blocks:** Interaction model finalization, relationship referencing

## Problem Statement

The Persona model is currently scoped to scenes (requires a SceneParticipation FK). This
prevents it from being used as the universal IC identity layer for interactions, journals,
reputation, and other systems that need to track "how a character appeared at this moment."

Additionally, the Interaction model carries redundant identity fields (roster_entry, character)
when a single persona reference could derive everything needed.

## Identity Hierarchy

The identity system has four layers, from OOC to IC:

### RosterEntry (OOC)

The specific player controlling a character. Privacy binds here — "very private" interactions
are locked to the roster entries who witnessed them, not future players of the same character.
Derivable from any layer below via `guise.character.roster_entry`.

### Character (ObjectDB / CharacterSheet)

The game entity. Container for all identities. Has stats, inventory, location. A character
has one or more guises. Currently represented by ObjectDB with CharacterSheet as a OneToOne
wrapper for demographics and stats.

**Known gap:** There is no dedicated "Character" model that serves as the primary identity
anchor. CharacterSheet, guises, and roster entries all point to ObjectDB directly. A future
refactor may introduce a proper Character model that everything hangs off of. For now,
CharacterSheet serves as the stand-in for "this ObjectDB is a player character."

### Guise (persistent identity)

A named identity that accumulates persistent game state: relationships, first impressions,
reputation, legend, organization memberships. Every character has at least one default guise
(just "them"). Characters with alter egos or secret identities have additional guises.

A guise always points to its character. Players form first impressions and relationship
updates with guises. When a player thinks "my character," they're thinking of their default
guise, even if they'd never use that word.

**Key property:** Can someone have an ongoing relationship with this identity? Yes — that's
what makes it a guise.

### Persona (point-in-time appearance)

How a guise appears at a specific moment. Always backed by a guise. The persona could be:

- **Identical to the guise** — the default case. "Ariel" appearing as "Ariel." No disguise,
  no modification. The persona's name matches the guise's name. This is the vast majority
  of all interactions.
- **Modified appearance** — same identity, different look. "Ariel with a new hairstyle" or
  "Ariel in formal attire." Still identifiable as Ariel.
- **Obscured identity** — a temporary disguise that hides the guise. "Hooded Dark Figure"
  or "Masked Stranger." Other characters cannot determine the guise from the persona until
  they identify it through gameplay.

**Key property:** A persona is how you see someone in the moment. You cannot form a
relationship with a persona — only with the guise underneath once identified.

### Summary Table

| Layer | Scope | Relationships? | Example |
|-------|-------|---------------|---------|
| RosterEntry | OOC player | N/A (privacy only) | "2nd player of Ariel" |
| Character | Game entity | N/A (container) | Ariel (the ObjectDB) |
| Guise | Persistent identity | Yes — impressions, updates, reputation, legend | "Ariel" (default), "The Masked Robber" (alter ego) |
| Persona | Point-in-time appearance | No — must identify guise first | "Ariel" (transparent), "Hooded Dark Figure" (obscured) |

### The Key Distinction

**Guises are for how the world sees you; characters are for what you know.**

- Reputation, legend, relationships → attach to guises
- Knowledge, identification, skills → belong to characters
- Privacy, deletion rights → bind to roster entries

## Model Changes

### Persona (modified)

Decouple from SceneParticipation so personas can exist outside of scenes.

```
Persona (modified)
├── participation: FK SceneParticipation (NULLABLE — was non-nullable)
├── guise: FK Guise (NEW, non-nullable — every persona is backed by a guise)
├── character: FK ObjectDB (kept — useful for direct queries)
├── name: CharField
├── is_fake_name: BooleanField (True = obscured identity, blocks relationship formation)
├── description: TextField
├── thumbnail_url: URLField
├── created_at: DateTimeField
```

When `is_fake_name` is True, the persona hides its guise from other characters until
identified through gameplay.

### PersonaIdentification (new)

Tracks which characters have identified an obscured persona's underlying guise. Knowledge
belongs to the character (the mind), not the guise (the face) — if Ariel figures out who
the Hooded Figure is while disguised as The Masked Robber, Ariel still knows when she's
just being Ariel.

```
PersonaIdentification (new)
├── persona: FK Persona          — the disguise that was identified
├── identified_by: FK CharacterSheet — the character who figured it out
├── identified_at: DateTimeField
```

Identification is per-character. Character A may have unmasked the Hooded Figure while
Character B hasn't. Scene logs check this to determine display.

### Interaction (simplified to 7 columns)

```
Interaction (final)
├── id: BigInt                   — PK (composite with timestamp for partitioning)
├── persona: FK Persona          — how the writer appeared (non-nullable)
├── scene: FK Scene              — scene container if active (nullable)
├── content: TextField           — the written text
├── mode: CharField(20)          — pose/emit/say/whisper/shout/action
├── visibility: CharField(20)    — default/very_private
├── timestamp: DateTimeField     — when (partition key)
```

**Removed fields:**
- `character` — redundant, derivable via `persona.guise.character`
- `roster_entry` — redundant, derivable via `persona.guise.character.roster_entry`
- `location` — derivable from `scene.location` for scene interactions; not needed for
  scene-less interactions (the interaction ledger tracks *that* it happened, not *where*)
- `sequence_number` — microsecond timestamp precision is sufficient for ordering;
  simultaneous poses are independent by definition in RP

**Derivation paths (no extra columns needed):**
- Character: `persona.guise.character`
- Roster entry: `persona.guise.character.roster_entry`
- Guise: `persona.guise`
- Location: `scene.location` (when scene is set)

### InteractionAudience (simplified)

```
InteractionAudience
├── interaction: FK Interaction (db_constraint=False for partitioned table)
├── timestamp: DateTimeField     — denormalized for composite FK
├── guise: FK Guise              — viewer's persistent identity
├── persona: FK Persona (nullable) — only if viewer was also disguised
```

Replaces `roster_entry` with `guise`. Privacy checks derive roster_entry through
`guise.character.roster_entry`.

### InteractionTargetPersona (simplified)

```
InteractionTargetPersona
├── interaction: FK Interaction (db_constraint=False)
├── timestamp: DateTimeField     — denormalized
├── persona: FK Persona          — whatever identity the writer could see
```

Single FK — the visible identity of the target, whether transparent or obscured.

### InteractionFavorite (unchanged except FK updates)

```
InteractionFavorite
├── interaction: FK Interaction (db_constraint=False)
├── timestamp: DateTimeField     — denormalized
├── roster_entry: FK RosterEntry — the player who bookmarked (OOC, stays as roster_entry)
```

Favorites are OOC bookmarks, so roster_entry is correct here — it's the player saving
a memory, not an IC action.

## Scene Log Display Logic

When rendering a scene log or interaction feed for a viewing character:

For each interaction, resolve the display name:

1. Get `interaction.persona`
2. If `persona.is_fake_name` is False → display `persona.name` (transparent, no disguise)
3. If `persona.is_fake_name` is True → check `PersonaIdentification` for this persona +
   viewing character:
   - **Not identified:** display `persona.name` ("Hooded Figure")
   - **Identified:** display `persona.guise.name` with annotation
     ("The Masked Robber (as Hooded Figure)")

This is a single query pattern: prefetch `PersonaIdentification` filtered by the viewing
character, then a simple lookup per interaction.

### Relationship Formation

The UI checks whether the target persona's guise is known to the viewing character:
- If `is_fake_name` is False → guise is known, first impression / relationship update allowed
- If `is_fake_name` is True and identified → guise is known, allowed
- If `is_fake_name` is True and not identified → blocked, must identify through gameplay first

## Persona Lifecycle

### Default Case (vast majority)

Character walks around as their default guise. A persona is auto-created (or reused) with
the guise's name and description. Zero player effort. The player never thinks about personas
or guises — they're just being their character.

### Alternate Identity

Character activates a non-default guise (e.g., their secret identity "The Masked Robber").
A persona is auto-created from that guise. Still zero effort — they just switch which
identity they're presenting as.

### Temporary Disguise (rare)

Character in a scene adds an extra layer on top of their guise — "Hooded Dark Figure" over
"The Masked Robber." Player explicitly creates a persona with `is_fake_name=True` and a
custom name/description. This is the only case requiring player input for persona creation.

## Performance

### Interaction Table (7 columns, partitioned by month)

Indexes on the partitioned table:
- BRIN on `timestamp` — tiny footprint, fast range scans, partition pruning
- `(persona_id, timestamp)` — "interactions by this identity"
- `(scene_id, timestamp)` — scene message ordering
- Partial on `visibility = 'very_private'` — fast exclusion for staff queries
- Partial on `scene_id IS NULL` — organic grid RP queries

### Privacy Check Cost

Privacy checks now go through `guise.character.roster_entry` instead of a direct
roster_entry FK. This adds one join, but:
- InteractionAudience records are always prefetched with `to_attr`
- Privacy checks are not in hot query paths (list filtering uses UNION subqueries)
- The trade-off is worth it: one fewer column on the biggest table in the database

## What This Design Does NOT Cover

- **Persona auto-creation mechanics** — how and when personas are created for default
  guise appearances (service function details)
- **Identification gameplay** — what checks, skills, or mechanics reveal a persona's guise
  (depends on the check system and capability system)
- **Guise switching UX** — how players switch between guises in the frontend
- **Smart input composer** — the chat input mode selector
- **Check integration** — embedding mechanical checks into interactions

## Open Questions

1. **Persona reuse vs creation** — When a character appears as their default guise in
   multiple interactions, is it one persona reused or a new one per interaction? Reuse
   is more efficient but means updating a persona's description updates all historical
   appearances. Probably reuse with snapshotting if descriptions change.
2. **Persona cleanup** — Do transparent personas (matching their guise) ever get cleaned
   up, or do they accumulate? At scale, this could be a lot of persona records. May want
   a cron to merge/deduplicate.
3. **Cross-scene identification** — If Character A identifies the Hooded Figure in Scene 1,
   and the same player uses "Hooded Figure" again in Scene 2, does the identification
   carry over? Probably yes if it's the same persona record, no if it's a new one.
4. **Character model extraction** — Future refactor to introduce a proper Character model
   that CharacterSheet, Guise, and RosterEntry all point to, instead of everything
   pointing to ObjectDB directly. This is needed beyond just interactions — codex entries,
   knowledge, and anything that represents "what a character knows" should persist through
   RosterEntry changes (new players of the same character inherit the character's knowledge).
   The Character model would be the anchor for: all guises, the character sheet, codex
   knowledge, persona identifications, and any other state that belongs to the character
   as a fictional entity rather than to the player controlling them.
