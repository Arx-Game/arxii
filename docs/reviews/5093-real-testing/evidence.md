# Real-testing evidence for #5093 (Rank means level)

- Branch: `feature-5093-scaling-rules-read-aggregate-point-total`, head `8fca62841` (the commit under test).
- Run on 2026-11-15, 10 GiB devcontainer, no other Evennia server or test run was up (checked with `pgrep` and `ss` first).
- Every database used was a scratch database created for this run. `arxiidev` and production were never opened for writing. No content load and no `pull-prod` was run. All scratch databases were dropped at the end, and the only server started (a Django `runserver` on 127.0.0.1:8765) was stopped.
- Raw outputs are quoted below. Screenshots are in this folder.

## Summary

| Item | Result |
|---|---|
| 1. Migrations 0411 to 0436 against the newest production dump | **FAIL.** `0411_check_ladder_rows` crashes on the production copy. With 0411 patched in the scratch copy only, 0412 to 0436 all run and keep the data. |
| 2a. Level-11 PC against a level-11 NPC | PASS through the web dispatch seam. Even chart, both sides at rank 17 (not rank 11, see the note under that item). Browser and WebSocket part: BLOCKED, not run. |
| 2b. Level-6 PC against a level-5 NPC | PASS. Four ranks apart. |
| 2c. Scaling settings panel, and editing a LevelTier row | PASS. |
| 2d. Skill steps 30 to 31, 39 to 40, 40 to 41 | PASS. 22, 22 and 33 development points. A skill cannot be bought across 39 by development points at all (it parks), so 39 to 40 is shown on a stat. |

## Bugs found (not fixed, as asked)

1. **`0411_check_ladder_rows` fails on a production database.** Input: the production dump `arxii-20261115T033001Z.sql.gz` (9 `CheckRank` rows, ranks 0 to 8, `min_points` 0, 10, 25, 50, 80, 115, 155, 200, 250). I expected 0411 to add ranks 9 to 30. I saw:
   `IntegrityError: null value in column "min_points" of relation "arxii_checkrank" violates not-null constraint. DETAIL: Failing row contains (10, 9, null, Rank 9, ).`
   Cause: at migration 0411 the column `min_points` still exists, is NOT NULL and has no default, and the migration calls `CheckRank.objects.get_or_create(rank=rank, defaults={"name": f"Rank {rank}"})` without a `min_points`. CI never sees it because the migration returns early on a database with no `CheckRank` rows. A production deploy would stop at 0411 and `migrate --noinput` would fail. The migration is atomic, so nothing is half-applied; the database stays at 0410.
2. **Two migrations cannot be reversed.** `0412_checkrank_drop_min_points` (re-adding the NOT NULL column to 31 rows) and `0421_difficulty_levels_batch2_remove` (re-adding `soulfrayconfig.base_check_difficulty`). Both die with `IntegrityError ... contains null values`. This is the expected RemoveField limit the task described, recorded here so the PR body names them. Everything else reverses, details under item 1.

Smaller observations, not defects:

- After the migrations the ranks the production copy already had keep their old names at the same rank numbers, so "Mythic" now sits at rank 8 (level 8) while the seeds reuse it nearest its old threshold. The 0411 docstring says existing ranks keep their names, so this is as written, but staff will want to rename them.
- Spec Verification item 1 says a failure looks like "a rank other than 11 plus or minus 1". Spec section 9 (tier jumps) amends decision 1, and at the seeded values a level-11 character stands at rank 17 (see 2a). The two sections disagree; section 9 is the newer owner ruling, so I used it. The verification line should be reworded in the PR.
- The seeded chart for a rank difference of 0 is named "Difficulty +0 (rank diff +0)", not "Even" as the spec says.
- The check text for the new ranks reads "Rank 17 (rank 17)" because the placeholder name repeats the number.
- Difficulties between 1 and 9 points convert to level 0, which is no difficulty (baseline 0). In the production copy that is `conditionstage.resist_difficulty` (one row, 8) and `challengetemplate.severity` (three rows, all 3: Interpose, Succor, Catch the Faller). Whether level 0 is what staff want for those four rows is a question for the maintainer.

---

