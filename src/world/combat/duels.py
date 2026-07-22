"""Duel setup and lifecycle services.

Keeps duel-specific logic out of the already-large services.py. A duel is a
PC-vs-PC encounter: both PCs are CombatParticipants (they declare actions) AND
each is mirrored by a passive ephemeral-free CombatOpponent surface the OTHER
attacks.

Mirror wiring:
    mirror_A.mirrors_participant = participant_A  (A's body surface; B attacks it)
    mirror_B.mirrors_participant = participant_B  (B's body surface; A attacks it)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.combat.beat_wiring import activate_stakes_for_scene
from world.combat.cast_seed import _opponent_kwargs_from_sheet
from world.combat.chosen_ground import compute_on_chosen_ground
from world.combat.constants import (
    DuelChallengeStatus,
    EncounterOutcome,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    RiskLevel,
)
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
from world.combat.services import (
    acknowledge_encounter_risk,
    add_opponent,
    add_participant,
    complete_encounter,
)
from world.scenes.constants import RoundStatus
from world.vitals.services import can_act

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import DuelChallenge
    from world.scenes.models import Scene


_PVP_PARTICIPANT_COUNT = 2  # two PC participants = PvP


def _scene_for_duel(room: ObjectDB) -> Scene:
    from world.scenes.place_services import ensure_scene_for_location  # noqa: PLC0415

    return ensure_scene_for_location(room)


def assert_duel_lethality_valid(encounter: CombatEncounter) -> None:
    """Raise ValueError if a DUEL encounter has two PC participants and is lethal.

    Enforces the hard invariant: PC-vs-PC duels can never be lethal.
    Called as a belt-and-suspenders guard in the begin-declaration path for DUEL
    encounters, catching any construction path that bypasses ``create_pvp_duel``.

    Args:
        encounter: The CombatEncounter to validate.

    Raises:
        ValueError: If ``encounter.is_lethal`` and the encounter has two or more
            PC participants (``CombatParticipant`` rows).
    """
    if encounter.is_lethal and encounter.participants.count() >= _PVP_PARTICIPANT_COUNT:
        msg = "A DUEL encounter with two PC participants cannot be lethal."
        raise ValueError(msg)


def _make_mirror(enc: CombatEncounter, participant: CombatParticipant) -> CombatOpponent:
    """Create a passive mirror opponent surface for a PC participant.

    The mirror is built from the participant's CharacterSheet stats via
    ``_opponent_kwargs_from_sheet``, then ``mirrors_participant`` is set on the
    returned instance (``add_opponent`` does not accept it as a kwarg).

    Position sync: the mirror's position is left as the opponent's default
    (derived from its ObjectDB location). Reach degrades gracefully to SAME
    when no explicit position is stored — Task 15 wires reach for duels.
    """
    sheet = participant.character_sheet
    kwargs = _opponent_kwargs_from_sheet(sheet)
    mirror = add_opponent(enc, **kwargs)
    mirror.mirrors_participant = participant
    mirror.save(update_fields=["mirrors_participant"])
    return mirror


@transaction.atomic
def create_pvp_duel(
    challenger_sheet: CharacterSheet,
    challenged_sheet: CharacterSheet,
    room: ObjectDB,
    *,
    risk_level: str = RiskLevel.MODERATE,
) -> CombatEncounter:
    """Set up a symmetric PC-vs-PC duel encounter.

    Creates a DUEL encounter in DECLARING status with two participants and two
    passive mirror opponents, records risk acknowledgements for both, and
    returns the encounter.

    Args:
        challenger_sheet: The sheet of the PC initiating the duel.
        challenged_sheet: The sheet of the PC accepting the duel.
        room: The ObjectDB room where the encounter takes place.
        risk_level: Risk level for this duel; must not be LETHAL (PvP is never
            lethal). Defaults to MODERATE.

    Returns:
        The newly created CombatEncounter in DECLARING status.

    Raises:
        ValueError: If ``risk_level`` is LETHAL.
    """
    if risk_level == RiskLevel.LETHAL:
        msg = "PC-vs-PC duels can never be lethal."
        raise ValueError(msg)

    # #2646: PvP is never lethal, so "chosen ground" deliberately does not apply
    # here — on_chosen_ground stays at its model default (False). Only the
    # PC-vs-NPC seams (create_lethal_duel, seed_or_feed_encounter_from_cast,
    # open_place_encounter) stamp it.
    enc = CombatEncounter.objects.create(
        encounter_type=EncounterType.DUEL,
        room=room,
        scene=_scene_for_duel(room),
        risk_level=risk_level,
        status=RoundStatus.DECLARING,
    )
    from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415

    assign_default_escalation_curve(enc)

    participant_a = add_participant(enc, challenger_sheet)
    participant_b = add_participant(enc, challenged_sheet)

    _make_mirror(enc, participant_a)
    _make_mirror(enc, participant_b)

    acknowledge_encounter_risk(enc, challenger_sheet)
    acknowledge_encounter_risk(enc, challenged_sheet)

    # #1770 PR4: entering the duel is the stakes commit moment — lock any
    # staked beats on the scene for this party (idempotent while open).
    activate_stakes_for_scene(enc.scene, [challenger_sheet, challenged_sheet])

    return enc


# Tiers that represent significant NPCs and are valid for a lethal duel.
_SIGNIFICANT_NPC_TIERS: frozenset[str] = frozenset(
    {OpponentTier.ELITE, OpponentTier.BOSS, OpponentTier.HERO_KILLER}
)


@transaction.atomic
def create_lethal_duel(
    pc_sheet: CharacterSheet,
    opponent_kwargs: dict,
    room: ObjectDB,
    *,
    tier: str = OpponentTier.ELITE,
) -> CombatEncounter:
    """Set up a lethal PC-vs-significant-NPC duel encounter.

    Creates a DUEL encounter with ``risk_level=LETHAL``, one PC participant,
    and one real (non-mirror) CombatOpponent of the given significant-NPC tier
    with its own threat pool.

    The PC must acknowledge the lethal risk via the #777 gate before acting —
    this function does NOT call ``acknowledge_encounter_risk``.

    Args:
        pc_sheet: The sheet of the PC entering the lethal duel.
        opponent_kwargs: Keyword arguments forwarded to ``add_opponent`` (must
            include at minimum ``name``, ``max_health``, and ``threat_pool``).
            The ``tier`` key, if present, is ignored in favour of the explicit
            ``tier`` parameter.
        room: The ObjectDB room where the encounter takes place.
        tier: Opponent tier; must be ELITE, BOSS, or HERO_KILLER. Defaults to
            ELITE.

    Returns:
        The newly created CombatEncounter in DECLARING status.

    Raises:
        ValueError: If ``tier`` is not a significant-NPC tier
            (ELITE / BOSS / HERO_KILLER).
    """
    if tier not in _SIGNIFICANT_NPC_TIERS:
        msg = (
            f"create_lethal_duel requires a significant NPC tier (significant NPC only);"
            f" got {tier!r}."
        )
        raise ValueError(msg)

    enc = CombatEncounter.objects.create(
        encounter_type=EncounterType.DUEL,
        room=room,
        scene=_scene_for_duel(room),
        risk_level=RiskLevel.LETHAL,
        status=RoundStatus.DECLARING,
        on_chosen_ground=compute_on_chosen_ground(room),
    )
    from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415

    assign_default_escalation_curve(enc)

    add_participant(enc, pc_sheet)

    # Forward caller-supplied kwargs, forcing the validated tier value.
    kwargs = dict(opponent_kwargs)
    kwargs["tier"] = tier
    add_opponent(enc, **kwargs)

    # #1770 PR4: entering the lethal duel is the stakes commit moment — lock
    # any staked beats on the scene for this party (idempotent while open).
    activate_stakes_for_scene(enc.scene, [pc_sheet])

    return enc


# ---------------------------------------------------------------------------
# Duel-end resolution (Task 7)
# ---------------------------------------------------------------------------


def _complete_duel(
    encounter: CombatEncounter,
    *,
    winner_sheet: CharacterSheet | None,
    outcome: EncounterOutcome,
) -> CombatEncounter:
    """Record the duel victor and route through the shared completion seam.

    ``duel_winner`` is persisted first so it is durable before
    ``complete_encounter`` flips status / fires aftermath / cleans up. The shared
    seam owns ``status=COMPLETED``, ``completed_at``, ``outcome``, broadcast, and
    cleanup — duels do not reimplement that tail.
    """
    encounter.duel_winner = winner_sheet
    encounter.save(update_fields=["duel_winner"])
    complete_encounter(encounter, outcome=outcome)
    return encounter


def resolve_duel_end(  # noqa: PLR0911 - distinct duel end conditions read clearest as guards
    encounter: CombatEncounter,
) -> CombatEncounter | None:
    """Complete a DUEL encounter if an end condition is met; else return None.

    Only acts on ``EncounterType.DUEL`` encounters that are not already COMPLETED.

    PvP (mirror surfaces present): a mirror ``CombatOpponent`` IS that PC's body.
    If a mirror is ``DEFEATED`` its mirrored participant is the LOSER and the OTHER
    participant is the WINNER (``duel_winner`` → winner's sheet, VICTORY).

    Lethal PC-vs-NPC (real, non-mirror opponent): if the opponent is ``DEFEATED``
    the PC wins (VICTORY); if the PC participant is down (``not can_act``) the NPC
    wins (``duel_winner`` stays null, DEFEAT). A still-fighting PC and a still-alive
    opponent means the duel is ongoing → None.

    Returns the completed encounter, or None if the duel has not ended.
    """
    if encounter.encounter_type != EncounterType.DUEL:
        return None
    if encounter.status == RoundStatus.COMPLETED:
        return None

    mirrors = list(
        CombatOpponent.objects.filter(
            encounter=encounter, mirrors_participant__isnull=False
        ).select_related("mirrors_participant__character_sheet")
    )

    if mirrors:
        # PvP: a DEFEATED mirror means its mirrored participant lost.
        defeated_mirror = next((m for m in mirrors if m.status == OpponentStatus.DEFEATED), None)
        if defeated_mirror is None:
            return None
        loser = defeated_mirror.mirrors_participant
        winner = (
            CombatParticipant.objects.filter(encounter=encounter)
            .exclude(pk=loser.pk)
            .select_related("character_sheet")
            .first()
        )
        winner_sheet = winner.character_sheet if winner is not None else None
        return _complete_duel(
            encounter, winner_sheet=winner_sheet, outcome=EncounterOutcome.VICTORY
        )

    # Lethal PC-vs-NPC: one real opponent, one PC participant.
    real_opponent = CombatOpponent.objects.filter(
        encounter=encounter, mirrors_participant__isnull=True
    ).first()
    pc = (
        CombatParticipant.objects.filter(encounter=encounter)
        .select_related("character_sheet__character")
        .first()
    )

    if real_opponent is not None and real_opponent.status == OpponentStatus.DEFEATED:
        winner_sheet = pc.character_sheet if pc is not None else None
        return _complete_duel(
            encounter, winner_sheet=winner_sheet, outcome=EncounterOutcome.VICTORY
        )

    if pc is not None and not can_act(pc.character_sheet):
        # PC is down → NPC wins; no PC duel_winner.
        return _complete_duel(encounter, winner_sheet=None, outcome=EncounterOutcome.DEFEAT)

    return None


def yield_duel(participant: CombatParticipant) -> CombatEncounter:
    """Yield the duel — the yielding participant LOSES.

    PvP: the OTHER participant becomes ``duel_winner`` (VICTORY for them). Lethal
    PC-vs-NPC: the NPC wins, so ``duel_winner`` stays null and the outcome is
    DEFEAT. Routes through the shared completion seam.
    """
    encounter = participant.encounter

    other = (
        CombatParticipant.objects.filter(encounter=encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is not None:
        # PvP yield: the other duelist wins.
        return _complete_duel(
            encounter, winner_sheet=other.character_sheet, outcome=EncounterOutcome.VICTORY
        )

    # Lethal yield: the NPC wins; no PC duel_winner.
    return _complete_duel(encounter, winner_sheet=None, outcome=EncounterOutcome.DEFEAT)


# ---------------------------------------------------------------------------
# Challenge transition services (Task 11)
# ---------------------------------------------------------------------------


@transaction.atomic
def accept_challenge(challenge: DuelChallenge) -> CombatEncounter:
    """Accept a PENDING duel challenge.

    Creates a PvP duel encounter (via ``create_pvp_duel``), links it to the
    challenge, transitions status to ACCEPTED, and stamps ``resolved_at``.

    Args:
        challenge: A DuelChallenge in PENDING status.

    Returns:
        The newly created CombatEncounter in DECLARING status.

    Raises:
        ValueError: If ``challenge.status`` is not PENDING.
    """
    if challenge.status != DuelChallengeStatus.PENDING:
        msg = f"Cannot accept a challenge in status {challenge.status!r}; must be PENDING."
        raise ValueError(msg)

    encounter = create_pvp_duel(
        challenge.challenger_sheet,
        challenge.challenged_sheet,
        challenge.room,
    )

    challenge.status = DuelChallengeStatus.ACCEPTED
    challenge.resolved_at = timezone.now()
    challenge.resulting_encounter = encounter
    challenge.save(update_fields=["status", "resolved_at", "resulting_encounter"])

    return encounter


@transaction.atomic
def decline_challenge(challenge: DuelChallenge) -> DuelChallenge:
    """Decline a PENDING duel challenge.

    Transitions the challenge to DECLINED and stamps ``resolved_at``.
    No encounter is created.

    Args:
        challenge: A DuelChallenge in PENDING status.

    Returns:
        The updated DuelChallenge instance.

    Raises:
        ValueError: If ``challenge.status`` is not PENDING.
    """
    if challenge.status != DuelChallengeStatus.PENDING:
        msg = f"Cannot decline a challenge in status {challenge.status!r}; must be PENDING."
        raise ValueError(msg)

    challenge.status = DuelChallengeStatus.DECLINED
    challenge.resolved_at = timezone.now()
    challenge.save(update_fields=["status", "resolved_at"])

    return challenge


@transaction.atomic
def withdraw_challenge(challenge: DuelChallenge) -> DuelChallenge:
    """Withdraw a PENDING duel challenge (challenger rescinds).

    Transitions the challenge to WITHDRAWN and stamps ``resolved_at``.
    No encounter is created.

    Args:
        challenge: A DuelChallenge in PENDING status.

    Returns:
        The updated DuelChallenge instance.

    Raises:
        ValueError: If ``challenge.status`` is not PENDING.
    """
    if challenge.status != DuelChallengeStatus.PENDING:
        msg = f"Cannot withdraw a challenge in status {challenge.status!r}; must be PENDING."
        raise ValueError(msg)

    challenge.status = DuelChallengeStatus.WITHDRAWN
    challenge.resolved_at = timezone.now()
    challenge.save(update_fields=["status", "resolved_at"])

    return challenge
