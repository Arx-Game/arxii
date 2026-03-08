# Achievements App

Cross-cutting meta-engagement layer. Characters earn achievements for milestones
across every game system. Hidden by default, designed to surprise and delight.

## Models

### StatTracker
General-purpose counter for measurable character actions.
- FK to CharacterSheet, stat_key string, integer value
- Unique together on character_sheet + stat_key
- Keys are dot-separated: 'relationships.total_established', 'combat.kills.total'

### Achievement (SharedMemoryModel)
Staff-defined achievement definitions.
- name, slug, description, icon
- hidden (default True), notification_level (Personal/Room/Gamewide)
- prerequisite (self FK for chained achievements)
- is_active flag

### AchievementRequirement
Conditions to earn an achievement. Points to StatTracker keys with thresholds.
- Multiple per achievement (all must be met)
- comparison: gte, eq, lte

### Discovery
First-time-earned record. OneToOne to Achievement.
- Supports simultaneous co-discoverers (party kills, etc.)

### CharacterAchievement
Records when a character earned an achievement.
- FK to Discovery if they were a co-discoverer

### AchievementReward
Rewards granted: titles, bonuses, cosmetics.

## Integration Pattern

Other apps call service functions — no Django signals:
```python
from world.achievements.services import increment_stat
increment_stat(character_sheet, "relationships.total_established")
```

## Key Rules

- Achievements are hidden by default — surprise and delight
- Notification level is per-achievement (personal, room, gamewide)
- Discovery tracks first-to-achieve with co-discoverer support
- No FKs from this app into specific game systems — stat_key strings decouple
- All achievements are hand-crafted by staff (no auto-generation)
