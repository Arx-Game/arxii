# Relationships App

Track-based character relationship system with temporary/permanent point progression,
mutual consent, deceit mechanics, and achievement integration.

## Core Concepts

- **Absolute Value**: Total magnitude of all track points (developed + temporary). Always positive.
- **Developed Absolute Value**: Sum of permanent points only. Drives mechanical bonuses (cube root).
- **Capacity**: Maximum developed points allowed per track. Increased by updates and capstones.
- **Affection**: Signed sum — positive tracks add, negative tracks subtract.
- **Tracks**: Categories of feeling (Friendship, Romance, Enemies, etc.) with positive or negative sign.
- **Tiers**: Intensity levels within tracks, unlocked by developed point thresholds.
- **Hybrid Types**: Staff-defined combinations (Frenemy = Friendship + Enemies).

## Progression System

Three ways to add points:

1. **Relationship Updates** (unlimited) — Add temporary points + capacity to a track.
   Temporary points decay linearly: 10% of original per day, zero after 10 days.
   Capacity increase is permanent.

2. **Development Updates** (7/week) — Add permanent (developed) points up to capacity.
   Social roll determines points. Awards XP.

3. **Capstone Events** (unlimited) — Add both permanent points AND capacity.
   Represent monumental moments. Never gated. Real mechanical power comes from
   magical tethers (future PR) built around capstones.

## Models

### Lookup Tables (SharedMemoryModel)
- **RelationshipCondition** — Gates modifier application (Attracted To, Fears, Trusts)
- **RelationshipTrack** — Feeling categories with sign (positive/negative)
- **RelationshipTier** — Intensity levels per track with point thresholds
- **HybridRelationshipType** — Combination types with HybridRequirement entries

### Character Data
- **CharacterRelationship** — Core relationship between two CharacterSheets. Tracks
  active/pending status, deceit state, weekly development/change counters.
- **RelationshipTrackProgress** — Capacity and developed_points per track per relationship.
  Temporary points derived from active updates. current_tier uses developed_points.
- **RelationshipUpdate** — Adds temporary points + capacity. Has title, writeup, track,
  points, visibility, optional scene link. `current_temporary_value()` computes decay.
- **RelationshipDevelopment** — Adds permanent points up to capacity. Has xp_awarded.
- **RelationshipCapstone** — Adds both permanent points and capacity. Monumental moments.
- **RelationshipChange** — Redistributes existing developed points between tracks.

## Lifecycle
1. **First Impression** — Unilateral, creates pending relationship with update + capacity
2. **Reciprocation** — Other player's first impression activates both sides
3. **Updates** — Unlimited, adds temporary + capacity (emotional spikes)
4. **Development** — 7/week, solidifies temporary into permanent (up to capacity)
5. **Capstones** — Unlimited, monumental moments add permanent + capacity
6. **Changes** — Redistribute developed points between tracks
7. **Inactivity** — Freeze relationship, reactivate later

## Safety
- Minimum-of-both rule for displayed relationship tier
- Player agree/disagree on designations (OOC consent layer)
- Deceit mechanic: displayed vs real designation with OOC warning flag
- Easy de-escalation to inactive at any time

## Integration
- Achievement stats fired via `world.achievements.services.increment_stat()`
- Mechanical bonus: cube root of developed absolute value (modest)
- Magical tethers (future PR): XP-gated power built around capstones
- Conditions gate modifier application in checks
