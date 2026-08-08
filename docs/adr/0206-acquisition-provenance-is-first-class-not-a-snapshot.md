# ADR-0206: Acquisition provenance is a first-class record, not a snapshot

Context: #3055 (beta-reset design) needed a way to reconstruct "pristine, as-authored"
character state at the early-access cutover — everything a staff-authored roster character
picked up during alpha play must be stripped, while what CG/authoring gave them must survive.
Two shapes were considered. The rejected one: capture a **baseline snapshot** of the
mutable-authored surface (stat/skill values, known technique/gift/distinction sets) at a staff
"mark baseline" moment before a character enters play; reset = delete play-state rows + restore
the snapshot. The accepted one: record **why** every acquisition happened, as a first-class
domain fact, and derive pristine state by filtering on it — strip every row whose acquisition
provenance is play-time, and whatever carries CG/authoring provenance IS the baseline. The
generalized pattern already existed in one place (`distinctions.DistinctionOrigin`); this ADR
extends it to the rest of the mechanical surface that had none: `CharacterTechnique.origin` and
`CharacterGift.origin` (`AcquisitionOrigin`, `world/magic/constants.py` — CHARACTER_CREATION /
PATH_GRANT / SPECIES_GRANT / TRAINED / ROLE_GRANT / ORGANIZATION_GRANT / ALTERNATE_SELF_GRANT /
AUTHORED / GM_GRANT), `traits.CharacterTraitChange` (a new durable record of every in-place
`CharacterTraitValue.value` mutation — old_value/new_value/source, since a stat raised in place
left no receipt at all, unlike XP/resonance/class-level which already had adequate ledgers), and
`CharacterAchievement.earned_by_tenure` (required FK, mirroring `Discovery.discovered_by_tenure`
from the sibling #3060 slice). Snapshotting was rejected for two reasons: it is reset-specific
bookkeeping that answers only "what was true then," where provenance answers "how did this
happen" — a strictly more useful fact that also unlocks acquisition events becoming GM-grantable
story rewards (#3055 slice 1c, `GM_GRANT` origin values reserved now so that slice needs no
further migration); and a snapshot is a second copy of truth that can drift from the live rows it
was taken from, where provenance lives beside the value it explains and is written in the same
transaction as the mutation, by construction.

> Status: accepted · Source: #3055 slice 1b · Related: ADR-0009 (no signals — every writer calls
> the provenance write explicitly), #3060 (Discovery.discovered_by_tenure, the RosterTenure-anchor
> pattern this generalizes for CharacterAchievement)
