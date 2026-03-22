# Persona Simplification Design

**Date:** 2026-03-22
**Status:** Design
**Supersedes:** Identity hierarchy sections of 2026-03-20 and 2026-03-21 design docs
**Depends on:** CharacterIdentity (built), Interaction system (built)

## Problem Statement

The current identity system has three overlapping models — CharacterIdentity, Guise, and
Persona — that are near-synonyms in English. This will confuse future contributors and
AI agents. The concepts need to be collapsed into fewer, more distinct models.

## What Changed

### Before (3 models + state manager)

- **CharacterIdentity** — "who is this character really?" + state pointers
- **Guise** — persistent identity (reputation, relationships, legend)
- **Persona** — point-in-time appearance of a guise (possibly disguised)

### After (2 models + state pointer)

- **CharacterIdentity** — "who is this character really?" Anchors knowledge, aggregates
  legend. Unchanged.
- **Persona** — any face the character shows the world. Replaces BOTH Guise and old Persona.

Guise is removed as a separate model. Its fields and purpose are absorbed into Persona.

## The New Persona Model

A Persona is any named face a character presents to the world. It can be:

- **Primary** (`is_primary=True`) — the character's "real" name. Always exists. Accumulates
  reputation, relationships, legend. When someone meets "Ariel," they're meeting the
  primary persona.
- **Established** (`is_established=True`) — a persistent alternate identity. Also accumulates
  reputation, relationships, legend independently. "Shadow the Thief" is an established
  persona that the world treats as a separate person.
- **Temporary** (`is_established=False, is_primary=False`) — a throwaway disguise. "Masked
  Figure" at a ball. No relationships, no reputation. Could be promoted to established
  if used repeatedly.

```
Persona (replaces both Guise and old Persona)
├── character_identity: FK CharacterIdentity (non-nullable — who this persona belongs to)
├── name: CharField
├── colored_name: CharField (blank)
├── description: TextField (blank)
├── thumbnail: FK PlayerMedia (nullable)
├── is_primary: BooleanField (default=False)
├── is_established: BooleanField (default=False)
├── participation: FK SceneParticipation (nullable — scene-scoped if set)
├── created_at: DateTimeField
├── updated_at: DateTimeField
```

### Key Relationships

- **Relationships** attach to established or primary personas (not temporary)
- **Reputation/Legend** attach to established or primary personas
- **Organization memberships** attach to established or primary personas
- **Interactions** reference whichever persona was active at the time
- **CharacterIdentity.active_persona** points to the currently active one

### Constraints

```python
# Only one primary persona per character identity
UniqueConstraint(
    fields=["character_identity"],
    condition=Q(is_primary=True),
    name="unique_primary_persona",
)
# Primary is always established
CheckConstraint(
    check=~Q(is_primary=True, is_established=False),
    name="primary_must_be_established",
)
```

## Simplified CharacterIdentity

With Guise removed, CharacterIdentity simplifies to:

```
CharacterIdentity
├── character: OneToOneField ObjectDB
├── active_persona: FK Persona (non-nullable — who they're presenting as right now)
```

One FK instead of three. `primary_guise` and `active_guise` are gone — the primary persona
is just `Persona.objects.get(character_identity=X, is_primary=True)`, and the active one is
`active_persona`.

## PersonaDiscovery

