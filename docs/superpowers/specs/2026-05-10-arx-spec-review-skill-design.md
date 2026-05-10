# Follow-up: arx-spec-review skill

**Date:** 2026-05-10
**Status:** Deferred follow-up (build after Covenants Slice A ships)
**Owner:** Tehom

## Context

During the Covenants Slice A brainstorm (2026-05-09 → 2026-05-10), Tehom flagged that I had written service-function descriptions that included user-input validation logic — a recurring violation of the project's `URL → View → Serializer → Service` pattern. The rule lives in `CLAUDE.md` ("Validation belongs in serializers, not views or services") but both the LLM (me) and humans miss it during active design work.

Tehom's diagnosis: a personal Claude memory only helps me; it doesn't help his brother (the main developer). Architectural enforcement must live in source control.

## Proposal

Build a project-level skill — `arx-spec-review` — that lives in the repo (so both developers get it via git), and is invoked by the `superpowers:brainstorming` flow's spec-review step (as a richer alternative to the generic `spec-document-reviewer-prompt`).

### Location

`.claude/skills/arx-spec-review/SKILL.md` (project root, in source control)

### Role

- Invoked from the brainstorming-flow spec-review step
- Also runnable on demand: `/arx-spec-review <path>` against any spec in `docs/superpowers/specs/`
- Sibling skill `arx-code-review` for diff-time enforcement of the same rules

### Rule corpus (initial)

Drawn from `CLAUDE.md` + lessons earned during recent specs. The skill should reference `CLAUDE.md` sections rather than duplicate them where possible, to minimize drift.

- **Service functions don't validate** — `URL → View → Serializer → Service`. Validation lives in serializers; services perform atomic operations on already-validated data. Defensive type-error checks are OK but rare. (See `feedback_service_functions_dont_validate.md` in personal memory for full context.)
- **Never use polymorphic models** — hard project rule. Flag any spec proposing multi-table inheritance or `polymorphic` library use.
- **No JSONField for cross-model references** — flag any proposal that uses a JSONField to hold what should be FKs.
- **No `.filter()` on SharedMemoryModel related managers** — services must use cached handlers; `.filter()` defeats the identity-map cache.
- **Avoid denormalization** — flag any "cached copy of related field" pattern. Particular attention to denormalized FKs that can contradict (the parent/child FK pattern in CLAUDE.md).
- **Avoid direct FKs to ObjectDB** — should be more specific (Persona, RosterEntry, CharacterSheet, RoomProfile). The "could this be a vase of flowers?" test from CLAUDE.md.
- **TextChoices in `constants.py`** — not nested inside models.
- **SharedMemoryModel for all concrete models** — enforced by pre-commit linter, but the spec should not propose plain `models.Model`.
- **No queries in loops** — flag recursive serializers without bounded prefetch, while-loops over relationships, etc.
- **FilterSets in views** — flag any `request.query_params` access in views.
- **Constants over spaceless string literals** — flag string-literal returns or comparisons.
- **`cached_property` from `django.utils.functional`** — never `functools.cached_property` (silently breaks `Prefetch(to_attr=...)`).
- **`Prefetch(to_attr=...)` with `cached_property`** — never bare strings in `prefetch_related()`.
- **No management commands** unless explicitly requested.
- **No backwards-compatibility shims in dev** — accept only the current format.
- **PostgreSQL features OK** — no SQLite-compatibility workarounds.

Each rule entry should include: a one-line restatement, "what to look for in the spec," "why this is a problem if violated," and a pointer to the relevant `CLAUDE.md` section.

### Maintenance

Keep the skill thin. Reference `CLAUDE.md` rather than duplicate. The skill's value is the *workflow* (running review with arx context loaded) and the *enumeration* (a checklist that's easier to skim than CLAUDE.md), not a parallel rule corpus.

When CLAUDE.md gains a new rule, the spec-review skill is updated in the same PR. When a spec review surfaces a new pattern worth enforcing, both `CLAUDE.md` and the skill are updated together.

## Build process

Use `superpowers:writing-skills` to design and implement. The skill should:

1. Have a clear `description` frontmatter so Claude Code surfaces it appropriately
2. Include a checklist that maps to each rule
3. Reference `CLAUDE.md` sections by anchor where possible
4. Output the same `Approved | Issues Found` format as the generic spec-document-reviewer (so the brainstorming flow can ingest it)

## Why deferred

Tehom chose to finish Covenants Slice A (spec → plan → implementation) before pausing to build this. The violation that surfaced this work has been addressed in the Covenants Slice A spec post-hoc; future specs will benefit from the skill once it ships.

## Cross-references

- Today's violation context: §4.4 of `docs/superpowers/specs/2026-05-09-covenants-slice-a-design.md`
- Rule source: `CLAUDE.md` "Validation belongs in serializers, not views or services"
- Personal memory (insufficient on its own; this doc supersedes for cross-developer enforcement): `feedback_service_functions_dont_validate.md`
