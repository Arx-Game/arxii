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


@dataclass(frozen=True)
class SituationContext:
    """Immutable input to a ``Situation`` evaluator (spec §1).

    Four fields, all read-only for the duration of one evaluation:

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
