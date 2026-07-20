# Currency glossary

**Copper**:
The single integer base unit of all money — every balance, calculation, and API value is stored and computed in coppers, with mixed-form display ("3g 4s 7c") generated on the way out. One silver is 10 coppers; one gold is 100 coppers.
_Avoid_: gold, money, coin (as the unit of account)

**Denomination**:
One of the named minted instrument coins above gold (Gold Knight, Baroness, Countess, Duchess, Queen, Empress), each worth ten times the last. A denomination is a physical instrument for theater, transport, and theft — not an account unit.
_Avoid_: coin type, bill

**Coin Cache**:
Everyday pocket cash withdrawn from a purse as a real, holdable item (`Denomination.LOOSE`) — arbitrary face value, no mint fee, unlike the six fixed grand-coin Denominations. Minted via `mint_loose_cache` and redeemed (deposited) via the same fee-free `redeem_instrument` path every instrument uses. Like every minted instrument it is born physical: a materialized `game_object` in the minter's inventory, so it can be dropped, given, stowed in a container, or stolen.
_Avoid_: loose coins (field/display name only), pocket money, cash

**Golden Hare**:
An org-issued favor token (`FavorTokenDetails`): a gold coin bearing a rabbit with emerald eyes, representing one deed done for `issuing_organization`. Deliberately NOT coppers-denominated — a distinct instrument from the `CurrencyInstrumentDetails` money coins, minted via `mint_favor_token` and surrendered via `redeem_favor_token`. Like a minted instrument it is born physical and tradeable via ordinary item give/trade (no market machinery), but unlike a coin its detail row survives redemption — deed-provenance is story-significant, so `redeem_favor_token` soft-disposes the item (stamps `destroyed_at`, relocates the game_object out of play) rather than hard-deleting it, and only the issuing organization may redeem its own Hare.
_Avoid_: favor coin, deed token, IOU

**CharacterPurse**:
The ledger holding one character's personal money as a copper balance, anchored to the body (CharacterSheet) rather than a persona.
_Avoid_: wallet, personal account

**OrganizationTreasury**:
The ledger holding one organization's money as a copper balance, with rank-gated spend authority controlling which members may draw from it.
_Avoid_: org bank, org wallet

**Graft**:
A never-zero percentage leak skimmed off the top of every organizational income flow, driven by NPC servant dissatisfaction and floored above zero by doctrine. It can be bought down by treating servants but never eliminated, and is deliberately distinct from magic's Corruption. Since #930 it bites the *collected* aggregate at dispatch time, so a hoarded pool pays a bigger absolute leak.
_Avoid_: tax, corruption, skim

**Uncollected pool**:
The uncapped per-stream copper amassment (`OrgIncomeStream.uncollected_pool`) the weekly cycle grows in place of any passive deposit (ADR-0081). Money in the pool is unusable until a collection dispatch lands it; the whole pool rides one graded outcome.
_Avoid_: pending income, savings, stockpile (item sense)

**Collection dispatch**:
The active org-level act (`collect_org_income`, the COLLECTION offer on a steward summon) that gathers every pooled stream and runs the Tax Collection check whose band decides how much arrives — the sole path from pools to treasury.
_Avoid_: payout, harvest, passive income

**Purse Drain**:
A weekly emptying of one holder's `CharacterPurse` driven by a distinction (`DistinctionPurseDrain` config), first shipped for "Somehow Always Broke" (#2613). Runs as two `CronPhase`-ordered cron tasks: the `SNAPSHOT` band records the opening balance before income lands, the `DRAIN` band (after upkeep) removes `opening_balance − outflows` so the holder keeps only that week's fresh income. Every drain is an audited `transfer` sink; physical coin, org treasuries, and coin held by others are never touched.
_Avoid_: wipe, reset, tax

**Opening balance**:
A `PurseDrainWeek` holder's purse balance captured in the `SNAPSHOT` band at week start, *before* weekly income lands — the baseline the `DRAIN` band drains down to (minus the week's outflows). Persists between the two cron bands and doubles as the drain's audit row.
_Avoid_: starting money, snapshot balance (field-adjacent only)
