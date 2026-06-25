# Covenants are group-only (min 2 members)

A covenant is inherently a group structure: `create_covenant()` rejects fewer than two distinct
founders (`InsufficientFoundersError`), and active membership falling below the minimum auto-dissolves
the covenant; we rejected solo oaths. A covenant of one is a contradiction, so the floor is enforced
at both formation and attrition.

> Status: accepted · Source: covenants.md · Confidence: derived-from-roadmap, verify against code
