# Battles — Glossary

Canonical vocabulary for `world.battles` (#1592, #1711). Use these terms in code,
docs, and issues; avoid synonyms.

- **Front / Place** — a `BattlePlace`: a named zone within a battle (e.g. "The Main
  Gates"). Not a room; battles are location-less (see ADR-0081).
- **Unit** — a `BattleUnit`: an abstract typed force (friendly or enemy) stationed at
  a place. Never "squad," "regiment," or "mob" in code/docs — "unit" is the term.
- **Composition** — a `BattleUnit`'s `UnitComposition` (infantry, cavalry, archers,
  siege, flying, naval, magical, irregular) — the mechanical type driving
  type-matchups and terrain effects. Distinct from `descriptor`, which is flavor text
  only.
- **Descriptor** — a `BattleUnit`'s free-text flavor tag (e.g. "zombies-on-nightmares").
  Narrative only; never mechanical. (Renamed from the spine's `unit_type` — #1711.)
- **Quality** — a `BattleUnit`'s `UnitQuality` tier (militia through elite); a flat
  check-difficulty modifier ladder, not a strength multiplier.
- **Commander** — the `CharacterSheet` assigned to `BattleUnit.commander`; their
  Battle Command modifier-walk bonus applies to participants on the same side/place.
  Never "leader" (reserved elsewhere — `Covenant.leader` is a distinct, COURT-only
  concept) or "general."
- **Type-matchup** — a `TechniqueCompositionAffinity` row: a technique's authored
  effectiveness against a specific composition.
- **Terrain effect** — a `TerrainCompositionEffect` row: a terrain type's authored
  effect on a specific composition's ease-of-strike.
- **Posture** — a `BattleSide`'s `BattlePosture` (balanced/aggressive/defensive):
  the pre-battle tactical trade-off between VP-gain speed and check
  difficulty/failure damage. Never "stance" or "tactics mode."
- **Military summon** — a `summon_ally` cast with `payload.military=True`: creates a
  `BattleUnit` (not a `CombatOpponent`) for a summon too potent for a skirmish. See
  `_summon_military_unit` in `world.magic.services.effect_handlers`.
