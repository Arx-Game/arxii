# Estate settlement is player-first and timer-backed; theft moves ownership, never history

A dead character's estate (#1985) executes through the first of three doors — a
funeral's finish (#2289's `execute_will` seam), an executor's `will_reading` action,
or an hourly sweeper at a config deadline (14 real days, PLACEHOLDER) — one
idempotent path (`execute_settlement`), first door wins. Two fail-states drove the
shape: code must never auto-execute RP players wanted to play out, and one idler
must never block everyone else's RP forever. **Retire is deliberately not a door**
(amending #2289's "retire is the backstop" note): a player may retire instantly
while the funeral is still days away, and early release must not yank the estate
from under the mourners. Debts settle before bequests (borrow-then-die is not a
loophole; killing your creditor substitutes your heir into the contract seat, it
cancels nothing). Intestacy is first-class — family-org head, then public-record
next of kin (hidden kin never auto-inherit; they must reveal to claim), then
escheat to the region's `Domain.owner_org` with corpse items' ownership cleared to
true free loot. PARKED settlements roll back to zero mutations.

We reaffirmed ADR-0091/#1025: **steal transfers the live owner pointer; the
`OwnershipEvent` ledger is the permanent history.** We rejected a sticky
rightful-owner pointer that theft can't move — it weaponizes deep fence chains
against downstream recipients who never opted into reclamation RP. Instead, the
new `receiving-stolen-goods` consent category (default-deny) gates hot-item
receipt at gives and bequests, so holding hot goods is always an OOC-acknowledged
risk, and heirs inherit `EstateClaim` grievances (never the items themselves) as
fuel for future recovery gameplay. We also rejected chained inheritance (a dead
heir's pending estate receiving on their behalf): bequests to invalid recipients
fall through the single estate-heir chain, keeping settlement deterministic.

> Status: accepted · Source: #1985, ApostateCD's design session 2026-07-13
