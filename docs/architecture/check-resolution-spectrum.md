# Check Resolution Spectrum

> The check system (`perform_check`) is the universal resolution mechanic for
> Arx II. Everything from flirting at a ball to surviving a dragon uses the same
> pipeline. What differs is how consequences are handled — not how checks work.

---

## The Spectrum

| Context | Check | Consequence Handler |
|---------|-------|-------------------|
| Social scene | `perform_check` | Narrative — displayed inline in scene, player decides response |
| Situation (exploration) | `perform_check` via `resolve_challenge` | Structured — ConsequenceEffect applies conditions, properties, flows |
| Combat | `perform_check` via combat system | Tactical — damage, conditions, positioning |

The check pipeline is identical in all contexts:
1. Weighted trait points (via CheckTypeTrait)
2. Aspect bonus (via PathAspect)
3. Extra modifiers (from conditions, buffs, equipment, etc.)
4. Total points → CheckRank → ResultChart → roll → CheckOutcome

**`resolve_challenge` is one consumer of `perform_check`, not a replacement for it.**
Social scenes call `perform_check` directly. Combat will call it through its own
resolution layer. The check stays generic; the context determines what happens with
the result.

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
- IMPOSSIBLE filtering (ResultChart has no success outcomes → action hidden)
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
