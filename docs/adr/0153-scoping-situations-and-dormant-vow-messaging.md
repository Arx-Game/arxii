# Court/Battle scoping, five new situations, the defense-side seam, and dormant-vow messaging

ADR-0151/ADR-0152 shipped Layer 4's live-firing machinery and outcome guarantees. This slice
(3 of 3, #2536) closes the remaining spec gaps: narrowing WHEN a fired perk applies to Court/
Battle contexts, four deferred situations plus a bonus fifth, a defense-side evaluation point,
and ruling 2's "loud OFF state" for a disengaged vow. It records the decisions worth keeping,
not a restatement of the spec (`gh issue view 2536`).

## Three scope columns, AND semantics, per-kind clean gates

`VowSituationalPerk` gains `mission_category`/`mission_template` (FKs) and `battle_action_kind`
(a `BattleActionKind` CharField) — narrower than a `Situation` (which asks "is this game-state
true right now"), a scope column asks "is this fired perk even eligible for THIS check/cast."
Every non-empty scope column on a row must match (AND composition — the same logic
`VowSituationalPerkSituation` uses for its own AND composition); an empty scope always matches,
so scoping is opt-in per perk. `perk_scope_matches` (`world.covenants.perks.services`) is the
single seam both fired-perk providers (`checks.services._situational_perk_check_bonus` for
CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY, `magic.services.power_terms.vow_situational_power_term`
for POWER_BONUS) filter through — one rule, one place, matching the existing `check_type` scope
column's shape rather than inventing a second scoping mechanism.

Rejected: a single generic "scope" filter (JSON blob or a small predicate DSL) that could
express arbitrary future scoping in one column. No JSON fields (ADR-0007) rules out the blob
form outright, and a predicate DSL would move scoping out of the queryable, admin-editable,
`clean()`-validated column world every other authored constraint in this table lives in — for
three concrete, enumerable axes (mission category, mission template, battle action kind), three
typed FK/CharField columns are simpler to author, validate, and query than a general mechanism
built for scopes that don't exist yet.

`mission_category`/`mission_template` are meaningful ONLY on `effect_kind=CHECK_BONUS` rows
(mission checks are CHECK_BONUS-only in v1 — no mission cast/power-bonus path exists);
`battle_action_kind` is meaningful on `CHECK_BONUS` **or** `POWER_BONUS` (a Battle warfare roll
scopes both the check AND the technique cast it may carry, spec §4). `clean()` rejects each
column authored outside its valid `effect_kind` set — the same per-kind gate pattern
`floor_success_level` (ADR-0152) and `check_type` (ADR-0151) already enforce, rather than a
looser "any scope on any kind" rule that would let a `TIER_FLOOR` row silently author a
`mission_category` no delivery seam would ever read.

## Champion duel is a Situation, not a scope column

`Situation.CHAMPION_DUEL` (a new evaluator reading `participant.encounter.is_champion_duel` off
`ctx.resolution`) joins the library rather than becoming a fourth scope column. Rejected: a
`combat_encounter_kind`-style scope column mirroring `battle_action_kind`. A duel is a
game-state fact about the resolving character's OWN encounter ("is this the encounter I am
fighting in a Champion duel"), the exact shape every other combat `Situation` already answers
(`AT_RANGE`, `IN_MELEE`, `SURROUNDED`) — not a caller-supplied classification of the CHECK
itself the way `battle_action_kind` is (the caller declares which warfare verb it is; nobody
declares "this check is a champion-duel check"). `CombatEncounter.is_champion_duel` is stamped
exclusively by `world.battles.services.open_champion_duel`; the sibling
`open_siege_engine_encounter` path (same `create_lethal_duel` helper, no Champion-role
requirement) leaves it False, so the flag distinguishes the two DUEL-creation paths precisely.

## The defense-side seam: `SituationContext.attacker` + `resolve_npc_attack` threading

Every situational-perk delivery seam through slice 2 fired only on the SUBJECT's own OFFENSIVE
action — a defender's `perform_check` call never threaded a `situation_ctx` at all, so
CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY perks (including any that key on the attacker, like the
new `ATTACKER_ABYSSAL`) were structurally unreachable on defense. `world.combat.services
.resolve_npc_attack` now builds a `SituationContext` with `attacker=opponent_action.opponent`
(the NPC's `CombatOpponent`) and threads it into the defender's real `perform_check` call — the
one context where the SUBJECT is not the aggressor, so `target` stays `None` and `attacker`
carries the attacking entity instead. `SituationContext.attacker` existed as a field since Task 1
but was never propagated into `applicable_perks`/`_PerkResolver`'s per-holder evaluation context
until this slice — fixed alongside the `resolve_npc_attack` wiring so `ATTACKER_ABYSSAL` can
actually observe a live attacker.

Rejected: a separate defense-side perk pipeline (its own `applicable_perks`-shaped function, its
own delivery seam) mirroring the offense path structurally but reading attacker instead of
target. `perform_check`'s `situation_ctx` parameter is already a generic optional context slot —
adding one more optional field (`attacker`, defaulting to `None`, byte-identical to pre-slice-3
behavior when unset) and threading it through the SAME `applicable_perks`/`_PerkResolver`/
delivery-seam code every offense check already runs is strictly less machinery than a parallel
pipeline, and keeps CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY perks working identically regardless
of which side of the roll fired them. `resolve_npc_attack` is the ONLY defense-check site
threaded with `attacker` in v1 — the penetration-vs-ward PvP path has no defender roll to thread
this into; that gap is a documented v1 scope limit, not an oversight (see `attacker_abyssal`'s
PvP note in `world.covenants.perks.evaluators`).

## Declared-guard semantics for `ally_intercepted_for_me`

`Situation.ALLY_INTERCEPTED_FOR_ME` holds the instant a covenant-mate's INTERPOSE declaration is
armed (`is_ready=True`) this round and guards the subject (`focused_ally_target` is the
subject's participant or `None` for guard-anyone) — DECLARED-guard semantics, ratified v1
judgment call. "The guarded moment is the situation": a perk keying off this fires when cover is
committed, not later when the interpose actually resolves and intercepts damage (which may not
happen at all — the guarded character might not be attacked this round).

Rejected: fired-marker persistence — stamping a flag (on the `CombatRoundAction` or the
participant) only once the INTERPOSE actually intercepts a hit, and keying the situation off
that instead. That would tie the situation to damage resolution timing, which happens AFTER
checks/casts have already resolved for the round in most orderings — a perk meant to reward "an
ally is standing between you and harm right now" would frequently evaluate too late to ever see
the state it's testing for. Declared-guard keeps the evaluation point aligned with when the
situation is actually meaningful to the guarded character: the moment they know someone has
their back, before the round's blows land.

## Parley/ambush v1 approximations

`CombatEncounter.opened_from_parley` is stamped only at encounter CREATE time (never on an
existing encounter fed by a later cast) by `world.combat.cast_seed
.seed_or_feed_encounter_from_cast`, when the seeding Scene is itself active and
non-Battle-backed (mirrors `during_negotiation`'s classification, ADR-0151). Once stamped, both
`Situation.COMBAT_OPENED_FROM_PARLEY` and (as one of two OR'd conditions) `Situation
.AMBUSH_UNDERWAY` read it for the encounter's ENTIRE lifetime — a documented v1 approximation:
"this fight started as a conversation that turned hostile" stays true at round 20 exactly as it
was at round 1, rather than decaying as the fight's own texture changes. `AMBUSH_UNDERWAY`
narrows this with its own approximation: holds ONLY during round 1 (checked via
`CombatEncounter.round_number`, the `AbstractRound` scalar shared with `SceneRound`) AND either
`opened_from_parley` OR a round-1 `from_entrance=True` `CombatRoundAction` (the #2183 dramatic
technique-entrance marker) — closing at round 2 regardless of how the fight opened.

Both approximations trade precision for the ceiling this slice holds everywhere else: zero new
polling machinery, zero new event-scoped state, reading only fields the encounter and its round
actions already carry. A more precise "opening MOMENT only" `opened_from_parley` semantic (e.g.
clearing after round 1) was considered and rejected as premature — no perk content or playtesting
exists yet to justify the added state-transition complexity; the flag can be narrowed later
without a schema change if that turns out to matter.

## Dormant-vow messaging is holder-only WHISPER, never the room

Ruling 2's "loud OFF state": `dormant_perk_firings` + `announce_dormant_perks`
(`world.covenants.perks.services`) enumerate the SUBJECT's own active-but-DISENGAGED
memberships (the inverted mirror of `_self_candidates`), run the same `_PerkResolver` situation
evaluation plus the slice-3 scope filter, and deliver the exact line `"your vow lies dormant —
{perk.name} would have answered here"` to the holder ALONE — a narrator-authored WHISPER-mode
`Interaction` (receiver-scoped to the subject's primary persona) plus a direct telnet
`.msg()` companion, wired into all three fired-perk seams (`_situational_perk_check_bonus`,
`_apply_outcome_guarantees`, `vow_situational_power_term`) right after each one's own live
`applicable_perks` call.

Rejected: broadcasting the dormant line to the room, mirroring `announce_fired_perks`'s
dual-dispatch presentation contract (ADR-0151) for LIVE firings. A live firing is a moment other
players in the scene should see — it's the vow shining, the spec's "loud, visible moment in
both clients" ruling. A dormant notice is the opposite: a diagnostic aside for the one player
whose vow could have answered and didn't, telling them WHY nothing happened. Broadcasting it
would spam every other participant with a non-event on every check where a `TIER_FLOOR` row is
merely eligible-but-disengaged (the common case for a partially-engaged holder), the identical
spam risk ADR-0152 already rejected for announce-on-eligible outcome guarantees — but now
multiplied by every onlooker in the room instead of contained to the one player it's actually
for.

> Status: accepted · Source: issue #2536 (slice 3 of 3) · Amends: none · Related: ADR-0149
> (four-layer vow-power model — Layer 4), ADR-0151 (situational-perk machinery, slice 1 —
> scoping mirrors its `check_type` scope-column shape, dormant messaging mirrors its
> dual-dispatch announce discipline), ADR-0152 (outcome guarantees, slice 2 — dormant messaging
> covers TIER_FLOOR/BOTCH_IMMUNITY too), #2183 (technique-entrance `from_entrance` marker — the
> precedent `ambush_underway` reuses), ADR-0118 (guardian reaction seam — informed the deferred
> `ally_intercepted_for_me` situation this slice ships)
