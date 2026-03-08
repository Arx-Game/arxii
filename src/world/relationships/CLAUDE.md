# Relationships App

Track-based character relationship system with mutual consent, deceit mechanics,
and achievement integration.

## Core Concepts

- **Absolute Value**: Total magnitude of all track points (always positive). Drives mechanical bonuses.
- **Affection**: Signed sum — positive tracks add, negative tracks subtract. Represents overall sentiment.
- **Tracks**: Categories of feeling (Friendship, Romance, Enemies, etc.) with positive or negative sign.
- **Tiers**: Intensity levels within tracks, unlocked by point thresholds.
- **Hybrid Types**: Staff-defined combinations (Frenemy = Friendship + Enemies).

## Models

### Lookup Tables (SharedMemoryModel)
- **RelationshipCondition** — Gates modifier application (Attracted To, Fears, Trusts)
- **RelationshipTrack** — Feeling categories with sign (positive/negative)
- **RelationshipTier** — Intensity levels per track with point thresholds
- **HybridRelationshipType** — Combination types with HybridRequirement entries

### Character Data
- **CharacterRelationship** — Core relationship between two CharacterSheets. Tracks active/pending status, deceit state, weekly counters.
- **RelationshipTrackProgress** — Points per track per relationship. current_tier derived property.
- **RelationshipUpdate** — Adds new absolute value. Has title, writeup, track, points, visibility, optional scene link.
- **RelationshipChange** — Redistributes existing points between tracks. No new absolute value.

## Lifecycle
1. **First Impression** — Unilateral, creates pending relationship with update + track progress
2. **Reciprocation** — Other player's first impression activates both sides
3. **Updates** — Weekly, adds points via scene checks or private reflection (diminishing returns)
4. **Changes** — Anytime, redistributes points between tracks (Level + Charm per week)
5. **Inactivity** — Freeze relationship, reactivate later. Reset option on roster transitions.

## Safety
- Minimum-of-both rule for displayed relationship tier
- Player agree/disagree on designations (OOC consent layer)
- Deceit mechanic: displayed vs real designation with OOC warning flag
- Easy de-escalation to inactive at any time

## Integration
- Achievement stats fired via `world.achievements.services.increment_stat()`
- Magic threads scale power off relationship absolute value
- Conditions gate modifier application in checks
- Track-specific combat bonuses (values TBD)
