# Check Resolution Spectrum

> The check system (`perform_check`) is the universal resolution mechanic for
> Arx II. Everything from flirting at a ball to surviving a dragon uses the same
> pipeline. What differs is how consequences are handled — not how checks work.

---

## The Spectrum

| Context | Check | Consequence Handler |
|---------|-------|-------------------|
| Social scene | `perform_check` | Narrative — displayed inline in scene, player decides response |
| Social scene (risky magic) | `select_consequence` + `apply_resolution` | Structured — mishap consequences from technique or context |
| Reactive/imposed (trap, poison) | `select_consequence` + `apply_resolution` | Structured — no player intent, consequences imposed |
| Situation (exploration) | `perform_check` via `resolve_challenge` | Structured — ConsequenceEffect applies conditions, properties, flows |
| Combat | `perform_check` via combat system | Tactical — damage, conditions, positioning |

The check pipeline is identical in all contexts:
1. Weighted trait points (via CheckTypeTrait)
2. Aspect bonus (via PathAspect)
3. Level term: the acting level's share of that level's baseline, plus its tier bonus
4. Extra modifiers (from conditions, buffs, equipment, etc.)
5. Total points → rank on the baseline ladder → ResultChart → roll → CheckOutcome

The next section says what a rank is, because every number in steps 1 to 5 is read against it.

**`resolve_challenge` is one consumer of `perform_check`, not a replacement for it.**

The **generic consequence pipeline** (`select_consequence` + `apply_resolution` in
`checks/consequence_resolution.py`) provides structured consequence handling for any
context — not just challenges. Any system that needs "roll + mapped consequences" can
use it: magic mishaps in social scenes, reactive checks (traps, poison), technique
risk pools, etc. `resolve_challenge` is a thin wrapper that adds challenge-specific
state management on top.

The pipeline is two-step to support future reroll/negation mechanics:
1. `select_consequence()` — perform check, select weighted consequence, return pending
2. `apply_resolution()` — dispatch ConsequenceEffects via handlers

Social scenes that need only narrative results still call `perform_check` directly.
Combat will call it through its own resolution layer. The check stays generic; the
context determines what happens with the result.

---

## What a rank means (#5093, ADR-5093)

A check rank is the level someone is acting at, plus any tier bonus counted in ranks. The ladder
is one row per level of `ModifierLevelBaseline` on the CHECK lane: rank N starts at the level-N
baseline, and the gap between two baselines is one level's width. Every other number is sized against that width, so
the code keeps no per-level coefficient and staff retune any of it by editing rows.

```
total   rank on the ladder (seeded baselines: 18 at level 1, 8 more each level)
 ...
 98 --- rank 11 starts (the level 11 baseline)
 90 --- rank 10 starts        one level's width (8 points) is one rank
 82 --- rank 9 starts
 ...
 58 --- rank 6 starts
 50 --- rank 5 starts (a level-5 NPC opposes with 50)

A level-6 character with ordinary skills: 29 from skills and stats, 29 from her level term
and 24 from the level 6 tier = 82, rank 9, four ranks above the level-5 NPC at 50.
A level-11 character and a level-11 NPC both stand at 98 + 48 (two tiers) = 146, rank 17.
```

Without tier rows a level-N character stands at rank N. Each tier row adds its bonus in ranks, so
at the seeded rows a level-11 character stands at rank 17, and what stays even is the match of two
characters at the same level.

- **A character** adds `CheckScaleConfig.level_share` (seed 0.5) of her level's baseline to every
  roll, plus her level's tier bonus. Her skills and stats supply the rest of the climb.
- **An NPC has no points.** It opposes with its level's baseline plus the tier bonus, which is
  where a character of that level with ordinary skills stands, so a level-N character with
  ordinary skills meets a level-N NPC on the even chart. A debuff on the NPC lowers that number by the debuff's derived value.
- **A player character who is the obstacle** (hiding something, resisting a social move) counts
  as her full check total, not her level.
- **A staff-authored difficulty is a level** (`*_level`), turned into points by
  `difficulty_points`: the level's baseline plus its tier bonus. An increment on top of another
  difficulty is tenths of one level's width (`*_tenths`).
- **A modifier is a fraction of a level.** Its value is its size's `ModifierSizeFraction` times
  one level's width at the level it applies at, so one Large buff is about half a rank at any
  level. A `ModifierValue` row at that exact level and size overrides the derived number.
- **A tier jump is a row.** `LevelTier(start_level, bonus_points)` adds points in full wherever a
  level's strength is read, so crossing into a new tier is worth several ranks. It does not change
  a level's width, so buff sizes stay the same inside a tier. The ladder runs past rank 30 as far
  as the top level's baseline plus its tier bonus.
- **Diminishing returns come from the curve and the taper.** The result charts stay one per rank
  difference (-8 to +6); the light taper on a pile of ordinary modifiers is unchanged; there is no
  cap on the total of all buffs.

The tuning numbers and the code that reads them are in `docs/systems/checks.md` ("Modifier values,
size fractions, level baselines and the taper", "Tier jumps", "Authored difficulty as a level").

---

## Social Scene Checks ("Action-Attached Poses")

Players write a pose and attach a mechanical check — flirt, deception, intimidation,
notice something, play cards, arm wrestling, anima rituals. `perform_check` runs, the
result displays inline in the scene narrative. This does NOT go through
`resolve_challenge` — the scene system handles display and narrative.

Social checks are not PvP. Arx II is fully collaborative. Outcomes matter to those
involved (affecting relationships, reputation, perception) but players control how
their characters respond to results. Stakes are lower than Situations but still
meaningful.

Examples:
- A flirt check (Charm-weighted) — affects relationship warmth
- A deception check (Wits-weighted) — other player knows IC if they were deceived
- A lore recall check (Intellect-weighted) — reveals codex-gated information
- An anima ritual in a social scene — magical discovery through RP

---

## Difficulty Preview

`preview_check_difficulty(character, check_type, target_difficulty)` in the checks app
calculates rank difference without rolling. Any system can call it to show how hard
something would be for a character right now — including all active modifiers.

This powers:
- Available action difficulty indicators (the "consider" display)
- IMPOSSIBLE label (ResultChart has no Success outcome, charts -7 and -8 → action listed, labelled Impossible, not hidden; #4593)
- Dynamic updates when buffs/debuffs change (a teammate's buff can make new actions appear)

---

## Skill Development from Checks

`perform_check` is where skill development hooks belong — not on any downstream
consumer. This ensures social checks, combat checks, and challenge checks all
contribute to skill development equally.

Development is **flag-based, not immediate:**
1. `perform_check` records "this trait was used this week" (lightweight upsert)
2. Weekly cron resolves: skills used get development points, skills not used may rust
3. The check plants the flag; the cron harvests it

This must be on `perform_check` because if the hook were on `resolve_challenge`,
social scene checks would not earn development — which would be wrong.

---

## Progression from Gameplay

Progression is intrinsic to the action, not bolted-on rewards.

- **Skill development points** — earned by using skills in real checks (any context).
  The check pipeline knows which traits were used via CheckTypeTrait weights.
- **Legend points** — earned for genuinely heroic acts. Virtually always combat-related
  or tied to extreme Situations (preventing catastrophe, death-defying feats). Things
  bards would sing about. Not awarded for routine challenge completion.
- **XP** — never awarded for game mechanics. Always from roleplay activities.
- **No loot-drop rewards** — no "Winner is you!" popup for beating a challenge.
  No ChallengeReward model. GM guardrails come from structured consequences, not
  reward-granting power.
