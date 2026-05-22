"""Clash service layer — strain conversion, clash-commit, per-round resolution, and related logic.

This module is the single entry point for all Clash mechanic operations.  It is
intentionally kept free of Django model writes and HTTP/Evennia I/O so that
each function is unit-testable in isolation.  Higher-level orchestration
(views, commands, flow steps) calls into this module rather than implementing
Clash logic themselves.

Current scope (Tasks 2.1–2.3):
  - ``strain_to_modifier``: converts anima committed past the strain floor into
    a diminishing-returns check modifier, driven entirely by ``StrainConfig``
    tuning knobs.
  - ``outcome_to_delta``: maps a ``CheckOutcome`` tier to a per-round progress
    delta, driven by the six ``ClashConfig.delta_*`` tuning knobs.
  - ``commit_to_clash``: routes a PC's per-round clash contribution through
    the ``use_technique`` magic pipeline and returns a ``ClashContributionResult``.

Future tasks will add round-resolution, NPC contribution, and outcome helpers here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import ClashConfig, StrainConfig
from world.combat.types import ClashContributionResult
from world.magic.services import use_technique
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import Clash
    from world.magic.models import Technique


def strain_to_modifier(*, anima_committed: int, config: StrainConfig) -> int:
    """Convert a strain commitment (anima poured in past the floor) to a check modifier.

    Diminishing-returns curve: the first points convert efficiently, deep strain
    converts poorly.  Knobs come from ``StrainConfig``:

    - ``conversion_base``: the per-anima conversion at the start of the curve
    - ``diminishing_step``: every ``diminishing_step`` anima reduces the per-anima
      conversion by 1
    - ``diminishing_floor``: the conversion never drops below this per-anima value

    ``anima_committed`` is treated as ``0`` when negative (defensive guard).
    Returns exactly ``0`` when ``anima_committed`` is ``0``.
    """
    remaining = max(anima_committed, 0)
    mod = 0
    rate = config.conversion_base
    while remaining > 0:
        take = min(remaining, config.diminishing_step)
        mod += take * rate
        remaining -= take
        rate = max(rate - 1, config.diminishing_floor)
    return mod


def outcome_to_delta(*, check_outcome: CheckOutcome, config: ClashConfig) -> int:
    """Map a CheckOutcome tier to a clash progress delta.

    Banding (by CheckOutcome.success_level):
      >= 3  → critical success → config.delta_critical_success
      == 2  → great success    → config.delta_great_success
      == 1  → success          → config.delta_success
      == 0  → partial          → config.delta_partial
      == -1 → failure          → config.delta_failure
      <= -2 → botch            → config.delta_botch

    Values outside the authored range are clamped to the nearest band.
    Pure function — no DB writes, no I/O.
    """
    level = check_outcome.success_level
    if level >= 3:  # noqa: PLR2004 — tier breakpoints are design constants, not magic values
        return config.delta_critical_success
    if level == 2:  # noqa: PLR2004 — tier breakpoints are design constants, not magic values
        return config.delta_great_success
    if level == 1:
        return config.delta_success
    if level == 0:
        return config.delta_partial
    if level == -1:
        return config.delta_failure
    return config.delta_botch


def commit_to_clash(  # noqa: PLR0913 — kw-only API; all params are part of the v1 contract
    *,
    character: ObjectDB,
    technique: Technique,
    clash: Clash,  # noqa: ARG001 — carried for future round-aggregation context; not used in v1
    strain_commitment: int,
    action_slot: str,  # noqa: ARG001 — carried for future FOCUSED/PASSIVE lane logic; not used in v1
    config_clash: ClashConfig,
    config_strain: StrainConfig,
    targets: list | None = None,
) -> ClashContributionResult:
    """Run a PC's per-round clash contribution through the cast pipeline.

    Resolves the technique through ``use_technique`` with an anima strain on top
    of the normal effective cost, captures the ``CheckResult``, converts the
    outcome tier to a progress delta via ``outcome_to_delta``, and returns a
    frozen ``ClashContributionResult``.  No damage or conditions are applied —
    the resolve closure performs only the check roll.

    Args:
        character: The PC performing the contribution (ObjectDB).
        technique: The technique being cast for the contribution.
        clash: The active Clash instance this contribution belongs to (reserved for
            future round-aggregation context; not used in v1).
        strain_commitment: Extra anima committed on top of the effective cost floor.
        action_slot: ``ClashActionSlot`` value (``"FOCUSED"`` or ``"PASSIVE"``);
            reserved for future FOCUSED/PASSIVE lane logic (not used in v1).
        config_clash: Clash tuning knobs for ``outcome_to_delta``.
        config_strain: Strain curve knobs for ``strain_to_modifier``.
        targets: Optional explicit targets forwarded to the magic pipeline.

    Returns:
        A frozen ``ClashContributionResult`` with the check outcome, progress
        delta, and all magic-pipeline side-effect metadata.

    Raises:
        ValueError: If ``technique.action_template`` is ``None`` (technique has
            not been configured for combat use) or if ``use_technique`` returns
            an unconfirmed result when ``confirm_soulfray_risk=True`` (should
            not happen in v1; indicates a pipeline inconsistency).
    """
    from world.checks.services import perform_check  # noqa: PLC0415 — local import avoids circular
    from world.checks.types import CheckResult  # noqa: PLC0415 — local import avoids circular

    # 1. Derive the check type from the technique's action_template (mirrors
    #    _resolve_pc_action in services.py: ``template.check_type``).
    template = technique.action_template
    if template is None:
        msg = (
            f"Technique {technique.pk!r} ({technique.name!r}) has no action_template "
            "and cannot be used in a Clash contribution. Configure the technique for "
            "combat use by assigning an ActionTemplate with a check_type."
        )
        raise ValueError(msg)
    check_type = template.check_type

    # 2. Convert strain commitment to a check modifier (diminishing-returns curve).
    strain_modifier = strain_to_modifier(
        anima_committed=strain_commitment,
        config=config_strain,
    )

    # 3. Build a resolve closure that performs only the check — no damage, no
    #    conditions.  use_technique calls resolve_fn() and stores its return
    #    value as resolution_result; we return a CheckResult directly.
    def resolve_fn() -> object:
        return perform_check(
            character,
            check_type,
            target_difficulty=0,
            extra_modifiers=strain_modifier,
        )

    # 4. Route through the full magic pipeline (anima cost, Soulfray, mishap,
    #    reactive events, corruption, resonance environment).
    technique_use_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=resolve_fn,
        strain_commitment=strain_commitment,
        targets=targets,
        confirm_soulfray_risk=True,
    )

    # 5. Guard against unconfirmed result (confirm_soulfray_risk=True should
    #    prevent this; guard exists for defensive correctness).
    if not technique_use_result.confirmed:
        msg = (
            "commit_to_clash received an unconfirmed TechniqueUseResult even though "
            "confirm_soulfray_risk=True was passed. This indicates a pipeline "
            "inconsistency and should not happen in v1."
        )
        raise ValueError(msg)

    # 6. Extract the CheckResult from the resolution_result (the closure returns
    #    a CheckResult directly, so resolution_result IS the CheckResult).
    check_result: CheckResult = technique_use_result.resolution_result  # type: ignore[assignment]
    if check_result.outcome is None:
        msg = "commit_to_clash: CheckResult has no outcome — check pipeline returned empty result."
        raise ValueError(msg)
    check_outcome: CheckOutcome = check_result.outcome

    # 7. Convert outcome to progress delta.
    progress_delta = outcome_to_delta(
        check_outcome=check_outcome,
        config=config_clash,
    )

    # 8. Derive soulfray severity accrued this cast.
    soulfray_severity_accrued = (
        technique_use_result.soulfray_result.severity_added
        if technique_use_result.soulfray_result is not None
        else 0
    )

    return ClashContributionResult(
        check_outcome=check_outcome,
        progress_delta=progress_delta,
        anima_committed=strain_commitment,
        was_overburn=technique_use_result.was_deficit,
        was_audere=technique_use_result.was_audere,
        soulfray_severity_accrued=soulfray_severity_accrued,
        technique_use_result=technique_use_result,
    )
