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

    Slice 1 ships these 9 values ONLY — the enum ships no inert entries;
    every value here has (or, per Task 2, will get) a registered evaluator
    with signature ``(ctx: SituationContext) -> bool``. ``SituationContext``
    (``perks.context``, Task 2) carries four fields: ``holder`` (the
    perk-owning vow-holder), ``subject`` (the acting character whose
    cast/check is resolving — equals ``holder`` for SELF perks), ``target``
    (the action's target sheet, ``None`` when the action has none), and
    ``resolution`` (the live resolution context — ``CombatRoundContext`` in
    combat, the check's context otherwise, ``None`` when absent). An
    evaluator whose required field is missing/``None`` returns False (a
    combat-positioning situation simply never holds outside combat; a
    DB-state situation like ``TARGET_DISTRACTED`` evaluates anywhere).
    DEFERRED to slices 2/3 (each arrives with its own machinery, not listed
    here): ``combat_opened_from_parley``, ``ambush_underway``,
    ``ally_intercepted_for_me``, ``attacker_abyssal``.

    - ``AT_RANGE`` — the holder's engagement distance profile this round is
      ranged (not adjacent to any engaged enemy). Reads ``resolution``
      (``CombatRoundContext``); False outside combat.
    - ``IN_MELEE`` — the holder's engagement distance profile this round is
      melee (adjacent to at least one engaged enemy). Reads ``resolution``;
      False outside combat.
    - ``SURROUNDED`` — the subject is engaged by at least a module-constant
      threshold of adjacent enemies this round. Reads ``subject`` +
      ``resolution``; False outside combat.
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
    - ``ALLY_LOW_HEALTH`` — at least one of the holder's engaged
      covenant-mates is below a module-constant health fraction (the "Last
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


class PerkEffectKind(models.TextChoices):
    """What a firing situational perk actually does (#2536 spec §3).

    All four values ship in slice 1's schema. ``POWER_BONUS``/``CHECK_BONUS``
    are wired into their resolution seams within this slice (Tasks 4-5).
    ``TIER_FLOOR``/``BOTCH_IMMUNITY`` are SCHEMA-ONLY this slice — rows may be
    authored but nothing reads them yet; the outcome-guarantee resolution
    logic (ruling 3, Apostate's can't-botch principle) ships in slice 2.

    - ``POWER_BONUS`` — flat power delta added to a qualifying technique
      cast, scaled by thread level, delivered via a new conditional
      ``PowerTermProvider``.
    - ``CHECK_BONUS`` — flat modifier added to a qualifying check, delivered
      via ``perform_check``'s optional ``situation_ctx`` threading, scoped
      by the perk's ``check_type`` (null = any check).
    - ``TIER_FLOOR`` — result-tier override: the check/cast cannot resolve
      below tier X. SLICE 2.
    - ``BOTCH_IMMUNITY`` — botch/critical-failure suppressed, downgraded to
      a plain failure. SLICE 2.
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
    - ``COVENANT_ALLIES`` — fires for an engaged covenant-mate's action;
      excludes the holder's own actions.
    - ``WHOLE_GROUP`` — fires for anyone in the group, including the holder.
    """

    SELF = "self", "Self"
    COVENANT_ALLIES = "covenant_allies", "Covenant Allies"
    WHOLE_GROUP = "whole_group", "Whole Group"
