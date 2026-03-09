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
- **Models:** RelationshipTrack, RelationshipTier, HybridRelationshipType + HybridRequirement, CharacterRelationship (with track progress, deceit fields, consent mechanics), RelationshipTrackProgress (capacity + developed_points), RelationshipUpdate (temporary + capacity), RelationshipDevelopment (permanent up to capacity), RelationshipCapstone (permanent + capacity), RelationshipChange, RelationshipCondition (modifier gating)
- **Services:** create_first_impression (with reciprocal activation), redistribute_points (atomic point movement between tracks), create_development (permanent points up to capacity), create_capstone (permanent + capacity)
- **Magic threads:** Thread, ThreadType, ThreadJournal, ThreadResonance models in the magic app
- **APIs:** Full viewsets and serializers for tracks, tiers, hybrids, conditions, and relationships
- **Admin:** Admin classes for all models with inlines
- **Tests:** Model tests, service tests, and view tests

## What's Needed for MVP

### Magic Integration
- **Thread-relationship bridge** — Magic Threads (axis-based: romantic/trust/rivalry/protective/enmity 0-100) and CharacterRelationships (track-based with points/tiers/capacity) are completely separate systems with no connection. Need a bridge so thread power scales off relationship absolute value as designed
- **Magical tethers** — XP-gated power amplifiers built around capstone events. The real source of significant mechanical power from relationships, connecting to the thread/resonance system. Future PR but core to the relationship power fantasy
- **Thread resonance bonuses** — Thread resonances should add magical bonuses on top of relationship mechanical bonuses. Currently no formula or integration
- **Aura farming tie-in** — Dramatic relationship moments in scenes should feed into resonance/aura (depends on scenes + magic integration)

### Mechanical Bonuses & Formulas
- **Cube root bonus in checks** — `mechanical_bonus` property exists on CharacterRelationship (cube root of developed absolute value) but nothing in the check/attempt pipeline consumes it
- **Track-specific bonus types** — Different tracks should give different bonus types (Romance → protective actions, Rivals → competitive performance, Found Family → resilience). No formulas defined, depends on combat system
- **Teamwork check bonuses** — Bonus when characters act together, scaled by developed absolute value. Not integrated into check resolution
- **Combat coordination bonuses** — Party members with strong relationships get coordination bonuses. Depends on combat system
- **Combo attack gating** — Effectiveness gated by relationship strength + thread resonances. Depends on combat system
- **Minimum-of-both rule** — Each player sets track designations independently; shared mechanical bonuses should use the lower of the two. No service function implements this

### Relationship Advancement Mechanics
- **Development roll formula** — What stat/skill is used for the social roll in development updates, and how roll result maps to points earned. Currently create_development just takes points directly
- **Tier point thresholds** — Exact point values for each tier on each track (Tier 1 easy, each subsequent much harder). Currently defined in fixture data but values may need tuning
- **XP reward formula** — How much XP a development update awards. xp_awarded field exists on RelationshipDevelopment but no formula calculates it
- **Temporary point decay cron** — RelationshipUpdate.current_temporary_value() calculates decay on read, but there's no cron job to clean up fully-decayed updates or update cached totals
- **RelationshipUpdate creation service** — No service function for creating relationship updates (only first impressions have a service). Need validation, achievement stat firing, capacity updates

### Consent & Safety
- **Player agreement flow** — OOC prompt when a player picks a designation ("Are you comfortable RPing this?"). No UI or backend for this consent exchange
- **Designation fallback logic** — When consent is denied, positive tracks fall to Acquaintance, negative to Unfriendly Acquaintance. No implementation
- **Deceit skill check** — What check is required for non-distinction characters to maintain a deceptive displayed relationship. No formula or integration with check system
- **Consent withdrawal** — Either player can withdraw consent at any time. No endpoint or UI for this
- **Inactivity/freezing** — Players can make relationships inactive (points freeze, bonuses stop). Frozen model referenced in design but not implemented
- **Roster transition reset** — When a new player takes over a character, both players can mutually agree to reset. No implementation

### Frontend UI
- **Relationship management page** — Currently RelationshipsSection.tsx is a stub showing string arrays with "TBD" placeholder. Needs full relationship list/detail views
- **First impression creation UI** — Writing the initial impression, picking track, coloring, visibility
- **Relationship update creation UI** — Writing updates with title, writeup, track assignment, scene linking, visibility
- **Development update UI** — Social roll interface, writeup, track selection (with 7/week counter display)
- **Capstone event UI** — Creating monumental moments with narrative writeup
- **Point redistribution UI** — Moving developed points between tracks with narrative explanation
- **Relationship timeline view** — Chronological display of all updates, developments, capstones, and changes for a relationship
- **Track progress visualization** — Visual display of points per track, tier progression, capacity vs developed vs temporary
- **Deceit indicator** — Red question mark OOC warning when a character's displayed feelings may differ from real
- **Asymmetric view rendering** — Each player sees their own real designations + the other's displayed designation
- **Visibility controls** — Private/Shared/Gossip/Public per update, with appropriate filtering
- **Consent prompt UI** — OOC agree/disagree modal for track designations
- **Hybrid type display** — Showing when a relationship qualifies as a hybrid type (Frenemy, Beloved Enemy, etc.)

### Achievement Integration
- **Achievement stat hooks** — Only reciprocation fires `relationships.total_established`. Missing stats for:
  - Relationships per track (number of Friends, Rivals, etc.)
  - Highest tier reached per track
  - Track transitions (Enemies → Romance = "enemies to lovers" trigger)
  - Total points in each track type
  - Number of relationship updates written
  - Total absolute value across all relationships
  - Pure positive relationships (no negative tracks)
  - Pure negative relationships (no positive tracks)
  - Time spent in relationship (weeks active)
  - Monogamous relationship milestones
  - Capstone events written
  - Development updates completed
- **Relationship achievement definitions** — Example achievements designed but not created as fixture data: First Impression, Social Butterfly, It's Complicated, Enemies to Lovers, Lone Wolf, Serial Monogamist, Heart of Gold, Enemies With Benefits, Irresistible
- **Hybrid type detection service** — No service function to check if a relationship's active tracks match hybrid type requirements (needed for achievement triggers)

### Content Authoring
- **Family track tier definitions** — Tier names and mechanics TBD
- **Mentor track tier definitions** — Tier names and mechanics TBD
- **Allies track tier definitions** — Tier names and mechanics TBD
- **Hybrid type definitions** — Frenemy, Friends With Benefits, Beloved Enemy designed; need fixture data and potentially more types
- **Relationship condition definitions** — RelationshipCondition model exists with M2M to ModifierTarget, but no service to apply conditions during checks

### Cross-System Integration
- **Progression requirements** — RelationshipRequirement stub in progression app always returns False. Needs implementation to query CharacterRelationship
- **Gossip system** — Gossip-visible updates should be discoverable by other players. No gossip system exists yet
- **Scene linking** — linked_scene FK exists on updates/developments/capstones but no UI to link scenes during creation
- **Adventuring party model** — Group formation, shared legend, coordination bonuses. No models exist
- **NPC reputation model** — Simpler -1000 to 1000 reputation for system NPCs (shopkeepers, faction contacts). No models exist

## Notes

See `docs/plans/2026-03-08-relationships-achievements-design.md` for the full design document.
