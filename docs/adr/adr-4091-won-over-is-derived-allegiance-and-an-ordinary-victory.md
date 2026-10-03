# ADR-4091: A won-over enemy is a derived allegiance, and winning them all is an ordinary victory

**Issue:** #4091 · **Related:** ADR-0059 (amended, see below), ADR-0058 (disposition storage,
unchanged), ADR-0010 (FK direction).

## Context

Charm (`Charmed`) and calm (`Calm`) already made an enemy sit a fight out, but no NPC could ever
attack another NPC, so a charmed enemy could not fight for the party and a turned enemy could not
fight its own side. Allegiance was also read by matching a condition's *name*
(`world/npc_services/allegiance.py`), which the repo's naming rules disallow: renaming `Charmed`
in admin silently broke every charm in the game. ADR-0059 had named the intended substrate for
this future work as "a future `allegiance` flip on an existing ENEMY opponent," a single mutable
field write.

## Decision

**D4. Allegiance stays derived on read; ADR-0059's flip sentence is superseded.** No condition
ever writes `CombatOpponent.allegiance`. It stays a stored field meaning "ALLY (summon, companion)
or ENEMY (everyone else)," set once at creation and never touched by a charm. A new
`ConditionTemplate.sets_allegiance` field (blank, or `ALLY_OF_CASTER`/`TURNED`/`NEUTRAL`) names
what side a condition puts its bearer on while it holds. `effective_allegiances()`
(`world/npc_services/allegiance.py`) composes the stored field with the bearer's active
allegiance-flagged conditions in one batched query, with fixed precedence charm, then turned,
then calm when more than one holds (Decision 5). The field is read, never the condition's name;
renaming `Charmed` to anything changes nothing, and the only name literals left in the codebase
are a historical-snapshot data migration and the out-of-scope parley Calm producer. Rejected:
flipping `CombatOpponent.allegiance` itself (ADR-0059's original plan). A stored flip can't
un-flip itself when the charm ends without a second write-back, and it collapses "why is this
NPC friendly" into one field that a renamed or stacked condition can no longer explain.

**In-fight routing (Decisions 1 through 5).** A charmed (`ALLY_OF_CASTER`) opponent targets other
opponents whose effective allegiance is still `ENEMY` or `TURNED`, never a PC. A turned opponent
targets other stored-`ENEMY` opponents still effectively `ENEMY`, never itself, never a PC. A
calmed (`NEUTRAL`) opponent skips its round. Stored-`ENEMY` opponents keep targeting PCs and
ignore charmed/turned NPCs the way they already ignore summons (Decision 3); no retaliation
against a won-over NPC in this issue. PC area and enemy-wide effects skip a charmed NPC; a
deliberate single-target attack on one stays legal (Decision 4).

**D1. Social victory is an ordinary `VICTORY`, priced like any other.** When every remaining
enemy opponent is won over (charmed, turned, or calmed) or otherwise overcome, the encounter
completes as `VICTORY`, no new outcome kind. `_classify_encounter_outcome`
(`world/combat/services.py`) treats a won-over enemy exactly like a defeated one for "any hostile
remain," via `hostile_opponents_remain`. Rewards (aftermath pools, Legend, the outcome line) come
from the same (outcome, risk) axes a fought win uses, never a separate flat table, never gated on
whether violence occurred (Decision 10). `OpponentStatus.WON_OVER` is stamped on each won-over
opponent at victory (`stamp_won_over_opponents`) so the per-opponent aftermath pool, the digest,
and the bind window can all find it later. `_apply_opponent_aftermath_pools` fires a won-over
opponent's authored pool on the same pass as a `DEFEATED` one: "overcome," not "defeated," is
what unlocks it.

**Hero Killer.** A Hero Killer that is won over counts like any other enemy: social victory ends
the fight even against an unbeatable boss, since the whole point of social victory is that it
never needed to be beatable. A Hero Killer that instead fled, was defeated, or was removed still
blocks `VICTORY` (`forced_escape`'s original rule, that any non-ACTIVE Hero Killer forbids
victory, is unchanged); only the won-over case is new.

**Ruling R1: only holds applied during this fight win it.** `hostile_opponents_remain` and
`stamp_won_over_opponents` both filter allegiance instances to `applied_since
=encounter.created_at`. Without this, striking an NPC that was already charmed before this fight
started ends the encounter in an instant, fully-rewarded `VICTORY` on the first hit: a farm. A
pre-charmed NPC still never attacks PCs during the fight (routing reads every active hold,
regardless of when it was applied); it simply doesn't count toward ending this particular
encounter.

**Settling and breaking (Decisions 13, 15 through 17).** `ConditionTemplate
.settle_consequence_pool` (and a stage-level override) grades how a charm ends.
`ActionTemplate.settles_allegiance` marks the one Settle template (`clean()` rejects a second).
Anyone present may settle a held NPC through the ordinary scene social-action pipeline; the
graded result lands through `end_allegiance_with_pool`, which also removes the designating
condition so the removal event fires. NPCs are targets, not rollers (Decision 15):
`attempt_break_free` refuses outright on any condition with `sets_allegiance` set; there is no
NPC break-free roll for a hold. Instead, a PC who harms a held NPC rolls to break it (Decision
16): hold strength is severity points (`charm_strength_points`) plus the hold's own caster's
level opposition, the same `level_opposition` term `attempt_break_free` already uses for this,
never a parallel formula, and difficulty is `max(0, strength - resistance - pressure)`, where
resistance is the target's own level/traits (`compute_resist_increment`) and pressure is the
blow's post-soak damage scaled by the target's max health. The roll (`attempt_allegiance_break`)
fires once per target per action, on the summed pressure of every blow that got through that
action, not once per profile, which would let a multi-hit action roll the break check repeatedly
for one action.

**Send away ends the hold (Decision 20).** `send_away` drops a named NPC off the grid
(`location = None`) rather than deleting it: most NPCs have no home to return to, and a GM places
it again when the story calls for it. Its persona, sheet, and `ObjectDB` survive untouched; only
the designating allegiance condition is lifted (`remove_condition`), so the hold really ends, not
just the body leaving. An ephemeral nameless won-over NPC is deleted instead, through the shared
identity-map-safe `delete_ephemeral_npc` guard, never a bare `.delete()`, and falls back to the
named-NPC drop-and-lift path if that guarded delete is refused, so a refusal never reports a
success that didn't happen.

**Shared predicates, one gate each.** `actor_holds_sway_present`
(`world/npc_services/allegiance.py`) answers "does this actor hold a qualifying allegiance
instance on this target, and are the two co-located right now," the one predicate behind Send
away's prerequisite, Retain's prerequisite, the won-over digest row's `can_send_away` flag, the
persona menu items, and telnet's `sendaway`/`retain`. `bind_window_open`
(`world/combat/won_over.py`) answers "is this charmed nameless opponent still bindable" and gates
both `can_bind` on the digest row and `promote_summon_to_companion`'s charmed-enemy path (telnet
`companion promote` and the web bind action). Before this PR these were separate, drifting
checks; one combat-opponent prerequisite never checked presence at all, so an action could
succeed on a target the digest already called gone.

