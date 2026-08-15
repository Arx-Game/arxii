# character_sheets glossary

Domain-local vocabulary. Cross-cutting terms live in the root
`AGENT_GLOSSARY_MAP.md`.

## Age axes (#2756, ADR-0172)

- **Chronological age** — years since birth on Arx's timeline; derived from
  `CharacterSheet.ic_birth_year` against `get_ic_now()`, never stored. Null
  birth year = unknowable ("Unknown" to every viewer, the player included).
  _Avoid_: real age, true age.
- **Matured years** — years of aging actually lived forward; the maturation
  meter that funds Maturation Points. Advanced by the birthday tick; paused by
  `aging_paused`; reduced only by true age-reversal magic.
- **Withered years** — years stacked on by curses/vitality drains. Count toward
  biological age (decline, death, looks) but never earn milestones; restoration
  magic may strip them. Pure detriment.
- **Biological age** — matured + withered years: how far the body has traveled
  toward death. What old-age decline reads. _Avoid_: physical age.
- **Apparent age** — the age the world reads; equals biological age. Cosmetic
  overrides (glamours, guises, shapechange) are an appearance-layer concern and
  deliberately free — they never touch the stored axes. _Avoid_: display age.
- **Celebrated birthday / waking day** — `birthday_month`/`birthday_day`, the
  date celebrated each IC year (a Sleeper celebrates the day they woke;
  whether it is their true birth date is unknowable). Surfaces in the Town
  Crier birthday digest (`tidings.FeedItemKind.BIRTHDAY`).
- **Maturation Point** — deterministic stat point earned at matured-year
  milestones (21, 24, 27, …); spends live in `progression.MaturationSpend`,
  active iff `milestone_year <= matured_years`. _Avoid_: birthday point, age
  point.
- **Frailty** — the old-age condition (vitals): severity counts accumulated
  decline and reduces max health −1 per point via the `max_health`
  ModifierTarget. Crossing the aging floor opens the **dying window**
  (`CharacterVitals.aging_death_ic_deadline`).

## Mood (#2994)

- **Mood** — a character's declared internal emotional state (`feel <state>`,
  `SetMoodAction`, `CharacterSheet.current_mood → MoodOption`). INTERNAL and
  SILENT by design: setting one never echoes to the room, is never rendered
  into look/appearance text, and carries no mechanical effect. Sticky until
  re-declared or cleared (`feel` with no argument) — mirrors
  `current_language`'s sticky-nullable-FK shape exactly, but lives on
  `CharacterSheet` (not `Persona`) since a mask doesn't change how the person
  underneath feels. Own mood is always visible to self and staff (owner/staff
  gate on `CharacterSheetSerializer`'s identity section); any other viewer
  learns it only through the earned `SenseMoodAction` (`sense_mood`, gated on
  an Empathy skill specialization + `perform_check` — never ambient). No
  collision with `StanceArchetype` (proclamations, ADR-0178) or `NpcRegard`'s
  declared stance (ADR-0085) — both are directed, numeric-judgment concepts;
  Mood has no target and no numeric value. `MoodOption` is a curated,
  content-authored lookup (ships empty in code; seeded via the lore repo's
  content round trip). _Avoid_: mood/stance/disposition as a synonym for
  `StanceArchetype` or `NpcRegard`'s declared stance — those are different,
  already-claimed concepts (see their own ADRs).
