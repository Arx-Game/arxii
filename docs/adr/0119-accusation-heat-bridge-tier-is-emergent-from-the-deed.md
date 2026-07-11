# The accusation→heat bridge lives justice-side, and its tier is emergent from the real deed underneath

A *criminal* frame-job (#1825) must do more than dent reputation (ADR-0114) — it must land
**pursuit heat** on the framed target, so a false accusation can get someone hunted, arrested,
or worse. The bridge is a single justice-side model, `AccusationCrimeClaim`
`(secret OneToOne → secrets.Secret, crime_kind, real_deed nullable → LegendEntry)`, plus three
services (`record_accusation_crime`, `accrue_accusation_heat`, `file_criminal_accusation`).
`accrue_accusation_heat` defers to the existing `accrue_heat`, so a frame obeys the same
jurisdiction rules as a real crime: heat mints only where the area's law criminalizes the
alleged kind, and it lands on `subject_sheet.primary_persona`. Actorship is never checked —
falsity stays emergent (ADR-0114, #1765).

**Two deliberate decisions.**

1. **The link is justice-side, never on `Secret`.** Per ADR-0010, the FK joining two systems
   lives on the more specific/dependent one and points at the reusable primitive. `Secret` is
   the primitive; justice is the consumer. So `AccusationCrimeClaim` points *into* `secrets`,
   and the composition `file_criminal_accusation` lives in justice (justice → secrets is the
   allowed import direction). `secrets` stays unaware of justice — it never learns what a crime
   or a heat row is. We rejected adding a `crime_kind` FK onto `Secret`: it would make the
   general scandal primitive import the justice taxonomy, exactly the coupling ADR-0010 forbids.

2. **The tier is emergent from `real_deed`, not a stored level.** The player-facing severity of
   a criminal accusation is not a number the accuser dials — it is a fact about how much real
   crime sits underneath, captured by whether `real_deed` is set:
   - **Wild accusation (L2)** — `real_deed` null. A named `crime_kind` with no crime underneath
     ("they murdered someone I invented"). It still mints heat, but it is fragile: scrutiny
     finds no corroborating deed, so it is easily refuted.
   - **Frame for a real crime (L3)** — `real_deed` anchors a crime that genuinely happened (the
     accuser, often the true culprit, shifting blame) but which the subject did not commit.
     Robust: the crime is real, so refuting it means proving the subject's *innocence*, not
     disproving the crime.

   This makes the later counter-play difficulty fall straight out of the data — an investigation
   against a wild L2 succeeds precisely because there is no deed to corroborate, while an L3
   frame resists because the deed is real. We rejected a stored `severity`/tier field on the
   claim: it would be a magnitude to tune and could contradict the deed, whereas
   `real_deed is None` is a fact that cannot lie about itself.

> Status: accepted · Source: #1825, Apostate ratification 2026-07-11
