# Achievements glossary

**Achievement**:
A staff-defined milestone a character can earn across any game system, hidden by default and awarded automatically when all its stat-threshold requirements are met. Achievements can chain via a prerequisite and carry a notification level (personal, room, or gamewide).
_Avoid_: badge, trophy, accomplishment

**Discovery**:
The single record marking the first time a hidden Achievement is earned by anyone, supporting simultaneous co-discoverers; once it exists, the Achievement becomes visible to all players.
_Avoid_: first-find, unlock event

**Stat**:
In this app, a named numeric counter (a tracked metric like "quests_completed" or "relationships.total_established") that game systems increment and that achievement requirements check against. This is distinct from a traits Stat (a core character statistic such as Strength) — an achievements Stat is a measured tally, not an ability score.
_Avoid_: counter, metric (as the canonical term)

**StatDefinition**:
The lookup row defining a trackable Stat — its unique dot-separated key, display name, and description — so the same normalized stat identity is shared between a StatTracker and an AchievementRequirement instead of raw strings.
_Avoid_: stat key, stat type

**StatTracker**:
The per-character row holding the current integer value of one StatDefinition for one character (unique per character + stat), incremented atomically by other systems and read by the achievements engine.
_Avoid_: stat counter, stat value row

**DiscoverableContent**:
A Django abstract base class (no table of its own) that adds a nullable `discovery_achievement` FK to any content model whose instances can be "discovered for the first time" — i.e., when the first character ever gains that content, a Discovery is recorded and an Achievement is granted. Inherited by `Technique` and `CovenantRole`; null FK means the content is not discoverable.
_Avoid_: discoverable mixin (it is a base class, not a mixin), achievement holder

**Access change**:
The event of a character gaining or losing access to techniques or capabilities, regardless of source (alternate-self shapeshift, covenant role engagement/disengagement, character creation). A single surface — `announce_access_change` in `achievements/discovery.py` — handles notification and fires any first-ever Discovery ceremony; callers never branch on the source.
_Avoid_: ability change, capability notification, technique grant (too narrow)
