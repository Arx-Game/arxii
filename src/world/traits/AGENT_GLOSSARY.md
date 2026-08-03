# Traits glossary

**Storage scale**:
Every `CharacterTraitValue` stores the fine-grained 1-100 range (ADR-0193, #2894), but display differs by family: **skills show their true stored value** (35 reads 35 — development moves them by single points, XP unlocks cross the ×10 rung boundaries), while **stats display single-digit and store ×10** (strength 2 = stored 20; players allocate 1-5 dots in CG, converted once at finalization). Convert stat display at the edge via `display_trait_value` / `STAT_DISPLAY_DIVISOR`; never divide a skill for display, and never write a display-scale stat to a trait row.
_Avoid_: "1-5 scale" for storage (that's stat display, draft-side only), dividing skill values by 10

**Trait**:
The base definition template for any measurable character quality, typed as STAT, SKILL, MODIFIER, or OTHER and grouped by category. Every Stat and Skill is backed by a Trait record, giving them a unified check-resolution pipeline.
_Avoid_: attribute, stat (for the generic case)

**Stat**:
One of the 12 core character statistics used in character creation and gameplay, organized into four categories — Physical (Strength, Agility, Stamina), Social (Charm, Presence, Composure), Mental (Intellect, Wits, Stability), and Meta (Luck, Perception, Willpower). A Stat is a Trait of type STAT.
_Avoid_: ability score, primary attribute

**Skill**:
A broad learnable competency (Melee Combat, Persuasion) backed one-to-one by a SKILL-type Trait, carrying development and rust progression on the character. Skills are the parent category beneath which Specializations live.
_Avoid_: proficiency, talent

**Specialization**:
A specific application beneath a parent Skill (Swords under Melee Combat, Seduction under Persuasion) that stacks with the parent when applicable and, unlike a Skill, is immune to rust. It unlocks once the parent Skill reaches the configured threshold.
_Avoid_: sub-skill, focus
