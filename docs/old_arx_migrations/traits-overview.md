# Traits System Overview

## What Are Traits?

Traits represent all measurable aspects of a character - from physical strength to magical corruption to skill in swordplay. They use a unified 1-100 internal scale (displayed as 1.0-10.0) and serve as the foundation for all character mechanics.

## Core Trait Types

### Stats *(Architecture Decided)*
- **Purpose**: Core attributes like strength, intelligence, charisma
- **Advancement**: Mostly fixed at creation, rare opportunities to change
- **Range**: Typically 10-50 for mortal characters (1.0-5.0 displayed)

### Skills *(Architecture Mostly Decided)*  
- **Purpose**: Learnable abilities like swordplay, medicine, crafting
- **Advancement**: Development points for incremental gains, XP for major thresholds
- **Practice Decay**: Unused skills accumulate "out of practice" penalties
- **Range**: Can reach 100+ (10.0+) for legendary masters

### Specializations *(Implementation Unclear)*
- **Purpose**: Conditional bonuses that apply in specific circumstances
- **Examples**: "Crafting at night", "Combat while mounted", "Persuasion with nobles"
- **Mechanics**: Filter system determines when bonuses apply to checks

## Narrative/Story Traits *(Architecture Open)*

Many character aspects may or may not be represented as traits:

### Examples of Possible Trait-Based Systems
- **Corruption Scores**: Abyssal taint, moral degradation
- **Atavism**: Past-life bleed-through with hidden revelation mechanics
- **Magical Scars**: Consequences of magical failure or misuse
- **Bloodline Traits**: Inherited capabilities tied to ancestry

### Examples of Likely Non-Trait Systems
- **Character Relationships**: Probably separate connection system
- **Location Bonds**: Ties to places, unclear integration
- **Magic Resonance**: May be part of separate magic app
- **Achievements**: Story milestones, likely separate tracking

## Trait Properties

### Value and Display *(Interface Design Open)*
- **Internal Scale**: 1-100 numerical values
- **Display Options**:
  - Show numbers (2.5 strength)
  - Show descriptions ("Above Average" strength)  
  - Hybrid approach with both
  - Selection-based creation (pick "Strong" → maps to hidden value)

### Naming and Descriptions *(Character Creation Interface)*
- **Selection Labels**: Descriptive names for trait values during character creation
- **Value Mapping**: Each label maps to specific trait value (divisible by 10)
- **Example**: Strength options: "Puny" (maps to 10), "Average" (maps to 20), "Strong" (maps to 30)
- **No Storage**: Labels are for selection only - character just gets the numerical value
- **Display Logic**: Display rank calculated as value/10 (so 30 shows as "3.0")

### Visibility Rules *(Mechanics Undefined)*
- **Hidden Traits**: Some traits invisible until revealed through story
- **Conditional Display**: Only show if significantly high/low (attractiveness)
- **Player vs Character Knowledge**: What characters know vs what players see

## Integration with Other Systems

### Check Resolution
Traits are the primary input for all action resolution - see [Check Resolution](check-resolution.md).

### Character Advancement  
Traits have different advancement paths based on type - see [Advancement](advancement.md).

### Magic and Connections
Integration points still being designed - see respective documents.

## Implementation Priorities

### Build Now *(Core Foundation)*
1. **Basic trait definitions** with 1-100 scale
2. **Character trait values** with validation  
3. **Simple advancement tracking** for development points
4. **Flexible display system** to accommodate different interface approaches

### Design First *(Before Implementation)*
1. **Character creation interface** - numbers vs descriptions vs hybrid
2. **Hidden trait mechanics** - revelation triggers and visibility rules
3. **Integration boundaries** - what's a trait vs separate system

### Add Later *(Extensions)*
1. **Practice decay system** for unused skills
2. **Specialization mechanics** with conditional bonuses
3. **Narrative trait systems** once story elements are designed
4. **Advanced display features** like dynamic naming

## Open Questions

1. **Trait Scope**: Which character aspects should be traits vs separate systems?
2. **Character Creation**: How do players initially set trait values?
3. **Hidden Mechanics**: When and how are secret traits revealed?
4. **Practice Decay**: How quickly do unused skills degrade?
5. **Specializations**: How many conditional bonuses per character?
