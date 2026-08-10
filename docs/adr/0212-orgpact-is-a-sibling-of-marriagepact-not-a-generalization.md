# ADR-0212: OrgPact is a sibling of MarriagePact, not a generalization

**Status:** Accepted (#2999, 2026-08-10)

The general diplomacy instrument (`OrgPact` + authored `PactKind` levers —
allied stature share, income tithe, non-aggression, mutual defense; ADR-0178's
payload rule) is a **separate model beside** `MarriagePact`, not a superclass
absorbing it. Marriage is genuinely different in kind: it is *embodied*
(union-bound, dissolves the instant a spouse dies), carries person-moving
commitments (dowry/subsidy/residency executors), and its formation is a
kinship event (betrothal → wedding rite) rather than a leadership signature.
Folding both into one model would either bolt nullable union machinery onto
every treaty or flatten marriage's death-seam semantics into paper terms.
Both instruments feed the same stature allied slot and the same dossier, so
consumers see one diplomacy surface. Betrayal is a stamped world event
(BETRAYAL dissolution reason + permanent prestige penalty + tidings), with
detection wired where hostile acts already resolve (offensive spy tasks; war
declarations join the same seam later). Rejected: one generalized `Pact`
model (above); prose treaty terms (ADR-0178 forbids — every effect is a
typed lever); auto-minting consort regional peace as OrgPact rows (predator
targeting already reads consort unions directly since #3093 — a second
surface would double-count and drift).
