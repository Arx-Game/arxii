"""Clash service layer — strain conversion, clash-commit, per-round resolution, and related logic.

This module is the single entry point for all Clash mechanic operations.  It is
intentionally kept free of Django model writes and HTTP/Evennia I/O so that
each function is unit-testable in isolation.  Higher-level orchestration
(views, commands, flow steps) calls into this module rather than implementing
Clash logic themselves.

Current scope (Tasks 2.1–5.1):
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
  - ``resolve_clash``: marks a clash as RESOLVED, fires the resolution-pool
    consequence keyed on the resolution tier, returns a ``ClashResolutionResult``.
  - ``detect_clash_opportunities``: inspects the round's declared PC + NPC actions
    and the opponents' state, and creates ``Clash`` rows for each opportunity that
    emerges (CLASH, LOCK, WARD, BREAK flavors). Task 5.1.
  - ``run_clash_round``: drives one full round of a clash — per-PC commit (with
    affinity tilt) → aggregate → per-round pool → threshold check → resolve if
    crossed. Task 5.2.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import ClashFlavor, ClashResolution, ClashStatus, LockPcRole
from world.combat.models import ClashConfig, ClashContribution, ClashRound, StrainConfig
from world.combat.types import (
    ClashContributionResult,
    ClashResolutionResult,
    ClashRoundResult,
    PreparedClashContribution,
)
from world.magic.constants import AffinityInteractionAggressor, ResonanceValence
from world.magic.models.resonance_environment import AffinityInteraction
from world.magic.services import use_technique
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence
    from world.combat.models import Clash, CombatEncounter, CombatRoundAction
    from world.magic.models import Affinity, Technique


def can_clash(
    props_a: frozenset[int] | set[int],
    props_b: frozenset[int] | set[int],
) -> bool:
    """Return True iff two effect-Property sets oppose each other in a clash.

    Inputs are sets of ``mechanics.Property`` pks. Symmetric.

    Rule: any non-empty overlap counts. Empty on either side returns False —
    unauthored content cannot clash. Authoring discipline is the gate: if a
    Property is too broad to be meaningful for clash-opposition, the fix is
    to scope it more narrowly or to not put it on techniques that shouldn't
    clash on it. The opposition system does not maintain a parallel
    "clash-bearing" subset; Property is the single taxonomy.

    Phase 3 — combat-resolution-loop PR.
    """
    if not props_a or not props_b:
        return False
    return bool(props_a & props_b)


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
    if level >= 3:  # noqa: PLR2004
        return config.delta_critical_success
    if level == 2:  # noqa: PLR2004
        return config.delta_great_success
    if level == 1:
        return config.delta_success
    if level == 0:
        return config.delta_partial
    if level == -1:
        return config.delta_failure
    return config.delta_botch


def commit_to_clash(  # noqa: PLR0913
    *,
    character_sheet: CharacterSheet,
    technique: Technique,
    clash: Clash,
    strain_commitment: int,
    action_slot: str,
    config_clash: ClashConfig,
    config_strain: StrainConfig,
    targets: list | None = None,
    check_modifier_extra: int = 0,
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
        check_modifier_extra: Additional flat modifier applied to the check on top
            of the strain modifier.  Default 0 (no effect).  Used by the round
            driver to thread the affinity tilt through without changing the
            strain computation.

    Returns:
        A frozen ``ClashContributionResult`` with the check outcome, progress
        delta, and all magic-pipeline side-effect metadata.

    Raises:
        ValueError: If ``technique.action_template`` is ``None`` (technique has
            not been configured for combat use) or if ``use_technique`` returns
            an unconfirmed result when ``confirm_soulfray_risk=True`` (should
            not happen in v1; indicates a pipeline inconsistency).
    """
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.services import collect_check_modifiers, perform_check  # noqa: PLC0415
    from world.checks.types import CheckResult, ModifierContribution  # noqa: PLC0415

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

    # 2b. Express strain + affinity-tilt as labeled ModifierContributions and route
    #     them through the shared collect_check_modifiers seam so the clash check
    #     ALSO honors condition + rollmod sources (the #851 individualization lever),
    #     not only its strain/affinity.  The summed .total replaces the former
    #     ad-hoc ``strain_modifier + check_modifier_extra`` arithmetic.
    extra_contributions: list[ModifierContribution] = []
    if strain_modifier:
        extra_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.STRAIN,
                source_label="Strain",
                value=strain_modifier,
            )
        )
    if check_modifier_extra:
        extra_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.STRAIN,
                source_label="Affinity tilt",
                value=check_modifier_extra,
            )
        )

    breakdown = collect_check_modifiers(
        character_sheet,
        check_type,
        extra_contributions=extra_contributions,
    )
    check_extra_modifiers = breakdown.total

    # 3. Build a resolve closure that performs only the check — no damage, no
    #    conditions.  use_technique calls resolve_fn() and stores its return
    #    value as resolution_result; we return a CheckResult directly.
    # clash check is strain-driven; the power ledger is ledger-independent here.
    def resolve_fn(*, power: int, ledger: object) -> object:  # noqa: ARG001
        return perform_check(
            objectdb,
            check_type,
            target_difficulty=0,
            extra_modifiers=check_extra_modifiers,
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

    # 9. Record the canonical strain audit on an ACTION-mode Interaction.
    #    The participant is resolved from clash.encounter + character_sheet so
    #    commit_to_clash callers don't need to thread it explicitly. When the
    #    participant lookup fails (legacy fixtures, isolated unit tests that do
    #    not wire a CombatParticipant), skip Interaction creation rather than
    #    fail the whole pipeline.
    from world.combat.interaction_services import (  # noqa: PLC0415
        create_action_interaction,
    )
    from world.combat.models import CombatParticipant  # noqa: PLC0415

    participant = CombatParticipant.objects.filter(
        encounter_id=clash.encounter_id,
        character_sheet=character_sheet,
    ).first()
    if participant is not None:
        clash_interaction = create_action_interaction(
            participant=participant,
            round_number=clash.started_round,
            summary_label=f"{technique.name} → clash contribution",
            strain_committed=strain_commitment,
        )
        if clash_interaction is not None:
            from world.scenes.interaction_services import (  # noqa: PLC0415
                push_interaction,
            )

            push_interaction(clash_interaction)

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


def npc_round_contribution(*, clash: Clash, round_number: int) -> int:  # noqa: ARG001
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


def _technique_effect_property_ids(technique: Technique) -> frozenset[int]:
    """Derive effect Property pks from a Technique's Gift's Resonances.

    Walks ``technique.gift.resonances.properties`` — the same chain
    ``mechanics.services._get_technique_effect_property_ids`` uses (we
    duplicate it here as a free function to avoid a circular import between
    combat.clash and mechanics.services). Returns an empty frozenset for
    techniques without a gift.

    Used by ``_detect_clash_flavor`` to compute the opposition surface for
    clash creation. The per-character ``CharacterTechniqueHandler`` is the
    cached path for inventory walks; this helper covers the one-off
    detect-time lookup.
    """
    if technique.gift_id is None:
        return frozenset()
    from django.db.models import Prefetch  # noqa: PLC0415

    from world.mechanics.models import Property  # noqa: PLC0415

    ids: set[int] = set()
    resonances = technique.gift.resonances.prefetch_related(
        Prefetch(
            "properties",
            queryset=Property.objects.all(),
            to_attr="cached_properties",
        ),
    )
    for resonance in resonances:
        ids.update(p.pk for p in resonance.cached_properties)
    return frozenset(ids)


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
    """LOCK/SUSTAINING sub-branch: PC holds the lock; winning = sustaining to threshold.

    PC wins when progress reaches or exceeds ``pc_win_threshold``.
    NPC wins when progress drops to 0 or below (lock broken / released).
    Overshoot from the crossed boundary decides decisive vs marginal.
    """
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
    """LOCK/ESCAPING sub-branch: PC escapes; winning = progress dropping to 0 or below.

    PC wins when progress drops to or below 0 (escaped).
    NPC wins when progress reaches ``pc_win_threshold`` (lock fully hardened).
    Overshoot from the crossed boundary decides decisive vs marginal.
    """
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


def _find_check_outcome_at_or_below(target_level: int) -> CheckOutcome:
    """Return the closest available ``CheckOutcome`` with ``success_level <= target_level``.

    Both ``_meter_band_to_check_outcome`` and ``_resolution_to_check_outcome``
    use the same fallback strategy: find the authored row at or below the
    desired level, so that a sparse configuration degrades gracefully without
    leaving gaps that would raise hard errors at runtime.

    Raises:
        CheckOutcome.DoesNotExist: If no row exists at or below ``target_level``.
            This always indicates incomplete configuration — every deployment
            should have at least the baseline success tiers seeded.

    Private helper — call only from within this module.
    """
    outcome = (
        CheckOutcome.objects.filter(success_level__lte=target_level)
        .order_by("-success_level", "pk")
        .first()
    )
    if outcome is None:
        msg = (
            f"No CheckOutcome row exists at or below success_level={target_level}. "
            "Configuration is incomplete — seed the CheckOutcome tier rows."
        )
        raise CheckOutcome.DoesNotExist(msg)
    return outcome


def _meter_band_to_check_outcome(*, clash: Clash) -> CheckOutcome:
    """Map the clash's current progress to a CheckOutcome by meter band.

    Band mapping (ratio = progress / pc_win_threshold):
      ratio >= 1.0   → success_level  3  (critical success — at/past target)
      ratio >= 0.5   → success_level  2  (great success — well ahead)
      ratio >= 0.0   → success_level  1  (success — distinctly ahead)
      ratio >= -0.25 → success_level  0  (partial — basically even)
      ratio >= -0.5  → success_level -1  (failure — behind)
      else           → success_level -2  (botch — far behind)

    ``pc_win_threshold`` is always populated and positive for all clash flavors
    that carry a per-round pool. The ratio is a signed float so it works for
    both CLASH's signed meter (progress can be negative) and 0-to-N meters
    (WARD, LOCK, BREAK).

    Fallback: delegates to ``_find_check_outcome_at_or_below`` — returns the
    closest available ``CheckOutcome`` at or below the computed target level.

    Raises:
        ValueError: If ``clash.pc_win_threshold`` is 0 (division by zero guard).
        CheckOutcome.DoesNotExist: If no ``CheckOutcome`` row exists at or
            below the computed ``target_level``.

    Pure read — no DB writes, no mutation of inputs.

    Private helper — call only from ``fire_clash_per_round``.
    """
    if clash.pc_win_threshold == 0:
        msg = f"clash {clash.pk} has pc_win_threshold=0; cannot compute meter band."
        raise ValueError(msg)

    ratio: float = clash.progress / clash.pc_win_threshold

    if ratio >= 1.0:
        target_level = 3
    elif ratio >= 0.5:  # noqa: PLR2004
        target_level = 2
    elif ratio >= 0.0:
        target_level = 1
    elif ratio >= -0.25:  # noqa: PLR2004
        target_level = 0
    elif ratio >= -0.5:  # noqa: PLR2004
        target_level = -1
    else:
        target_level = -2

    return _find_check_outcome_at_or_below(target_level)


def _resolution_to_check_outcome(resolution: ClashResolution) -> CheckOutcome:
    """Map a ``ClashResolution`` tier to a ``CheckOutcome`` for pool filtering.

    Tier -> success_level mapping:
      PC_DECISIVE  -> 3  (critical success -- decisive PC win)
      PC_MARGINAL  -> 2  (great success -- marginal PC win)
      MUTUAL       -> 0  (partial -- stalemate)
      NPC_MARGINAL -> -1 (failure -- marginal NPC win)
      NPC_DECISIVE -> -2 (botch -- decisive NPC win)
      ABANDONED    -> -1 (failure -- equivalent to a marginal NPC win)

    Delegates to ``_find_check_outcome_at_or_below`` for the same
    closest-tier-<=target fallback used by ``_meter_band_to_check_outcome``.

    Raises:
        CheckOutcome.DoesNotExist: If no ``CheckOutcome`` row exists at or
            below the mapped ``success_level``. This always indicates
            incomplete configuration.

    Private helper -- call only from ``resolve_clash``.
    """
    _RESOLUTION_LEVEL: dict[str, int] = {
        ClashResolution.PC_DECISIVE: 3,
        ClashResolution.PC_MARGINAL: 2,
        ClashResolution.MUTUAL: 0,
        ClashResolution.NPC_MARGINAL: -1,
        ClashResolution.NPC_DECISIVE: -2,
        ClashResolution.ABANDONED: -1,
    }
    target_level = _RESOLUTION_LEVEL[resolution]
    return _find_check_outcome_at_or_below(target_level)


def fire_clash_per_round(
    *,
    clash: Clash,
    clash_round: ClashRound,  # noqa: ARG001
) -> Consequence | None:
    """Fire the per-round consequence pool, keyed on the current meter band.

    No-op (returns None) when ``clash.per_round_consequence_pool`` is null.
    Otherwise: maps the clash's ``progress`` to a ``CheckOutcome`` band, picks a
    matching consequence from the pool (weighted), applies its effects, and
    returns the chosen Consequence.

    Effect context targets the NPC opponent's ObjectDB as both ``character`` and
    ``target`` — per-round pool effects are NPC-side (damage absorption for WARD,
    narrative stress for CLASH). If ``npc_opponent.objectdb`` is None (opponent
    has no attached world object — common for non-ephemeral persona-bearing
    opponents in some setups), effect application is **skipped entirely**. The
    selected ``Consequence`` is still returned so the caller can see which one
    was drawn, but no ``apply_all_effects`` call is made. Callers that need to
    distinguish "consequence drawn and applied" from "consequence drawn but
    skipped" must check ``clash.npc_opponent.objectdb`` themselves before
    calling this function.

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
    from world.checks.outcome_utils import (  # noqa: PLC0415
        select_weighted,
    )
    from world.checks.types import (  # noqa: PLC0415
        ResolutionContext,
    )
    from world.mechanics.effect_handlers import (  # noqa: PLC0415
        apply_all_effects,
    )

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
    selected = selected_wc.consequence

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


# ---------------------------------------------------------------------------
# Task 4.2 -- end-of-clash resolution pool firing
# ---------------------------------------------------------------------------


@transaction.atomic
def resolve_clash(
    *,
    clash: Clash,
    resolution: ClashResolution,
    round_number: int,
) -> ClashResolutionResult:
    """Mark a clash as RESOLVED and fire its resolution consequence pool.

    Sets ``clash.status = RESOLVED``, ``clash.resolution = resolution``,
    ``clash.resolved_round = round_number``, saves.

    Fires the resolution pool (``clash.resolution_consequence_pool``):
      - maps the ``resolution`` tier to a ``CheckOutcome`` via
        ``_resolution_to_check_outcome``
      - filters ``pool.cached_consequences`` to entries with matching
        ``outcome_tier``
      - weight-picks via ``select_weighted``
      - applies effects via ``apply_all_effects``

    If no pool entry matches the resolution tier, ``consequence_applied``
    in the result is ``None`` and no effects are applied.

    Effect context targets the NPC opponent's ObjectDB as both ``character``
    and ``target``. If ``npc_opponent.objectdb`` is ``None`` (opponent has no
    attached world object -- common for non-ephemeral persona-bearing
    opponents in some setups), effect application is **skipped entirely**.
    The selected ``Consequence`` is still returned so callers can see which
    one was drawn, but no ``apply_all_effects`` call is made.  Callers that
    need to distinguish "consequence drawn and applied" from "consequence
    drawn but skipped" must check ``clash.npc_opponent.objectdb`` themselves
    before calling this function.

    Atomic -- all DB writes (Clash update + condition applications from effects)
    happen in one transaction.

    Args:
        clash: The active Clash instance to resolve.
        resolution: The ``ClashResolution`` tier determined by the round driver.
        round_number: The round number at which the clash was resolved (1-indexed).

    Returns:
        A frozen ``ClashResolutionResult`` with the resolved clash, the
        resolution tier, and the consequence applied (if any).
    """
    from world.checks.outcome_utils import (  # noqa: PLC0415
        select_weighted,
    )
    from world.checks.types import (  # noqa: PLC0415
        ResolutionContext,
    )
    from world.mechanics.effect_handlers import (  # noqa: PLC0415
        apply_all_effects,
    )

    # 1. Mark the clash resolved.
    clash.status = ClashStatus.RESOLVED
    clash.resolution = resolution
    clash.resolved_round = round_number
    clash.save(update_fields=["status", "resolution", "resolved_round"])

    # 2. Fire the resolution pool.
    pool = clash.resolution_consequence_pool

    # Map the resolution tier -> CheckOutcome for pool filtering.
    outcome = _resolution_to_check_outcome(resolution)

    # Filter pool's consequences to those matching the outcome tier.
    all_consequences = pool.cached_consequences
    tier_entries = [wc for wc in all_consequences if wc.outcome_tier == outcome]

    if not tier_entries:
        return ClashResolutionResult(
            clash=clash,
            resolution=resolution,
            consequence_applied=None,
        )

    # 3. Weighted selection.
    selected_wc = select_weighted(tier_entries)
    selected = selected_wc.consequence

    # 4. Build ResolutionContext targeting the NPC's ObjectDB.
    #    npc_opponent.objectdb may be None for opponents created without an ObjectDB
    #    (e.g. in tests, or non-ephemeral persona-bearing opponents in some setups).
    #    Effect application is skipped entirely when objectdb is None --
    #    the selected Consequence is still returned for caller visibility.
    npc_objectdb = clash.npc_opponent.objectdb

    if npc_objectdb is not None:
        context = ResolutionContext(
            character=npc_objectdb,
            target=npc_objectdb,
        )
        apply_all_effects(selected, context)

    return ClashResolutionResult(
        clash=clash,
        resolution=resolution,
        consequence_applied=selected,
    )


# ---------------------------------------------------------------------------
# Task 5.1 — clash opportunity detection
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD = 10  # TODO(tuning): replace with authored attack-power fields when available


@transaction.atomic
def detect_clash_opportunities(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Inspect the round's declared PC + NPC actions and the opponents' state,
    and create ``Clash`` rows for each opportunity that emerges.

    Detects four flavors:
      - **CLASH** — opposed clash-capable PC attack vs clash-capable NPC action.
      - **LOCK/SUSTAINING** — a lock-applying PC technique lands on the boss;
        PC wins by sustaining the lock to its threshold.
      - **LOCK/ESCAPING** — a lock-applying NPC action targets PCs; each targeted
        PC must escape.
      - **WARD** — a sustained NPC attack opens; one WARD per (opponent, entry)
        pair, idempotent for the duration.
      - **BREAK** — opponent has a standing barrier; one BREAK per opponent,
        idempotent until breached.

    Any flavor whose authored resolution pool is missing (None) is skipped rather
    than crashing — a missing pool is a content authoring gap, not a bug.

    Atomic — if any individual row write fails, none persist.

    Returns the list of newly-created ``Clash`` rows (already-existing WARD/BREAK
    rows are not included in the returned list).
    """
    created: list[Clash] = []

    created.extend(_detect_clash_flavor(encounter=encounter, round_number=round_number))
    created.extend(_detect_lock_sustaining(encounter=encounter, round_number=round_number))
    created.extend(_detect_lock_escaping(encounter=encounter, round_number=round_number))
    created.extend(_detect_ward(encounter=encounter, round_number=round_number))
    created.extend(_detect_break(encounter=encounter, round_number=round_number))

    return created


def _detect_clash_flavor(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Detect CLASH-flavor opportunities: opposed clash-capable attacks.

    For each PC round action with a clash-capable technique targeting an opponent,
    check whether the opponent's NPC action this round also has a clash_capable
    threat entry.  If both sides are clash-capable and the PC technique has a
    resolution pool, form a CLASH.

    Skips silently when the PC technique's ``clash_resolution_pool`` is None — a
    Clash without a resolution pool cannot fire its resolution effects and is a
    content-authoring gap, not a runtime case.

    Private helper — call only from ``detect_clash_opportunities``.
    """
    from world.combat.models import CombatRoundAction  # noqa: PLC0415

    created: list[Clash] = []

    pc_actions = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        round_number=round_number,
        focused_action__clash_capable=True,
        focused_opponent_target__isnull=False,
    ).select_related(
        "participant__character_sheet",
        "focused_action",
        "focused_opponent_target",
    )

    # Pre-resolve clash config once for the intensity floor.
    from world.combat.services import get_clash_config  # noqa: PLC0415

    intensity_floor = get_clash_config().clash_min_intensity

    for pc_action in pc_actions:
        clash = _build_clash_for_action(
            pc_action,
            encounter=encounter,
            round_number=round_number,
            intensity_floor=intensity_floor,
        )
        if clash is not None:
            created.append(clash)

    return created


def _build_clash_for_action(
    pc_action: CombatRoundAction,
    *,
    encounter: CombatEncounter,
    round_number: int,
    intensity_floor: int,
) -> Clash | None:
    """Form a CLASH for one PC action, or return None if no clash opens.

    Applies the gates in order: technique has a resolution pool, a matching
    clash-capable NPC action exists this round, the property opposition gate
    passes, and the intensity floor is met.
    """
    from world.combat.models import (  # noqa: PLC0415
        Clash,
        CombatOpponentAction,
    )
    from world.combat.services import compute_intensity_for_clash  # noqa: PLC0415

    technique = pc_action.focused_action
    opponent = pc_action.focused_opponent_target

    # Skip if no resolution pool — cannot create a non-nullable FK row.
    if technique.clash_resolution_pool is None:
        return None

    # Find the matching NPC action this round for the same opponent.
    try:
        npc_action = CombatOpponentAction.objects.select_related("threat_entry").get(
            opponent=opponent,
            round_number=round_number,
        )
    except CombatOpponentAction.DoesNotExist:
        return None  # NPC has no action this round — no clash

    if not npc_action.threat_entry.clash_capable:
        return None  # NPC action is not clash-capable

    # Property-based opposition gate — clash only opens if technique and
    # threat entry share at least one Property. Legacy-permissive: when
    # either side has no authored effect properties, fall through (we're
    # in pre-Phase-1 content territory). Once seed content authors
    # Properties for production, the gate engages naturally.
    pc_props = _technique_effect_property_ids(technique)
    npc_props = frozenset(npc_action.threat_entry.effect_properties.values_list("pk", flat=True))
    if pc_props and npc_props and not can_clash(pc_props, npc_props):
        return None

    # Intensity floor — prevents trivial round-1 clashes. When floor is 0
    # (default — set to a real value by seed content), this is a no-op.
    if intensity_floor > 0:
        eff_intensity = compute_intensity_for_clash(pc_action.participant, pc_action)
        if eff_intensity < intensity_floor:
            return None

    # Determine thresholds from authored base_damage fields.
    # Use TechniqueDamageProfile.base_damage if a profile exists; fall back to
    # ThreatPoolEntry.base_damage; if neither side provides signal, use the
    # design scaffold default.
    pc_power = _technique_attack_power(technique)
    npc_power = npc_action.threat_entry.base_damage or 0
    threshold = max(pc_power, npc_power) or _DEFAULT_THRESHOLD

    return Clash.objects.create(
        encounter=encounter,
        npc_opponent=opponent,
        initiator=pc_action.participant.character_sheet,
        resolution_consequence_pool=technique.clash_resolution_pool,
        per_round_consequence_pool=technique.clash_per_round_pool,
        flavor=ClashFlavor.CLASH,
        progress=0,
        pc_win_threshold=threshold,
        npc_win_threshold=threshold,
        started_round=round_number,
        triggering_threat_entry=npc_action.threat_entry,
    )


def _detect_lock_sustaining(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Detect LOCK/SUSTAINING opportunities: PC lock-applying techniques.

    For each PC whose focused technique is lock-applying (``is_lock_applying``
    cached_property — at least one applied condition with ``is_clash_lock=True``),
    form a LOCK/SUSTAINING clash. The PC holds the lock; the NPC tries to break free.

    pc_win_threshold is taken from the lock condition's ``clash_lock_strength``
    (defaulting to ``_DEFAULT_THRESHOLD`` when null).

    ``triggering_threat_entry`` is set to the NPC's round action's threat entry
    (so ``npc_round_contribution`` can read ``clash_break_free_force``).  When
    there is no NPC action this round, ``triggering_threat_entry`` is left null
    (NPC contributes 0 that round).

    Skips silently when the technique's ``clash_resolution_pool`` is None.

    Private helper — call only from ``detect_clash_opportunities``.
    """
    from world.combat.models import (  # noqa: PLC0415
        Clash,
        CombatOpponentAction,
        CombatRoundAction,
    )

    created: list[Clash] = []

    pc_actions = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        round_number=round_number,
        focused_action__isnull=False,
        focused_opponent_target__isnull=False,
    ).select_related(
        "participant__character_sheet",
        "focused_action",
        "focused_opponent_target",
    )

    for pc_action in pc_actions:
        technique = pc_action.focused_action
        if not technique.is_lock_applying:
            continue

        if technique.clash_resolution_pool is None:
            continue

        opponent = pc_action.focused_opponent_target

        # Find the clash-lock condition to read its strength.
        lock_application = (
            technique.condition_applications.select_related("condition")
            .filter(condition__is_clash_lock=True)
            .first()
        )
        if lock_application is None:
            # is_lock_applying returned True but no row found — data inconsistency;
            # skip defensively.
            continue
        threshold = lock_application.condition.clash_lock_strength or _DEFAULT_THRESHOLD

        # Find the NPC's round action for break-free pressure source.
        triggering_entry = None
        npc_action = (
            CombatOpponentAction.objects.filter(
                opponent=opponent,
                round_number=round_number,
            )
            .select_related("threat_entry")
            .first()
        )
        if npc_action is not None:
            triggering_entry = npc_action.threat_entry

        clash = Clash.objects.create(
            encounter=encounter,
            npc_opponent=opponent,
            initiator=pc_action.participant.character_sheet,
            resolution_consequence_pool=technique.clash_resolution_pool,
            per_round_consequence_pool=technique.clash_per_round_pool,
            flavor=ClashFlavor.LOCK,
            lock_pc_role=LockPcRole.SUSTAINING,
            progress=0,
            pc_win_threshold=threshold,
            npc_win_threshold=None,
            started_round=round_number,
            triggering_threat_entry=triggering_entry,
        )
        created.append(clash)

    return created


def _detect_lock_escaping(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Detect LOCK/ESCAPING opportunities: lock-applying NPC actions.

    For each NPC round action whose threat entry is ``is_lock_applying``, and
    for each targeted PC participant, form a LOCK/ESCAPING clash.  The PC must
    escape; the NPC maintains the lock.

    ``pc_win_threshold`` comes from the NPC threat entry's
    ``clash_break_free_force`` (the BREAK-free meter max). The NPC's per-round
    maintenance pressure is ``clash_npc_pressure``.

    progress starts at 0; PCs must push it back to 0 (ESCAPING sign convention).

    Skips silently when the threat entry has no ``clash_resolution_pool``.

    Private helper — call only from ``detect_clash_opportunities``.
    """
    from world.combat.models import (  # noqa: PLC0415
        Clash,
        CombatOpponentAction,
    )

    created: list[Clash] = []

    npc_actions = CombatOpponentAction.objects.filter(
        opponent__encounter=encounter,
        round_number=round_number,
        threat_entry__is_lock_applying=True,
    ).select_related("opponent", "threat_entry")

    for npc_action in npc_actions:
        entry = npc_action.threat_entry
        if entry.clash_resolution_pool is None:
            continue

        threshold = entry.clash_break_free_force or _DEFAULT_THRESHOLD

        for participant in npc_action.targets.select_related("character_sheet").all():
            clash = Clash.objects.create(
                encounter=encounter,
                npc_opponent=npc_action.opponent,
                initiator=participant.character_sheet,
                resolution_consequence_pool=entry.clash_resolution_pool,
                per_round_consequence_pool=entry.clash_per_round_pool,
                flavor=ClashFlavor.LOCK,
                lock_pc_role=LockPcRole.ESCAPING,
                progress=0,
                pc_win_threshold=threshold,
                npc_win_threshold=None,
                started_round=round_number,
                triggering_threat_entry=entry,
            )
            created.append(clash)

    return created


def _detect_ward(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Detect WARD opportunities: sustained NPC attacks.

    For each NPC round action with a sustained-attack threat entry, create a
    WARD clash — unless one already exists for that (opponent, threat entry)
    pair (a sustained attack opens exactly one WARD for its duration).

    ``ward_ends_on_round = round_number + sustained_duration_rounds``
    ``progress`` starts at ``pc_win_threshold`` (full ward integrity; NPC drains it).
    ``pc_win_threshold = sustained_duration_rounds * clash_npc_pressure``

    Skips silently when the threat entry has no ``clash_resolution_pool``.

    Private helper — call only from ``detect_clash_opportunities``.
    """
    from world.combat.models import (  # noqa: PLC0415
        Clash,
        CombatOpponentAction,
    )

    created: list[Clash] = []

    npc_actions = CombatOpponentAction.objects.filter(
        opponent__encounter=encounter,
        round_number=round_number,
        threat_entry__is_sustained_attack=True,
    ).select_related("opponent", "threat_entry")

    for npc_action in npc_actions:
        entry = npc_action.threat_entry
        if entry.clash_resolution_pool is None:
            continue

        # Idempotency: skip if an active WARD already exists for this pair.
        already_active = Clash.objects.filter(
            encounter=encounter,
            npc_opponent=npc_action.opponent,
            flavor=ClashFlavor.WARD,
            status=ClashStatus.ACTIVE,
            triggering_threat_entry=entry,
        ).exists()
        if already_active:
            continue

        duration = entry.sustained_duration_rounds or 1
        pressure = entry.clash_npc_pressure or _DEFAULT_THRESHOLD
        threshold = duration * pressure
        ward_ends = round_number + duration

        clash = Clash.objects.create(
            encounter=encounter,
            npc_opponent=npc_action.opponent,
            initiator=None,
            resolution_consequence_pool=entry.clash_resolution_pool,
            per_round_consequence_pool=entry.clash_per_round_pool,
            flavor=ClashFlavor.WARD,
            lock_pc_role=None,
            progress=threshold,  # starts at full integrity
            pc_win_threshold=threshold,
            npc_win_threshold=None,
            ward_ends_on_round=ward_ends,
            started_round=round_number,
            triggering_threat_entry=entry,
        )
        created.append(clash)

    return created


def _detect_break(*, encounter: CombatEncounter, round_number: int) -> list[Clash]:
    """Detect BREAK opportunities: opponents with a standing barrier.

    For each CombatOpponent in the encounter with a non-null ``barrier_strength``,
    create a BREAK clash — unless one already exists (the barrier is a standing
    target until breached or the encounter ends).

    ``pc_win_threshold = opponent.barrier_strength``
    ``progress`` starts at 0 (PCs must accumulate up to threshold).

    Skips silently when the opponent has no ``barrier_break_pool``.

    Private helper — call only from ``detect_clash_opportunities``.
    """
    from world.combat.models import (  # noqa: PLC0415
        Clash,
        CombatOpponent,
    )

    created: list[Clash] = []

    opponents = CombatOpponent.objects.filter(
        encounter=encounter,
        barrier_strength__isnull=False,
        barrier_break_pool__isnull=False,
    ).select_related("barrier_break_pool")

    for opponent in opponents:
        if opponent.barrier_break_pool is None:
            continue

        # Idempotency: skip if an active BREAK already exists for this opponent.
        already_active = Clash.objects.filter(
            encounter=encounter,
            npc_opponent=opponent,
            flavor=ClashFlavor.BREAK,
            status=ClashStatus.ACTIVE,
        ).exists()
        if already_active:
            continue

        clash = Clash.objects.create(
            encounter=encounter,
            npc_opponent=opponent,
            initiator=None,
            resolution_consequence_pool=opponent.barrier_break_pool,
            per_round_consequence_pool=None,
            flavor=ClashFlavor.BREAK,
            lock_pc_role=None,
            progress=0,
            pc_win_threshold=opponent.barrier_strength,
            npc_win_threshold=None,
            ward_ends_on_round=None,
            started_round=round_number,
            triggering_threat_entry=None,
        )
        created.append(clash)

    return created


def _technique_attack_power(technique: Technique) -> int:
    """Return a representative attack-power value for a Technique.

    Reads the first damage profile's ``base_damage`` if one exists.  Falls back
    to 0 when no damage profile is attached (caller applies the design-scaffold
    default).

    Private helper — used only by ``_detect_clash_flavor``.
    """
    profile = technique.damage_profiles.first()
    if profile is None:
        return 0
    return profile.base_damage


# ---------------------------------------------------------------------------
# Task 5.2 — per-clash round driver
# ---------------------------------------------------------------------------


def _consecutive_idle_rounds(clash: Clash) -> int:
    """Count consecutive trailing ``ClashRound``s with no ``ClashContribution`` rows.

    The canonical BREAK-abandonment signal: PCs stopped declaring contributions.
    Reads the persisted ``ClashRound`` rows for this clash ordered newest-first.
    Iterates until a round with contributions is hit, or all rows are exhausted.

    Pure read — no DB writes, no mutation of inputs.

    Private helper — called only by ``run_clash_round``.
    """
    count = 0
    for round_row in clash.rounds.order_by("-round_number"):
        if not round_row.contributions.exists():
            count += 1
        else:
            break
    return count


@transaction.atomic
def run_clash_round(
    *,
    clash: Clash,
    round_number: int,
    pc_contributions: list[PreparedClashContribution],
    config_clash: ClashConfig,
    config_strain: StrainConfig,
) -> ClashRoundResult:
    """Drive one round of a clash: per-PC commit (with affinity tilt) → aggregate
    → per-round pool → threshold check (resolve if crossed).

    Composes the Phase 2–4 service functions into a single atomic round driver.
    If any inner step raises, the entire round (ClashRound row, ClashContribution
    rows, and ``clash.progress`` update) rolls back via the outer ``@transaction.atomic``.

    Args:
        clash: The active ``Clash`` instance to advance by one round.
        round_number: The 1-indexed round being processed.
        pc_contributions: List of ``PreparedClashContribution`` objects, one per
            PC participating this round.  May be empty (NPC-only push or idle round).
        config_clash: Clash tuning knobs (thresholds, deltas, abandon window, etc.).
        config_strain: Strain-to-modifier curve knobs for per-PC commit calls.

    Returns:
        A frozen ``ClashRoundResult`` with the persisted ``ClashRound`` row and
        the updated meter state.  The clash's ``status`` may be ``RESOLVED`` on
        return if a threshold was crossed.

    Raises:
        Any exception from the inner service functions propagates after rolling
        back the transaction.
    """
    # -------------------------------------------------------------------------
    # 1. Per-PC commit — call commit_to_clash once per contribution, threading
    #    the affinity tilt as ``check_modifier_extra``.
    # -------------------------------------------------------------------------
    contribution_results: list[ClashContributionResult] = []
    for contrib in pc_contributions:
        tilt = affinity_tilt(
            contributor_technique=contrib.technique,
            npc_attack_affinity=contrib.npc_attack_affinity,
            config=config_clash,
        )
        result = commit_to_clash(
            character_sheet=contrib.character_sheet,
            technique=contrib.technique,
            clash=clash,
            strain_commitment=contrib.strain_commitment,
            action_slot=contrib.action_slot,
            config_clash=config_clash,
            config_strain=config_strain,
            check_modifier_extra=tilt,
        )
        contribution_results.append(result)

    # -------------------------------------------------------------------------
    # 2. NPC contribution for this round.
    # -------------------------------------------------------------------------
    npc_delta = npc_round_contribution(clash=clash, round_number=round_number)

    # -------------------------------------------------------------------------
    # 3. Aggregate — writes ClashRound + ClashContribution rows and updates
    #    clash.progress. The in-memory instance is kept fully in sync.
    # -------------------------------------------------------------------------
    round_result = aggregate_clash_round(
        clash=clash,
        round_number=round_number,
        pc_contributions=contribution_results,
        npc_delta=npc_delta,
    )

    # -------------------------------------------------------------------------
    # 4. Per-round consequence pool — fires incremental feedback effects.
    # -------------------------------------------------------------------------
    fire_clash_per_round(clash=clash, clash_round=round_result.clash_round)

    # -------------------------------------------------------------------------
    # 5. Threshold / abandon check — determine whether the clash should resolve.
    # -------------------------------------------------------------------------
    resolution: ClashResolution | None = None

    # Skip the threshold check on the clash's creation round when PCs had no
    # chance to declare contributions yet.
    #
    # When a clash is born mid-round (detect_clash_opportunities creates it and
    # run_clash_round fires for it in the same post-pass), PCs have not had a
    # chance to declare a ClashContributionDeclaration — the clash was formed in
    # response to their *round action*, not from a pre-declared contribution.
    # Checking the threshold on the creation round with pc_contributions=[] would
    # resolve a LOCK/SUSTAINING or LOCK/ESCAPING clash immediately because progress
    # starts at 0 and the ``<= 0`` boundary fires even when neither side has had a
    # fair contest.  We only skip when contributions are empty; unit tests that
    # pre-load progress and pass contributions still run the threshold normally.
    is_uncontested_creation_round = round_number == clash.started_round and not pc_contributions

    if not is_uncontested_creation_round:
        # BREAK-specific abandonment: the normal threshold check does not detect
        # ABANDONED (NPC never wins via the meter in BREAK clashes).  Detect it
        # here by counting consecutive trailing idle (zero-PC-delta) rounds.
        if clash.flavor == ClashFlavor.BREAK and len(pc_contributions) == 0:
            idle_count = _consecutive_idle_rounds(clash)
            if idle_count >= config_clash.break_abandon_idle_rounds:
                resolution = ClashResolution.ABANDONED

        # If not already determined by the BREAK abandonment path, run the
        # standard threshold check.
        if resolution is None:
            resolution = check_clash_threshold(
                clash=clash, round_number=round_number, config=config_clash
            )

    # If a resolution was determined, fire resolve_clash and surface its result
    # on the round result (it was previously computed and discarded). The
    # round-resolution layer reads ``ClashRoundResult.resolution`` to broadcast
    # an outcome narration (#644).
    if resolution is not None:
        clash_resolution = resolve_clash(
            clash=clash, resolution=resolution, round_number=round_number
        )
        round_result = replace(round_result, resolution=clash_resolution)

    return round_result
