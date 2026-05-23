"""Clash service layer — strain conversion, clash-commit, per-round resolution, and related logic.

This module is the single entry point for all Clash mechanic operations.  It is
intentionally kept free of Django model writes and HTTP/Evennia I/O so that
each function is unit-testable in isolation.  Higher-level orchestration
(views, commands, flow steps) calls into this module rather than implementing
Clash logic themselves.

Current scope (Tasks 2.1–4.1):
  - ``strain_to_modifier``: converts anima committed past the strain floor into
    a diminishing-returns check modifier, driven entirely by ``StrainConfig``
    tuning knobs.
  - ``outcome_to_delta``: maps a ``CheckOutcome`` tier to a per-round progress
    delta, driven by the six ``ClashConfig.delta_*`` tuning knobs.
  - ``commit_to_clash``: routes a PC's per-round clash contribution through
    the ``use_technique`` magic pipeline and returns a ``ClashContributionResult``.
  - ``npc_round_contribution``: returns the NPC's per-round progress contribution.
  - ``affinity_tilt``: computes a per-contributor check-modifier tilt from the
    AffinityInteraction matrix.
  - ``aggregate_clash_round``: aggregates PC contributions and the NPC delta into
    a ``ClashRound`` row, writes per-PC ``ClashContribution`` audit rows, and
    updates ``clash.progress`` per the flavor's sign convention.
  - ``fire_clash_per_round``: fires the per-round consequence pool, keyed on the
    current meter band. No-op when ``clash.per_round_consequence_pool`` is null.

Future tasks will add the full round driver, resolution-pool firing, and outcome helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import ClashFlavor, ClashResolution, LockPcRole
from world.combat.models import ClashConfig, ClashContribution, ClashRound, StrainConfig
from world.combat.types import ClashContributionResult, ClashRoundResult
from world.magic.constants import AffinityInteractionAggressor, ResonanceValence
from world.magic.models.resonance_environment import AffinityInteraction
from world.magic.services import use_technique
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence
    from world.combat.models import Clash
    from world.magic.models import Affinity, Technique


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
    character_sheet: CharacterSheet,
    technique: Technique,
    clash: Clash,  # noqa: ARG001 — carried for future round-aggregation context; not used in v1
    strain_commitment: int,
    action_slot: str,
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
        character_sheet: The PC performing the contribution (CharacterSheet).
            The underlying ObjectDB is resolved internally via
            ``character_sheet.character`` for the magic pipeline calls.
        clash: The active Clash instance this contribution belongs to (reserved for
            future round-aggregation context; not used in v1).
        strain_commitment: Extra anima committed on top of the effective cost floor.
        action_slot: ``ClashActionSlot`` value (``"FOCUSED"`` or ``"PASSIVE"``);
            echoed into the returned ``ClashContributionResult`` for audit use by
            the round aggregator.
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

    # 0. Resolve the ObjectDB from the CharacterSheet for the magic pipeline.
    #    CharacterSheet.character is a OneToOneField to ObjectDB (primary_key=True).
    #    A CharacterSheet without an ObjectDB is a data integrity violation, not a
    #    normal operational case — raise loudly rather than silently proceeding.
    objectdb: ObjectDB = character_sheet.character
    if objectdb is None:
        msg = (
            f"CharacterSheet pk={character_sheet.pk!r} has no associated ObjectDB. "
            "This is a data integrity violation — CharacterSheet.character is a "
            "non-nullable OneToOneField and should never be None."
        )
        raise ValueError(msg)

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
            objectdb,
            check_type,
            target_difficulty=0,
            extra_modifiers=strain_modifier,
        )

    # 4. Route through the full magic pipeline (anima cost, Soulfray, mishap,
    #    reactive events, corruption, resonance environment).
    technique_use_result = use_technique(
        character=objectdb,
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
        character=character_sheet,
        action_slot=action_slot,
        technique=technique,
        check_outcome=check_outcome,
        progress_delta=progress_delta,
        anima_committed=strain_commitment,
        was_overburn=technique_use_result.was_deficit,
        was_audere=technique_use_result.was_audere,
        soulfray_severity_accrued=soulfray_severity_accrued,
        technique_use_result=technique_use_result,
    )


def npc_round_contribution(*, clash: Clash, round_number: int) -> int:  # noqa: ARG001 — round_number reserved for future phase-aware modifiers
    """The NPC's per-round contribution to a Clash's meter, in progress units.

    Per-flavor behavior:
      - BREAK → always 0 (the boss contributes nothing structurally; PCs grind
        through the barrier on their own).
      - WARD → the sustained attack's per-round pressure
        (``triggering_threat_entry.clash_npc_pressure``).
      - CLASH → the big-attack entry's ``clash_npc_pressure``.
        TODO (Phase 5 / boss tuning): add a boss-phase modifier when
        ``clash.npc_opponent.current_phase`` has a clash-relevant
        BossPhase field. BossPhase has no such field in v1, so the base
        pressure is used unmodified.
        Variance: ``_resolve_npc_action`` in services.py applies no variance
        to NPC base_damage — it uses the authored value directly.  This
        function mirrors that convention: no variance in v1. The function
        is fully deterministic and pure.
        TODO (tuning): add a small variance roll here if playtesting shows
        the meter feels too mechanical.
      - LOCK / SUSTAINING → the NPC is trying to break free of the lock;
        returns ``triggering_threat_entry.clash_break_free_force``.
      - LOCK / ESCAPING → the NPC is maintaining the lock against the PC's
        escape attempt; returns ``triggering_threat_entry.clash_npc_pressure``.

    Returns 0 when no ``triggering_threat_entry`` is set or its relevant field
    is null.  Phase 5 (opportunity detection) is responsible for setting the
    entry at clash creation; this function degrades cleanly when it isn't set.

    Pure read — no DB writes, no mutation of inputs.
    """
    if clash.flavor == ClashFlavor.BREAK:
        return 0

    entry = clash.triggering_threat_entry
    if entry is None:
        return 0

    if clash.flavor == ClashFlavor.WARD:
        return entry.clash_npc_pressure or 0

    if clash.flavor == ClashFlavor.CLASH:
        return entry.clash_npc_pressure or 0

    # LOCK flavor — branch on the PC's role in the contest.
    if clash.lock_pc_role == LockPcRole.SUSTAINING:
        # PC is holding the lock; NPC is trying to break free.
        return entry.clash_break_free_force or 0
    # LockPcRole.ESCAPING: PC is escaping; NPC is maintaining the lock.
    return entry.clash_npc_pressure or 0


def _get_technique_affinity(technique: Technique) -> Affinity | None:
    """Derive the dominant affinity for a technique from its gift's first resonance.

    Walks ``technique.gift.resonances.first()`` and returns its ``.affinity``.
    Returns ``None`` if the gift has no resonances (no affinity signal).

    This is the simplest defensible derivation: one technique → one gift →
    first resonance → affinity.  A richer "majority vote" approach would require
    loading all resonances; the first-resonance proxy is sufficient for the
    RPS tilt calculation. The per-contributor tilt is a per-action decision; the
    first-resonance derivation is deterministic within a session and avoids the
    authoring cost of a richer aggregation rule until playtesting demands it.

    Private helper — call only from within this module.
    """
    first_resonance = technique.gift.resonances.select_related("affinity").first()
    if first_resonance is None:
        return None
    return first_resonance.affinity


def affinity_tilt(
    *,
    contributor_technique: Technique,
    npc_attack_affinity: Affinity | None,
    config: ClashConfig,
) -> int:
    """Compute the per-contributor check-modifier tilt for a clash contribution.

    Reads the existing ``AffinityInteraction`` matrix as a directed
    (contributor-affinity, NPC-affinity) pair — the caster-vs-caster analogue of
    the shipped caster-vs-place interaction.  Returns:

      - ``0`` if ``npc_attack_affinity`` is ``None`` (non-magical NPC attack)
      - ``0`` if the contributor's technique has no derivable affinity
      - ``0`` if no ``AffinityInteraction`` row exists for the pair
      - ``0`` for ALIGNED matchups (same-affinity diagonal — the AMPLIFY
        semantics are caster-vs-place only and do not transfer to
        caster-vs-caster)
      - For OPPOSED matchups: ``±round(severity_multiplier × config.affinity_tilt_coefficient)``,
        positive when the contributor's affinity dominates (``aggressor=CASTER``),
        negative when the NPC's dominates (``aggressor=ENVIRONMENT``).

    Magnitude uses Python's built-in ``round()``, which applies banker's
    (round-half-to-even) rounding for deterministic, bias-free behaviour when
    the product lands exactly on a half-integer.

    Pure read — no DB writes, no mutation of inputs.
    """
    # 1. Non-magical NPC attack → no tilt.
    if npc_attack_affinity is None:
        return 0

    # 2. Derive the contributor's affinity; no affinity signal → no tilt.
    tech_affinity = _get_technique_affinity(contributor_technique)
    if tech_affinity is None:
        return 0

    # 3. Look up the directed (tech, npc) pair in the matrix; no row → no tilt.
    interaction = AffinityInteraction.objects.interaction_for(tech_affinity, npc_attack_affinity)
    if interaction is None:
        return 0

    # 4. ALIGNED (same-affinity diagonal) → no tilt; AMPLIFY semantics are
    #    caster-vs-place only and do not apply here.
    if interaction.valence == ResonanceValence.ALIGNED:
        return 0

    # 5. OPPOSED: compute magnitude from authored severity × tuning coefficient.
    #    Both are Decimal; round() returns a plain int.
    magnitude: int = round(interaction.severity_multiplier * config.affinity_tilt_coefficient)

    # 6. Sign: CASTER aggressor means the contributor's affinity dominates → positive.
    if interaction.aggressor == AffinityInteractionAggressor.CASTER:
        return magnitude
    # ENVIRONMENT aggressor: NPC's affinity dominates → negative.
    return -magnitude


@transaction.atomic
def aggregate_clash_round(
    *,
    clash: Clash,
    round_number: int,
    pc_contributions: list[ClashContributionResult],
    npc_delta: int,
) -> ClashRoundResult:
    """Aggregate per-round PC contributions and the NPC delta into a ClashRound.

    Writes one ``ClashRound`` row and one ``ClashContribution`` row per PC
    contribution.  Updates ``clash.progress`` according to the flavor's sign
    convention.  The whole operation is atomic: if any DB write fails, none persist.

    Sign convention by flavor:

    - ``CLASH``: PCs push positive, NPC pushes against.
      ``progress_after = clash.progress + pc_delta_sum - npc_delta``
    - ``LOCK / SUSTAINING`` (Suppress — PCs hold, NPC breaks):
      ``progress_after = clash.progress + pc_delta_sum - npc_delta``
    - ``LOCK / ESCAPING`` (Break Free — PCs escape, NPC holds):
      ``progress_after = clash.progress - pc_delta_sum + npc_delta``
    - ``WARD``: PCs strengthen, NPC drains.
      ``progress_after = clash.progress + pc_delta_sum - npc_delta``
    - ``BREAK``: PC-only push; ``npc_delta`` is always 0.
      ``progress_after = clash.progress + pc_delta_sum - npc_delta``

    Args:
        clash: The active ``Clash`` instance whose progress meter to update.
        round_number: The round of the Clash being aggregated (1-indexed).
        pc_contributions: List of ``ClashContributionResult`` objects, one per
            PC that contributed this round.  May be empty (NPC-only push).
        npc_delta: The NPC's raw per-round push magnitude (non-negative integer).

    Returns:
        A frozen ``ClashRoundResult`` with the persisted rows and updated meter value.
    """
    # 1. Sum all PC contribution deltas.
    pc_delta_sum = sum(c.progress_delta for c in pc_contributions)

    # 2. Apply the flavor's sign convention to compute progress_after.
    if clash.flavor == ClashFlavor.LOCK and clash.lock_pc_role == LockPcRole.ESCAPING:
        # LOCK / ESCAPING: PCs push to escape (reduces progress toward NPC win);
        # NPC maintains the lock (increases progress back toward NPC win).
        progress_after = clash.progress - pc_delta_sum + npc_delta
    else:
        # CLASH, LOCK/SUSTAINING, WARD, BREAK — all follow the same convention:
        # PCs push positive, NPC pushes against.
        progress_after = clash.progress + pc_delta_sum - npc_delta

    # 3. Write the ClashRound row.
    clash_round = ClashRound.objects.create(
        clash=clash,
        round_number=round_number,
        pc_progress_delta=pc_delta_sum,
        npc_progress_delta=npc_delta,
        progress_after=progress_after,
    )

    # 4. Bulk-create one ClashContribution row per PC contribution.
    contribution_rows = ClashContribution.objects.bulk_create(
        [
            ClashContribution(
                clash_round=clash_round,
                character=c.character,
                action_slot=c.action_slot,
                anima_committed=c.anima_committed,
                technique=c.technique,
                check_outcome=c.check_outcome,
                progress_delta=c.progress_delta,
                was_overburn=c.was_overburn,
                was_audere=c.was_audere,
                soulfray_severity_accrued=c.soulfray_severity_accrued,
            )
            for c in pc_contributions
        ]
    )

    # 5. Update clash.progress with the new value.
    clash.progress = progress_after
    clash.save(update_fields=["progress"])

    # 6. Return the aggregated result.
    return ClashRoundResult(
        clash_round=clash_round,
        contributions=contribution_rows,
        pc_delta_sum=pc_delta_sum,
        npc_delta=npc_delta,
        progress_after=progress_after,
    )


def check_clash_threshold(
    *, clash: Clash, round_number: int, config: ClashConfig
) -> ClashResolution | None:
    """Inspect a clash's current state and return a ``ClashResolution`` if a
    threshold or window has been crossed; else ``None`` (the clash is ongoing).

    Pure read — no DB writes; no mutation of inputs.

    Per-flavor logic:

    **CLASH** (0-centered meter, ``pc_win_threshold`` and ``npc_win_threshold``
    both populated, both positive):
    - ``progress >= pc_win_threshold`` → PC win. Overshoot =
      ``progress - pc_win_threshold``. ``PC_DECISIVE`` if
      ``overshoot >= config.decisive_overshoot``, else ``PC_MARGINAL``.
    - ``progress <= -npc_win_threshold`` → NPC win. Overshoot =
      ``-npc_win_threshold - progress``. ``NPC_DECISIVE`` if
      ``overshoot >= config.decisive_overshoot``, else ``NPC_MARGINAL``.
    - ``round_number > config.max_round_cap`` → ``MUTUAL``.
    - Otherwise → ``None`` (ongoing).

    **LOCK** (meter 0 to ``pc_win_threshold``):
    - SUSTAINING (PC holds): ``progress >= pc_win_threshold`` → PC wins;
      ``progress <= 0`` → NPC wins. Overshoot from the crossed boundary
      decides decisive/marginal.
    - ESCAPING (PC escapes): ``progress <= 0`` → PC wins (escaped);
      ``progress >= pc_win_threshold`` → NPC wins (lock hardened). Overshoot
      from the crossed boundary decides decisive/marginal.
    - Otherwise → ``None`` (ongoing).

    **WARD** (meter is ward integrity; PCs strengthen, NPC drains):
    - ``progress <= 0`` → ward collapsed early → ``NPC_DECISIVE``.
    - ``round_number > clash.ward_ends_on_round`` → barrage expired; band by
      final ``progress`` value relative to ``pc_win_threshold``:
        - ``progress >= pc_win_threshold`` → ``PC_DECISIVE`` (endured cleanly).
        - ``progress >= pc_win_threshold // 2`` → ``PC_MARGINAL``
          (barely held; closer to intact than collapsed).
        - Otherwise → ``NPC_MARGINAL`` (partial collapse; closer to 0 than intact).
      Half-threshold uses integer division (``pc_win_threshold // 2``);
      when ``pc_win_threshold`` is odd, the midpoint rounds down, meaning
      exactly half goes to ``NPC_MARGINAL``.
    - Otherwise → ``None`` (still enduring).

    **BREAK** (one-way PC accumulation toward ``pc_win_threshold``; NPC never
    wins via meter — ``ABANDONED`` is detected by the Phase 5 idle-rounds
    rule, not here):
    - ``progress >= pc_win_threshold`` → PC win. Overshoot =
      ``progress - pc_win_threshold``. ``PC_DECISIVE`` if
      ``overshoot >= config.decisive_overshoot``, else ``PC_MARGINAL``.
    - Otherwise → ``None`` (ongoing).
    """
    if clash.flavor == ClashFlavor.CLASH:
        return _check_clash_flavor(clash=clash, round_number=round_number, config=config)
    if clash.flavor == ClashFlavor.LOCK:
        return _check_lock_flavor(clash=clash, config=config)
    if clash.flavor == ClashFlavor.WARD:
        return _check_ward_flavor(clash=clash, round_number=round_number)
    # BREAK
    return _check_break_flavor(clash=clash, config=config)


def _tier_from_overshoot(
    overshoot: int,
    decisive_tier: ClashResolution,
    marginal_tier: ClashResolution,
    config: ClashConfig,
) -> ClashResolution:
    """Return decisive_tier if overshoot meets the config threshold, else marginal_tier."""
    if overshoot >= config.decisive_overshoot:
        return decisive_tier
    return marginal_tier


def _check_clash_flavor(
    *, clash: Clash, round_number: int, config: ClashConfig
) -> ClashResolution | None:
    """Threshold detection for CLASH-flavor clashes.

    npc_win_threshold is non-null for CLASH flavor — enforced by Clash.clean()
    and the DB CheckConstraint. The explicit guard converts it to a plain int
    for arithmetic without triggering S101 (assert).
    """
    npc_threshold = clash.npc_win_threshold
    if npc_threshold is None:
        # Defensive guard: should never happen for a CLASH-flavor row.
        return None  # pragma: no cover
    if clash.progress >= clash.pc_win_threshold:
        overshoot = clash.progress - clash.pc_win_threshold
        return _tier_from_overshoot(
            overshoot, ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL, config
        )
    if clash.progress <= -npc_threshold:
        overshoot = -npc_threshold - clash.progress
        return _tier_from_overshoot(
            overshoot, ClashResolution.NPC_DECISIVE, ClashResolution.NPC_MARGINAL, config
        )
    if round_number > config.max_round_cap:
        return ClashResolution.MUTUAL
    return None


def _check_lock_sustaining(*, clash: Clash, config: ClashConfig) -> ClashResolution | None:
    """LOCK/SUSTAINING sub-branch: PC holds the lock; winning = sustaining to threshold."""
    if clash.progress >= clash.pc_win_threshold:
        overshoot = clash.progress - clash.pc_win_threshold
        return _tier_from_overshoot(
            overshoot, ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL, config
        )
    if clash.progress <= 0:
        overshoot = -clash.progress  # how far past 0
        return _tier_from_overshoot(
            overshoot, ClashResolution.NPC_DECISIVE, ClashResolution.NPC_MARGINAL, config
        )
    return None


def _check_lock_escaping(*, clash: Clash, config: ClashConfig) -> ClashResolution | None:
    """LOCK/ESCAPING sub-branch: PC escapes; winning = progress reaching/crossing 0."""
    if clash.progress <= 0:
        overshoot = -clash.progress
        return _tier_from_overshoot(
            overshoot, ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL, config
        )
    if clash.progress >= clash.pc_win_threshold:
        overshoot = clash.progress - clash.pc_win_threshold
        return _tier_from_overshoot(
            overshoot, ClashResolution.NPC_DECISIVE, ClashResolution.NPC_MARGINAL, config
        )
    return None


def _check_lock_flavor(*, clash: Clash, config: ClashConfig) -> ClashResolution | None:
    """Threshold detection for LOCK-flavor clashes."""
    if clash.lock_pc_role == LockPcRole.SUSTAINING:
        return _check_lock_sustaining(clash=clash, config=config)
    # LockPcRole.ESCAPING
    return _check_lock_escaping(clash=clash, config=config)


def _check_ward_flavor(*, clash: Clash, round_number: int) -> ClashResolution | None:
    """Threshold detection for WARD-flavor clashes.

    ward_ends_on_round is non-null for WARD flavor — enforced by Clash.clean()
    and the DB CheckConstraint. The explicit guard converts it to a plain int.
    """
    ward_ends_on_round = clash.ward_ends_on_round
    if ward_ends_on_round is None:
        return None  # pragma: no cover
    if clash.progress <= 0:
        # Ward collapsed early — barrage poured through.
        return ClashResolution.NPC_DECISIVE
    if round_number > ward_ends_on_round:
        # Attack's duration expired — band by final progress relative to pc_win_threshold.
        half_threshold = clash.pc_win_threshold // 2
        if clash.progress >= clash.pc_win_threshold:
            return ClashResolution.PC_DECISIVE
        if clash.progress >= half_threshold:
            return ClashResolution.PC_MARGINAL
        return ClashResolution.NPC_MARGINAL
    return None


def _check_break_flavor(*, clash: Clash, config: ClashConfig) -> ClashResolution | None:
    """Threshold detection for BREAK-flavor clashes."""
    if clash.progress >= clash.pc_win_threshold:
        overshoot = clash.progress - clash.pc_win_threshold
        return _tier_from_overshoot(
            overshoot, ClashResolution.PC_DECISIVE, ClashResolution.PC_MARGINAL, config
        )
    return None


# ---------------------------------------------------------------------------
# Task 4.1 — per-round consequence pool firing
# ---------------------------------------------------------------------------


def _meter_band_to_check_outcome(*, clash: Clash) -> CheckOutcome:
    """Map the clash's current progress to a CheckOutcome by meter band.

    Band mapping (ratio = progress / pc_win_threshold):
      ratio >= 1.0  → success_level 3  (critical success — at/past target)
      ratio >= 0.5  → success_level 2  (great success — well ahead)
      ratio >= 0.0  → success_level 1  (success — ahead or even)
      ratio >= -0.5 → success_level -1 (failure — behind)
      else          → success_level -2 (botch — far behind)

    ``pc_win_threshold`` is always populated and positive for all clash flavors
    that carry a per-round pool. The ratio is a signed float so it works for
    both CLASH's signed meter (progress can be negative) and 0-to-N meters
    (WARD, LOCK, BREAK).

    Falls back to the closest available ``success_level`` row when an exact
    match is absent — different deployments may not seed every level.

    Pure read — no DB writes, no mutation of inputs.

    Private helper — call only from ``fire_clash_per_round``.
    """
    ratio: float = clash.progress / clash.pc_win_threshold

    if ratio >= 1.0:
        target_level = 3
    elif ratio >= 0.5:  # noqa: PLR2004 — meter-band breakpoints are design constants
        target_level = 2
    elif ratio >= 0.0:
        target_level = 1
    elif ratio >= -0.5:  # noqa: PLR2004 — meter-band breakpoints are design constants
        target_level = -1
    else:
        target_level = -2

    # Exact lookup first; fall back to nearest lower level for robustness.
    outcome = (
        CheckOutcome.objects.filter(success_level__lte=target_level)
        .order_by("-success_level")
        .first()
    )

    if outcome is None:
        # No row at or below target — take the minimum available.
        outcome = CheckOutcome.objects.order_by("success_level").first()

    if outcome is None:
        msg = (
            "No CheckOutcome rows exist in the database. "
            f"Cannot map meter band for clash pk={clash.pk}."
        )
        raise ValueError(msg)

    return outcome


def fire_clash_per_round(
    *,
    clash: Clash,
    clash_round: ClashRound,  # noqa: ARG001 — reserved for Phase 5 audit hooks; part of v1 contract
) -> Consequence | None:
    """Fire the per-round consequence pool, keyed on the current meter band.

    No-op (returns None) when ``clash.per_round_consequence_pool`` is null.
    Otherwise: maps the clash's ``progress`` to a ``CheckOutcome`` band, picks a
    matching consequence from the pool (weighted), applies its effects, and
    returns the chosen Consequence.

    Effect context targets the NPC opponent's ObjectDB as both ``character`` and
    ``target`` — per-round pool effects are NPC-side (damage absorption for WARD,
    narrative stress for CLASH). If the opponent has no ObjectDB (non-ephemeral
    opponents without an attached world object), effects are still fired but
    ``ResolutionContext.character`` falls back to a fallback-safe no-op path
    inside each handler.

    The only side effects are those produced by ``apply_all_effects`` — this
    function itself writes nothing to the database.

    Args:
        clash: The active Clash instance whose per-round pool to fire.
        clash_round: The ClashRound that was just written (carried for future
            audit/logging hooks; not read by v1 implementation).

    Returns:
        The selected Consequence, or None when there is no pool or no matching
        tier entry.
    """
    from world.checks.models import Consequence as ConsequenceModel  # noqa: PLC0415
    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.mechanics.effect_handlers import apply_all_effects  # noqa: PLC0415

    pool = clash.per_round_consequence_pool
    if pool is None:
        return None

    # 1. Map the meter to a CheckOutcome band.
    outcome = _meter_band_to_check_outcome(clash=clash)

    # 2. Filter the pool's consequences to those matching the outcome tier.
    #    cached_consequences is a @cached_property returning list[WeightedConsequence].
    all_consequences = pool.cached_consequences
    tier_entries = [wc for wc in all_consequences if wc.outcome_tier == outcome]

    if not tier_entries:
        return None

    # 3. Weighted selection — select_weighted works on any object with a .weight attr.
    selected_wc = select_weighted(tier_entries)

    # WeightedConsequence wraps the real Consequence model instance.
    selected: ConsequenceModel = selected_wc.consequence

    # 4. Build a minimal ResolutionContext using the NPC as actor/target.
    #    npc_opponent.objectdb may be None for opponents created without an ObjectDB
    #    (e.g. in tests). Handlers that need a real ObjectDB guard internally.
    npc_objectdb = clash.npc_opponent.objectdb

    if npc_objectdb is None:
        # No ObjectDB to target — skip effect application.
        return selected

    context = ResolutionContext(
        character=npc_objectdb,
        target=npc_objectdb,
    )

    # 5. Apply all effects on the selected consequence.
    apply_all_effects(selected, context)

    return selected
