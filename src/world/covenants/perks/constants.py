"""Situation + perk vocabulary for per-vow situational perks (#2536).

Code-defined labels with precise, testable semantics (ruling 5): adding a
situation later is a one-line enum value + a registered evaluator
(``perks.evaluators``, Task 2); attaching situations to perks, tuning
magnitudes, and authoring perk rows are data edits forever after.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models

from world.magic.constants import TechniqueFunction


class Situation(models.TextChoices):
    """Code-defined situation library for per-vow situational perks (#2536).

    Slice 1 shipped 9 values; ``CHAMPION_DUEL`` is slice 3's Battle-wiring
    addition (#2536 Task 3); ``COMBAT_OPENED_FROM_PARLEY`` and
    ``AMBUSH_UNDERWAY`` are slice 3's origin-marker addition (#2536 Task 4);
    ``ALLY_INTERCEPTED_FOR_ME`` is slice 3's declared-guard addition (#2536
    Task 5); ``ATTACKER_AFFINITY`` (renamed from its original Abyssal-only
    v1 spelling, #2623) is slice 3's defense-side seam addition (#2536 Task
    6); ``ON_CHOSEN_GROUND`` is #2646's whole-encounter chosen-ground
    addition — the enum ships no other inert entries; every value here has a
    registered evaluator with signature ``(ctx: SituationContext, params:
    SituationParams) -> bool`` (params parameterization landed #2623 Task 3 —
    see ``SITUATION_PARAM_SPECS`` below for which situations read which
    columns).
    ``SituationContext`` (``perks.context``) carries four required fields plus
    slice-3 scoping/defense fields: ``holder`` (the perk-owning vow-holder),
    ``subject`` (the acting character whose cast/check is resolving — equals
    ``holder`` for SELF perks), ``target`` (the action's target sheet,
    ``None`` when the action has none), ``resolution`` (the live
    resolution context — ``CombatRoundContext`` in combat, the check's
    context otherwise, ``None`` when absent), and ``attacker`` (the attacking
    entity on a defense-side resolution, ``None`` on every offense-side one —
    see ``ATTACKER_AFFINITY`` below). An evaluator whose required field is
    missing/``None`` returns False (a combat-positioning situation simply
    never holds outside combat; a DB-state situation like
    ``TARGET_DISTRACTED`` evaluates anywhere).

    - ``AT_RANGE`` — the SUBJECT's engagement distance profile this round is
      ranged (has at least one actively-engaged enemy, none of them sharing
      the subject's ``Position``). ``resolution`` is always the subject's
      round context (see ``SituationContext`` docstring) — corrected from an
      earlier "holder's" wording, since the same ``resolution`` object is
      reused across every candidate holder for one subject resolution. Reads
      ``resolution``; False outside combat or when unpositioned.
    - ``IN_MELEE`` — the SUBJECT's engagement distance profile this round is
      melee (at least one actively-engaged enemy shares the subject's
      ``Position``). Reads ``resolution``; False outside combat or when
      unpositioned.
    - ``SURROUNDED`` — the subject is engaged by at least a module-constant
      threshold of active ``EngagementLock`` rows this round (adjacency
      approximated via lock count, not the position graph — see
      ``perks.evaluators`` for why). Reads ``subject`` + ``resolution``;
      False outside combat.
    - ``TARGET_DISTRACTED`` — the target carries an applied condition whose
      template links a ``distraction``/``charm`` ``TechniqueFunction`` tag
      (or, absent technique->condition provenance, a name/category match —
      Task 2 verifies and documents which). Reads ``target``; DB-state,
      evaluates anywhere (False when ``target`` is None).
    - ``TARGET_SWAYED_BY_ALLY`` — the same distraction/charm condition as
      above, but applied by the holder or one of the holder's covenant-mates
      (the vow-holder's own self-created situation — worked-example
      calibration, spec §"Worked examples"). Reads ``holder`` + ``target``;
      DB-state, evaluates anywhere.
    - ``TARGET_FOCUSED_ELSEWHERE`` — the target's declared action this round
      targets someone other than the subject. Reads ``subject`` + ``target``
      + ``resolution``; False outside combat.
    - ``ALLY_LOW_HEALTH`` — at least one of the holder's co-present
      covenant-mates (mate's own engagement irrelevant, Tehom's 2026-07-20
      reversal) is below a module-constant health fraction (the "Last
      Bulwark" rung-1 calibration from the worked examples). Reads
      ``holder`` + ``resolution`` (group roster); False outside a resolvable
      group context.
    - ``DURING_NEGOTIATION`` — the subject's active scene is a social/parley
      context, not tactical combat. Reads ``subject``; DB-state, evaluates
      anywhere.
    - ``TARGET_FAVORABLY_DISPOSED`` — the target's disposition/regard toward
      the holder is favorable, set by a landed charm/flirt/social success
      (distinct from ``TARGET_SWAYED_BY_ALLY``, which reads applied
      conditions rather than disposition state). Reads ``holder`` +
      ``target``; DB-state, evaluates anywhere.
    - ``CHAMPION_DUEL`` — the SUBJECT is a participant in a Champion-duel
      combat encounter (#2536 slice 3 Battle wiring). The flag is stamped
      exclusively by ``world.battles.services.open_champion_duel`` on the
      ``CombatEncounter`` it creates — every other DUEL creation path,
      including the siege-engine skirmish opened by
      ``open_siege_engine_encounter`` (same ``create_lethal_duel`` helper,
      no Champion-role requirement), leaves ``is_champion_duel`` False.
      Combat checks/casts already thread ``resolution`` (a
      ``CombatRoundContext``) into every ``SituationContext``, so no new
      threading was needed for this situation. Reads ``resolution``; False
      outside combat.
    - ``COMBAT_OPENED_FROM_PARLEY`` — the SUBJECT's combat encounter was
      CREATED (never fed) by ``world.combat.cast_seed.
      seed_or_feed_encounter_from_cast`` while its seeding Scene was an
      active, non-Battle-backed Scene — "this fight started as a
      conversation that turned hostile" (#2536 slice 3, Task 4). v1
      approximation (PR-body judgment call): holds for the encounter's
      ENTIRE lifetime once stamped, not just its opening moment. Reads
      ``resolution``; False outside combat.
    - ``AMBUSH_UNDERWAY`` — v1 semantics (documented approximation): holds
      only during ROUND 1 of an encounter that opened as a surprise —
      either ``opened_from_parley=True`` OR a round-1 ``from_entrance=True``
      ``CombatRoundAction`` exists (a dramatic technique-entrance opener,
      #2183) — and is False from round 2 on. Reads ``resolution``; False
      outside combat.
    - ``ALLY_INTERCEPTED_FOR_ME`` — a covenant-mate of the HOLDER, co-present
      in the SUBJECT's encounter, has an armed (``is_ready=True``) INTERPOSE
      declaration THIS round whose ``focused_ally_target`` is the SUBJECT's
      participant or ``None`` (guard-anyone) (#2536 slice 3, Task 5).
      Ratified v1 judgment call: DECLARED-guard semantics — declared cover
      counts as soon as it is armed; the situation does not wait for the
      interpose to actually intercept damage. Reads ``holder`` + ``resolution``;
      False outside combat.
    - ``ATTACKER_AFFINITY`` — the attacking entity on a DEFENSE resolution is
      typed to an authored affinity axis (#2536 slice 3 Task 6; renamed +
      parameterized #2623, see ``SITUATION_PARAM_SPECS`` below — required
      param ``affinity``, optional ``threshold_percent``): a ``CombatOpponent``
      with a non-empty authored ``affinity`` matching the row's ``affinity``
      is definitional (threshold ignored); otherwise falls back to a
      reachable ObjectDB's ``CharacterAura`` — with ``threshold_percent`` set,
      that axis's percentage must be >= the threshold; unset, the aura's
      ``dominant_affinity`` must equal the axis. Reads ``attacker``; False
      when ``attacker`` is ``None`` (every offense-side resolution) or
      carries no affinity/aura data. ``world.combat.services.
      resolve_npc_attack`` is the only defense-check site that threads
      ``attacker`` in v1. Task 3 wires the evaluator itself to the params
      contract; the enum rename lands here (#2623).
    - ``ON_CHOSEN_GROUND`` — the SUBJECT's combat encounter was created on ground
      the caster's side prepared ahead of time (#2646) — "the fight was won
      yesterday." The flag is stamped exclusively at encounter-CREATE time by
      ``world.combat.chosen_ground.compute_on_chosen_ground``, called from the
      three PC-vs-NPC encounter-creation seams (``world.combat.cast_seed.
      seed_or_feed_encounter_from_cast``, ``world.combat.duels.
      create_lethal_duel``, ``world.battles.services.open_place_encounter``);
      ``world.combat.duels.create_pvp_duel`` never stamps it (PvP is never
      lethal). False outside combat, mirroring ``CHAMPION_DUEL``'s shape — a
      whole-encounter stamp that holds every round once set, never re-derived
      mid-fight. Reads ``resolution``.
    """

    AT_RANGE = "at_range", "At Range"
    IN_MELEE = "in_melee", "In Melee"
    SURROUNDED = "surrounded", "Surrounded"
    TARGET_DISTRACTED = "target_distracted", "Target Distracted"
    TARGET_SWAYED_BY_ALLY = "target_swayed_by_ally", "Target Swayed by Ally"
    TARGET_FOCUSED_ELSEWHERE = "target_focused_elsewhere", "Target Focused Elsewhere"
    ALLY_LOW_HEALTH = "ally_low_health", "Ally Low Health"
    DURING_NEGOTIATION = "during_negotiation", "During Negotiation"
    TARGET_FAVORABLY_DISPOSED = "target_favorably_disposed", "Target Favorably Disposed"
    CHAMPION_DUEL = "champion_duel", "Champion Duel"
    COMBAT_OPENED_FROM_PARLEY = "combat_opened_from_parley", "Combat Opened From Parley"
    AMBUSH_UNDERWAY = "ambush_underway", "Ambush Underway"
    ALLY_INTERCEPTED_FOR_ME = "ally_intercepted_for_me", "Ally Intercepted for Me"
    ATTACKER_AFFINITY = "attacker_affinity", "Attacker Affinity"
    ON_CHOSEN_GROUND = "on_chosen_ground", "On Chosen Ground"


class PerkEffectKind(models.TextChoices):
    """What a firing situational perk actually does (#2536 spec §3).

    All four values are live. ``POWER_BONUS``/``CHECK_BONUS`` are wired into
    their resolution seams (Tasks 4-5). ``TIER_FLOOR``/``BOTCH_IMMUNITY``
    (#2536 slice 2) fire in ``perform_check``'s outcome resolution: both are
    absolute (never thread-scaled) and ungated, and announce only when they
    actually alter the resolved outcome.

    - ``POWER_BONUS`` — flat power delta added to a qualifying technique
      cast, scaled by thread level, delivered via a new conditional
      ``PowerTermProvider``.
    - ``CHECK_BONUS`` — flat modifier added to a qualifying check, delivered
      via ``perform_check``'s optional ``situation_ctx`` threading, scoped
      by the perk's ``check_type`` (null = any check).
    - ``TIER_FLOOR`` — result-tier override: the resolved outcome cannot land
      below the perk's authored ``floor_success_level`` (canonical -10..+10
      scale).
    - ``BOTCH_IMMUNITY`` — a botch/critical failure (``success_level`` ≤
      ``world.checks.constants.BOTCH_SUCCESS_LEVEL_MAX``) is downgraded to
      the least-bad non-botch outcome instead.
    """

    POWER_BONUS = "power_bonus", "Power Bonus"
    CHECK_BONUS = "check_bonus", "Check Bonus"
    TIER_FLOOR = "tier_floor", "Tier Floor"
    BOTCH_IMMUNITY = "botch_immunity", "Botch Immunity"


class PerkBeneficiary(models.TextChoices):
    """Who benefits when a ``VowSituationalPerk`` fires (#2536 spec §2).

    Evaluated at the ACTING character's resolution moment, never on the
    perk-holder's own timer — see ``perks.services.applicable_perks``
    (Task 3).

    - ``SELF`` — fires only for the perk-owning vow-holder's own actions.
    - ``COVENANT_ALLIES`` — fires for a co-present covenant-mate's action
      (membership + co-presence — the mate's OWN engagement is irrelevant,
      Tehom's 2026-07-20 reversal); excludes the holder's own actions.
    - ``WHOLE_GROUP`` — fires for anyone in the group, including the holder.
    """

    SELF = "self", "Self"
    COVENANT_ALLIES = "covenant_allies", "Covenant Allies"
    WHOLE_GROUP = "whole_group", "Whole Group"


class SituationOriginSide(models.TextChoices):
    """Which side sprang a directed combat-origin situation (#2623).

    Read against ``CombatEncounter.initiated_by_pc_side``; v1 side model: the
    subject is always a PC, so the PC side is "ours".
    """

    OURS = "ours", "Our Side Sprang It"
    THEIRS = "theirs", "Their Side Sprang It"


@dataclass(frozen=True)
class SituationParamSpec:
    """Which parameter columns a situation reads (#2623 spec §2)."""

    allowed: frozenset[str]
    required: frozenset[str] = frozenset()


#: Per-situation parameter contract. A situation absent here reads NO params;
#: clean() rejects any authored param it does not read, both directions.
SITUATION_PARAM_SPECS: dict[str, SituationParamSpec] = {
    Situation.ATTACKER_AFFINITY: SituationParamSpec(
        allowed=frozenset({"affinity", "threshold_percent"}),
        required=frozenset({"affinity"}),
    ),
    Situation.ALLY_LOW_HEALTH: SituationParamSpec(allowed=frozenset({"threshold_percent"})),
    Situation.SURROUNDED: SituationParamSpec(allowed=frozenset({"count_threshold"})),
    Situation.TARGET_FAVORABLY_DISPOSED: SituationParamSpec(allowed=frozenset({"count_threshold"})),
    Situation.AMBUSH_UNDERWAY: SituationParamSpec(allowed=frozenset({"origin_side"})),
    Situation.COMBAT_OPENED_FROM_PARLEY: SituationParamSpec(allowed=frozenset({"origin_side"})),
}


#: Which ``TechniqueFunction`` casts can CREATE each DB-state ``Situation`` (#2640,
#: the Sphinx of Black Quartz) — the ``target_swayed_by_ally``/``target_distracted``
#: provenance mapping (``perks.evaluators``, which reads applied-condition rows for
#: LIVE resolution) run in REVERSE as a static report: "which of my kit's function
#: tags could plausibly have produced this DB-state situation in the first place."
#: A situation absent from this dict demands nothing from a kit — it is a
#: positional/encounter state (``AT_RANGE``, ``SURROUNDED``, ``CHAMPION_DUEL``, ...)
#: with no single-cast provenance, not an oversight. Extending this mapping (a new
#: row, or a new function added to an existing set) is a deliberate one-line change
#: — see ``world.covenants.sphinx`` for the only reader.
SITUATION_CREATOR_FUNCTIONS: dict[str, frozenset[str]] = {
    Situation.TARGET_SWAYED_BY_ALLY: frozenset(
        {TechniqueFunction.CHARM, TechniqueFunction.DISTRACTION}
    ),
    Situation.TARGET_DISTRACTED: frozenset(
        {TechniqueFunction.CHARM, TechniqueFunction.DISTRACTION}
    ),
    Situation.TARGET_FAVORABLY_DISPOSED: frozenset({TechniqueFunction.CHARM}),
}
