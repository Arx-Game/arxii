# Visibility = eligibility: one predicate, no locked options

A single `eligibility_rule` predicate decides both whether an option appears and whether it can be
selected, so there is no separate visibility layer and no greyed-out "locked, here's how to unlock"
UI; we rejected splitting visibility from selectability. If you can't pick it, you don't see it — one
rule, no teasing locked rows.

> Status: accepted · Source: design-tenets.md, npc_services
