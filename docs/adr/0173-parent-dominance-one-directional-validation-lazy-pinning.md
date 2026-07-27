# ADR-0173: Parent Dominance validates one-directionally at creation time, with lazily-pinned parent stubs

**Status:** Accepted (2026-07-27, #2815)

Species inheritance (maternal-dominant; paternal flip on a strictly-greater power
band; chimeric only when both parents are Grand+) is enforced **only at the moment a
child is created**: a species flip, off-palette inherited color, or chimeric child
requires parental bands that support it *then*, and nothing is ever re-validated
afterward. Because trait expression is chance, a GM retroactively defining a
player-invented parent as powerful contradicts nothing — it just never showed. The
same lazy principle drives parent data: players author nothing beyond names; an
undefined mother is pinned to the child's species at approval, and a child's
off-palette color pick is attributed to the cross-species parent as a
`KinspersonTraitValue` pin (get_or_create — the first child to draw on an unpinned
trait defines it, and later siblings are constrained by it). Tree of Souls children
carry the dominant role via `ParentageEdge.is_ritual_invoker` (a fact about the
ritual, not a gendered slot — ADR-0097's retired mother/father model stands).

**Rejected:** a species-affinity flag on `FormTraitOption` ("this color is human") —
derivable from `SpeciesFormTrait` palettes, and dual-maintained flags drift; storing
inherited-trait provenance on the character instead of pinning parents — siblings
could then give the same father contradictory colors, destroying the family
consistency the system exists for; a separate heredity app — the kinship graph the
rules read already lives in roster, and splitting parentage data across apps helps
no one. Also deliberate: player-invented parents can never carry a power band
(species flips and chimeric children descend only from staff-authored kinspeople),
and dominance never re-checks when bands change later.
