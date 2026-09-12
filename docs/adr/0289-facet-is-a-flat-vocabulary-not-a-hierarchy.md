# ADR-0289: Facet is a flat vocabulary, not a Category > Subcategory > Specific hierarchy

`Facet` carried a `parent` self-FK forming a Category > Subcategory > Specific tree, which made a
node's mechanical reach depend on how deep it sat — picking "Hawk" matched far fewer items than
picking "Bird" for the same thematic intent, because one tree was trying to be both a picker (wants
breadth, so a player can find the exact word) and a matcher (wants a small, fair, equal-weight
vocabulary, so every choice is worth the same) at once; #3776 dropped `parent` and made every facet
a peer, with `name` now unique across the whole vocabulary, so the pool a character binds through
`MotifResonanceAssociation`, a `WorshippedBeing` binds through `BeingFacet`, and an `ItemTemplate`
stamps through `inherent_facets` is one shared flat list. We rejected keeping the hierarchy and
normalizing reach at match time (an ancestor walk on every comparison, which buys the tree's
breadth back at the cost of making the fairness rule invisible to the player picking the word) and
rejected keeping it purely as an authoring convenience (a tree nobody may read is a tree that
silently rots).

> Status: accepted · Source: issue #3776 (Task 1), the reviewer's 2026-09-11 ruling
