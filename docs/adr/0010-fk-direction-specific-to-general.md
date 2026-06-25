# FK direction is specific→general; avoid FKs to ObjectDB

A link between two systems puts the FK on the more specific/dependent side pointing at the reusable
primitive, never the reverse, so primitives (e.g. `Secret`) stay dependency-free instead of importing
every consumer; a direct FK to generic `ObjectDB` is lint-blocked by `tools/lint_objectdb_param.py`. We
rejected anchoring the FK on whichever app we happened to be editing, and FKs to ObjectDB ("could this
be a vase of flowers?") in favor of specific models like Persona or CharacterSheet.

> Status: accepted · Source: CLAUDE.md
