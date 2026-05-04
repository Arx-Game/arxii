"""Soul Tether services (Spec B §16).

Public functions:
- accept_soul_tether: formation Ritual Capstone (§12).
- dissolve_soul_tether: stub dissolution (§13).
- request_sineating: Sinner asks (§7).
- resolve_sineating: Sineater @reply resolution (§7).
- perform_soul_tether_rescue: stage-3+ rescue ritual (§9).

Reactive subscribers (registered as TriggerDefinition rows backed by
FlowDefinition + SERVICE step):
- soul_tether_redirect_handler: drains Hollow on CORRUPTION_ACCRUING (§5).
- soul_tether_stage_advance_prompt: fires PROMPT_PLAYER on
  CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (§8).
- resolve_stage_advance_prompt: Sineater @reply resolution for the
  stage-advance prompt (§8).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.exceptions import (
    AffinityGateError,
    NoSoulTetherUnlockError,
    SoulTetherFormationError,
)
from world.magic.models import CharacterThreadWeavingUnlock, Ritual
from world.magic.models.affinity import Resonance
from world.magic.services.threads import weave_thread
from world.magic.types.aura import AffinityType
from world.magic.types.soul_tether import (
    RescueOutcome,
    SineatingResult,
    SoulTetherRole as SoulTetherRoleEnum,
)
from world.relationships.models import CharacterRelationship, RelationshipCapstone

# =============================================================================
# Internal helpers
# =============================================================================

_MSG_SINEATER_GATE = "Sineater must be Celestial- or Primal-affinity primary."
_MSG_SINNER_GATE = "Sinner cannot be Celestial-affinity primary."
_MSG_DUPLICATE_TETHER = "An active Soul Tether already exists between these characters."


def _resolve_primary_affinity(sheet: CharacterSheet) -> str:
    """Return the AffinityType value of the sheet's dominant affinity.

    Reads CharacterAura.dominant_affinity via sheet.character (ObjectDB).
    Returns one of AffinityType.CELESTIAL / .PRIMAL / .ABYSSAL (lowercase values).

    Raises AttributeError if the character has no CharacterAura row.
    """
    aura = sheet.character.aura  # OneToOne: ObjectDB → CharacterAura
    return aura.dominant_affinity


def _validate_affinity_gates(sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet) -> None:
    """Enforce Spec B §3 affinity gates.

    - Sineater must NOT be Abyssal-primary.
    - Sinner must NOT be Celestial-primary.

    Raises:
        AffinityGateError: If either gate fails.
    """
    sinner_primary = _resolve_primary_affinity(sinner_sheet)
    sineater_primary = _resolve_primary_affinity(sineater_sheet)

    if sineater_primary == AffinityType.ABYSSAL:
        raise AffinityGateError(_MSG_SINEATER_GATE)
    if sinner_primary == AffinityType.CELESTIAL:
        raise AffinityGateError(_MSG_SINNER_GATE)


def _validate_unlock(sinner_sheet: CharacterSheet) -> None:
    """Verify the Sinner has a RELATIONSHIP_TRACK ThreadWeavingUnlock.

    RELATIONSHIP_CAPSTONE thread weaving inherits from RELATIONSHIP_TRACK
    unlocks (ThreadWeavingUnlock has no CAPSTONE kind — see model constraint
    "threadweaving_no_capstone"). A Sinner who has any RELATIONSHIP_TRACK
    CharacterThreadWeavingUnlock has the prerequisite needed to weave a
    RELATIONSHIP_CAPSTONE Thread.

    The per-track specificity check happens inside weave_thread(); this gate
    is the coarse "has the player bought into this unlock kind at all" check.

    Raises:
        NoSoulTetherUnlockError: If the Sinner has no RELATIONSHIP_TRACK unlock.
    """
    has_unlock = CharacterThreadWeavingUnlock.objects.filter(
        character=sinner_sheet,
        unlock__target_kind=TargetKind.RELATIONSHIP_TRACK,
    ).exists()
    if not has_unlock:
        raise NoSoulTetherUnlockError


def _get_or_create_relationship(
    source: CharacterSheet,
    target: CharacterSheet,
) -> CharacterRelationship:
    """Get or create a CharacterRelationship row from source to target."""
    rel, _ = CharacterRelationship.objects.get_or_create(
        source=source,
        target=target,
    )
    return rel


# =============================================================================
# Public service: accept_soul_tether
# =============================================================================


def accept_soul_tether(  # noqa: PLR0913
    initiator_sheet: CharacterSheet,
    partner_sheet: CharacterSheet,
    sinner_role: SoulTetherRoleEnum,
    resonance: Resonance,
    writeup: str,
    ritual_components: list[Any],  # noqa: ARG001 — consumed by caller; validated pre-call
) -> RelationshipCapstone:
    """Form a Soul Tether bond (Spec B §12.4).

    Either the initiator or the partner is the Sinner; sinner_role determines
    which. The Sinner must be the one who is Abyssal- (or Primal-) primary and
    who holds the RELATIONSHIP_CAPSTONE Thread that carries the Hollow.

    Args:
        initiator_sheet: The character sheet of the person initiating the ritual.
        partner_sheet: The character sheet of the other party.
        sinner_role: Which role the INITIATOR has. If ABYSSAL, initiator is the
            Sinner. If SINEATER, initiator is the Sineater (partner is Sinner).
        resonance: The Resonance the Sinner's Thread will channel.
        writeup: Narrative description of the bond's formation.
        ritual_components: Items consumed by the ritual (validated by caller).

    Returns:
        The RelationshipCapstone created for this ritual formation event.

    Raises:
        AffinityGateError: Sineater is Abyssal-primary or Sinner is Celestial-primary.
        NoSoulTetherUnlockError: Sinner lacks a RELATIONSHIP_TRACK ThreadWeavingUnlock.
        SoulTetherFormationError: A Soul Tether already exists between these characters.
    """
    # 1. Determine Sinner/Sineater from sinner_role.
    if sinner_role == SoulTetherRoleEnum.ABYSSAL:
        sinner_sheet, sineater_sheet = initiator_sheet, partner_sheet
    else:
        sinner_sheet, sineater_sheet = partner_sheet, initiator_sheet

    # 2. Validate affinity gates (§3).
    _validate_affinity_gates(sinner_sheet, sineater_sheet)

    # 3. Validate Sinner has a RELATIONSHIP_TRACK ThreadWeavingUnlock (§12.4).
    _validate_unlock(sinner_sheet)

    with transaction.atomic():
        # 4. Get-or-create both directional CharacterRelationship rows.
        rel_outgoing = _get_or_create_relationship(source=sinner_sheet, target=sineater_sheet)
        rel_incoming = _get_or_create_relationship(source=sineater_sheet, target=sinner_sheet)

        # Lock both rows to prevent concurrent formation requests from duplicating state.
        # Two concurrent transactions could both pass the idempotency check if it runs
        # outside the atomic block; select_for_update() ensures only one can proceed.
        rel_outgoing = CharacterRelationship.objects.select_for_update().get(pk=rel_outgoing.pk)
        rel_incoming = CharacterRelationship.objects.select_for_update().get(pk=rel_incoming.pk)

        # 5. Idempotency check — raise if either direction is already a Soul Tether.
        if rel_outgoing.is_soul_tether or rel_incoming.is_soul_tether:
            raise SoulTetherFormationError(_MSG_DUPLICATE_TETHER)

        # 6. Locate the accept_soul_tether Ritual row (seeded by wire_soul_tether_content).
        ritual = Ritual.objects.get(name="accept_soul_tether")

        # 7. Determine a default relationship track for the capstone.
        #    We use the Sinner's first RELATIONSHIP_TRACK unlock's track so
        #    that weave_thread's unlock-check passes for this specific capstone.
        unlock_row = (
            CharacterThreadWeavingUnlock.objects.filter(
                character=sinner_sheet,
                unlock__target_kind=TargetKind.RELATIONSHIP_TRACK,
            )
            .select_related("unlock__unlock_track")
            .first()
        )
        # unlock_row is guaranteed non-None because _validate_unlock passed.
        assert unlock_row is not None  # noqa: S101  # type narrowing for mypy
        capstone_track = unlock_row.unlock.unlock_track

        # 8. Create the RelationshipCapstone (the ritual formation event).
        capstone = RelationshipCapstone.objects.create(
            relationship=rel_outgoing,
            author=sinner_sheet,
            title="Soul Tether Formation",
            writeup=writeup,
            track=capstone_track,
            points=0,  # Formation capstones grant no points; power comes from the Thread.
            is_ritual_capstone=True,
            ritual=ritual,
        )

        # 9. Flag both directional relationship rows.
        rel_outgoing.is_soul_tether = True
        rel_outgoing.soul_tether_role = SoulTetherRole.ABYSSAL
        rel_outgoing.save(update_fields=["is_soul_tether", "soul_tether_role"])

        rel_incoming.is_soul_tether = True
        rel_incoming.soul_tether_role = SoulTetherRole.SINEATER
        rel_incoming.save(update_fields=["is_soul_tether", "soul_tether_role"])

        # 10. Weave the Sinner's RELATIONSHIP_CAPSTONE Thread (§4.1).
        #     weave_thread validates the unlock again internally; if the track
        #     mismatch causes WeavingUnlockMissing, let it propagate.
        weave_thread(
            character_sheet=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target=capstone,
            resonance=resonance,
            name="Soul Tether Hollow",
            description=(
                f"The hollow woven between {sinner_sheet} and {sineater_sheet}. "
                "Absorbs corruption before it reaches the Sinner's soul."
            ),
        )

        # 11. Install the SoulTetherActive ConditionInstance on the Sinner if absent.
        #     Multiple tethers reuse the single ConditionInstance (no duplicate).
        active_template = ConditionTemplate.objects.get(name="Soul Tether Active")
        active_condition = ConditionInstance.objects.filter(
            target=sinner_sheet.character,
            condition=active_template,
        ).first()
        if active_condition is None:
            active_condition = ConditionInstance.objects.create(
                target=sinner_sheet.character,
                condition=active_template,
                stacks=1,
                severity=1,
                source_description="Soul Tether bond active",
            )

            # 12. Install the 2 Trigger rows (only on first tether; later tethers reuse them).
            _install_soul_tether_triggers(sinner_sheet, active_condition)

    return capstone


def _install_soul_tether_triggers(
    sinner_sheet: CharacterSheet,
    active_condition: ConditionInstance,
) -> None:
    """Install the two reactive Trigger rows on the Sinner's ObjectDB.

    Called only the first time a Sinner forms a tether (when the
    SoulTetherActiveTemplate ConditionInstance is first created). Later
    tethers reuse the existing Triggers.

    Raises:
        flows.models.triggers.TriggerDefinition.DoesNotExist: if Phase 3
            content has not been seeded. In production this is always seeded;
            in tests, call wire_soul_tether_content() first.
    """
    from flows.models.triggers import Trigger, TriggerDefinition  # noqa: PLC0415

    sinner_objectdb = sinner_sheet.character
    for definition_name in (
        "soul_tether_redirect",
        "soul_tether_stage_advance_prompt",
    ):
        trigger_def = TriggerDefinition.objects.get(name=definition_name)
        trigger = Trigger.objects.create(
            obj=sinner_objectdb,
            trigger_definition=trigger_def,
            source_condition=active_condition,
        )
        # Invalidate the in-memory TriggerHandler cache so it picks up the new row.
        trigger_handler = getattr(sinner_objectdb, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if trigger_handler is not None:
            trigger_handler.on_trigger_added(trigger)


# =============================================================================
# Stub functions (later phases)
# =============================================================================


def dissolve_soul_tether(
    relationship_id: int,
    initiator_sheet: CharacterSheet,
) -> None:
    """Dissolve a Soul Tether — MVP stub (Spec B §13)."""
    raise NotImplementedError


def request_sineating(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    resonance: Resonance,
    max_units: int,
    scene: Any,
) -> str:
    """Sinner-initiated Sineating request — fires PROMPT_PLAYER, returns prompt id (Spec B §7.2)."""
    raise NotImplementedError


def resolve_sineating(
    prompt_id: str,
    units_accepted: int,
) -> SineatingResult:
    """Resolve a Sineating prompt with the Sineater's chosen amount (Spec B §7.2)."""
    raise NotImplementedError


def perform_soul_tether_rescue(
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
    components: list[Any],
) -> RescueOutcome:
    """Perform a stage-3+ rescue ritual (Spec B §9.4)."""
    raise NotImplementedError


def soul_tether_redirect_handler(payload: Any) -> None:
    """Subscriber for CORRUPTION_ACCRUING — drains Hollow, cancels event (Spec B §5.2)."""
    raise NotImplementedError


def soul_tether_stage_advance_prompt(payload: Any) -> None:
    """Subscriber for CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (Spec B §8.1)."""
    raise NotImplementedError


def resolve_stage_advance_prompt(
    prompt_id: str,
    units_committed: int,
) -> None:
    """Resolve the stage-advance bonus prompt with the Sineater's commitment (Spec B §8.1)."""
    raise NotImplementedError
