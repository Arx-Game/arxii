"""Interaction-creation service for resolved combat actions.

When the resolve_round pipeline finishes a PC action or a clash contribution,
it creates an ACTION-mode ``Interaction`` row so the pose log can link to it.
The ``Interaction.content`` carries the **declaration label** of the action
(e.g. "Frost Bolt at Pyromancer") — not pre-rendered outcome text. Outcome
details are derived live by ``views_outcome_details`` from existing model
state (combo, conditions, vitals).

Phase 3 — combat-resolution-loop PR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ClashResolution
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction

if TYPE_CHECKING:
    from world.combat.models import (
        ClashContribution,
        CombatEncounter,
        CombatParticipant,
        CombatRoundAction,
    )
    from world.combat.types import ActionOutcome
    from world.magic.types.power_ledger import PowerLedger


def create_action_interaction(
    *,
    participant: CombatParticipant,
    round_number: int,
    summary_label: str,
    strain_committed: int = 0,
) -> Interaction | None:
    """Create one ACTION-mode Interaction for a resolved action.

    Args:
        participant: The PC participant whose action resolved.
        round_number: The encounter round this resolution happened in. Currently
            informational; the Interaction itself carries timestamp via
            auto_now_add.
        summary_label: Short label for ``Interaction.content`` — the action's
            declaration text. Examples: "Frost Bolt at Pyromancer",
            "Strain commitment to Suppress vs Pyromancer".
        strain_committed: Strain the participant actually committed for this
            action. Recorded on the resulting Interaction's canonical
            ``strain_committed`` audit column. Defaults to 0 for non-clash
            actions that do not commit strain.

    Returns:
        The newly-created Interaction row, or ``None`` if the participant's
        character sheet has no PRIMARY persona (legacy fixture content predating
        the create_character_with_sheet invariant — skipped silently to allow
        the resolve loop to continue without writing a pose-log link).
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    sheet = participant.character_sheet
    try:
        persona = sheet.primary_persona
    except Persona.DoesNotExist:
        # Legacy fixture content; skip Interaction creation. The action still
        # resolves; it just won't have a pose-log link.
        return None

    encounter = participant.encounter
    scene = encounter.scene  # nullable on Interaction; pass through as-is

    # The round_number parameter is currently informational — it's encoded in
    # the action row that calls this, and Interaction.timestamp gives temporal
    # ordering. Kept in the signature so callers can pass it without having to
    # walk back through the action.
    del round_number

    return Interaction.objects.create(
        persona=persona,
        scene=scene,
        content=summary_label,
        mode=InteractionMode.ACTION,
        strain_committed=strain_committed,
    )


def render_action_declaration_label(action: CombatRoundAction) -> str:
    """Render a one-line declaration label for an ACTION Interaction's content.

    Format: ``<TechniqueName> at <TargetName>`` for targeted attacks;
    ``<TechniqueName>`` alone when no target. Falls back to ``"passives only"``
    when ``focused_action`` is null (which the resolver normally skips, but
    surfacing a non-empty string is safer than empty content).
    """
    technique = action.focused_action
    if technique is None:
        return "passives only"

    if action.focused_opponent_target_id is not None:
        target_name = action.focused_opponent_target.name
        return f"{technique.name} at {target_name}"
    if action.focused_ally_target_id is not None:
        ally = action.focused_ally_target
        target_name = ally.character_sheet.character.db_key
        return f"{technique.name} at {target_name}"
    return technique.name


def render_clash_contribution_label(contribution: ClashContribution) -> str:
    """Render a one-line declaration label for a clash contribution.

    Format: ``<TechniqueName> → <ClashFlavor> vs <OpponentName>``.
    """
    technique = contribution.technique
    clash = contribution.clash_round.clash
    flavor = clash.get_flavor_display()
    opponent_name = clash.npc_opponent.name if clash.npc_opponent_id else "?"
    return f"{technique.name} → {flavor} vs {opponent_name}"