## 1. Migrations 0411 to 0436 against the production copy

**What I did.** Ran `just prod-migration-check --keep --tables ...` in the foreground. It downloads the newest production dump with the read-only key, restores it to a scratch database, and migrates forward to this branch's head. Then I took copies of the restored database and walked the migrations by hand, one step at a time, with counts taken between steps. Because 0411 fails (bug 1), everything after it was done on scratch copies where I ran `ALTER TABLE arxii_checkrank ALTER COLUMN min_points DROP NOT NULL` first. That workaround is mine and is not in the branch; it only lets the later migrations be checked.

**What I expected, and why.**
- 0411 to add ranks 9 to 30 and the 30 check baselines to a database that already has ranks (its docstring).
- 0414 to touch only lanes that already hold `ModifierValue` rows (its docstring says production held none).
- Difficulty conversions by the migration docstring: a standalone difficulty becomes the level whose new baseline (18 + 8 per level before level 1, 0 at level 0) is nearest the threshold of the old rank it reached (0, 10, 25, 50, 80, 115, 155, 200, 250); per-step values double into tenths.
- The tier rows (levels 3, 6, 11, 16, 21, 26 at 0, 24, 24, 24, 24, 24) from 0433.

**What I saw.**

Report of the tool, as printed:

```
== prod-migration-check report
head: 8fca6284177b19af6e2825698abf0db4edb3465e (feature-5093-scaling-rules-read-aggregate-point-total)
dump: arxii-20261115T033001Z.sql.gz
scratch database: scratch_pmc_20261115T211844Z_19200 (django connected to: scratch_pmc_20261115T211844Z_19200)
production tip: 0403_channels_carry_from_evennia | branch head: 0436_drop_rescue_thread_mult | main tip: 0410_alter_gift_resonances | step back to: 0410_alter_gift_resonances
== forward to branch head
...
django.db.utils.IntegrityError: null value in column "min_points" of relation "arxii_checkrank" violates not-null constraint
DETAIL:  Failing row contains (10, 9, null, Rank 9, ).
[prod-migration-check] REFUSING/FAILED: migrate (forward) failed
cleanup: KEPT scratch_pmc_20261115T211844Z_19200 (--keep); dump deleted.
RESULT: FAIL (exit 1); logs above
```

(The "rows before" lines in that report say "table absent" because I passed table names with the wrong prefix; every table here is `arxii_*`. The counts below are my own queries.)

- **Dump date:** `arxii-20261115T033001Z`, taken 2026-11-15 03:30:01 UTC, about 18 hours before the run. Production tip 0403; main's tip 0410, so 0404 to 0410 applied cleanly first (the scratch database was at 0410 when 0411 failed).
- **CheckRank rows:** before 9 (ranks 0 to 8, names Incompetent to Mythic). After 31 (ranks 0 to 30), min_points column gone. Ranks 9 to 30 are named "Rank N".
- **ModifierLevelBaseline rows written:** before 0 rows in every lane. After, 30 rows (levels 1 to 30) in each of 12 lanes: check (18 to 250), anima_pool (100 to 3000), soul_tether_cap (2 to 60), hollow_max (10 to 300), techniques_per_gift (3 to 90), outfit_trickle (1 to 30), rescue_budget_thread (50 to 1500), moon_tuning, facet_effect_bonus, vow_effect_severity, vow_effect_duration and vow_effect_damage (10 to 300 each). The stat, to_hit, damage and partial_protection lanes get no rows, 0 each. Total 360. The pool and cap rows carry the production config values (anima `maximum_per_level` was 100; production has no soul tether or gift acquisition config rows, so the code defaults were used).
- **ModifierSizeFraction rows:** 0 written (0414 touches only lanes that hold `ModifierValue` rows).
- **LevelTier rows written:** 6 (levels 3, 6, 11, 16, 21, 26 at 0, 24, 24, 24, 24, 24).
- **ModifierValue rows:** production held 0, so 0 deleted and 0 kept as overrides. Consequence: a production database after this deploy has no fractions or baselines for the stat, to-hit, damage and protection lanes, so sized buffs there keep their flat authored values (`ValueTable.value` returns None) until staff run the modifier seeds. That is also how production behaved before, because it had no value rows either. The check lane works, since its baselines were written.
- **CheckScaleConfig, DevelopmentCostConfig, FatigueConfig:** 0 rows after migration. They are created from their defaults the first time something reads them, and the panel on the migrated copy shows "not set" for them while still computing with the defaults.