Tracks when a character discovers that two personas are the same person. Stores only the
raw discovery data — a service function handles all resolution logic (what name to display,
whether they've pierced a disguise, transitive knowledge chains).

```
PersonaDiscovery
├── persona_a: FK Persona
├── persona_b: FK Persona
├── discovered_by: FK CharacterSheet (the character who figured it out)
├── discovered_at: DateTimeField
```

### How Discovery Works

The discovery data is minimal pairs. A service function `resolve_persona_display()` handles
all the logic:

1. Prefetch the viewer's PersonaDiscovery records once per request
2. For each persona in a scene/interaction feed, check if the viewer has any discovery
   linking it to another persona
3. If discovered: show the most "real" identity they know about (primary > established >
   the linked persona)
4. If not: show the persona's name as-is

The handler can be as simple or complex as needed without changing the data model. If the
logic evolves (partial discoveries, degrees of certainty), only the handler changes.

### Discovery Examples

Character X's discovery records:
- `(Masked Figure, Shadow)` — X knows Masked Figure is Shadow
- No record linking Shadow to Ariel — X doesn't know the main identity

What X sees in a scene log:
- Ariel poses → "Ariel" (primary persona, no disguise)
- Shadow poses → "Shadow" (established persona, X doesn't know it's Ariel)
- Masked Figure poses → "Shadow (as Masked Figure)" (X discovered the link)

Later, X discovers `(Shadow, Ariel)`:
- Now X sees Masked Figure → "Ariel (as Masked Figure)" (transitive: Masked Figure = Shadow = Ariel)
- The handler computes transitivity from the prefetched pairs

### Performance

- Discovery records are per-character, per-pair. A character with 100 known discoveries
  has 100 records — trivially small.
- Prefetch once per request, O(1) lookup per persona in the feed.
- New discoveries are rare (gameplay events), so write-time cost is irrelevant.
- No recursive CTEs needed — the handler computes transitive chains in Python from the
  prefetched set.

## Migration Path

### Models to Create
- New Persona (absorbs Guise fields + old Persona fields)
- PersonaDiscovery

### Models to Remove
- Guise (replaced by Persona)
- Old Persona (replaced by new Persona)
- PersonaIdentification (replaced by PersonaDiscovery)

### FK Updates Required

Everything that currently points to Guise needs to point to Persona:
- `OrganizationMembership.guise` → `.persona`
- `SocietyReputation.guise` → `.persona`
- `OrganizationReputation.guise` → `.persona`
- `LegendEntry.guise` → `.persona`
- `LegendSpread.spreader_guise` → `.spreader_persona`
- `LegendDeedStory.author` (guise FK) → `.author` (persona FK)
- `InteractionAudience.guise` → `.persona`
- `CharacterIdentity.primary_guise`, `active_guise` → removed, just `active_persona`

Everything that currently points to old Persona stays pointing to new Persona:
- `Interaction.persona` — unchanged
- `InteractionTargetPersona.persona` — unchanged
- `SceneMessage.persona` — unchanged (legacy, pending deprecation)
- `SceneSummaryRevision.persona` — unchanged

### CharacterIdentity Simplification
- Remove `primary_guise` FK
- Remove `active_guise` FK
- Keep `active_persona` FK (points to new Persona)

### Data Handler Updates
- `CharacterItemDataHandler` methods that reference Guise → reference Persona
- `get_default_guise()` → `get_primary_persona()` or similar
- `_get_guises()` → `_get_personas()`

## What This Design Does NOT Cover

- **Discovery gameplay mechanics** — what checks/skills reveal personas. Just the data model.
- **Guise switching UX** — frontend for changing active persona.
- **Persona promotion** — workflow for promoting a temporary persona to established.
- **Transitive display logic** — the exact implementation of the handler that computes
  what name to show. Just the interface contract.

## Open Questions

1. **Should `is_primary` and `is_established` be a single TextChoices field?** e.g.,
   `persona_type: PRIMARY / ESTABLISHED / TEMPORARY`. Avoids the "primary must be
   established" constraint issue. Cleaner semantics.
2. **Scene-scoped personas** — do temporary personas still need the `participation` FK?
   If a Masked Figure appears in multiple scenes, is it the same persona or a new one
   per scene? Probably the same (reusable), which means `participation` might not be
   needed at all on the new Persona.
3. **CharacterItemDataHandler** — should it reference CharacterIdentity instead of
   querying Guise/Persona directly? CharacterIdentity could become the single entry
   point for all identity queries.
