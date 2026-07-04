# The watched player is always OOC-aware

Concealment can hide who or what is present, but never *that* someone is present, and there is no
`staff_only_can_see` hidden-observer backdoor; we rejected invisible observation. A player is always
OOC-aware they may be perceived — a structural privacy floor that no concealment or staff path may
breach.

`#1225`/ADR-0083 later built the concrete mechanism (`ConditionCategory.conceals_from_perception`,
the identity-free OOC observer notice) that satisfies this tenet.

> Status: accepted · Source: design-tenets.md · Related: ADR-0083 (the concrete
> OOC-transparency mechanism, #1225)
