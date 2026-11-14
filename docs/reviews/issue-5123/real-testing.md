# Real-testing pass: #5123 "A character with several resonances"

**Verdict: all seven spec flows PASS against a real running server.** No flow failed. One low-severity
defect in the Settle your aura dialog was found (D1), plus a few notes that are not failures of this
change (N1 to N5).

## What was run, and on what

| Item | Value |
|---|---|
| Code | Branch `feature-5123-a-character-with-several-resonances-mixe` at `21f6097e9` (frontend bundle built from that tree with `just fe-build`) |
| Form | Form B of the real-testing skill: my own Evennia server from this worktree, web on :4001, websocket :4002, telnet :4000. Before starting, `pgrep ... evennia/twistd/server.py/portal.py` and `ss -ltn \| grep :400[12]` both printed nothing. |
| Database | Throwaway `rt_5123` on the shared Postgres (never `arxiidev`, no `pull-prod`, no `--hard`). Built with `tools/build_schema.py` with `PGOPTIONS='-c max_parallel_workers_per_gather=0'`. Dropped at the end. |
| Browser | Playwright, headless Chromium 1208 shell, 1280 wide (1440 for the in-world combat page). |
| Telnet | A small socket driver (`scripts/tn.py.txt`) talking to the real telnet port: `connect`, `ic`, then the commands. Passwords on `connect` lines are masked in the transcripts. |
| Test data | Everything in the throwaway database came from test factories, written by `scripts/seed_rt5123.py.txt` in one transaction (see "What I set up"). Every later change to data is a `scripts/staff-adjust-*.py.txt` file, each run with the server stopped so the server's in-memory cache never held a stale row. |

Evidence lives next to this file in `docs/reviews/issue-5123/real-testing/` (screenshots `flowN-*.png`,
transcripts `flowN-*.txt`, scripts under `scripts/`).

## What I set up (all staff-authored or player rows, in `rt_5123` only)

- Affinities and conversion pairs (the production Fall and Redemption multipliers), the check system, a
  "Keeping Focus" check, the "Resonance Conflict" condition (-10 on the cast check), tolerance 5 percent.
  Drift correction rite authored with a Fury-tied offering, check difficulty 0, every outcome converting a full share, cap 50 percent per deed.
- Resonances: Fury and Wonder (Primal), Domination and Dread (Abyssal), Mercy and Dawnlight (Celestial).
- Pull cost tier 1: 3 resonance, 1 anima. Gift-thread perks (target kind Gift), tier 1, **Intensity bump**:
  Fury +2 at thread level 0 and +4 at level 5 (and +5 at 10); Domination +3 at 0, +6 at 5 (and +7 at 10). Wonder has none.
  (My first attempt authored these as flat bonuses; see N3 for why I changed them.) Technique-thread perks: Domination +4 at level 0 and +8 at 20, Dread +6 at 0 and +10 at 20.
- Players, one account each, password `RtPass5123!`: Ysmay (Gift thread "Kindling", technique thread "Loom Strand" at level 20, Primal 70 / Abyssal 30 settled), Veyra (Primal 90 / Abyssal 10 settled, Fury 200, Domination 10), Hobb (same line, Domination 50, outside any scene), Marrow (staff, tags moments), Sorrel (settled wholly Celestial, 700 Dawnlight), and `rt_staff` (superuser, approves the creation application).
- Moment types: "Dominating Stare" (30 Domination) and "Fury Flare" (20 Fury), per-scene cap raised to 10.
- A live scene "Lantern Night" in the room The Lantern. (The game ends a scene when the last player leaves its room; I started later scenes with `scene start` on telnet and, for combat, by factory. See N5.)
- The creation draft for `e2e_test_account` sits at the Gift stage, built from the repo's finalization test fixture (a complete base draft; Gift picks cleared).
- Sineater: no Soul Tether bond. Sorrel received the same Mire grant the Soul Tether service writes (`grant_resonance(..., source=SINEATING, from_mire=True)`) through the shell: 200 first, a second 200 later with the server stopped.

## Flow 1. Creation

