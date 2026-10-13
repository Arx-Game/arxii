"""Resolving clashes at round end."""

from __future__ import annotations

from collections import defaultdict

from world.combat.models import (
    Clash,
    ClashContributionDeclaration,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
)
from world.combat.services.encounter.config import get_clash_config, get_strain_config
from world.combat.types import ClashRoundResult, PreparedClashContribution


def _resolve_clashes(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],  # noqa: ARG001
) -> list[ClashRoundResult]:
    """Post-pass: detect clash opportunities, then drive one round per active Clash.

    Called after all combat-action resolution for the round.  Two phases:

    1. **Opportunity detection** — ``detect_clash_opportunities`` inspects the
       round's declared PC + NPC actions and creates ``Clash`` rows for newly-
       emerged opportunities.  Newly-created clashes participate in the same
       round's post-pass so that the first round of a clash is resolved
       immediately.

    2. **Per-clash round driver** — for each ACTIVE Clash (including any just
       created in step 1), gather the PC's ``ClashContributionDeclaration`` rows,
       build ``PreparedClashContribution`` objects, and call ``run_clash_round``.
       Clashes are iterated in ``Clash.pk`` order for deterministic resolution.

       TODO(Phase 5 / initiative ordering): order PC-initiated clashes by the
       initiating participant's initiative slot, mirroring how
       ``_resolve_declared_challenges`` follows ``resolution_order``.  NPC-initiated
       clashes (WARD, LOCK/ESCAPING) don't have a PC initiator in the same sense;
       they can resolve at a fixed NPC slot or after all PC-initiated clashes.
       For v1, pk order is sufficient and deterministic.

    3. **Declaration cleanup** — all ``ClashContributionDeclaration`` rows for
       this round are deleted atomically after all clashes are processed, inside
       the caller's ``@transaction.atomic`` block.

    ``npc_attack_affinity`` is resolved at post-pass time from
    ``clash.triggering_threat_entry``.  ``ThreatPoolEntry`` has no affinity field
    (confirmed in Task 5.3 investigation) — ``npc_attack_affinity`` is always
    ``None`` in v1, so ``affinity_tilt`` always returns 0.  When a future task
    adds an affinity field to ``ThreatPoolEntry``, update this function to read it.

    Runs inside the outer ``@transaction.atomic`` on ``resolve_round`` — no
    separate ``@transaction.atomic`` decorator is needed here.

    Args:
        encounter: The active ``CombatEncounter`` being resolved.
        round_number: The current encounter round number (1-indexed).
        resolution_order: PC/NPC action resolution order (reserved for future
            initiative-based clash ordering; unused in v1).

    Returns:
        A list of ``ClashRoundResult`` objects, one per Clash that was driven
        this round.  May be empty when no Clashes are active.
    """
    from world.combat.clash import (  # noqa: PLC0415
        detect_clash_opportunities,
        run_clash_round,
    )
    from world.combat.constants import ClashStatus  # noqa: PLC0415

    # 1. Detect new opportunities this round (creates Clash rows).
    detect_clash_opportunities(encounter=encounter, round_number=round_number)

    # 2. Find all ACTIVE clashes (includes any just created in step 1).
    # TODO(Phase 5 / initiative ordering): order by initiating participant's
    # initiative slot instead of pk for PC-initiated clashes.
    active_clashes = list(
        Clash.objects.filter(
            encounter=encounter,
            status=ClashStatus.ACTIVE,
        ).select_related("npc_opponent", "triggering_threat_entry")
    )

    if not active_clashes:
        return []

    # 3. Gather all declarations for this round and group by clash_id.
    declarations = list(
        ClashContributionDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "clash",
            "participant__character_sheet",
            "technique",
            "technique__action_template",
        )
    )
    decls_by_clash: dict[int, list[ClashContributionDeclaration]] = defaultdict(list)
    for decl in declarations:
        decls_by_clash[decl.clash_id].append(decl)

    # 4. Load configs once (singleton reads; SharedMemoryModel caches them).
    # get_clash_config / get_strain_config are defined later in this module;
    # Python resolves names at call time so the forward reference is fine.
    config_clash = get_clash_config()
    config_strain = get_strain_config()

    # 5. Drive one round per active clash.
    outcomes: list[ClashRoundResult] = []
    for clash in active_clashes:
        clash_decls = decls_by_clash.get(clash.pk, [])

        # Build PreparedClashContribution objects for this clash's declarations.
        # npc_attack_affinity: ThreatPoolEntry has no affinity field in v1 — pass None.
        # When a future task adds an affinity field, read it here from
        # clash.triggering_threat_entry.
        pc_contributions: list[PreparedClashContribution] = [
            PreparedClashContribution(
                character_sheet=decl.participant.character_sheet,
                action_slot=decl.action_slot,
                technique=decl.technique,
                strain_commitment=decl.strain_commitment,
                npc_attack_affinity=None,  # ThreatPoolEntry has no affinity field in v1
            )
            for decl in clash_decls
        ]

        result = run_clash_round(
            clash=clash,
            round_number=round_number,
            pc_contributions=pc_contributions,
            config_clash=config_clash,
            config_strain=config_strain,
        )
        outcomes.append(result)

        # When the clash resolved this round, broadcast a durable, Narrator-
        # authored OUTCOME line for the break/lock/ward result (#644). Mirrors
        # the per-action broadcast in _resolve_pc_action.
        if result.resolution is not None:
            from world.combat.interaction_services import (  # noqa: PLC0415
                broadcast_action_outcome,
                render_clash_outcome_narration,
            )

            opponent_label = clash.npc_opponent.name if clash.npc_opponent_id else "?"
            consequence = result.resolution.consequence_applied
            narration = render_clash_outcome_narration(
                flavor_label=clash.get_flavor_display(),
                opponent_label=opponent_label,
                resolution_tier=result.resolution.resolution,
                consequence_label=consequence.label if consequence is not None else None,
            )
            broadcast_action_outcome(encounter=encounter, narration=narration)

    # 6. Delete all declarations for this round (inside caller's atomic block).
    ClashContributionDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes
