# Classes glossary

**Path**:
The narrative-facing class system — a named position in a character's evolution hierarchy (e.g. "Path of Steel" evolving into "Vanguard"), tracing the journey toward greatness through acts, legend, and achievements. Each Path has a `PathStage` and a minimum level.
_Avoid_: class (reserve "class" for `CharacterClass`), career, profession.

**CharacterClass**:
The mechanical class definition — trait requirements, level tracking, and the anchor for XP-cost charts and per-stage health rates. The backend Class/Level system that underlies a character's Path.
_Avoid_: Path (the two are distinct systems), job.

**PathStage**:
The evolution-stage band of a Path — PROSPECT, POTENTIAL, PUISSANT, TRUE, GRAND, TRANSCENDENT — derived from level by fixed breakpoints (levels 1/3/6/11/16/21).
_Avoid_: tier (tier is a separate Class/Level concept), rank, phase.

**Level**:
A character's numeric standing (1–30) in a specific `CharacterClass`, stored on a `CharacterClassLevel` row; the primary class level drives health and advancement.
_Avoid_: rank, grade.

**ClassStageHealthRate**:
The authored per-(`CharacterClass`, `PathStage`) rate of health gained per character level while inside that stage band.
_Avoid_: HP curve, health table.
