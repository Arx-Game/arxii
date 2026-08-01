# ADR-0184: Consumables ride the consequence spine; unconscious bodies ride consent

**Status:** Accepted (built #2852)

**Decision.** Every edible is pure content: three new `EffectType`s on the
authored-consequence spine (`RESTORE_FATIGUE` via the new `recover_fatigue`
partial-recovery service — fatigue previously only rose or dawn-reset;
`RESTORE_ANIMA`, the ruled magical-consumable exception, clamped and distinct
from regeneration so appetite holders' no-natural-regen stands; `INTOXICATE`,
whose single `imbibe` seam owns the whole drunk arc) make a food or drink item
a plain consumable `ItemTemplate` with a deterministic on-use pool — no
item-app code per dish. Intoxication is a severity-staged condition
(Tipsy→Drunk→Sodden→Blackout, IC-clock expiry); past Blackout each further
drink rolls the existing stamina check and failure lands the built
`Unconscious` machinery plus `Hungover`, whose willpower penalty is exactly
what the #2845 moon impairment predicate reads. Unconscious bodies become
interactable through consent: carrying rides a new `body-handling` category
(the `makeover` body-autonomy precedent — allowlist default; NPCs open) with a
`CarriedBody` link and an `at_post_move` follow (raw `move_to`, since
`move_object` refuses third parties by design), releasing the moment the
carried can act; robbing is a steal-path-only reach widening (never plain
`get`, worn gear excluded) through the existing `theft` category. The cooking
tradeskill is pure activation of the built crafting engine (Cooking
skill/check, first live QualityTier ladder, stationless ITEM_CREATE recipes),
and quality feeds the one new event-completion hook: catered dishes are
consumed into snapshot rows (the money sink) whose quality sum mints the
host's Hospitality deed (the ceremony finish→prestige precedent) — rich
preparations are money out, grandeur in.

**Rejected alternatives.** (a) A per-item fatigue side-channel model (mirroring
appearance effects) — cheaper but off the authored-consequence spine every
other effect uses. (b) A hunger/thirst survival clock — ruled out; food is
restorative and social, never a timer. (c) Carrying via captivity — captivity
is imprisonment with its own lifecycle; a rescue-shaped carry must not imply
capture. (d) Widening `get`/reach generally for downed holders — robbery is a
deliberate act; only `steal` (and its consent gate) may reach a body.
(e) Addiction mechanics — the ruled deeper layer, deferred; drugs ride the same
`INTOXICATE` seam as future content.