def _power_outcome_clause(power_ledger: PowerLedger | None) -> str:
    """Return a short, dramatic prose clause describing the ledger’s notable event.

    Inspects PENETRATION and ENVIRONMENT stages in priority order:

    1. Bounce (PENETRATION SET to 0) — the ward entirely turned the working aside.
    2. Partial bleed (PENETRATION MULTIPLY with a negative percent) — the ward
       absorbed much of the force but the working still landed.
    3. Clean penetration (PENETRATION SET to a positive value, label
       "ward (penetrated)") — the working tore cleanly through the ward.
    4. Environment amplification (ENVIRONMENT ADD with a positive amount) —
       a resonant node swelled the working’s power.

    Returns ``""`` when none of these cases apply (plain unwarded, non-magic, or
    combo path). Only one clause is returned — priorities run top to bottom.
    """
    if power_ledger is None:
        return ""

    from world.magic.constants import LedgerOp, PowerStage  # noqa: PLC0415

    for entry in power_ledger.entries:
        if entry.stage != PowerStage.PENETRATION:
            continue
        # Bounce: SET to 0 (label "ward (bounced)")
        if entry.op == LedgerOp.SET and entry.amount == 0:
            return "— the ward turns it aside"
        # Partial: MULTIPLY with negative percent (ward reduced power)
        if entry.op == LedgerOp.MULTIPLY and entry.amount < 0:
            return "— the ward bleeds off much of its force"
        # Clean / over penetration: SET to positive value (label "ward (penetrated)")
        # or MULTIPLY with a positive pct (overpenetration amplified by the bounce factor).
        # Both are "tore through" — collapse into one condition.
        if entry.amount > 0:
            return "— it tears through the ward"

    # Environment amplification: ENVIRONMENT ADD with positive amount
    for entry in power_ledger.entries:
        if entry.stage == PowerStage.ENVIRONMENT and entry.op == LedgerOp.ADD and entry.amount > 0:
            return "— the place’s resonance swells the working"

    return ""


def _build_tail_clauses(
    *, wounds: list[str], defeated: bool, dying: bool, knocked_out: bool
) -> list[str]:
    """Collect the consequence tail clauses for a damage hit."""
    tail: list[str] = []
    if wounds:
        tail.append("leaving them " + ", ".join(wounds))
    if defeated:
        tail.append("defeating them")
    elif dying:
        tail.append("leaving them dying")
    elif knocked_out:
        tail.append("knocking them out")
    return tail


def _assemble_hit_line(head: str, tail_clauses: list[str], power_clause: str) -> str:
    """Compose the damage-hit narration line from its constituent parts."""
    body = head + (", " + ", ".join(tail_clauses) if tail_clauses else "")
    return f"{body} {power_clause}." if power_clause else f"{body}."


def render_action_outcome_narration(
    *,
    actor_label: str,
    technique_name: str,
    target_label: str | None,
    outcome: ActionOutcome,
    power_ledger: PowerLedger | None = None,
) -> str:
    """Render a one-line, deterministic outcome narration from resolved data.

    Pure function — no DB access, no randomness. Composes clauses from the
    ActionOutcome’s damage results and consequences. Absent data → omitted
    clause. Used as the content of an OUTCOME-mode Interaction authored by the
    Narrator persona.

    When ``power_ledger`` is supplied (magic-pipeline actions only), a concise
    ward/environment clause is appended to the OUTCOME line: e.g.
    "— the ward turns it aside" for a full bounce, "— it tears through the ward"
    for clean penetration, or "— the place’s resonance swells the working" for
    an environment amplification. Combo and non-magic paths pass ``None`` and
    get no clause, preserving backward compatibility.

    Examples:
        "Kira’s Frost Bolt strikes the Pyromancer for 24 damage."
        "Kira’s Frost Bolt strikes the Pyromancer for 40 damage, defeating them."
        "Kira’s Frost Bolt misses the Pyromancer — the ward turns it aside."
        "Garruk uses Guard Stance."
    """
    total_damage = sum(dr.damage_dealt for dr in outcome.damage_results)
    defeated = any(getattr(dr, "defeated", False) for dr in outcome.damage_results)  # noqa: GETATTR_LITERAL
    knocked_out = any(c.knocked_out for c in outcome.damage_consequences)
    dying = any(c.dying for c in outcome.damage_consequences)
    wounds = [ct.name for c in outcome.damage_consequences for ct in c.wounds_applied]

    # No target → self/utility action.
    if target_label is None:
        if outcome.combo_used is not None:
            return f"{actor_label} unleashes {outcome.combo_used.name}."
        return f"{actor_label} uses {technique_name}."

    power_clause = _power_outcome_clause(power_ledger)

    # Targeted action with no damage and no wounds → miss (or warded bounce).
    if total_damage <= 0 and not wounds:
        base = f"{actor_label}’s {technique_name} misses {target_label}"
        return f"{base} {power_clause}." if power_clause else f"{base}."

    head = f"{actor_label}’s {technique_name} strikes {target_label} for {total_damage} damage"
    tail = _build_tail_clauses(
        wounds=wounds, defeated=defeated, dying=dying, knocked_out=knocked_out
    )
    return _assemble_hit_line(head, tail, power_clause)


