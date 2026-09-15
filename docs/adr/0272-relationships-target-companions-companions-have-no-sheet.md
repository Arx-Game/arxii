# ADR-0272: A relationship may target a Companion; companions do not get a CharacterSheet

## Status
Accepted (#3575)

## Context
The 2026-09-01 ruling: a bonded companion falling surges its owner iff the owner holds a
relationship to it, on the one bond currency the surge engine reads
(`CharacterRelationship` track progress on a `fuels_escalation_spikes` track). A
`CharacterRelationship` could only point at a `CharacterSheet`, and a companion has none
(ADR-0088). Two ways to close the gap: give the `CompanionObject` a sheet and PRIMARY
persona at bind, or let the relationship point at the `Companion` row.

## Decision
`CharacterRelationship.target` is nullable and a sibling `target_companion` FK to
`Companion` is added, exactly one set (two partial unique constraints replace the old
pair constraint). `DramaticSurgeRecord` gains the matching `subject_companion` subject.
Companions still have no sheet. Only the bonded owner may hold such a row and it is active
from creation (the bind is the consent); the rule is app-layer only because a check
constraint cannot compare `source` with `target_companion.owner` across tables. The
companion's defeat emits `CHARACTER_INCAPACITATED` from the opponent damage path, never
`CHARACTER_KILLED` (defeat is not death; #1873 resolves death at encounter end).

## Alternatives rejected
- **A sheet and persona for every companion.** Roughly thirty room-presence walkers read
  `sheet_data` and would treat the wolf as a person: it would count toward a scene round's
  declaration quorum (`round_services.py`, quorum default 60 percent) and stall rounds,
  count as a conscious bystander for abandonment (`vitals/services.py`), and be enrolled,
  observed, witnessed or addressed by cast observation, ceremony leak, precapture, ambient
  narrative and covenant perks. ADR-0088 and the `Companion.objectdb` comment already lean
  on companions having no sheet.
- **A bespoke companion-bond model.** Rejected by the one-bond-currency ruling and the
  standing rule against a model per mechanic.

## Consequences
Every reader of `relationship.target` must tolerate `None`: the model exposes
`target_name`, writeup kudos and complaints treat a companion writeup as subject-less, and
the relationship pull terms in `world.magic` return no bond term for a companion-targeted
thread. `ALLY_PERIL` stays inert for companions: acute peril is `BLEED_OUT` on the
participant vitals path, and an opponent has no peril band. Non-owner relationships toward
a companion are refused rather than left pending forever.
