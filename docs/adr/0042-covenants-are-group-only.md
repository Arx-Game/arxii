# Covenants are group-only at formation (min 2 founders)

A covenant is inherently a group structure: `create_covenant()` rejects fewer than two distinct
founders (`InsufficientFoundersError`); we rejected solo oaths. **Amended 2026-08-11 (#2992):**
the attrition half of this rule — auto-dissolving when active membership fell below two — is
removed. Covenants are magically core to their characters and accrue shared legend
(`CovenantLegendCredit` → covenant level); destroying that identity through member churn was an
artifact of thinking of covenants as ad-hoc clubs. A covenant now persists at one or even zero
active members (minor members can keep a lone core member's vow lit; an empty covenant is inert
but its legend endures). Formation still requires two.

> Status: accepted (amended by #2992) · Source: covenants.md · Confidence: verified against code
