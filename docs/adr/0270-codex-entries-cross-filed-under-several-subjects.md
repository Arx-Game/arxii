# ADR-0270: A codex entry cross-files under several subjects through a dedicated link table

**Status:** Accepted (#2896). Related ADR-0221 (visibility), ADR-0238 (content durability).

**Context.** `CodexEntry.subject` is a single required FK: an entry lives in exactly
one place in the category/subject tree, which is also the subject used for
same-subject wikilink preference in `resolve_codex_links`. Staff want an entry
(e.g. a treaty that touches two houses) to also show up in a second subject's
listing without copying its content or picking a new canonical home.

**Decision.** Add `CodexEntryFiling(entry, subject, sort_order)`, a dedicated
link table with a unique `(entry, subject)` pair, `services.file_entry_under`/
`unfile_entry` as the only sanctioned mutation path, and CASCADE from both
sides. `CodexEntry.subject` stays untouched and remains the entry's one
canonical home; a filing is a secondary listing only, never a second home.

**Rejected.** A `CodexEntry.subject = ManyToManyField(CodexSubject)` replacing
the single FK: `breadcrumb_path` is one deterministic walk up one `parent`
chain per subject today; with an entry M2M, every entry would carry a *set* of
breadcrumb paths (one per member subject) instead of one, and every caller
that currently reads "the" breadcrumb for an entry (wikilink same-subject
preference, the entry detail page, the perspective/perspective_of surfaces)
would need to pick one out of the set or render all of them - breadcrumb-path
explosion for no offsetting benefit, since staff only ever want *one* extra
listing, not an entry with no fixed home at all. A `CodexSubject.entries =
ManyToManyField(CodexEntry)` replacing the subject's reverse FK instead: a
subject's listing would then have to be built by copying/attaching every
entry into every subject that wants to show it, duplicating the same rows
across whatever part of the subtree wants them rather than adding one small
cross-reference row per (entry, subject) pair - whole-subtree duplication in
exchange for the same feature this link table gives for one row per filing.
