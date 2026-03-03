# Relationships & Bonds

**Status:** in-progress
**Depends on:** Magic (threads/resonance), Scenes, Progression

## Overview
Relationships are the heart of the game. Every mechanical relationship type — rivalry, romance, soul tethers, adventuring party bonds — provides distinct bonuses that grow with intensity. The system rewards the RP that MUSH players already love doing, while providing escape valves so drama stays fun and never feels like obligation.

## Key Design Points
- **Many relationship types:** Rivalry, romance, mentorship, soul tethers (Abyssal/redeemer bonds), adventuring party bonds, and more — each with distinct mechanical bonuses
- **Intensity scaling:** Relationship bonuses grow as the relationship develops. A heated rivalry gives increasing bonuses to both characters on magical checks
- **Situational modifiers:** Character emotions influence checks. A character fighting to save their romantic partner who is near death gets an overwhelming combat bonus, nudging them toward an Audere Majora
- **Adventuring parties:** Established groups build legend together and gain magical coordination bonuses. Characters become interdependent — stronger together than alone
- **Soul tethers:** Abyssal characters paired with a redeemer. The Abyssal can be kept in check; the redeemer risks corruption from abyssal intrusive thoughts. Tracks redemption and corruption arcs
- **Redemption/corruption tracking:** Mechanical tracking of a character's moral trajectory, influenced by relationships and choices
- **OOC safety:** Easy opt-in and opt-out for all relationship types. No pressure mechanics. If a rivalry stops being fun, either player can de-escalate
- **Thread integration:** Magic threads (in the magic system) represent the supernatural dimension of relationships — bond strength feeds magical power
- **Alter ego relationships:** Characters may have relationships under masked/alternate identities

## What Exists
- **Models:** RelationshipCondition (states like "Attracted To", "Fears", "Trusts"), CharacterRelationship (character-to-character with reputation score -1000 to 1000 and conditions M2M)
- **Magic threads:** Thread, ThreadType, ThreadJournal, ThreadResonance models exist in the magic app
- **APIs:** Viewsets and serializers for relationships
- **Tests:** Model and view tests exist

## What's Needed for MVP
- Relationship type system with distinct mechanical bonuses per type
- Intensity/development tracking — how relationships grow and change over time
- Situational modifier engine — applying relationship bonuses during checks, combat, and scenes
- Adventuring party model — group formation, shared legend, coordination bonuses
- Soul tether mechanics — Abyssal/redeemer pairing with redemption/corruption tracking
- Rivalry mechanics — escalation, bonuses, de-escalation safety valves
- Romance mechanics — collaborative bonuses, dramatic combat modifiers
- Thread integration — connecting magic threads to relationship development
- Alter ego / masked identity relationship handling
- Relationship UI — viewing, managing, and developing relationships through the web interface

## Notes
