# Character Creation App

This app handles the staged character creation flow for Arx II.

## Overview

Character creation is a multi-stage process that guides players through creating a playable character. The flow is:

1. **Origin** - Select starting area (city), which gates heritage options
2. **Heritage** - Special heritage (Sleeper/Misbegotten) or normal → Species → Gender/Pronouns → Age
3. **Lineage** - Family selection (or "Unknown" for special heritage)
4. **Attributes** - Primary stat allocation
5. **Path & Skills** - Class/path selection and skill customization
6. **Traits** - Advantages and disadvantages
7. **Identity** - Name, description, personality, background
8. **Review** - Final review and submission

## Key Models

### StartingArea
- Selectable origin locations with crest images
- Gates which heritage options, species, and families are available
- Maps to an Evennia room for character starting location
- Access control: all players, trust-required, or staff-only

### SpecialHeritage
- Special origin types (e.g., Sleeper, Misbegotten) that bypass normal family restrictions
- Can unlock expanded species lists
- Sets family to "Unknown" (discoverable in play)
- Can override starting room (e.g., Sleeper Wake Room)

### CharacterDraft
- Stores in-progress character creation state
- Tracks current stage and all selections
- Expires after 2 months of account inactivity (staff exempt)
- JSON blob for complex staged data (stats, skills, traits)

## Service Functions

### `finalize_character(draft, add_to_roster=False)`
Creates a Character from a completed draft:
- Resolves starting room (heritage override → area default → None)
- Creates Character object via Evennia's create_object
- Creates RosterEntry for roster management
- Handles staff "Add to Roster" vs player submission

### `get_accessible_starting_areas(account)`
Returns StartingArea queryset filtered by account access level.

### `can_create_character(account)`
Checks if account can create characters (verified, positive trust, under limit).

## Gender & Pronouns

- Gender stored as CharField with choices: male, female, nonbinary, other
- Pronouns are separate editable fields (subject, object, possessive)
- Default pronouns auto-populated on gender selection
- Players can customize pronouns freely; abuse handled via moderation

## Important Notes

- Starting rooms may be None during early testing before the grid is built
- Commoner families are created only at final submission to avoid orphaned records
- Staff bypass all access restrictions and limits
- Navigation between stages is free; incomplete stages are highlighted but not blocked
- Submit is blocked until all required stages are complete
