# Distinctions App

Character advantages/disadvantages that mechanically modify stats, rolls, and abilities. CG-time
acquisition is `character_creation`'s job (draft storage, point budget); this app owns the
catalog (`Distinction` — including its `mutually_exclusive_with` symmetrical M2M for mutual
exclusion, `DistinctionEffect`, ...), the per-character
grant (`CharacterDistinction`), and — as of #2037 — the **single seam every post-CG acquisition
goes through**. Full model/API reference: `docs/systems/distinctions.md`.

## `grant_distinction` — the only in-play writer of `CharacterDistinction` (#2037)

`world.distinctions.services.grant_distinction(character, distinction, *, origin, rank=None,
source_description="")` is the single commit point for every in-play (post-CG) distinction
acquisition or rank-up. CG finalization (`world.character_creation.services`) and Django admin
are the only other writers — no in-play caller re-implements the create/rank-up branching.

**When touching this seam, keep these invariants:**

- `rank=None` means "advance one step," not "no-op" — 1 for a new grant, `current + 1` (clamped,
  no-op at `max_rank`) for a rank-up. An explicit `rank` only ever raises, never lowers.
- **`origin` is stamped once, at creation, and never rewritten by a rank-up.** It is
  first-acquisition provenance, not latest-touch — do not "fix" a rank-up call to overwrite an
  existing row's `origin`; that reverses a ratified #2037 design decision (see the docstring in
  `services.py` and "Post-CG acquisition" in `docs/systems/distinctions.md`).
  `DistinctionOrigin.GAMEPLAY` is vestigial — kept for schema stability, no writer assigns it.
- Exclusion checks (`_check_exclusions`, a service-layer port of `DraftDistinctionViewSet`'s
  mutual/variant checks) raise `DistinctionExclusionError`, not a DRF `ValidationError` — this
  seam has non-HTTP callers. **Every in-play caller except the GM action/telnet path catches it
  and skips just that grant** (logs, continues) rather than failing the surrounding operation —
  mirrors `_apply_capture`'s `AlreadyCapturedError` skip pattern in `world/checks/`. Adding a
  fifth source means adding this same catch-and-skip, not letting the exception propagate.
- **No XP path.** This seam never spends or checks XP — CG-time point cost does not extend past
  character creation. If a new acquisition source needs a cost gate, that is a new design
  decision, not something to bolt onto `grant_distinction`.
- Both grant and rank-up reuse the CG-time modifier machinery
  (`world.mechanics.services.create_distinction_modifiers` / `update_distinction_rank`), so the
  resonance-seed cascade (`world.magic.services.distinction_resonance`, #1834) fires
  automatically on every call — do not hand-roll modifier creation in a new caller.

**Five ratified sources** (each stamps its own `DistinctionOrigin`): `GM_AWARD` (GM action
`gm_award_distinction` / telnet `grant_distinction`, JUNIOR-tier GM), `ACHIEVEMENT_AUTO_GRANT`
(`RewardType.DISTINCTION` on `achievements.RewardDefinition`), `CONSEQUENCE_POOL`
(`EffectType.GRANT_DISTINCTION` on `checks.ConsequenceEffect`), `ENDORSEMENT_THRESHOLD`
(`DistinctionResonanceRankThreshold` in `world.magic`, fired from sustained-endorsement resonance
gain), and — as of #2441 Task 8 — `GAMEPLAY` (`world.magic.services.tradition_membership.
leave_tradition` re-applying the Unbound drawback; previously vestigial/unassigned). Full
per-source detail: `docs/systems/distinctions.md` "Post-CG acquisition" section.

**The removal counterpart is `remove_distinction` (#2628/#2631).** It requires an APPROVED
`SheetUpdateRequest` and tears down modifiers (`delete_distinction_modifiers`) and the
relocated Secret (`clear_distinction_secret`) before deleting the row. Deliberately NOT torn
down: resonance currency seeded via `DistinctionResonanceGrant` (permanent, monotonic ledger —
no clawback), `NPCAsset` rows, and codex grants. Legacy ad hoc deleters (e.g.
`world.magic.services.tradition_membership._shed_traditionless_drawbacks`) predate the seam;
new removal callers go through `remove_distinction`.

## Post-CG change requests — the `SheetUpdateRequest` framework (#2628, table-routed #2631)

`create_sheet_update_request` (PENDING, XP cost stamped at creation on the sign-based model:
add-beneficial and remove-detrimental charge `|cost_per_rank| × rank`; the other two quadrants
are free) → `approve_sheet_update_request` (atomic XP auto-debit + `grant_distinction` /
`remove_distinction`; no separate player accept step) or `deny_sheet_update_request`. An ADD
for an already-held distinction is a one-step rank-up. GM-direct grants
(`gm_award_distinction`) go through the same framework as auto-approved requests — no free
bypass. **Review pool (#2631 ruling):** staff, or a GM whose table the target character
actively sits at — enforced in both the `review_sheet_update` action and
`world.gm.services.signoff_table_update_request` (the table-routed web flow, which
creates-and-approves in one step). The cost gate lives on this framework, not on
`grant_distinction` itself — the grant seam's "No XP path" invariant (above) still holds.

## Profile Visibility — Secrets, not a boolean (#1109 → #1334)

A sensitive distinction is *relocated* into a `secrets.Secret`, not flagged public/private.
`CharacterDistinction.secret` (`OneToOneField`, `SET_NULL`) — **the FK's presence is the
secret-state**; there is no separate boolean, and `CharacterDistinction.is_secret` just reads the
FK. `mint_distinction_secret` / `clear_distinction_secret` (`services.py`) are the single
authority for minting/clearing — do not set/clear `.secret` directly anywhere else.

## Key Rules

- `grant_distinction` is the only writer outside CG finalization and admin — route every new
  in-play acquisition source through it.
- `origin` is first-acquisition provenance; never rewritten on rank-up.
- Exclusion conflicts in play are skip-and-log, not fail-the-caller (except GM action/telnet,
  which surfaces the conflict to the GM issuing the award).
- No XP gate on this seam.
- Secret relocation is FK-presence-is-state, mediated only through
  `mint_distinction_secret`/`clear_distinction_secret`.
