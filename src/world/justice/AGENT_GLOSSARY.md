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
- **Accusation crime claim** — an `AccusationCrimeClaim` row; the bridge from a
  player-authored ACCUSATION `Secret` (frame-jobs, #1825) into heat. Carries the
  alleged `crime_kind` and an optional `real_deed`.
- **Wild accusation** — an accusation crime claim with no `real_deed` (an L2):
  a named crime with nothing underneath. Mints heat but is fragile — easily
  refuted, because scrutiny finds no corroborating deed.
- **Frame** — an accusation crime claim whose `real_deed` anchors a crime that
  genuinely happened (an L3), pinned on someone who did not commit it. Robust:
  refuting it means proving innocence, not disproving the crime. _Avoid_:
  using "frame" loosely for any false accusation — a wild accusation is not a frame.
- **Crime evidence** — a `CrimeEvidence` row: the physical traces a crime-tagged
  deed left at its located scene (one per deed). Gathered, it becomes a real
  `ItemInstance` (holdable/givable/stealable); holding it is itself a lead.
  _Avoid_: "clue" for the physical object — the clue is the `clues.Clue` pointer.
- **Gather / dispose / tamper** — the criminal's post-crime evidence moves
  (#1825): gather claims it (Skulduggery), dispose destroys it (dampens future
  deed-knowledge heat), tamper perverts it through a frame-job project.
- **Workshop of Iniquity** — the criminal-projects `RoomFeatureKind`; frame jobs
  require standing in one. Future counterfeiting/heist planning shares the gate.
- **Frame job** — the FRAME_JOB `Project` (payload `FrameJobDetails`) that
  doctors gathered evidence into an anchored L3 accusation. Consent-gated at
  start AND re-checked at completion.
- **Tamper quality** — `CrimeEvidence.tamper_quality`: the forger's recorded
  craft; the Scrutinize Evidence examine check's target difficulty.
- **Nullification** — an `AccusationNullification` row: the investigation's
  proof of fabrication. Reverses reputation, zeroes gossip heat, retracts the
  crime claim, and mints the **authorship secret**. The accusation Secret stays.
- **Authorship secret** — the ACTION_ANCHORED secret *about the framer* a
  nullification mints (granted to no one) — the author-unmask trail's target
  and the denounce verb's ammunition.
- **Denounce** — `denounce_framer`: exposing the authorship secret at a hub
  (reputation via the normal engine + false-accusation heat scaled by the
  original accusation's level). The ONE consent-gated counter-play move
  (Tom/Bob/Fred rule); once per denouncer (`DenounceRecord`).
- **Case file** — where OFF_GRID frame evidence lives (not a model — the state
  plus its `AccusationCrimeClaim`). Produced back out by local authority
  (`has_local_authority`, PLACEHOLDER predicate pending #2378), then examined.
