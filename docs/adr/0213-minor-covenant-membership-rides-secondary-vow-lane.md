# Minor covenant membership rides the secondary-vow lane

Guest ("minor") membership in a Covenant of the Durance (#2992) reuses the secondary-vow
machinery (#2641, ADR-0159) rather than adding a parallel guest tier: a MINOR-standing
membership may only occupy the secondary engagement lane, so its potency scaling, layer split,
and TIER_FLOOR weakening are the already-shipped rules. Rejected alternative: a separate guest
model or a full-power "only lit vow" mode — both would have re-litigated vow-power balance and
duplicated the #2641 layer plumbing. Consequences: minor members count for co-presence (a lone
core member with a guest is no longer dark), bypass the level-band join gate, credit legend
fully while engaged, and are DURANCE-only until a battle/court use case appears.

> Status: accepted · Source: issue #2992 spec · Confidence: verified against code
