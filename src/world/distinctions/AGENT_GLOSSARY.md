# Distinctions glossary

**Distinction**:
The catalog definition of a character advantage or disadvantage (`Distinction`) — a rankable, costed trait that mechanically modifies stats, rolls, or abilities via its `DistinctionEffect` rows. Not a per-character record; see CharacterDistinction.
_Avoid_: perk, feat, trait (too generic — see `traits` app for the separate stat system)

**CharacterDistinction**:
The per-character record of an acquired Distinction — its rank, origin, and optional secret relocation. The unit every acquisition source (CG or in-play) ultimately creates or updates.
_Avoid_: distinction grant (that names the act, not the record), character trait

**Origin**:
`CharacterDistinction.origin` (`DistinctionOrigin`) — the acquisition's **first-acquisition provenance**, stamped once at creation and never rewritten by a later rank-up. A distinction originally earned via `ENDORSEMENT_THRESHOLD` keeps that origin even after a GM manually ranks it up. Distinct from `source_description` (a free-text audit note on the same call). Values: `CHARACTER_CREATION`, `GAMEPLAY` (vestigial — no writer assigns it), `GM_AWARD`, `ACHIEVEMENT_AUTO_GRANT`, `CONSEQUENCE_POOL`, `ENDORSEMENT_THRESHOLD`.
_Avoid_: source (ambiguous with `source_description`), latest touch, last-granted-by

**Acquisition seam** (`grant_distinction`):
The single service function every in-play (post-CG) Distinction grant or rank-up calls — the only writer of `CharacterDistinction` outside CG finalization and Django admin. "Acquisition" covers both a brand-new grant and a rank-up of a held Distinction; both go through the same call.
_Avoid_: award function, grant handler

**Distinction Exclusion**:
A mutual-exclusion (`Distinction.mutually_exclusive_with`, a symmetrical self-referential M2M — not a separate model) or variant-sibling conflict that blocks acquiring a Distinction the character already effectively holds one side of. Enforced at CG draft time (blocks the stage) and, separately, by the acquisition seam's `_check_exclusions` in play (raises `DistinctionExclusionError`, which every in-play caller but the GM-award path catches and skips rather than failing the surrounding operation).
_Avoid_: conflict (use in prose, not as the canonical term), incompatibility
