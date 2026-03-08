# Relationships & Bonds

**Status:** in-progress
**Depends on:** Magic (threads/resonance), Scenes, Progression, Achievements

## Overview
Relationships are the heart of the game. A track-based system lets characters develop feelings across multiple dimensions simultaneously — friendship, romance, rivalry, enmity, family, mentorship, and alliances. The absolute value of a relationship (total intensity regardless of direction) drives mechanical bonuses, meaning a bitter rival and a devoted lover are equally powerful. The system rewards all forms of intense RP while providing safety mechanics so drama stays fun and never feels like obligation.

## Key Design Points
- **Track-based progression:** Characters allocate points across feeling tracks (Friendship, Romance, Enemies, Rivals, Family, Mentor, Allies), each with tiered intensity levels
- **Absolute value = mechanical power:** A character with 500 love and 500 hate has 1000 absolute value — massive bonuses regardless of emotional direction
- **Conflicted feelings are first-class:** Characters can simultaneously love and hate someone. The system supports "enemies to lovers" and "beloved enemy" arcs naturally
- **Mutual consent at every step:** Intense relationship types (Rivals, Romance, Enemies) only activate with both players' agreement. Easy de-escalation at any time
- **Deceit mechanic:** Characters with Deceitful distinctions can display a fake relationship type, with an OOC warning flag so the other player is never truly blindsided
- **Weekly updates with diminishing returns:** Relationship growth is gated by scene-based or private reflection rolls, with decreasing returns per update per week
- **Hybrid types:** Staff-defined combinations (Frenemy, Beloved Enemy, Friends With Benefits) emerge when multiple tracks are active simultaneously
- **OOC safety:** Player-level agree/disagree on designations. Any player can make a relationship inactive at any time
- **Thread integration:** Magic threads amplify and solidify existing relationships, scaling power off the relationship's absolute value
- **Achievement integration:** Relationship milestones fire achievement stats (first relationship, enemies-to-lovers, etc.)

## What Exists
- **Models:** RelationshipTrack, RelationshipTier, HybridRelationshipType + HybridRequirement, CharacterRelationship (with track progress, deceit fields, consent mechanics), RelationshipTrackProgress, RelationshipUpdate, RelationshipChange, RelationshipCondition (modifier gating)
- **Services:** create_first_impression (with reciprocal activation), redistribute_points (atomic point movement between tracks)
- **Magic threads:** Thread, ThreadType, ThreadJournal, ThreadResonance models in the magic app
- **APIs:** Full viewsets and serializers for tracks, tiers, hybrids, conditions, and relationships
- **Admin:** Admin classes for all models with inlines
- **Tests:** Model tests, service tests, and view tests

## What's Needed for MVP
- Weekly update service function with diminishing returns curve
- Player consent flow (agree/disagree on track designations)
- Deceit skill check mechanics (for non-distinction characters)
- Track-specific combat bonus formulas (depends on combat system design)
- Family, Mentor, Allies track tier definitions
- Private reflection roll mechanics
- Gossip system integration for gossip-visibility updates
- Adventuring party model — group formation, shared legend, coordination bonuses
- Soul tether mechanics — connecting to Abyssal/redeemer system
- Thread integration — connecting thread power scaling to relationship absolute value
- Relationship UI — web interface for managing relationships
- NPC simple reputation model for system NPCs (shopkeepers, etc.)

## Notes

See `docs/plans/2026-03-08-relationships-achievements-design.md` for the full design document.