**Expected (written from the spec before running):** the step opens with the intro text (resonance is what
powers your magic; it is what invigorates, drives or thrills you). Picking Fury 6, Wonder 1, Domination 3 of
10 points shows "Mostly primal, a third abyssal". After finalize the aura is not a fixed 80/20, the halo
matches, and the Gift thread lists Fury, Domination, Wonder at nothing imbued with Fury first. Failure would be
one resonance only, a fixed 80/20 aura, or an empty Gift.

**What I did:** as `e2e_test_account` in the browser I opened `/characters/create`, Gift stage, "Your Resonance"
step, and pressed "More" on Fury six times, Wonder once, Domination three times. Reloaded the page. Took one
point off Fury to read the halo at 9 of 10. Then submitted the draft as the player, and as `rt_staff` claimed and approved the application
(the real submit, claim and approve routes). Read the aura, resonances and threads back through the API as the
player.

**What I saw:** the intro paragraphs read word for word as ruled. The budget read "0 of 10 placed", then "10 of 10 placed"
(and "9 of 10" mid-way). Pip counts Fury 6, Wonder 1, Domination 3. The halo sentence read **"Mostly primal, a third abyssal."**
at both 9 and 10 of 10. The picks survived a reload. After approval the API held: aura Primal 70 / Abyssal 30, each
settled at the same figures, `unsettled: false`; resonances Fury 60, Wonder 10, Domination 30 lifetime, balance 0 each;
one Gift thread with Fury (0, leads), Domination (0), Wonder (0). That is 10 points at 10 lifetime a point.
Evidence: `flow1-01..04-*.png`, `flow1-web-transcript.txt`, `flow1-api-readback.txt`.

**Limit:** the finalized character's own sheet was not drawn as an owner: its page rendered the public view
("Nothing is known of their magic", "Apply to Play"; `flow1-05-sheet-halo.png`), because approval did not seat the account on her in
this database. I did not chase why. The sheet halo itself I show for Ysmay, who has the identical 70/30 shares: "Mostly primal, a third abyssal" (`flow1-06-settled-sheet-halo-ysmay.png`).

**PASS.**

## Flow 2. Imbue and pull

**Expected:** imbuing Fury and Domination into the Gift thread debits each and writes each its row. Pull threads then
lists, for each resonance that could pay, that resonance's perks: the leader at the thread's level, another resonance
one staff-set level (10) lower, Wonder (never imbued) none. Pulling with each applies those effects and charges
only the payer. Failure: the same perks for every payer.

**What I did:** web, as Ysmay: `/threads/1`, the imbue panel: Fury 4, then Domination 11 (I meant 8; the amount
stepper kept the 4 across payers and I clicked up 7 times, so 11 went in. The rows below reflect that). Then, on the scene page, Cast, Lantern Ward, Thread pulls, tier 1, and for each of Domination,
Fury, Wonder chose "Pay with" and cast. Also opened the in-combat "Pull Threads" dialog (an encounter was seeded; see below).

**What I saw:**
- Imbue: balances Fury 70 to 66, Domination 25 to 14; thread rows Domination 11 (leads), Fury 4, Wonder 0; level 9, "Blocked by: xp lock" at 10 (existing rule). Message "You complete the rite, imbuing Kindling. Kindling is now level 9."
- Pull picker (and the API preview): **Domination lists Intensity +3 and +5; Fury lists +2 and +4; Dread and Wonder say "No perks on this thread"** (Dread has no row; Wonder has a row of 0). Every option shows its own cost and "you have N".
- Casting: Domination pay added "thread power +8" (power 1 to 9) and took 3 Domination only (11 to 8); Fury pay added +6 (to 7) and took 3 Fury only (63 to 60; an earlier run of the same cast, with flat-bonus perks, had taken it 66 to 63); Wonder pay added nothing (power 1) and took 3 Wonder only (7 to 4).
- **Level step:** on this Gift thread (level 9) Fury reads level 9, the same as the leader, not 10 lower. That is the clamp the spec and `payer_level_read` describe (the level multiplier is 0.9 at level 9 and 1.0 at level 0, so a lower read would score higher). The step shows where it should: see flow 6, where Dread reads level 10 on a level 20 thread and loses the level-20 perk. So the spec sentence for flow 2 ("one level lower") holds only for threads at level 10 and up.
- Evidence: `flow2-02-thread-after-imbue.png`, `flow2-imbue-web-transcript.txt`, `flow2-03-pull-picker-tier1-domination-pays.png`, `flow2-04-cast-pay-with-*.png`, `flow2-05-cast-result-*.png`, `flow2-casts-web-transcript.txt`, `flow2-pull-preview-api.json`.

