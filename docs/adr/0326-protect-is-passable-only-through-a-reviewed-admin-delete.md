# 0326 — PROTECT is passable only through a reviewed admin delete

**Status:** accepted (2026-09-30, #4064)

The organization model is pointed at by nineteen `PROTECT` links (domains, fealty edges,
house templates, threads, ownership records, favor tokens, ...), each chosen so that a
row with dependants cannot vanish by accident. Django's admin honours that by stopping:
it lists the blocking rows and offers nothing, and two of the kinds that block most
often had no admin page at all, so a staff member removing a placeholder organization
had no path but a shell. **The ruling:** the guard stays exactly as it is and gains one
reviewed way through, in the admin, for a superuser, one row at a time.
`ReviewedDeleteMixin` (`web/admin/reviewed_delete.py`) rebuilds a plan from the posted
choices on every request: every blocking row is decided as *detach* (offered only where
the link is nullable and the row still validates without it) or *delete* (whose own
cascade and protectors then join the plan), nothing is preselected, and nothing is
written until every row is decided and the organization's name is typed back, then in
one transaction or not at all. **Rejected:** (a) relaxing any `on_delete` to
`SET_NULL`/`CASCADE`, which would let the shell, services and the bulk action delete
authored rows silently; (b) a `signals`-style pre-delete hook that detaches
automatically, which decides for the deleter what the ruling says the deleter decides;
(c) letting any staff account with delete permission use the review, when the content
conflict resolver already sets superuser as the bar for deleting authored rows on typed
confirmation; (d) walking the bulk "delete selected" action through one review per row,
which is easy to lose track of and defeats the one-row-at-a-time point. Related:
ADR-0237 (the production database is the only copy of authored content), ADR-0201
(credited rows are shown with their author on the review so the deleter knows whose
work goes).
