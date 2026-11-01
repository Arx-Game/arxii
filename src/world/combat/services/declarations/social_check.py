"""Social combat checks: difficulty, verb success, and consequences."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.social_target import SocialDifficulty, social_target_difficulty
from world.checks.types import ModifierContribution
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.techniques.technique_targets import _resolve_primary_target_sheet
from world.fatigue.constants import EffortLevel

if TYPE_CHECKING:
    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ModifierBreakdown, PendingResolution
    from world.scenes.models import Interaction


# ---------------------------------------------------------------------------
# Round resolution orchestrator
# ---------------------------------------------------------------------------


def _record_combat_consequence(  # noqa: PLR0913 - mirrors record_consequence_outcome's fields
    sheet: CharacterSheet,
    check_type: CheckType,
    pool: ConsequencePool,
    pending: PendingResolution,
    breakdown: ModifierBreakdown,
    *,
    interaction: Interaction | None,
    summary: str,
) -> None:
    """Persist ConsequenceOutcome provenance for a pool-routed combat resolution.

    Mirrors vitals' _record_combat_outcome guard: a sourceless ConsequenceOutcome
    is forbidden, so skip when no interaction anchor exists (sheet without a
    PRIMARY persona). Shared by flee and encounter-aftermath resolution.
    """
    if interaction is None:
        return

    from actions.types import WeightedConsequence  # noqa: PLC0415
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415

    selected = pending.selected_consequence
    if isinstance(selected, WeightedConsequence):
        selected = selected.consequence
    record_consequence_outcome(
        sheet,
        check_type,
        pool,
        selected if selected.pk is not None else None,
        breakdown,
        combat_interaction=interaction,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Social/mental combat verb resolution (#2015)
# ---------------------------------------------------------------------------


def _social_combat_difficulty(
    target: CombatOpponent,
    *,
    actor_sheet: CharacterSheet,
    check_type: CheckType,
    effort_level: str = EffortLevel.MEDIUM,
) -> SocialDifficulty:
    """Grade a social-combat check against an opponent (#2015, #4145).

    Delegates to ``social_target_difficulty`` so combat verbs, scenes and standoffs share
    one grade: Composure defense via ``compute_resist_increment`` plus
    ``MINDLESS_MORALE_RESISTANCE`` for a mindless target (a high resistance tier, not a
    wall). Rally targets an ally and never grades here.

    ``target_level=target.level`` (whole-branch-review fix, #2707): an ephemeral
    ``CombatOpponent`` has no ``CharacterClassLevel`` rows, so without the override it
    would floor at level 1 regardless of its authored ``level``. The override SUBSTITUTES
    the authored level for the objectdb-resolved one; it does not add a second level term.
    """
    from world.combat.constants import MINDLESS_MORALE_RESISTANCE  # noqa: PLC0415
    from world.combat.morale import tier_has_morale  # noqa: PLC0415

    return social_target_difficulty(
        actor_sheet=actor_sheet,
        target_character=target.objectdb,
        check_type=check_type,
        target_level=target.level,
        resist_effort=effort_level,
        mindless_resistance=0 if tier_has_morale(target) else MINDLESS_MORALE_RESISTANCE,
    )


def _social_verb_success_level(
    participant: CombatParticipant,
    check_type: CheckType | None,
    action: CombatRoundAction,
    target: CombatOpponent,
) -> int:
    """Grade a social verb's designated CheckType against ``target`` and roll it (#4145).

    ``check_type`` is the verb's designation on ``SocialManeuverConfig`` (#4739). An unset
    designation (None) or an inactive CheckType resolves as a failed roll (success level 0)
    with nothing rolled; the Required content dashboard lists the unset designation.
    """
    if check_type is None or not check_type.is_active:
        return 0
    graded = _social_combat_difficulty(
        target, actor_sheet=participant.character_sheet, check_type=check_type
    )
    return _resolve_social_check(
        participant,
        check_type,
        graded.difficulty,
        target=_resolve_primary_target_sheet(action),
        extra_contributions=graded.contributions,
        # A strained compulsion resist (#4802) lands its penalty on the verb's roll.
        extra_modifiers=-action.compulsion_penalty,
    )


def _resolve_social_check(  # noqa: PLR0913 - mirrors roll_social_check's terms
    participant: CombatParticipant,
    check_type: CheckType,
    target_difficulty: int,
    target: CharacterSheet | None = None,
    extra_contributions: list[ModifierContribution] | None = None,
    extra_modifiers: int = 0,
) -> int:
    """Roll a social-combat check and return the success_level (#2015).

    A thin wrapper over ``roll_social_check``; see it for the modifier handling.
    """
    result = roll_social_check(
        participant,
        check_type,
        target_difficulty,
        target=target,
        extra_contributions=extra_contributions,
        extra_modifiers=extra_modifiers,
    )
    return result.success_level or 0


def roll_social_check(  # noqa: PLR0913 - each term feeds the one roll
    participant: CombatParticipant,
    check_type: CheckType,
    target_difficulty: int,
    target: CharacterSheet | None = None,
    extra_contributions: list[ModifierContribution] | None = None,
    extra_modifiers: int = 0,
) -> CheckResult:
    """Roll a social-combat check and return the whole ``CheckResult`` (#2015, #4737).

    Routes modifiers through ``collect_check_modifiers`` (the same seam combat uses),
    folding in ``extra_contributions`` (the actor-side terms from
    ``social_target_difficulty``), then ``perform_check``. ``extra_modifiers`` is a flat
    term added on top (a strained compulsion's penalty, #4802). Returns
    the ``CheckResult`` (``_resolve_social_check`` keeps only its success_level; the
    surge roll (#4737) also needs the outcome).

    ``target`` (#2536 Task 6 fold-in fix, extended to Parley on review): the
    acting participant's declared opponent, when this social action has one
    — threaded into ``SituationContext.target`` so target-keyed CHECK_BONUS
    perks (``TARGET_DISTRACTED``/``TARGET_SWAYED_BY_ALLY``/
    ``TARGET_FOCUSED_ELSEWHERE``/``TARGET_FAVORABLY_DISPOSED``) can fire on
    Demoralize/Taunt/Parley, whose callers all resolve
    ``_resolve_primary_target_sheet(action)`` and pass it through. Rally
    (targets an ally, not an opponent) keeps the default ``None`` — it has no
    opposing target for a TARGET_* situation to key off.
    """
    from world.checks.services import collect_check_modifiers, perform_check  # noqa: PLC0415
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.conditions.services import spend_contributing_conditions  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    character = participant.character_sheet.character
    breakdown = collect_check_modifiers(
        participant.character_sheet,
        check_type,
        scene=participant.encounter.scene,
        extra_contributions=extra_contributions,
    )
    # #2536 Task 5 review fix (Task 6: now target-threaded for callers that
    # have one — see the docstring above): thread the live round context so
    # CHECK_BONUS situational perks can fire on Rally/Demoralize/Taunt/Parley.
    situation_ctx = SituationContext(
        holder=participant.character_sheet,
        subject=participant.character_sheet,
        target=target,
        resolution=CombatRoundContext(participant),
    )
    result = perform_check(
        character,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=breakdown.extra_modifiers_total + extra_modifiers,
        situation_ctx=situation_ctx,
    )
    spend_contributing_conditions(breakdown)
    return result
