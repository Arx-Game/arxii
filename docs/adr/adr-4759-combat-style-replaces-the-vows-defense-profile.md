# A combat style replaces the vow's defense profile

How a character defends (evasion, barrier or mitigation, and how much of their armor counts)
comes from a `CombatStyle` the character holds on `CharacterSheet.combat_style`, which replaces
their vow's `CovenantRoleDefenseProfile`; a character with no style keeps the profile, so every
existing character behaves as before. A combat style is how a character was taught to fight with
magic, so it lives on its own table rather than as a column on `TechniqueStyle`: a technique style
is how a Path or Gift casts, a Path and a character choose the two separately, and a casting
manner has no defense to carry. We give up deriving defense from the vow alone, which kept one
fewer thing to author per character, so that two holders of one tank vow can defend differently.

> Status: accepted · Source: #4759 (owner rulings 2026-10-27 to 10-31), slice 1 #4805