Converted difficulty columns. "1-9" counts old values from 1 to 9, which become level 0 for a level column. "<0" counts negative old values. Columns not listed had 0 rows in production: breathholdconfig, compulsion (2), compulsionforbiddenaction, controllosstrigger (5), furytier, giftacquisitionconfig (2), driftconfig (2), driftcorrectionconfig, encounteraftermathrule, strainconfig, companionarchetype (2), situationtraplink (2), trap (2), roomclue, captivityconfig, ceremonyconfig, courtgrantconfig, listenerpost, skillcourseofferdetails, missionassistpattern, missionnodesupportoption and challengeinstance.

```
batch table.column                                kind     rows nonnull   1-9   <0    =0  >=10
0417  conditiontemplate.cure_difficulty            level     141     141     0    0     0   141
0417  conditiontemplate.resist_difficulty          level     141     141     0    0     0   141
0417  conditiontemplate.break_free_difficulty      tenths    141     141     0    0     0   141
0417  conditiontemplate.subtlety                   tenths    141     141     0    0   141     0
0417  conditionstage.resist_difficulty             level      51      51     1    0     3    47
0417  treatmenttemplate.target_difficulty          level       3       3     0    0     0     3
0417  vitalsconsequenceconfig.knockout_base_difficulty    level 1 1 0 0 0 1
0417  vitalsconsequenceconfig.knockout_scaling_per_percent tenths 1 1 1 0 0 0
0417  vitalsconsequenceconfig.death_base_difficulty       level 1 1 0 0 0 1
0417  vitalsconsequenceconfig.death_scaling_per_percent   tenths 1 1 1 0 0 0
0417  vitalsconsequenceconfig.wound_base_difficulty       level 1 1 0 0 0 1
0417  vitalsconsequenceconfig.wound_scaling_per_percent   tenths 1 1 1 0 0 0
0417  vitalsconsequenceconfig.aging_difficulty_per_year   tenths 1 1 1 0 0 0
0417  vitalsconsequenceconfig.wake_base_difficulty        level 1 1 0 0 0 1
0417  vitalsconsequenceconfig.wake_scaling_per_percent    tenths 1 1 1 0 0 0
0417  vitalsconsequenceconfig.wake_ease_per_round         tenths 1 1 1 0 0 0
0417  dreamperilconfig.resist_difficulty           level       1       1     0    0     0     1
0417  itemtemplate.on_use_difficulty               level      73       0     0    0     0     0   (all null)
0417  craftingrecipe.base_difficulty               level       6       6     0    0     4     2
0417  codexentry.learn_difficulty                  level     130     130     0    0     0   130
0420  soulfrayconfig.base_check_difficulty         level       1       1     0    0     0     1
0420  ritualcheckconfig.target_difficulty          level       5       5     0    0     0     5
0420  ritualcheckconfig.non_founder_target_difficulty level 5 1 0 0 0 1
0420  resonanceenvironmentconfig.backfire_base_difficulty level 1 1 0 0 0 1
0420  resonanceenvironmentconfig.backfire_difficulty_per_magnitude tenths 1 1 0 0 0 0
0420  fleeconfig.base_difficulty                   level       1       1     0    0     0     1
0420  escalationcurve.pace_difficulty_base         level       1       1     0    0     1     0
0420  escalationcurve.pace_difficulty_per_level    tenths      1       1     0    0     1     0
0420  fleetiermodifier.difficulty_modifier         tenths      5       5     1    1     1     2
0423  consequenceeffect.capture_clue_detect_difficulty level 33 0 0 0 0 0   (all null)
0423  tasktemplate.check_difficulty                level      14      14     0    0     0    14
0423  npcserviceoffer.check_difficulty             level      42      42     0    0    42     0
0426  challengetemplate.severity                   level       3       3     3    0     0     0
```