**Decision 21 (no fix here, recorded for the ADR trail).** A charm's lapse never starts a fight.
A one-minute sweep (`lapsed_allegiance_sweep`) removes expired allegiance instances through
`remove_condition`, firing the removal event, and narrates a placeholder fade line where the NPC
is still present; it never opens an encounter and never errors on a target that moved, was
deleted, or sits in another live encounter. The hourly bulk condition-expiry cleanup
(`batch_condition_expiration_cleanup`) now skips every `sets_allegiance`-bearing row, so the
one-minute sweep is always the one that owns (and fires the removal event for) an allegiance
condition's expiry. Whether a lapsed NPC can ever turn hostile on its own is explicitly deferred
to #4121 (NPC motive, force comparison), out of scope here by design, not by omission.

**Renewing is a cast, never a fight (Decision 9).** Re-casting a pure allegiance technique on a
target the caster already holds (`is_allegiance_renewal`, `world.magic.services.hostility`)
routes through the ordinary immediate-cast path instead of `_route_hostile_cast`, even though the
same technique aimed at a fresh target is hostile (it targets `ENEMY`). Striking first still
opens a fight normally; renewal is narrow: no damage profile, no removed conditions, every
applied condition sets allegiance, and the caster already has an active hold sourced on that
exact target.

## Rejected

A peaceful-win reward table, priced separately from a fought win (Decision 10 rejects rewarding
or penalizing by whether violence occurred); an NPC break-free roll against an allegiance hold
(Decision 15: NPCs are targets, PCs roll); `LAUNCH_ATTACK` or any mechanism that lets a lapsed
NPC resume fighting on its own (Decision 21: deferred whole to #4121, never built as a stopgap
here).

> Status: accepted · Source: issue #4091 · Supersedes in part: ADR-0059's sentence naming a
> future `allegiance` flip on an existing ENEMY opponent (the substrate is derived-on-read
> instead; the rest of ADR-0059, the mutable field for summons, `summoned_by`/
> `bond_expires_round`, the `opponent_targets` M2M, is unchanged).
