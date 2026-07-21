"""Situation + perk vocabulary for per-vow situational perks (#2536).

Code-defined labels with precise, testable semantics (ruling 5): adding a
situation later is a one-line enum value + a registered evaluator
(``perks.evaluators``, Task 2); attaching situations to perks, tuning
magnitudes, and authoring perk rows are data edits forever after.
"""

from __future__ import annotations

from django.db import models


class Situation(models.TextChoices):
    """Code-defined situation library for per-vow situational perks (#2536).

    Slice 1 shipped 9 values; ``CHAMPION_DUEL`` is slice 3's Battle-wiring
    addition (#2536 Task 3) — the enum ships no other inert entries; every
    value here has a registered evaluator with signature ``(ctx:
    SituationContext) -> bool``. ``SituationContext`` (``perks.context``)
    carries four required fields plus slice-3 scoping/defense fields:
    ``holder`` (the perk-owning vow-holder), ``subject`` (the acting
    character whose cast/check is resolving — equals ``holder`` for SELF
    perks), ``target`` (the action's target sheet, ``None`` when the action
    has none), and ``resolution`` (the live resolution context —
    ``CombatRoundContext`` in combat, the check's context otherwise,
    ``None`` when absent). An evaluator whose required field is
    missing/``None`` returns False (a combat-positioning situation simply
    never holds outside combat; a DB-state situation like
    ``TARGET_DISTRACTED`` evaluates anywhere). DEFERRED (each arrives with
    its own machinery, not listed here): ``combat_opened_from_parley``,
    ``ambush_underway``, ``ally_intercepted_for_me``, ``attacker_abyssal``.

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
