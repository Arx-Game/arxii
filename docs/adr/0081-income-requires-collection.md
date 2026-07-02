# 0081 — Org income requires active collection; idle approaches stasis, never decay

**Status:** accepted (2026-07-02, #930)

The weekly economy pass no longer deposits income into treasuries. Each
`OrgIncomeStream` accrues its gross into an **uncollected pool with no cap**;
money reaches the treasury only through an active collection dispatch (a
steward summon) whose graded check outcome decides how much of the gathered
aggregate arrives — graft leaks its percentage off the *collected* amount, and
the catastrophic band loses the entire pool. Debt withholding, garnishments,
declarations, and therefore obligations all ride collection, so a truly idle
org reaches stasis in both directions: nothing it owns decays, nothing new
accrues to it or against it. The design line (Apostate): *slightly undesirable
to never collect — a hoarded pool is concentrated outcome risk and a bigger
absolute graft bite — but never a knockout for not logging in.*

**Rejected:** pool caps (a hard stop reads as punishment and hides the
risk-concentration drama); passive trickle with an active bonus (recreates the
AFK-rich-house failure the change exists to kill); decay of held wealth
(punishes absence, the other side of the forbidden line).
