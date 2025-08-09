# Character Data Storage Migration from Arx I

## Overview

This document details all the character data storage components that need to be migrated from Arx I to Arx II. Character data in Arx I is primarily stored through the evennia_extensions system, with data spread across multiple models and accessed through the `item_data` handler system. This is fundamental infrastructure that blocks character creation and roster system implementation.

## Current Arx I Character Data Architecture

### Core Storage Components

#### 1. ItemDataHandler (`evennia_extensions/object_extensions/item_data_handler.py`)
- **Purpose**: Abstraction layer that routes character data to appropriate storage models
- **Pattern**: Uses wrapper classes to hide storage implementation details
- **Usage**: Accessed as `character.item_data.property_name`

#### 2. CharacterSheet Model (`evennia_extensions/character_extensions/models.py`)
Primary character data storage with these fields:

**Basic Identity & Demographics:**
- `age` - Character age (PositiveSmallIntegerField, default=18)
- `real_age` - Hidden/secret age (nullable)
- `gender` - Character gender (via SheetValueWrapper)
- `race` - Character race (ForeignKey to Race model)
- `breed` - Character breed/subtype (via SheetValueWrapper)

**Physical Characteristics:**
- `eye_color` - Eye color (via SheetValueWrapper)
- `hair_color` - Hair color (via SheetValueWrapper)
- `height` - Character height (via SheetValueWrapper)
- `skin_tone` - Skin tone (via SheetValueWrapper)

**Social & Identity:**
- `concept` - Public character concept (CharField, max_length=255)
- `real_concept` - Hidden/secret concept (CharField, max_length=255)
- `marital_status` - Marital status with choices (default=SINGLE)
- `family` - Family name (CharField, max_length=255) - to be converted to FK later
- `fealty` - House allegiance (ForeignKey to dominion.Fealty)
- `vocation` - Character profession (CharField, max_length=255) - to be FK later
- `social_rank` - Social standing (PositiveSmallIntegerField, default=10)

**Temporal & Cultural:**
- `birthday` - Character birthday (CharField, max_length=255) - consider DateField later
- `religion` - Religious affiliation (ForeignKey to prayer.Religion)

**Descriptive Text Fields:**
- `quote` - Character quote/motto (TextField)
- `personality` - Character personality description (TextField)
- `background` - Character background story (TextField)
- `obituary` - Death notice if deceased (TextField)
- `additional_desc` - Additional description text (TextField)

**Relationship System:**
- `characteristics` - M2M to Characteristic model via CharacterSheetValue

#### 3. DisplayNames Model (`evennia_extensions/object_extensions/models.py`)
- `false_name` - Fake/disguised name
- `colored_name` - Name with color formatting
- `longname` - Full character name with titles

#### 4. Descriptions Model (`evennia_extensions/object_extensions/models.py`)
- `permanent_description` - Character's permanent description
- `temporary_description` - Temporary desc (masks, illusions, etc.)

#### 5. Character Combat Settings (`evennia_extensions/character_extensions/models.py`)
**Note: Combat settings will be completely redesigned in Arx II - see combat.md**
- `guarding` - Character being guarded (ForeignKey)
- `xp` - Current experience points (will move to advancement/progression app)
- `total_xp` - Total XP ever earned (will move to advancement/progression app)
- `combat_stance` - Current combat stance (system TBD)
- `autoattack` - Auto-attack setting (system TBD)

#### 6. Character Titles (`evennia_extensions/character_extensions/models.py`)
- Multiple titles through CharacterTitle model
- `title` - Individual title text

#### 7. Traits System
**Note: Traits are being handled in the dedicated traits app - see traits.md and traits-overview.md**
**From @sheet command and traitshandler.py:**
- **Stats**: strength, dexterity, stamina, charm, command, composure, intellect, perception, wits
- **Special Stats**: mana, luck, willpower  
- **Skills**: Dynamic skill system with name/value pairs
- **Abilities**: Magical/special abilities with name/value pairs

#### 8. Relationship System
**Note: Relationships will be a much more elaborate system in Arx II - see relationships.md for design goals**

**Arx I Implementation (for reference):**
**Short Relationships** (`character.db.relationship_short`):
- Stored as Evennia attribute (dict structure)
- Categories: parent, sibling, friend, enemy, frenemy, family, client, patron, protege, acquaintance, secret, rival, ally, spouse, regional loyalties, deceased
- Format: `{relationship_type: [(name, description), ...]}`

**Long Relationships** (Messages system):
- White journal relationships (public)
- Black journal relationships (private)
- Full relationship entries with timestamps
- Accessed via `character.messages.white_relationships` and `character.messages.black_relationships`

#### 9. Characteristic System
**Note: Will need adjustments for non-human races in Arx II's high fantasy setting**
- **Characteristic** - Types of physical traits (eye color, hair color, etc.)
- **CharacteristicValue** - Specific values for characteristics ("blue", "red", etc.)
- **CharacterSheetValue** - Links characters to their characteristic values
- **SheetValueWrapper** - Descriptor class for easy access

## Data Access Patterns Used in Arx I

