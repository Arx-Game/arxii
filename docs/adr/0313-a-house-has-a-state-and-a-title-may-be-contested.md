# ADR-0313: A house carries its own lifecycle state, and a title can be contested

**Status:** Accepted (2026-09-23, #3983).

`Organization.house_state` (`HouseState`: standing/in_exile/extinct/gentry) is a field on the
house itself, set by `set_house_state`; `Title.claimant_org` lets a second house declare a claim
on a title another house currently holds (`house` stays the incumbent; `claimant_org` is the
contender), without touching who actually holds it. The rejected alternative was **inferring a
house's standing purely from per-member exile** — `OrganizationMembership` already carries
`exiled_at` for an individual, and the tempting shortcut was to read "is this house in exile or
extinct" off whether its members are. That fails on both ends: a house can be formally stripped of
standing (a crown decree, a lost war) while every one of its members personally remains unexiled,
and "extinct" (no living line left to claim it) is a fact about the FAMILY's kinship graph, not a
query over membership rows that happens to come back empty. A house's own standing needed to be a
fact recorded once, on the house, not a derivation staff would have to compute — and get wrong —
every time it mattered.
