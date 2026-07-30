# ADR-0178: Proclamations judge stance vectors, never prose; reception scales asymmetrically with the roll

**Status:** Accepted (#2842) · **Date:** 2026-07-29

Arx 1's proclamations/org stances generated excellent RP but required humans
to judge free text and hand-issue reputation changes. Arx II's rule: **prose
is for players, vectors are for mechanics** — the ADR-0175 principle
(surveillance never reads prose) extended to public speech. A proclamation's
entire mechanical content is an authored `StanceArchetype` (a *sibling* of
`PhilosophicalArchetype` — same six principle axes, worded as positions
rather than deed-judgments, so the vocabularies grow independently; Apostate
ruling) plus the stored oratory roll. Reception reuses the renown dot-product
against each society's principles, scaled **asymmetrically** by outcome tier:
aligned societies warm only on success (a failed speech wins nobody), while
opposed societies are provoked regardless — mitigated by success, taken in
full on failure, amplified on a botch. Rejected alternatives: any
LLM/agent parsing of RP text (never — unjudgeable, unfair, and it would make
prose a mechanical liability instead of a creative surface); reusing the
scandal-archetype rows directly (transgression wording would leak into stance
menus). Domain edicts ride the same act: `EdictKind` carries an inherent
stance (the social bill) and a mechanical payload (income pct, weekly unrest,
upkeep — the bite), so enacting policy IS taking a public position.
