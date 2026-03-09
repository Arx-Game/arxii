# Achievements App

Cross-cutting meta-engagement layer. Characters earn achievements for milestones
across every game system. Hidden by default, designed to surprise and delight.

## Models

### StatDefinition (SharedMemoryModel)
Lookup table for trackable stats. Normalizes stat keys so they stay in sync
between StatTracker and AchievementRequirement.
- key (unique): dot-separated identifier, e.g., 'relationships.total_established'
- name: player-facing display name
- description: what this stat measures

### StatTracker (SharedMemoryModel)
General-purpose counter for measurable character actions.
- FK to CharacterSheet, FK to StatDefinition, integer value
- UniqueConstraint on character_sheet + stat
- Uses SharedMemoryModel for caching

### Achievement (SharedMemoryModel)
Staff-defined achievement definitions.
- name, slug, description, icon
- hidden (default True), notification_level (Personal/Room/Gamewide)
- prerequisite (self FK for chained achievements)
- is_active flag

### AchievementRequirement
Conditions to earn an achievement. FK to StatDefinition with thresholds.
- Multiple per achievement (all must be met)
- comparison: gte, eq, lte
- `is_met(value)` method encapsulates comparison logic

### RewardDefinition (SharedMemoryModel)
Lookup table for rewards. Normalizes reward identifiers across game systems.
- key (unique): dot-separated identifier, e.g., 'title.champion'
- name: player-facing display name
- reward_type: TextChoices (title, bonus, cosmetic)
- Stub entries for systems not yet built

### AchievementReward
Links an achievement to a RewardDefinition with optional parameterization.
- FK to Achievement, FK to RewardDefinition
- reward_value: optional extra data (e.g., bonus amount)

### Discovery
First-time-earned record. OneToOne to Achievement.
- Supports simultaneous co-discoverers (party kills, etc.)

### CharacterAchievement
Records when a character earned an achievement.
- FK to Discovery if they were a co-discoverer
- UniqueConstraint on character_sheet + achievement

## StatHandler (handlers.py)

Cached stat handler attached to CharacterSheet as `@cached_property`:
```python
character_sheet.stats.get(stat_def)           # Returns int, 0 if not tracked
character_sheet.stats.increment(stat_def, 3)  # Atomic increment, returns new value
```
- Lazily loads all stat values on first access
- Mutations update both DB (atomic F() expression) and local cache
- Automatically checks for newly met achievement requirements after increment

## Integration Pattern

Other apps use the StatHandler via CharacterSheet — no Django signals:
```python
from world.achievements.models import StatDefinition

stat_def = StatDefinition.objects.get(key="relationships.total_established")
character_sheet.stats.increment(stat_def)
```

Service functions `get_stat()` and `increment_stat()` are thin wrappers around
the handler for backward compatibility.

Since StatDefinition is a SharedMemoryModel, `.get()` hits the in-memory cache after first access.

## Key Rules

- Achievements are hidden by default — surprise and delight
- Notification level is per-achievement (personal, room, gamewide)
- Discovery tracks first-to-achieve with co-discoverer support
- StatDefinition normalizes stat keys — no raw strings in FKs
- RewardDefinition normalizes reward keys — no raw strings for rewards
- Service functions accept StatDefinition instances, not string keys
- All achievements are hand-crafted by staff (no auto-generation)
- Character ownership queries use RosterTenure chain, NOT db_account
