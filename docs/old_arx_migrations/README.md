# Arx II System Migration Documentation

This directory contains planning documents for migrating systems from Arx I to Arx II, along with design exploration for new systems.

## Core Character Systems

### [Traits System](traits-overview.md)
What traits are, how they're structured, and their role in character definition.

### [Check Resolution](check-resolution.md)
How trait values convert to points, ranks, and determine action outcomes via result charts.

### [Character Advancement](advancement.md)
Classes, levels, tiers, development points, XP, and "Crossing the Threshold" mechanics.

## System Integration *(Many Details TBD)*

### [Magic and Resonance](magic-integration.md) *(Mostly Undesigned)*
How magical systems interact with traits, resonance generation, and spell mechanics.

### [Connections and Relationships](connections-integration.md) *(Architecture Open)*
Character bonds, location ties, object connections, and their role in advancement/abilities.

### [Character Creation](character-creation.md) *(Interface Unclear)*
How players select traits, whether via descriptions or numbers, and initial character setup.

## Implementation Planning

### [Migration Strategy](migration-plan.md)
Step-by-step plan for implementing the new systems while preserving what worked in Arx I.

### [Open Questions](open-questions.md)
Major design decisions that need resolution before full implementation.

---

## Migration Philosophy

**Design Migration, Not Data Migration**: We are migrating *designs, patterns, and code architecture* from Arx I to Arx II, not data. No database-to-database copying or data import scripts will be used. Any reference data needed (like trait definitions) will be created fresh through Django data migrations.

**Build Flexible Foundations**: Create abstract systems that can accommodate complex rules still being designed.

**Preserve What Worked**: Arx I's final check system (points → ranks → charts) was sophisticated and effective.

**Embrace Uncertainty**: Many systems (magic, connections, character creation) are still being designed.

**Empower Player GMs**: Systems should support player GM autonomy within strong guardrails.
