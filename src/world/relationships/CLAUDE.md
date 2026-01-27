# Relationships App

Character-to-character relationship tracking with condition-based modifier gating.

## Models

### RelationshipCondition
Conditions that can exist on a relationship (e.g., "Attracted To", "Fears", "Trusts").
- Gates which modifiers from the mechanics app apply situationally
- SharedMemoryModel for caching

### CharacterRelationship
One character's opinion/status toward another character.
- Tracks reputation score (-1000 to 1000)
- Has multiple conditions via M2M
- Unique per source/target pair

## Usage
Relationships determine when situational modifiers (like Allure from Attractive) apply during roll resolution.
