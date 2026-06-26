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
- **GrievanceOption** (#1429) — Staff-authored preset swings a wronged character may register
  against whoever harmed them (label + negative `track` + `points`). Used by the secret-victim
  flow: the victim picks one (or a custom value) and `register_grievance` applies it. `clean`
  enforces a NEGATIVE-sign track.

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

## Services
- **`register_grievance(*, source, target, option=None, custom_points=None, custom_track=None, …)`**
  (#1429) — a wronged character's **one-sided** grievance: resolves a `GrievanceOption` (or a
  custom points+track) and applies it as a `create_capstone` on the (source→target) relationship.
  Unilateral — never needs the target's consent; the relationship stays `is_pending` until/unless
  reciprocated. Track must be NEGATIVE-sign. The secret-victim prompt is the caller (web slice).
- **`create_first_impression` / `create_development` / `create_capstone` / `redistribute_points`**
  (`services.py`) — the four positive relationship-building verbs. Each is wrapped by a
  corresponding Action in `actions/definitions/relationships.py` and reachable from both surfaces
  below.

## Player Surface (#1485)

The positive relationship-building loop is reachable from both web and telnet:

- **Web** — `RelationshipUpdateViewSet` exposes four POST endpoints (`first_impression` /
  `develop` / `capstone` / `redistribute`) that dispatch the Actions via `action.run()`. List/
  detail reads live on `CharacterRelationshipViewSet` (read-only).
- **Telnet** — `CmdRelationship` (`relationship <subverb>`) runs the same Actions; it adds
  telnet-only `relationship list` and `relationship show <name|#>` read surfaces (the web provides
  these implicitly).

`linked_scene` defaults to the caller's active scene in the current room when the target is
co-located. **No consent gate** — these describe the caller's regard for another character; they do
not compel or provoke the target's behavior (ADR-0024). The Golden Rule covers bad-faith writeups;
a positive kudos / complaint feedback layer for shared/public writeups is a follow-up (#1328).

## Integration
- Achievement stats fired via `world.achievements.services.increment_stat()`
- Mechanical bonus: cube root of developed absolute value (modest)
- Magical tethers (future PR): XP-gated power built around capstones
- Conditions gate modifier application in checks
- **Secret reputation consequences (#1429):** a secret's persona-victim, on learning who wronged
  them, registers a grievance via `register_grievance` (the relationship effect they *decide*).
