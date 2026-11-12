# Traits glossary

**Storage scale**:
Every `CharacterTraitValue` stores the fine-grained 1-100 range (#2894), and every surface shows that stored value for stats and skills alike (ADR-5091, #5091; superseded ADR-0193's divide-by-10 for stats): strength 20 reads 20, a skill at 35 reads 35. A **stat point** is `STAT_POINT_VALUE` (10), the step character creation (10 to 50), maturation, level stat points and GM raises move a stat by. Formulas tuned per whole stat point count `whole_stat_points(value)` (`value // 10`), an internal step that is never shown.
_Avoid_: "display value", "dots" or a "1-5 scale" for stats (removed by #5091); dividing any stat, skill or thread value by 10 for display

**Trait**:
The base definition template for any measurable character quality, typed as STAT, SKILL, MODIFIER, or OTHER and grouped by category. Every Stat and Skill is backed by a Trait record, giving them a unified check-resolution pipeline.
_Avoid_: attribute, stat (for the generic case)

**Stat**:
One of the 12 core character statistics used in character creation and gameplay, organized into four categories — Physical (Strength, Agility, Stamina), Social (Charm, Presence, Composure), Mental (Intellect, Wits, Stability), and Meta (Luck, Perception, Willpower). A Stat is a Trait of type STAT.
_Avoid_: ability score, primary attribute

**Skill**:
A broad learnable competency (Melee Combat, Persuasion): a Trait of type SKILL, seen through the `Skill` proxy model (#5008, ADR-5008), carrying development and rust progression on the character. Skills are the parent category beneath which Specializations live.
_Avoid_: proficiency, talent

**Specialization**:
A specific application beneath a parent Skill (Swords under Melee Combat, Seduction under Persuasion) that stacks with the parent when applicable and, unlike a Skill, is immune to rust. It unlocks once the parent Skill reaches the configured threshold.
_Avoid_: sub-skill, focus
