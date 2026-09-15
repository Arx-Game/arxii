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
A mutual-exclusion (`Distinction.mutually_exclusive_with`, a symmetrical self-referential M2M, not a separate model) or variant-sibling conflict that blocks acquiring a Distinction the character already effectively holds one side of. Enforced at CG draft time (a locked offer, #3675: `offers_for` flags the conflicting choice `is_locked` with a `lock_reason`, it never picks) and, separately, by the acquisition seam's `_check_exclusions` in play (raises `DistinctionExclusionError`, which every in-play caller but the GM-award path catches and skips rather than failing the surrounding operation).
_Avoid_: conflict (use in prose, not as the canonical term), incompatibility

**Feature** (#3739):
Any single physical thing about a character that a distinction can be aimed at: one
`forms.FormTrait` row (hair colour, eye colour, horns) or one `forms.FormMarking`
(a scar, a tattoo). A species-required marker is a feature like any other.
_Avoid_: characteristic (retired model name), body part, appearance slot.

**Distinctive** (#3739):
The state of a feature the character paid to single out — a `Distinction` with
`opens_feature` held on that feature. A distinctive feature reaches every option of
its trait (the off-species Unnatural umbrella included), carries a written
description, and can hold the presence axes. Say "made distinctive", never
"unlocked", when writing player-facing words.
_Avoid_: enhanced, upgraded, special.

**Presence axis** (#3739):
Alluring, Menacing or Regal — a `Distinction` with `requires_feature_opened`, bought
on a distinctive feature, adding to the `allure` / `menace` / `regal`
`mechanics.ModifierTarget` the item accents share (#2886). "Tier" is the unit
(1 to 3 in character creation); a rank of an ordinary distinction is a "rank".
_Avoid_: aura, presence stat, accent (that word belongs to items).

**Per-feature distinction** (#3739):
A `Distinction` with `taken_per_feature` — one a character holds once per feature
rather than once, so `CharacterDistinction` carries the feature it names
(`feature_trait` or `feature_marking`, never both).
_Avoid_: repeatable distinction, stackable.

**Offer** (#3675):
Not a `distinctions` app concept: CG-time distinction picks are gated by a
`character_creation.DistinctionOffer` row, never added directly. See "Offer" in
`src/world/roster/AGENT_GLOSSARY.md`, which holds the Character Creation
domain's own vocabulary (offer, opener, arrives as, chapter, tradition state,
standard lines, schooling line, closed by route, and since #3709 enemy reason,
Appearance section, first look, held, awards, add from a table).
