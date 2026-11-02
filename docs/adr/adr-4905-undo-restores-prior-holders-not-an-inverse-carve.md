# ADR-4905: The map's undo restores each pip's prior holder; it never inverts the carve

**Status:** Accepted (built #4905; related ADR-0328, #4317)

**Decision.** Every footprint write on the region map, `set_footprint` and `clear_footprint`,
reports what it did per pip: `(x, y, holder before, holder after)`. The page keeps those
lists as its undo and redo stacks and writes one column back through `restore_pips`
(`atlas_restore_footprint`), which gives each named pip its named holder, or open ground
for None, with no containment rule beyond the staff gate: a restore reproduces a state the
map has already been in. **Rejected:** undo as the inverse carve (remove what the gesture
added, add back what it removed, through `set_footprint`). It is wrong whenever the prior
holder was higher than the ladder parent: `_release` hands a pip to the parent, not to
whoever held it, so undoing a county carved out of kingdom-held land would leave the pip
with the duchy between them, and `_claim` cannot push a row back up past a descendant.
The restore write is a few lines and exact; the inverse is free and silently wrong on the
common top-down carve (realm first, then its duchies and counties). The cost is one more
staff action and a page that remembers prior holders per gesture rather than per domain.