**Pull Threads dialog colours in a real session (asked for in the brief).** In the in-world combat page (`/game`, "In world", "In combat"), opened as Ysmay:
the selected tier button and the "Select Pull" confirm button are **near-black, rgb(24, 24, 27)**, with white text; the page has no `data-realm`
(`--primary` 240 5.9% 10%). With a realm stored in the browser (`realm-theme=arx` in localStorage, which Character Creation's origin
stage sets) the same two controls are **rust, rgb(139, 52, 35)**. The realm theme is a per-browser stored choice, so a player on a fresh browser or one who never went through origin selection gets
near-black here. The demo draws these rust. Evidence: `flow2-07-*.png` (no realm), `flow2-09-*.png` (realm arx), `flow2-combat-dialog-transcript.txt`, `flow2-combat-dialog-realm-transcript.txt`. The scene-page picker and the thread page show the same black primary for Ysmay. This is the demo check's open item S2, and it reproduces in a real session. (The Settle your aura dialog, by contrast, rendered rust in a no-realm session, as F4 fixed.)

**PASS** (with the colour finding above, and N3).

## Flow 3. Unsettled

**Expected:** past the line, the sheet shows Unsettled with "Your Domination has grown strong enough to make you unsettled",
and the next cast rolls the focus check. A settled character gets neither.

**What I did:** Veyra (settled 90/10, Domination 10 of 210) sheet first. Then Marrow, on telnet, tagged her
"Dominating Stare" (a 30 Domination deed). Read her sheet and `aura` on telnet, then cast Lantern Ward on the web (4 casts) and on telnet.

