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

**The asymmetry rule (Apostate):** *automatic loss is fine; automatic gain is
not.* Every creditor claim therefore collects **at source** from the amassing
pools each cycle, before the debtor can touch a copper: contractual debt
service (`_service_debts_from_pools` — oldest first, capped at what the pools
hold, `diverting` debts skipped so the embezzlement-discovery loop survives)
and defaulted-contract liens (`_service_contract_liens_from_pools` — the
agreed percent of the fresh gross; there is deliberately NO separate
landing-time garnishment machinery). Debts feel like big deals and
unavoidable; counterplay is dramatic — refute, go to war, get them
cancelled — never a collection-scheduling dodge.

**Rejected:** pool caps (a hard stop reads as punishment and hides the
risk-concentration drama); passive trickle with an active bonus (recreates the
AFK-rich-house failure the change exists to kill); decay of held wealth
(punishes absence, the other side of the forbidden line); debt service waiting
for collection (rewards an indebted house for never collecting — inverts the
asymmetry rule).
