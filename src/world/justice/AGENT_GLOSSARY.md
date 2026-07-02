# Justice — Agent Glossary (#1765)

- **Heat** — how actively local forces hunt a *persona* in an *area*; the
  `PersonaHeat.value` int, always displayed as a `HeatTier`, never a number.
  _Avoid_: notoriety (rejected name), wanted-level. **Not** the comfort system's
  `StatKey.HEAT` (temperature) — different namespace, different app.
- **Warrant (row)** — one `PersonaHeat` row: `(persona, area, enforcing society)`.
  Informal term used in docstrings; there is no `Warrant` model.
- **Crime kind** — a `CrimeKind` row; the normalized vocabulary laws reference.
  **CONTENT RULE (user-ratified): no sexual crimes of any nature are ever
  represented — no rape/sexual-assault kinds, in seeds, admin, or fixtures.**
- **Law** — an `AreaLaw` row; most-specific-wins up the area tree; `exempts`
  short-circuits. The winning row carries the local posture (`heat_weight`).
- **Enforcing society** — nearest `Area.dominant_society` above the *winning
  law's* area; jurisdiction boundary for both minting and reading heat.
- **Deed** — here always `societies.LegendEntry` (what `DeedCrimeTag` and
  `HeatSource.deed` reference), **not** `missions.MissionDeedRecord`.
- **Association / outing** — copying a mask persona's heat onto another persona
  (`associate_heat`); the identification gameplay. First writer: mission-report
  association chance; #1334 secrets outing plugs in later.
- **Allegation** — a `HeatSource` row; recorded, never verified against
  actorship. False accusations are emergent, not flagged.
- **Sanctuary** — an area (usually BUILDING level) whose `dominant_society`
  differs from the surrounding jurisdiction; reads SAFE by the same mismatch
  rule as cross-border immunity. Not a model — a data pattern.
