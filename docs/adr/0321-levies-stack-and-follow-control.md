# 0321 — Levies stack, never either/or; they name the rung, not the taker

**Status:** accepted (2026-09-29, #4060 slice 3)

The maintainer ruled (2026-09-28) that a business in a contested area may be forced to pay
both the Lord Mayor's taxes and a gang's enforcement money: "this probably shouldn't be
either/or." Income streams belong to one organization each, so a business's gross had one
owner and nobody above it took anything. **Decision:** a `Levy` is a rung plus a rate,
TAX or PROTECTION, and whoever controls that rung *right now* takes it (the Domain's owner,
the Turf's holder). At accrual a holding stream's gross loses every applicable levy up its
parent chain, each into the levy's own LEVY stream on the current controller; a contested
rung takes nothing, a controller never levies its own holdings, and the takes scale down
proportionally past 100 percent so the payer never goes negative. Only holdings pay: a
rung's own base territory yield is the controller's, not a business. The levy names the
rung and never the taker so that a turf flip moves the protection money (pool included,
as kick-up already moves) without anyone re-authoring rates; tax streams never follow a
flip, because they belong to the legitimate ladder.

**Rejected:** (a) one levy per business (either/or by construction); (b) a levy row per
controller (rates would have to be re-authored on every flip, and a deposed gang's rate
would linger); (c) levies as fealty obligations (fealty is between organizations that
swore; a levy is imposed on whoever happens to be under the rung); (d) sequential
deduction (the order of rungs would decide who gets more; proportional scaling is
order-free).
