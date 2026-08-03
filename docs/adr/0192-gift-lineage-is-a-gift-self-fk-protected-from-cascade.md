# ADR-0192: Gift lineage is a `Gift` self-FK, and it is PROTECTed rather than CASCADEd

**Status:** Accepted · **Date:** 2026-08-03 · **Issue:** #2891 (prerequisite for #2764)

Shared species material lives in an umbrella `Gift`, and each kind's gift hangs beneath it via
`Gift.parent` (self-FK, `related_name="children"`). **Holding a gift reaches the techniques of
that gift and of every ancestor, and the character's GIFT thread on the held gift is the thread
for all of them** — one `CharacterGift`, one thread. `on_delete` is **`PROTECT`**, deliberately
unlike the two existing self-FK hierarchies in the codebase.

**Why a gift-chain at all.** The shipped Vampire/Dhampir pattern (#2692) expresses shared
material as a second `SpeciesGiftGrant` row, which gives the character a second `CharacterGift`
and a second GIFT thread. Thread level rises through the Rite of Imbuing, which charges AP per
rite (`_charge_imbue_ap`) plus XP at locked boundaries (`cross_thread_xp_lock`). So every Khati,
Elf, Infernal and Vampire would pay twice to develop both gifts while a Human or Lycan pays
once. The third option — one self-contained gift per species — costs the player nothing but
duplicates the shared senses across every sibling, so a change to one shared sense is four
edits. `Gift.parent` is the only shape that is both one thread and one copy.

`SpeciesGiftGrant.inheritable` is **not** made redundant: it walks the *species* chain
(`Species.parent`), this walks the *gift* chain. `Dhampir.parent = Vampire` still propagates
Vampire's grant. Both axes are needed.

**Why PROTECT.** `Species.parent` (`world/species/models.py`) and `Facet.parent`
(`world/magic/models/motifs.py`) both CASCADE, and consistency argued for a third. It was
rejected because the analogy does not hold: a subspecies row and a facet leaf are taxonomy
entries that are meaningless without their parent, whereas a child gift is a **self-standing
playable gift** that characters hold (`CharacterGift`) and thread (`Thread.target_gift`).
Cascading from the umbrella would delete gifts carrying live character state. `CharacterGift.gift`
is already `PROTECT`, so a *held* child would raise `ProtectedError` anyway — but only once
someone holds it; on an authoring database the cascade silently wipes the kinds and takes their
techniques' `gift` FK with them. PROTECT makes re-parenting an explicit authoring step.

**Rejected.** *`SET_NULL`* — orphans the kinds instead of deleting them, which is worse: the
gift survives but silently stops reaching the shared material, so the bug surfaces as a player
who quietly can no longer learn their species' senses. *A downward `descendants` walk* on the
umbrella (query children, then their children) instead of the upward `lineage` — rejected because
every load-bearing question ("does this learner own it?", "which techniques does this gift
reach?", "which thread governs this technique?") is asked from the held gift, so the upward walk
answers all three and mirrors `Species.lineage` (PR #2897) exactly, seen-set cycle guard and all.
A second walk shape would have been the reinvention this repo pays most for.

**Consequence.** `Gift.cached_techniques` keeps meaning "this gift's own techniques" — it is the
`Prefetch(to_attr=)` target for the gift API — and the pool read is the new
`Gift.inherited_techniques`. Ownership and thread resolution go through `resolve_owned_gift`
(`services/gift_acquisition.py`) and `gift_threads_for`
(`specialization/services.py`); see the "Gift lineage" section of `docs/systems/magic.md` for
the full call-site table, including the three reads that are deliberately **not** lineage-aware.
