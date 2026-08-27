# ADR-0233: Sentences are enforced by a daily sweep, and exile rides the existing heat ladder

Four decisions from the #2378 sentence-enforcement slice. **(1) Enforcement is a daily
sweep** (`sentence_sweep_tick`, cron `justice.sentence_sweep`) that serves matured brig
terms and carries out due terminals, **plus public marks derived on read**
(`active_public_marks` — term-limited by arithmetic, no stored row). Rejected: modeling
a served sentence as an expiring `CharacterDistinction` — no expiry/decay machinery
exists on that model today, and removing a Distinction is gated behind the
human-reviewed `SheetUpdateRequest` flow, wrong for something a cron must retract
automatically at term end. **(2) Exile is a heat pin riding the existing max-tier
pursuit ladder** — `ExileDecree` + `PersonaHeat.pinned_until` floored at
`EXILE_PIN_VALUE` (`pin_heat_for_decree`), read by the same `maybe_guard_encounter`/
evasion machinery heat already drives. Rejected: a bespoke area-ban wall — a parallel
access-control layer duplicating what heat + guard encounters already do, and blind to
the sanctuary/cross-border jurisdiction rules ADR-0080 already worked out for heat.
**(3) The terminal fork** — `terminal_kind_for` routes EXECUTION only when ADR-0023's
lethal wall (`_execution_reachable`, unchanged) lets it through; every non-opted-in PC
terminal instead lands BANISHMENT, the new non-lethal terminal (a heat pin + ejection,
permanent unless pardoned). This *amends* ADR-0023's scope note — see the line added
there — rather than superseding it: the wall itself, and everything it already gated,
is untouched; BANISHMENT only supplies the terminal that used to have no non-lethal
landing spot. **(4) The sentencing ladder is data, per society** (`SentenceLadderRung`,
keyed on `(society, level)`, `level` matched against `failed_outs - 1`): each society
escalates repeat offenders its own way, with `ARENA_TRIAL` seeded as an inert rung
(substituted for `BRIG_TERM` at consult time, never gated behind the lethal wall since
it isn't lethal) pending the combat substrate that would let it resolve as a fight.
Rejected: one hardcoded escalation table — the reviewed realm sketches (Luxen vs.
Umbros/Inferna) already want different ladders, and a hardcoded table would need a
code change per society to author one.

> Status: accepted · Source: #2378 spec, world/justice/sentences.py, world/justice/pipeline.py
