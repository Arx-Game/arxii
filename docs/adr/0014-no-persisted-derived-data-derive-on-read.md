# No persisted derived data; derive-on-read

Derived or synthesized values are computed on read — in-memory `cached_property` is fine — and never
stored as DB rows or columns, so the source data stays the single truth; we rejected denormalized
"synthesized" rows. For example, a covenant member's effective speed and sub-role are derived per
character per thread-level on read, not cached on a participant row.

> Status: accepted · Source: memory, covenants.md
