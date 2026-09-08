# ADR-0283: an empty path starter pool is missing content, not a design case

**Status:** Accepted (#3682 ruling 1, 2026-09-08). Related ADR-0055, ADR-0136, ADR-0281.

**Context.** `get_technique_options` (`world/magic/services/cg_catalog.py`) builds the
character-creation technique menu by unioning two authored pools: the path's
`PathGiftGrant.starter_techniques` and the tradition's
`TraditionGiftGrant.special_techniques`. `get_gift_options` offers a gift when *either*
side is non-empty. The tradition's specials are not qualified by path, so a tradition
special can make a gift pickable on a path that offers nothing at all for it: a player on
Path of Whispers in the Metallic Order can pick Oathcraft today and receive only that
tradition's extras, because Path of Whispers has no Oathcraft starter pool.

The September 2026 alpha technique-readiness audit raised this as an open design question:
whether availability should be triple-qualified (path AND tradition) rather than unioned.

**Decision.** It is not a design question. There will never be a gift a path offers
nothing for. The union stays exactly as it is, no path-qualification filter is added, and
an empty path pool for a gift a tradition makes pickable is **missing authored content**.

It is therefore reported rather than guarded: the `path-gift-starter-pools`
`ContentDependency` (`web/admin/tuning/required_content.py`) names each `(path, gift)`
pair in that state on the required-content dashboard, alongside the `PathGiftGrant` admin
page added in the same change so staff can fill the pool they are told about. This follows
the standing rule that a missing must-exist content row gets a dashboard sentinel, never a
code guard: a guard would hide the gap behind correct-looking behaviour, and the gift
quietly disappearing from a path's menu is indistinguishable from it never having been
authored.

**Consequence.** 17 (tradition, path, gift) combinations, collapsing to 8 distinct
(path, gift) pairs, are reported as gaps on the day this lands. That is content work, and
the sentinel is how it stays visible until it is done.

**Deliberately not reported:** a `TraditionGiftGrant` with no special techniques. That is a
legitimate authored state meaning "this tradition teaches this gift and adds no unique
extras of its own"; the gift still reaches the player through the path pool, the grant
creates no availability of its own and so cannot produce this gap, and 39 of 69 authored
rows are in it. Folding those in would make the sentinel report 39 false gaps beside the 8
real ones.

**Rejected alternative.** Triple-qualify the pool so a tradition special only appears when
the path also offers the gift. Rejected because it encodes a content gap as a rule: the
menu would silently narrow wherever authoring is incomplete, and the incompleteness that
caused it would never surface.
