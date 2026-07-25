# Level is a guaranteed, additive term on both sides of every check

#2707 (level both sides of check) closes two gaps found once ADR-0165's chart-direction
fix landed and made rank comparisons trustworthy again: a level-30 veteran and a level-1
recruit rolled identically on any check whose `CheckType` had no authored aspect
matching the character's Path (most checks), and a defender's level was invisible to
whichever side of an opposed check wasn't the roller — an attacker's technique swung at
a level-30 tyrant exactly as hard as at a level-1 recruit, and a lock's rating never grew
harder because the intruder outleveled the room. This ADR records the shape of the fix
that closes both gaps at once.

## Decision

**Level contributes `LEVEL_POINTS_PER_LEVEL` (5) points per level on the acting side of
every check, unconditionally.** `_compute_check_breakdown` adds `level_points =
LEVEL_POINTS_PER_LEVEL * level` into `total_points` for every `perform_check` call,
sourced from `world.progression.services.skill_development.get_character_path_level` —
never gated on an authored `CheckTypeAspect`. Before this, level only reached the roll
through the aspect bonus, which is zero unless the check's authored aspects happen to
match the character's Path; on every other check, level did nothing at all.

**Additive to the aspect bonus, never a replacement for it.** `level_points` and
`aspect_bonus` are two separate terms summed into `total_points`; a character whose Path
matches the check's authored aspects still gets the full aspect bonus on top of level
points. Level is a guaranteed floor under every check, not a substitute for authored
composition.

**The magnitude is brutal by design.** `LEVEL_POINTS_PER_LEVEL = 5` against a
`CheckRank` ladder whose rungs sit roughly 10-50 points apart means a four-level gap (20
points) typically crosses one to two rungs on its own, before a single trait or aspect
point is counted. The ladder itself was widened from four rungs to nine
(`0/10/25/50/80/115/155/200/250`, alongside the level term) specifically so a level-30
character doesn't pin at the old top rung from level 10 onward — level needs room to keep
mattering at the high end, where the power fantasy is loudest.

**The opposing side gets level too, through one of two mutually exclusive helpers.**
`compute_check_rating(character, check_type, extra_modifiers=0)` is the shared no-roll
answer for "what does this character bring to this check" (reuses
`_compute_check_breakdown`, so it already carries level points for whoever calls it).
Two callers build opposed-check difficulty on top of it:

- `level_opposition(check_type, *, level, character=None)` — the **passive** half: what
  a defender contributes when they are not spending a defence check of their own.
  `LEVEL_POINTS_PER_LEVEL * level` always, plus (when `character` is given) the acting
  check's aspects scored against the *defender's* Path — what you're trying to do to
  them is harder when it's their wheelhouse. `character=None` (an ephemeral NPC with no
  sheet) contributes level alone.
- `compute_resist_increment(defender_character, resist_effort_level)` — the **active**
  half: the defender's full `compute_check_rating` on the Composure `CheckType` (trait,
  specialization, aspect, capability, and perk points) plus the effort-level modifier,
  clamped to >= 0.

**The two opposing-side helpers are mutually exclusive — a call site uses one or the
other, never both.** `compute_resist_increment` already contains the defender's level
points internally, because it routes through the shared breakdown the same as any other
check; `level_opposition` adds level points too, on top of whatever authored difficulty
(a lock's rating, a ward's barrier strength) the caller already has. Using both at one
call site would double-count the defender's level. This is currently guaranteed only by
convention (each helper's docstring says so), not by a type-level guard, which makes it
the single easiest way for someone to break the balance later — hence writing it down
here as the invariant a future call site must honor. Combat wires three offense-side and
one defense-side call site through `level_opposition` (offense, penetration, and NPC
attack all read the *other* party's `CombatOpponent.level`); `compute_resist_increment`
is the social-resistance path (scenes' active-resistance actions), where the defender
rolls their own Composure check instead of standing on authored difficulty.

**Clash stays unopposed — `target_difficulty=0` there is deliberate, not an
oversight.** `world/combat/clash.py:310` still passes `target_difficulty=0` and must NOT
be wired to either opposing-side helper. A clash is a *symmetric contest*: both
participants roll their own check and the results are compared directly — the same
shape as `_resolve_joust_pass` (`world/combat/services.py`), which grades on
`check_a.success_level - check_b.success_level` rather than either side rolling against
the other's difficulty. Each side's level already rides its own acting-side
`level_points` term inside its own roll, so the level differential between the two
participants is already fully expressed by comparing the two outcomes. Adding an
opposition term on top would count level twice — once inside each roll, and again as an
artificial difficulty neither symmetric-contest shape needs. A future reader who notices
the bare `target_difficulty=0` here should not "fix" it into a double-count.

## Rejected alternatives

- **Reusing `power_tier_for_level`** (`world/covenants/power_tier.py`) — the obvious
  existing power-scaling helper, and #2706 had already flagged it as a candidate.
  Rejected: its bands are `TIER_ONE_MAX_LEVEL` (5) levels wide, so a level 1 character
  and a level 5 character land in the same tier. It cannot express the motivating case —
  a level 1 attacker's swing at a level 5 defender must already land differently, and a
  banded tier that treats levels 1-5 as identical can't do that. A per-level linear term
  was needed, not a banded tier.

> Status: accepted · Source: issue #2707 (level both sides of check) · relates to
> ADR-0165 (chart-direction convention; landed alongside this); extends ADR-0019; extends
> ADR-0145; supersedes nothing.