Only `fleetiermodifier.difficulty_modifier` held a negative value (one row, -5, a tenths column, so it becomes -10 and nothing clamps). The two level columns with values from 1 to 9 are `conditionstage.resist_difficulty` (one row, 8) and `challengetemplate.severity` (three rows, 3).

What each converted to, read back from the scratch database after each convert step (old value -> new value x rows):

```
conditiontemplate.cure_difficulty       10->1 x135; 12->1 x1; 15->1 x2; 20->1 x1; 25->2 x2
conditiontemplate.resist_difficulty     10->1 x141
conditiontemplate.break_free_difficulty 10->20 x141 (tenths)
conditionstage.resist_difficulty        0->0 x3; 8->0 x1; 10->1 x25; 12->1 x3; 15->1 x6; 18->1 x2; 20->1 x1; 22->1 x1; 25->2 x4; 28->2 x1; 30->2 x1; 35->2 x3
treatmenttemplate.target_difficulty     15->1 x3
vitalsconsequenceconfig                 knockout 20->1; death 30->2; wound 15->1; wake 20->1; the scaling and aging columns double (3->6, 5->10, 2->4, 7->14, 1->2, 2->4)
dreamperilconfig.resist_difficulty      20->1
craftingrecipe.base_difficulty          0->0 x4; 20->1 x2
codexentry.learn_difficulty             10->1 x130
soulfrayconfig.base_check_difficulty    15->1
ritualcheckconfig.target_difficulty     10->1 x1; 12->1 x2; 15->1 x1; 20->1 x1
ritualcheckconfig.non_founder_target    40->2 x1; null stays null x4
resonanceenvironmentconfig              backfire base 30->2; per magnitude 0.5->1.0 (tenths)
fleeconfig.base_difficulty              15->1
escalationcurve                         pace base 0->0; per level 0->0
fleetiermodifier.difficulty_modifier    -5->-10; 0->0; 5->10; 10->20; 20->40 (tenths)
tasktemplate.check_difficulty           10->1 x14
npcserviceoffer.check_difficulty        0->0 x42
challengetemplate.severity              3->0 x3   (Interpose, Succor, Catch the Faller)
```

These agree with the docstring's rule (each of 10 to 24 points lands on level 1, 25 to 49 on level 2 and 1 to 9 on level 0). One thing the table makes plain: many distinct authored values (10, 12, 15, 18, 20, 22) collapse onto level 1, because the old ladder had one rank for the whole range. That is what the spec describes, not a defect.

- **ChallengeTemplate severity before and after:** 3, 3, 3 (ids 1, 2, 3) before; 0, 0, 0 after (`severity_level`).
- **Rows after the run:** 6 `LevelTier`, 31 `CheckRank`, 360 `ModifierLevelBaseline`, 0 `ModifierValue`, 0 `ModifierSizeFraction`.

**Forward, back, forward.** On a scratch copy migrated to head, I stepped back one migration at a time, with the production data in place:

- 0436 down to 0422 all reversed cleanly. That includes the drops in 0424, 0427 and 0431, which re-add the old columns at their defaults and do not write the old values back.
- Going forward again from 0421 to 0436 applied cleanly; baselines (360), ranks (31), tiers (6), the three severity values and the condition levels matched the first run.
- `0421_difficulty_levels_batch2_remove` does not reverse: `IntegrityError: column "base_check_difficulty" of relation "arxii_soulfrayconfig" contains null values` (the first of its columns, 1 row; the migration is not reversible once rows exist).
- On two other scratch copies (one at 0418, one at 0420), 0420, 0419, 0418, 0417, 0416, 0415, 0414 and 0413 all reversed, and then 0419 to 0421 applied again. `0412_checkrank_drop_min_points` does not reverse: `IntegrityError: column "min_points" of relation "arxii_checkrank" contains null values` (31 rows).
- Not reversible, by the task's own description: RemoveField on 0412 and 0421. The other RemoveField migrations (0418, 0424, 0427, 0431, 0436) did reverse, because their re-added columns have defaults.

Not run: a clean forward, back and forward with the tool itself, since the tool stops at the failing 0411. Rerun it once 0411 is fixed.

