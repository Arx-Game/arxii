# ADR-0177: One crisis engine for domains AND orgs, with a covert detection window

**Status:** Accepted (#2837) · **Date:** 2026-07-28

The generated-content loop (weighted catalog → weekly ambient spawn → judgment
menu → worsen-on-neglect → economic bite) ships once, on the existing
`DomainCrisis` machinery, generalized rather than duplicated: `DomainCrisis`
gains a nullable `org` leg (exactly-one-of domain/org), `DomainCrisisType`
gains `valence` (threat/opportunity) and `audience` (domain / org /
criminal-org), and org-target threats bite through a stream-accrual skim
symmetric with the domain income malus. We considered renaming the models
(`DomainCrisis` → `Crisis`) since the name now under-describes the row, and
rejected it: the repo's own `CRIME_KICKUP` precedent ("one machinery, two
fictions", #926) covers generalizing a model past its name, and the rename
would have swept every consumer (tidings, serializers, missions, spy payouts)
for zero behavior. Generated crises spawn **covert** (`surfaces_at`, default
+7d): hidden even from their own target until surfaced or swept — spy
`CrisisIntel` is the only early sight, which is what makes spy networks the
overseer layer instead of a report generator. Opportunities expire on
schedule even unjudged; this deliberately narrows the #2238 AFK-protection
ruling ("an unjudged crisis never worsens") to *harm* — a windfall closing is
not a punishment. Rejected alternative: a standalone org-hostility/threat
model — targeting stays episodic (per-task, per-crisis); no rivalry ledger
until play proves the need.