### Through @sheet Command (roster.py:687-1553)
```python
# Basic identity access
character.item_data.longname
character.item_data.quote
character.item_data.social_rank
character.item_data.concept
character.item_data.fealty
character.item_data.family
character.item_data.gender
character.item_data.age
character.item_data.birthday
character.item_data.religion
character.item_data.vocation
character.item_data.height
character.item_data.eye_color
character.item_data.hair_color
character.item_data.skin_tone
character.item_data.marital_status

# Hidden fields for staff
character.item_data.real_concept
character.item_data.real_age
character.item_data.obituary

# Relationship data
character.db.relationship_short  # Dict of relationship types to lists
character.messages.white_relationships  # Public relationship entries
character.messages.black_relationships  # Private relationship entries

# Descriptive content
character.perm_desc  # From Descriptions model
character.item_data.background
character.item_data.personality

# Traits
character.traits.strength, dexterity, stamina
character.traits.charm, command, composure  
character.traits.intellect, perception, wits
character.traits.mana, luck, willpower
character.traits.skills  # Dict of skill names to values
character.traits.abilities  # Dict of ability names to values

# Titles
character.titles  # Concatenated titles string
```

### Through Web Templates (sheet.html)
**Note: Arx II uses a modern SPA frontend, not Django server-side templates**

The Arx I web template expects the same `item_data` access patterns as the in-game command, plus:
- `character.portrait` - Character portrait image
- Secrets and clue systems
- First impressions system

## Missing from Arx II

Based on analysis of current Arx II codebase, the following are completely missing:

### 1. Character Sheet Data Storage
- No equivalent to CharacterSheet model
- No data handler abstraction system
- No characteristic system for physical traits
- No basic demographic fields (age, gender, concept, family, etc.)

### 2. Character Description System  
- Missing permanent/temporary description storage
- No longname/colored name/false name system
- Current Arx II only has basic Evennia desc

### 3. Relationship System
- No relationship storage (will be designed from scratch - see relationships.md)

### 4. Character Title System
- No title storage or display system

### 5. Character Data Integration
- Need to integrate character data with flows/states/behaviors system
- Character data must be modifiable through Arx II's flow system
- API exposure for modern SPA frontend

## Migration Priority

### Phase 1: Critical Blockers (Required for Roster System)
1. **CharacterSheet equivalent model** - Store basic demographics and identity
2. **Description system** - Permanent/temporary descriptions, longname, colored_name
3. **Item data handler equivalent** - Abstraction layer for data access
4. **Basic demographic fields**: age, gender, concept, family, fealty, vocation, social_rank

### Phase 2: Character Development Features
1. **Character titles system**
2. **Background/personality text storage**
3. **Characteristic system** - Physical traits with validation (adjusted for non-human races)
4. **Flow system integration** - Character data modifiable through flows/states/behaviors

### Phase 3: Advanced Systems
1. **Relationship system** - Will be designed from scratch (see relationships.md)
2. **API development** - Full exposure for SPA frontend
3. **Advanced characteristic features** - Race-specific traits for high fantasy setting

## Implementation Strategy

### 1. Create Arx II Character Extensions App
Following Arx II's evennia_extensions pattern:
- `evennia_extensions/character_data/` - New app for character sheet data
- Models following SharedMemoryModel pattern where appropriate
- Wrapper system for clean data access

### 2. Data Handler Pattern
Create equivalent to item_data handler:
- `CharacterDataHandler` class
- Property-based access to underlying models
- Caching for performance

### 3. Django Data Migrations
- Create Django migrations for initial data setup (trait definitions, characteristics, etc.)
- Use data migrations for any reference data that needs to be ported from Arx I
- No database-to-database copying or import scripts

### 4. System Integration
- Update @sheet command to work with new data storage
- Integrate character data with flow system for state-based modifications
- Create API endpoints for SPA frontend access
- Ensure character data is modifiable through flows/states/behaviors

## Technical Considerations

### Database Design
- Follow Arx II patterns: SharedMemoryModel where appropriate
- Use proper ForeignKey relationships instead of CharField where possible
- Implement proper validation and constraints
- Consider indexing for frequently accessed fields

### Performance
- Cache character data effectively
- Use SharedMemoryModel for lookup tables (races, characteristics)
- Lazy loading for expensive operations

### Compatibility
- Maintain similar access patterns (`character.sheet_data.age` vs `character.item_data.age`)
- Keep same field names where possible
- Support gradual implementation rather than big-bang approach

### Data Validation  
- Implement proper choices for fields like marital_status
- Validate characteristic values against allowed options
- Ensure relationship data integrity

## Design Migration Notes

**Important**: This document focuses on migrating *designs and code patterns* from Arx I, not data. For the overall migration philosophy, see the main README in this directory.

## Next Steps

1. **Design character data models** following Arx II evennia_extensions patterns
2. **Create data handler abstraction layer**
3. **Implement basic character sheet storage** to unblock roster system
4. **Create Django data migrations** for reference data (characteristic types, etc.)
5. **Integrate with flow system** for character data modifications
6. **Create API endpoints** for SPA frontend access
7. **Design relationships system** (see relationships.md)

## Related Documentation

- **traits.md** - Traits system implementation
- **traits-overview.md** - Traits system overview
- **combat.md** - Combat system design (affects combat settings)
- **progression.md** - Advancement system (affects XP handling)
- **relationships.md** - Relationship system design (to be created)

This migration is essential for the roster system and character creation - it should be prioritized as foundational infrastructure for Arx II.