**Evidence.** The tool output and the counts are quoted above. Scratch databases: `scratch_pmc_20261115T211844Z_19200`, `rt5093_pre0411`, `rt5093_fwd`, `rt5093_back`, `rt5093_b418`, `rt5093_b420` (all dropped afterwards).

---

## 2. The changes through their real interfaces

Scratch database for 2a to 2d: `rt5093_live`, built with `tools/build_schema.py` (full schema plus the repo's own idempotent seeds), then `seed_check_resolution_tables()` and `seed_modifier_value_tables()` for the ladder, size fractions and tiers. Seeded values I worked the expectations from: baseline 18 at level 1 and 8 more each level; level share 0.5; tier rows at levels 3 (0), 6, 11, 16, 21, 26 (24 each).

### 2a. Level-11 PC with ordinary skills against a level-11 NPC

**What I did.** In `rt5093_live` I made Hobb, a played character at level 11 with Unarmed Combat 49, and "Bandit L11", a combat opponent at level 11, in one encounter. I declared a Strike through `dispatch_player_action` (the call the websocket `execute_action` handler ends in, and the same seam the journeys use), then resolved the round with the real roll, with a spy on the roll to read what it saw.

**What I expected, and why (worked out from the spec, before running).**
- The NPC has a level and no points: baseline at level 11 is 18 + 8 x 10 = 98, plus tiers at levels 3, 6 and 11 (0 + 24 + 24 = 48), so 146. Spec decisions 2 and 16.
- Hobb's level term is 0.5 x 98 + 48 = 97 (decisions 5 and 16). His skill makes up the other half of the baseline, 49. Total 146.
- Both sides sit at 146, which is where rank (146 - 18) / 8 + 1 = 17 starts. Rank difference 0, with no slide, so the chart for difference 0.
- This is rank 17, not rank 11. Spec item 1 says "rank 11 plus or minus 1", from decisions 1, 2 and 5; section 9 (decision 16, a later owner ruling) says rank is level plus the tier bonus in ranks (11 + 48 / 8 = 17). I followed section 9 and flag the mismatch above.

**What I saw.**
```
[Hobbx11] PC level 11, Unarmed Combat 49, NPC level 11
target_difficulty passed to roll: 146
level_points=97 trait_points=49 total_points=146
roller rank=17 target rank=17 rank_difference=0 slide_share=0.0
chart used: Difficulty +0 (rank diff +0)
standing_text: 'Rank 17 (rank 17) against Rank 17 (rank 17)'
roll: d100=66 outcome=Success (level 1)
```
The interaction row the player sees: "Hobbx11 strikes Bandit L11 with bare hands. A fair hit: 2 damage." (An earlier run of the same setup, "Hobb11", rolled a miss; the roll is real, only the standing is fixed by the numbers.)

**Result: PASS** for the chart and the rank on the dispatch seam.
**BLOCKED: browser and WebSocket path.** The action went through `dispatch_player_action` inside `evennia shell`, not through the web client over a socket, so this does not show that the React encounter panel declares the Strike or that the page renders the result. I did not build the frontend or start the Evennia server for this pass. The `real-test` workflow or the maintainer would cover that.

Evidence: script `combat_scn.py` and output `combat_run.txt` in the session scratchpad, rows in the `rt5093_live` database (dropped).

### 2b. Level-6 PC against a level-5 NPC

**What I did.** Same flow with "Tessax6" (level 6, Unarmed Combat 29) against "Bandit L5", and "Brinx5" (level 5, Unarmed Combat 25) against "Bandit L4" as the within-tier comparison.

**What I expected.**
- Level 5 NPC: baseline 18 + 8 x 4 = 50, no tier (the first tier row is level 3 at 0 and the next starts at 6). Rank (50 - 18) / 8 + 1 = 5.
- Level 6 PC: 0.5 x 58 + 24 = 53, plus skills 29 (half the 58 baseline) = 82. Rank (82 - 18) / 8 + 1 = 9. Difference 4 ranks, one for the level and three for the tier. The spec says the same: "A level-6 character stands 4 ranks above a level-5 NPC, while a level-5 character stands 1 rank above a level-4 NPC."
- Level 5 PC: 25 + 25 = 50 against a level 4 NPC at 42: rank 5 against rank 4, difference 1.

**What I saw.**
```
[Tessax6] PC level 6, Unarmed Combat 29, NPC level 5
target_difficulty=50  level_points=53 trait_points=29 total_points=82
roller rank=9 target rank=5 rank_difference=4  chart: Difficulty +4
[Brinx5] PC level 5, Unarmed Combat 25, NPC level 4
target_difficulty=42  level_points=25 trait_points=25 total_points=50
roller rank=5 target rank=4 rank_difference=1  chart: Difficulty +1
```
**Result: PASS.** The 4-rank jump at the tier and the 1-rank step inside the tier both came out as the spec says. Same BLOCKED note for the browser and socket path as 2a.

### 2c. Scaling settings panel, and editing a LevelTier row

**What I did.** Started `runserver` on 127.0.0.1:8765 against `rt5093_live` with a throwaway superuser. In headless Chromium (Playwright) I opened `/admin/_tuning/`, waited for the Scaling settings panel to load, and screenshotted it. Then I opened `/admin/arxii/leveltier/`, opened the level 6 row, changed Bonus points from 24 to 40, saved, reloaded the Tuning dashboard and screenshotted the panel again.

**What I expected (from the spec's rules).**
- Before: baselines 18, 34, 58, 98, 138, 178, 218 at levels 1, 3, 6, 11, 16, 21, 26. Level term = 0.5 x baseline + the cumulative tier bonus: 9, 17, 53, 97, 141, 185, 229. NPC opposition = baseline + cumulative tier bonus: 18, 34, 82, 146, 210, 274, 338. Width 8 everywhere. Development cost per step (base 100, growth 150 percent from level 1, a band of ten steps each costing a tenth, rounded down): bands 0 to 9 and 10 to 19 cost 10, then 15, 22, 33, 50.
- After changing the level 6 tier from 24 to 40: the tier bonus row shows +40 at level 6 and leaves the others. Cumulative tier bonus becomes 0, 0, 40, 64, 88, 112, 136. Level term 17, 69, 113, 157, 201, 245 at levels 3 to 26 (0.5 x baseline + cumulative), NPC opposition 34, 98, 162, 226, 290, 354.

**What I saw (text read from the page).**
```
before:  Tier bonus     0 | +0 | +24 | +24 | +24 | +24 | +24
         Level term     9 | 17 | 53 | 97 | 141 | 185 | 229
         NPC opposition 18 | 34 | 82 | 146 | 210 | 274 | 338
         Baseline       18 | 34 | 58 | 98 | 138 | 178 | 218
         Development cost per step: 10 | 10 | 15 | 22 | 33 | 50
after:   Tier bonus     0 | +0 | +40 | +24 | +24 | +24 | +24
         Level term     9 | 17 | 69 | 113 | 157 | 201 | 245
         NPC opposition 18 | 34 | 98 | 162 | 226 | 290 | 354
         Tier rows      level 3: +0 · level 6: +40 · level 11: +24 · ...
```
Every number matches what I expected. The edit changes the panel on reload, and the panel's own sentence ("Tier rows") followed the edit.

I also ran one more fight after the edit, with level 6 "Tessay6edit" (Unarmed Combat 29) against the level 5 bandit: expected level term 0.5 x 58 + 40 = 69, total 98, rank 11 against rank 5, difference 6. Saw: `level_points=69 total_points=98 roller rank=11 target rank=5 rank_difference=6`. So the admin edit changed the real roll, not just the panel.

I also loaded the same panel on the production copy after all migrations (the `rt5093_fwd` database): it returned 200 with the check-lane numbers above; Level share, Buff sizes, Development cost and Fatigue read "not set" or "no rows yet", and the buff tables read "No size rows yet", which is what that database holds after the migrations (see item 1). No error on the page.

The browser console showed one error, `Pin status check failed: TypeError: Failed to fetch` from `arx_admin.js`; it comes from the admin's pin check calling an outside address and is not part of this change.

**Result: PASS.**

Evidence: [light panel before the edit](scaling-panel-before-edit.png), [panel after](scaling-panel-after-edit-level6-to-40.png), [the Level tiers list](admin-leveltier-list.png), [the edit form](admin-leveltier-edit.png), [the panel on the migrated production copy](scaling-panel-on-migrated-production-copy.png).

### 2d. Buying skill steps

**What I did.** In `rt5093_live`, on a played character, I set skills to chosen starting values with `set_skill_trait` and then paid development points one at a time through `train_skill` (the single writer that weekly training and Academy courses call), counting how many points it took for the rating to rise by one. I did the same for a stat from the base value of 10 through `DevelopmentPoints.award_points`, one point at a time, noting the running total each time the stat rose.

**What I expected, and why.** The curve is base 100 at level 1 growing 150 percent per band, a band is ten steps, each step costs a tenth of its band and a step counts in the band of its starting value (spec section 7).
- Band 3 (values 30 to 39) costs 100 x 1.5 x 1.5 = 225 and each step 22 (rounded down).
- So 30 to 31 costs 22, 39 to 40 costs 22 (it starts at 39, in band 3).
- 40 to 41 starts in band 4: 337.5 rounds to 338, a step is 33, which is one growth step more.
- A stat's running totals from 10: reach 20 at 100, 30 at 250, 31 at 272, 40 at 470, 41 at 503.

**What I saw.**
```
config row: 1 100 150
skill RT Fencing      30 -> 31 costs 22 development points
skill RT Archery      40 -> 41 costs 33 development points
skill RT Lockpicking  31 -> 32 costs 22 development points
skill RT Swimming     20 -> 21 costs 15 development points
skill RT Riding       50 -> 51 costs 50 development points
skill RT Parked at 39 given 100 points: now 39 ... "training maintains, does not advance until the breakthrough is unlocked."
stat reached 20 after 100 total points
stat reached 30 after 250 total points   stat reached 31 after 272
stat reached 39 after 448               stat reached 40 after 470   stat reached 41 after 503
stat 30->31 cost 22 | 39->40 cost 22 | 40->41 cost 33
```
**Result: PASS.** 30 to 31 and 39 to 40 cost the same (22) and 40 to 41 costs 33, one growth step more. The panel's "Development cost per step" row (10, 10, 15, 22, 33, 50) agrees.

**Caveat on the skill case.** A skill rated 39 is at an XP boundary and DP training will not move it past 39 (the 100 points I gave it were dropped, with the plateau message above); the step from 39 to 40 for a skill is bought with an XP breakthrough, which is a different, unchanged path. So the spec's "buy a skill step 39 to 40" can only be shown on a stat or by the formula; I showed it on a stat (and the skill 40 to 41 and 30 to 31 steps directly). Worth rewording in the spec's Verification line.

---

## Not done

- Browser or WebSocket check of the combat flow (2a, 2b): BLOCKED, not run. I used the dispatch seam in `evennia shell`.
- Spec Verification items 2 (Large buff half a rank), 3 (Large debuff) and 4 (a lock authored at level 8) were outside this pass's brief. The journeys in `integration_tests/test_rank_means_level_journeys.py` cover them through the test runner, not on a live database.
- A clean forward, back and forward with `just prod-migration-check` itself: blocked by bug 1.

## Re-run after the 0411 fix

0411 now gives each new rank row a `min_points` value (0 for rank 0, otherwise that rank's new baseline), because the column is still NOT NULL until 0412 drops it. I re-ran `just prod-migration-check` on the same production dump, `arxii-20261115T033001Z`. Every migration from 0404 through 0436 applied OK on the production copy, including 0411 and 0412.

- Rows before: 9 `arxii_checkrank` rows, 0 `arxii_modifierlevelbaseline` rows, 3 `arxii_challengetemplate` rows. The `arxii_leveltier` table did not exist yet.
- The step back failed for an unrelated reason. The tool steps back to main's tip, `0417_kindled_deed_label`, which this branch does not contain, because main has since added its own 0411 to 0417. That is the ordinary collision between migration numbers, and it gets fixed by renumbering this branch's migrations after main's tip. The earlier hand walk above covers reversibility: 0412 and 0421 are the two migrations that cannot be reversed.