def render_challenge_outcome_narration(
    *,
    actor_label: str,
    challenge_name: str,
    approach_name: str,
    outcome_label: str,
    success_level: int,
) -> str:
    """Render a one-line, deterministic outcome narration for a resolved challenge.

    Pure function — no DB access, no randomness. Sibling of
    ``render_action_outcome_narration`` for the challenge-resolution path. The
    caller supplies primitives extracted from the ``ChallengeResolutionResult``
    and the resolving participant, so this stays DB-free and unit-testable.

    Examples:
        "Kira attempts Scale the Wall (Athletics) and succeeds (Decisive Success)."
        "Kira attempts Scale the Wall (Athletics) and fails (Failure)."
    """
    verb = "succeeds" if success_level > 0 else "fails"
    return (
        f"{actor_label} attempts {challenge_name} ({approach_name}) and {verb} ({outcome_label})."
    )


# Per-tier resolution clause for clash-outcome narration. Keys are
# ``ClashResolution`` members (str-valued TextChoices, so a raw value string
# from a resolved clash matches the same key). ``{opponent}`` is interpolated
# at render time for NPC-favored tiers.
_CLASH_TIER_CLAUSES: dict[str, str] = {
    ClashResolution.PC_DECISIVE: "resolves decisively in the casters' favor",
    ClashResolution.PC_MARGINAL: "resolves narrowly in the casters' favor",
    ClashResolution.MUTUAL: "ends in a mutual stalemate",
    ClashResolution.NPC_MARGINAL: "resolves narrowly in {opponent}'s favor",
    ClashResolution.NPC_DECISIVE: "resolves decisively in {opponent}'s favor",
    ClashResolution.ABANDONED: "is abandoned",
}


def render_clash_outcome_narration(
    *,
    flavor_label: str,
    opponent_label: str,
    resolution_tier: str,
    consequence_label: str | None = None,
) -> str:
    """Render a one-line, deterministic outcome narration for a resolved clash.

    Pure function — no DB access, no randomness. Primitives in (the caller
    extracts them from the ``ClashResolutionResult`` + its ``Clash``) so this
    stays DB-free and unit-testable like ``render_action_outcome_narration``.

    Examples:
        "The Break with the Pyromancer resolves decisively in the casters' favor."
        "The Ward with the Pyromancer resolves decisively in the Pyromancer's "
        "favor, leaving Stagger."
    """
    clause = _CLASH_TIER_CLAUSES.get(resolution_tier, "resolves").format(opponent=opponent_label)
    head = f"The {flavor_label} with {opponent_label} {clause}"
    if consequence_label:
        return f"{head}, leaving {consequence_label}."
    return f"{head}."


def broadcast_action_outcome(
    *,
    encounter: CombatEncounter,
    narration: str,
) -> Interaction | None:
    """Persist a Narrator-authored OUTCOME interaction and broadcast it.

    Returns the created Interaction, or None when there is no narration
    text (empty string -> nothing to say). The OUTCOME is persisted in
    the encounter's scene so it appears in the scene log on re-read;
    broadcast goes to every object in the encounter room via the existing
    interaction WebSocket payload. When the encounter has no room, the
    interaction is still persisted (durable) but not broadcast.
    """
    if not narration:
        return None

    from world.combat.narrator import get_or_create_narrator_persona  # noqa: PLC0415
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _broadcast_to_location,
        _build_interaction_payload,
        create_interaction,
    )

    narrator = get_or_create_narrator_persona()
    interaction = create_interaction(
        persona=narrator,
        content=narration,
        mode=InteractionMode.OUTCOME,
        scene=encounter.scene,
    )

    room = encounter.room
    if room is None:
        return interaction

    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=narrator,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        scene_id=interaction.scene_id,
    )
    _broadcast_to_location(room, payload)
    return interaction
