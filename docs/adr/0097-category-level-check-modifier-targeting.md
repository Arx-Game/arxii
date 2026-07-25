# ADR-0097: Category-level check modifier targeting

## Date
2026-07-25

## Status
Accepted

## Context
`ConditionCheckModifier` matched `CheckType` by exact FK. The per-character
magic check (`ensure_character_magic_check_type`, ADR-0096) creates a distinct
`CheckType` row per PC, so no authored condition row could name it — conditions
structurally could not modify magic casts.

Three options were considered (see issue #2697):
1. Category-level match (add optional `check_category` FK).
2. Modifier hook on the cast path (leave model alone, consult conditions separately).
3. Reconsider per-character check rows (shared `Magic Check` CheckType).

## Decision
Option 1: add an optional `check_category` FK to `ConditionCheckModifier`,
mutually exclusive with `check_type`. A category-targeted row matches any check
in that category, including per-character ones.

This preserves ADR-0096's per-character check design (Option 3 would have
undone it) and is the smallest change that fixes the structural gap.

Additionally, the standalone cast path (`_resolve_cast`) and social
technique-enhanced action path (`_resolve_enhanced_action`) were wired through
`collect_check_modifiers` — they previously bypassed it, so even a matching
condition would have been invisible. The combat path already called it.

## Consequences
- `check_type` is now nullable on `ConditionCheckModifier`.
- Exactly one of `check_type` / `check_category` must be set (CheckConstraint + clean()).
- Exact-FK and category-targeted rows stack additively.
- Sibling models (`ItemCheckModifier`, `SceneCheckModifier`) share the same
  gap but are deferred to follow-up issues.
