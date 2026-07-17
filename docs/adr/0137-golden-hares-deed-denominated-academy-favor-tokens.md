# Golden Hares: deed-denominated Academy favor tokens

Shroudwatch Academy's training economy is priced in **Golden Hares**
(`currency.FavorTokenDetails`) — physical, tradeable, org-issued deed tokens, one
Hare = one deed done for the issuing org — rather than an abstract obligation
ledger. **Rejected: a ledger currency (a plain debt/credit integer).** A ledger
can't be resold, given away, or stolen without inventing market/transfer
machinery from scratch; a Hare is an ordinary `ItemInstance` from the moment it's
minted, so player-to-player resale at *any* price rides existing item give/trade
surfaces for free — and that resale is a feature, not a leak: the Academy
"wouldn't mind" who carries the coin, since it still represents a deed done for
them (Tehom, 2026-07-17). **Hares are deliberately Academy-specific** — issuer-match
is enforced at redemption (`redeem_favor_token(token, redeemer_org=...)` raises
unless `redeemer_org` is the token's own `issuing_organization`); if another org
ever wants favor tokens, that is its own separate instrument, not a shared
currency (ruling on #2428, applied to #2440's TRAIN handler: a Hare always
redeems to the Academy as venue, regardless of which tradition the trainer
teaches). **Sponsorship is a real spend, not a waiver**: a Tradition-sponsored
Prospect's `OrganizationObligation` starts `SETTLED_BY_SPONSOR` because the
sponsor literally spent a Golden Hare on the Prospect's behalf at CG finalize (a
deed-coin transaction, lore-recorded rather than a minted item at CG time); an
Unbound Prospect starts `OWED` one Hare against Shroudwatch Academy instead. Both
Academy training (#2440, AP + coin + 1 Hare per technique) and the CG entrance fee
exclude XP entirely — XP still only buys gated unlocks, never a direct purchase
(ADR-0053 unaffected) — and reaching character level 2 requires knowing ≥3
techniques of the character's major Gift (a count, not a completeness bar; #2440
ruling 4), gating advancement on the same training loop rather than a separate XP
toll. **Rejected: halving resonance earned/spent as the Unbound penalty** (the
original draft substrate) — doubling the resonance cost of imbuing makes an
Unbound mage *weaker*, since resonance feeds thread power, not merely slower;
corrected (Tehom, 2026-07-17) to a +50% Action Point surcharge on magic-learning
activities instead (`magic_learning_ap_cost` ModifierTarget, #2442) — TIME, not
power, so a self-taught mage develops just as strong, only slower.

> Status: accepted · Source: #2428, #2440, #2441, #2442, Tehom design ruling
> 2026-07-17 · Confidence: built and wired — `currency.FavorTokenDetails` /
> `mint_favor_token` / `redeem_favor_token`; `societies.OrganizationObligation` /
> `settle_obligation`, reached in play via the Academy Registrar's
> `npc_services.OfferKind.SETTLE_OBLIGATION` offer
> (`run_settle_obligation_offer`, whole-branch fix — the original Task 1 landed
> `settle_obligation` with no live caller, so an Unbound Prospect could not yet
> pay off the debt this ADR describes; the Registrar seam closes that gap);
> `npc_services.OfferKind.TRAIN` / `run_train_offer`;
> `progression.MajorGiftTechniqueRequirement`; `magic` "unbound" drawback
> `Distinction` on the `magic_learning_ap_cost` `ModifierTarget`.
