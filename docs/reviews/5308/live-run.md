# #5308 live run

Run on 2026-11-24 against branch head `8ba1e2e1e`, on a throwaway database (`rt_5308`) with its own server and a frontend built from the worktree. No production data was touched. The server was stopped and the database dropped afterwards.

Later commits changed only validation, ledger display, result-line wording and the web cast worth line. The checks below cover the gain, harvest, pull and reach behaviour those commits left unchanged.

## Setup (test setup, not the change under test)

- Villainy, Heroism and Reflection were linked to Abyssal, Celestial and Primal. Abyssal's spend floor was 110.
- The award table gave Success +25% gain and 130 worth, and Critical Success +50% gain and 160 worth. Lower results gave +0 and 100.
- A bonus check type was set at difficulty level 3. A kindling situation named Cruelty (Abyssal), and a mission carried it.
- Mirelle had an Abyssal aura, Villainy 30 and a room tagged Cruelty as her residence. Aldric had a Celestial aura, held Mercy and had no Villainy. Corin Vale was the fighter.

## Results

1. **The same act by both characters: PASS.** Both ran the same `mission resolve` act over telnet, and neither held Cruelty before it.
   - Each result line read like "You earned 12 Cruelty. Your Villainy check added 25 percent. 12 more is waiting to be claimed." Each ledger amount was 10 plus the percent.
   - Both characters held Cruelty afterwards, and Aldric's aura became Unsettled (Abyssal 31.5% against a settled 0%).
   - Mirelle's check gave a boosted result 21 of 27 times (78%). Aldric's gave one 1 of 6 times (17%).
2. **A +Villainy accent with no training: PASS.** A worn +20 Villainy doublet raised Aldric's check from 20 trait points to 40 while his Villainy stayed 0. With it he was boosted 44 of 62 times (71%).
3. **Trickles and the anima ritual harvest: PASS.**
   - Four residence ticks wrote waiting rows and changed neither the balance nor the held-back share. The panel read "12 waiting for your anima ritual" (screenshots 04 and 08).
   - The ritual harvested the rows into one `TRICKLE_HARVEST` grant per resonance. A Failure round paid 12 with +0. A Success round paid 15: "15 Cruelty waiting from your days arrived. Your Villainy check added 25 percent."
   - The ritual's outward part used the same check result, with no second roll.
   - The panel showed no waiting line after the harvest (screenshot 09).
4. **A Cruelty-paid pull's worth: PASS.** In a fight, `combat pull 1=Embercrown:Cruelty` printed "Your Villainy check made it worth 110 percent." (the Abyssal floor) on three rounds and 130 percent on two. An authored effect of 20 was stored as 22 and as 26.
5. **A reached pose: PASS.**
   - On the web, the composer's "Reaching for" picker listed every resonance (screenshots 01 to 03). Mirelle reached for Mercy, which she did not hold. Aldric's endorse control was one button, "Endorse their Mercy" (screenshots 06c and 07).
   - Over telnet, `pose/reach Hollow=...` followed by `endorse pose Aldric confirm` paid Hollow.
   - A pose with no reach asked "Which resonance?". A bad name gave "There is no resonance called 'Nonexistent'.".
6. **The resonances panel's waiting line: PASS** (screenshots 04, 08 and 09).
7. **The web result line and a claim: PASS.**
   - The web composer showed the gain line (screenshot 10).
   - `pose/claim` collected the set-aside share with no check line, and its ledger row has bonus 0.

**Not run live:** the worth of a kindled Abyssal cast, and the web cast worth line added after this run. The properties and the `ActionPanel` tests cover them.

## Evidence

Screenshots `01` to `10` and the telnet transcripts and ledger dump are in this directory.