**What I saw:** before: "Nearly all primal, a tenth abyssal." and nothing else. After the deed (Domination 40 of 240, 16.7 percent against a 15 percent line):
the halo shows the sentence, an "Unsettled" tag and a "Settle your aura" button (`flow3-02-veyra-unsettled-sheet.png`); telnet `aura` prints the same sentence. Casting by telnet printed
**"Your Domination has grown strong enough to make you unsettled. You must keep your focus."** before the cast resolved. After the web casts a
"Resonance Conflict" condition was on Veyra in the database (the focus roll failed at least once); Ysmay, settled, had cast six times on the web by then with no condition on her (the only condition row in the database was Veyra's).
The web cast card showed no focus line for Veyra (only the telnet session receives it; see N4).
Evidence: `flow3-*.png`, `flow3-telnet-transcript.txt`, `flow3-casts-web-transcript.txt`.

**PASS.**

## Flow 4. Atone and accept

**Expected:** in a live scene a Fury deed (main affinity) opens an offer; the Settle your aura dialog offers Atone; performing it turns
Domination into Fury and the halo returns under the line. Outside a scene the dialog offers only Accept; accepting moves the line and ends the check.

**What I did:**
- Atone: reset Veyra to Fury 200 / Domination 10 (server stopped), held her telnet session in the room, Marrow tagged Dominating Stare then Fury Flare in the live scene, then on the web Settle your aura on the scene page, picked the "Fury Ember" offering, "Begin the rite".
- Accept: Hobb (Domination 50, no scene) on the web, `/characters/3`, Magic, Settle your aura, Accept; then telnet `aura`.

**What I saw:**
- Veyra's held telnet session was told **"You have grown unsettled. Use aura to see how you can atone."** The pending API listed an offer: cap 10 toward Fury, source Domination (40 held, Redemption 0.70, up to 1), qualifying component Fury Ember. The scene page opened the dialog with **both cards: Atone ("Perform the rite of atonement. The Domination you gained turns to Fury.", Cap remaining 10, offering, "Redemption: 1 Domination becomes about 1 Fury") and "Accept the changes to your Aura"** (`flow4-03-scene-page-offer.png`). After the rite: "Partial Success: 1 Domination became 1 Fury." Domination 40 to 39, Fury 220 to 221, shares Abyssal 15.00 / Primal 85.00 (the line is 10 plus 5 tolerance), `unsettled: false`, sentence gone.
- Hobb before: unsettled, no pending offers. The dialog offered **only** "Accept the changes to your Aura", "Accept" (rust), "Not now" (`flow4-hobb-02-dialog-accept-only.png`). After Accept: "You become more abyssal." Shares moved from settled 10 to settled 20 (Abyssal 20.00 / Primal 80.00), sheet reads "Nearly all primal, a fifth abyssal.", `unsettled: false`. Telnet `aura` for Hobb: settled, and `aura accept` now says "You are not unsettled, so there is nothing to accept."
- Defect D1 below (the dialog after the rite).
- Evidence: `flow4-*.png`, `flow4-web-atone-transcript.txt`, `flow4-hobb-web-transcript.txt`, `flow4-telnet-transcript.txt`, `flow4-hobb-telnet-transcript.txt`.
- Note on setup: my first Fury deed landed while Veyra was logged out (a character outside the world has no room), and no offer opened. That matches the contract (an offer needs the character standing in a live scene), so I repeated it with her in the room.

**PASS** (D1 aside).

## Flow 5. Sineater

**Expected:** the halo shows the Mire share apart, and no Unsettled state until it passes the allowance (30 percent of everything gained).

**What I did:** Sorrel (settled wholly Celestial, 700 Dawnlight) took 200 Mire of Domination, I read the sheet, then took another 200 (server stopped and restarted around the write) and read it again, then pressed Accept.

**What I saw:** at 200 of 900: halo sentence **"Mostly celestial. A fifth of what you have gained came from the Mire."** with a key "your own / from the Mire" and the Mire arc drawn apart in olive; API `mire_share_words: "a fifth"`, `unsettled: false` (`flow5-01-*.png`). At 400 of 1100 (36 percent): "a third", `unsettled: true`, "Your Domination has grown strong enough to make you unsettled." Accept: "You become more abyssal.", settled shares Abyssal 36.36 / Celestial 63.64, Mire "none" (it became her own), sentence "Mostly celestial, a third abyssal." Evidence: `flow5-*.png`, `flow5-sorrel-web-transcript.txt`.

**PASS.**

## Flow 6. Retune

**Expected:** retuning 5 of a thread's Domination to a related Abyssal resonance leaves the thread's level alone, its mix shows the move, there is still one thread, and the pull dialog now lists the new resonance's perks.

**What I did:** as Ysmay on `/threads/2` (Loom Strand: level 20, 40 developed, one Domination row of 40), "Change resonance", moved 5 points, to Dread (same affinity), with the Dread Shard offering, "Retune thread".

**What I saw:** before: rows Domination 40; pull preview Domination perks 8 and 16, Dread none. After: level 20 and developed points 40 (unchanged), rows **Domination 35, Dread 5**, Domination still leads, Ysmay's thread count still 2. The pull preview now lists **Dread: level read 10, perk 6** (the level 0 perk; the +10 level 20 perk is not read, which is the one-level-lower step working), Domination still reads 20. Evidence: `flow6-*.png`, `flow6-web-transcript.txt`.

**PASS.**

## Flow 7. Telnet

**Expected:** `imbue thread=<gift> amount=5 resonance=domination`, `cast ... pull=<gift>:domination`, `aura`, `aura accept` give the same outcomes as the web.

**What I did / saw (Ysmay and Veyra on the real telnet port):**
- `threads`: "Domination (nearly all), Dread (a tenth) Loom Strand (Lantern Ward) (level 20)" and "Domination (most), Fury (a fifth) Kindling (level 9)": the mix in words, the Gift thread named by its Gift.
- `ritual Rite of Imbuing`, `imbue thread=Kindling amount=5 resonance=domination`: "You complete the rite, imbuing Kindling." The mix became "Domination (nearly all), Fury (a fifth)". `imbue ... resonance=nonesuch`: "You hold no resonance called 'nonesuch'. Your resonances: Domination, Dread, Fury, Wonder."
- `cast Lantern Ward pull=Kindling:domination` resolved; `pull=Kindling:fury` resolved; `pull=Kindling:nonesuch` refused in words; bare `pull=Kindling` (leading resonance, Domination, by now at 0) refused with "You do not have enough resonance for this." The API read-back after: Fury 57 (60 less 3), Domination 0 (8, less the 5 imbued, less 3), Wonder 4, Dread 5.
- `aura` read in words; for Veyra after two more Domination deeds: unsettled sentence, `aura accept` "You become more abyssal.", then `aura` no longer says unsettled.
- Evidence: `flow7-telnet-transcript.txt`.

**PASS.**

## Defects

| # | Severity | Defect |
|---|---|---|
| D1 | Low | **Settle your aura dialog stays stale after a successful atone.** Right after the rite finishes the dialog still shows the header "Your Domination has grown strong enough to make you unsettled" and still offers the Accept card, while the aura API already says `unsettled: false` (`flow4-05-after-rite.png`). On a fresh load the open offer (cap remaining 9, no sources) still auto-opens an "Atone" card with an enabled "Begin the rite" and nothing to convert (`flow4-06-fresh-load-after-atonement.png`). The offer lingers until the scene ends. |

## Notes (not failures of this change)

- **N1. Gift threads have no name on the web.** Thread page title "(unnamed)", anchor "GIFT"; the pull picker and combat dialog say "Thread #1". Telnet shows "Kindling". Code is identical on `main` (`displayName = thread.name.trim() || '(unnamed)'`, `Thread #${thread.id}`), so it predates this change, but with several Gift threads a player cannot tell which Gift is which in the picker.
- **N2. Spec text vs code.** The issue body's Data shape says `sum(amount) == Thread.developed_points`. In the running game, rows are cumulative (Domination 11, Fury 4) while `developed_points` is what is left after levelling (6). `docs/systems/magic.md` and the fuzz test already state the rows do not sum to `developed_points`; only the issue's spec sentence is stale.
- **N3. Flat-bonus perks never show in the cast ledger.** My first authoring of the Gift-thread perks was flat bonuses; the cast's power ledger then showed no thread power for any payer, because a flat bonus goes to the cast roll, not to power. I did not inspect the roll modifier, so flat-bonus application is **not** verified here. Intensity perks (what the shipped journey uses) show in the ledger and were verified.
- **N4. The web cast card prints no focus line.** The "You must keep your focus / You lose your focus" lines go to the character's session (seen on telnet); the web cast result for an unsettled caster had none, though the condition was applied.
- **N5. Scene ends when the room empties.** The live scene finished the moment its last player left (the log shows it at the logout), after which `cast` says "There is no active scene here." Existing behavior; I started new scenes for the later steps.
- **Server log:** the only errors in the whole session were `ThreadPullCost matching query does not exist` (76; a 500 from `thread-pull-preview` when the picker previews tiers 2 and 3, for which I authored no cost row) and a missing `Property` for the daily anima regen task (6). Both are rows the throwaway database lacks; the 500 on an unauthored tier predates this change.

## Not covered

- The finalized creation character's own sheet as an owner (flow 1 limit above).
- Soul Tether's own accept and respond routes (Sorrel got the same Mire grant by service).
- Flat-bonus perk application (N3), and any ritual or cast path other than those named above.
- A Sineater unsettled at a lower share than an ordinary character would be (I show only that 22 percent Mire is not unsettled and 36 percent is).
- No frontend unit run, no Postgres suite run: this pass was only the running program.

## Cleanup

Server stopped with plain `uv run arx stop`; `rt_5123` dropped; nothing listening on :4001 or :4002 afterwards (checked with the skill's two commands).
