"""Situation evaluation context for per-vow situational perks (#2536).

``SituationContext`` is the single input every registered evaluator
(``perks.evaluators``) reads. See that module's ``SITUATION_EVALUATORS``
registry for the evaluator signature contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.missions.models import MissionInstance


@dataclass(frozen=True)
class SituationContext:
    """Immutable input to a ``Situation`` evaluator (spec §1).

    Four required fields plus three optional scoping/defense fields (#2536
    slice 3), all read-only for the duration of one evaluation:

    - ``holder`` — the ``CharacterSheet`` of the perk-owning vow-holder (the
      covenant-role holder whose ``VowSituationalPerk`` is being tested).
    - ``subject`` — the ``CharacterSheet`` of the acting character whose
      cast/check is resolving right now. Equals ``holder`` for ``SELF``
      perks; differs for ``COVENANT_ALLIES``/``WHOLE_GROUP`` perks, where a
      covenant-mate's vow answers on the SUBJECT's action.
    - ``target`` — the acting character's action target, or ``None`` when
      the action has no target (self-buffs, untargeted checks).
    - ``resolution`` — the live resolution context for the SUBJECT's action:
      a ``CombatRoundContext`` (``world/combat/round_context.py:136``) in
      combat, a check-pipeline context otherwise, or ``None`` when no
      resolution context is threaded (e.g. a bare DB-state evaluation).
      Callers always construct ``resolution`` from the RESOLVING character
      (the subject) — see ``perks.services.applicable_perks`` (Task 3), which
      reuses one ``resolution`` object across every candidate perk holder for
      a single subject resolution. Evaluators that must read a specific
      character's positional/round state therefore read it off
      ``resolution`` as the SUBJECT's state (documented per-evaluator in
      ``perks.evaluators``), not the holder's.
    - ``mission`` — the live ``MissionInstance`` for a mission-driven check
      (Court scoping, #2536 slice 3), or ``None`` outside a mission
      resolution. Read by ``perks.services.perk_scope_matches`` for
      ``mission_category``/``mission_template`` scope matching and by any
      mission-flavored ``Situation`` evaluator; a scope column authored on a
      perk fails to match whenever ``mission is None``.
    - ``battle_action_kind`` — the declared ``BattleActionKind`` (a value
      from ``world.battles.constants.BattleActionKind``) for a warfare roll
      (Battle scoping, #2536 slice 3), or ``None`` outside a Battle
      declaration. Read by ``perks.services.perk_scope_matches`` for
      ``battle_action_kind`` scope matching.
    - ``attacker`` — the attacking entity (a ``CombatOpponent`` or an
      ObjectDB-backed attacker) when the SUBJECT is resolving a DEFENSE —
      the one context where the subject is not the aggressor (defense-side
      seam, #2536 slice 3). ``None`` for every offense-side resolution.

    **Conventions (stated once, spec §1):**

    - An evaluator whose required field is missing/``None`` returns
      ``False`` — a combat-positioning situation simply never holds outside
      combat (``resolution is None`` or lacks the expected shape).
    - DB-state evaluators (conditions, disposition, scene state) are NOT
      gated on ``resolution`` being present — they evaluate anywhere,
      reading only ``holder``/``subject``/``target``.
    - Holder/subject-only situations ignore ``target``.
    - Group-scan situations (e.g. ``ally_low_health``) read a roster off
      ``resolution`` (the subject's encounter/scene), not a separate field.
    """

    holder: CharacterSheet
    subject: CharacterSheet
    target: CharacterSheet | None
    resolution: object | None
    mission: MissionInstance | None = None
    battle_action_kind: str | None = None
    attacker: object | None = None


@dataclass(frozen=True)
class SituationParams:
    """Authored parameters of one situation-requirement row (#2623 spec §2).

    Hashable so ``_PerkResolver`` can key its evaluation cache on
    ``(situation, params, holder_pk)``. Blank/None fields mean "use the
    evaluator's documented default" (module constants in ``perks.evaluators``).
    """

    threshold_percent: int | None = None
    count_threshold: int | None = None
    affinity: str = ""
    origin_side: str = ""


#: Shared no-parameter instance (the default for every pre-#2623 row shape).
NO_PARAMS = SituationParams()
