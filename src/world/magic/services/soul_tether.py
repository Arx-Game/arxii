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

from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.exceptions import (
    AffinityGateError,
    NoSoulTetherUnlockError,
    SineatingValidationError,
    SoulTetherFormationError,
)
from world.magic.models import CharacterThreadWeavingUnlock, Ritual
from world.magic.models.affinity import Resonance
from world.magic.services.threads import weave_thread
from world.magic.types.aura import AffinityType
from world.magic.types.soul_tether import (
    RescueOutcome,
    SineatingOffer,
    SineatingResult,
    SoulTetherRole as SoulTetherRoleEnum,
)
from world.relationships.models import CharacterRelationship, RelationshipCapstone

if TYPE_CHECKING:
    from world.magic.models import Thread

# =============================================================================
# Internal helpers
# =============================================================================

_MSG_SINEATER_GATE = "Sineater must be Celestial- or Primal-affinity primary."
_MSG_SINNER_GATE = "Sinner cannot be Celestial-affinity primary."
_MSG_DUPLICATE_TETHER = "An active Soul Tether already exists between these characters."
_MSG_NO_ACTIVE_TETHER = "No active Soul Tether exists between these characters."
_MSG_NOT_IN_SAME_SCENE = "Both characters must be in the same scene to perform Sineating."
_MSG_RESONANCE_NOT_ACCRUED = "Resonance specified is not one the Sinner accrues."
_MSG_PER_SCENE_CAP_REACHED = "Per-scene Sineating cap reached for this bond."


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


# =============================================================================
# Sineating helpers
# =============================================================================

#: Anima deducted per accepted unit (tunable — Phase 12 may adjust).
_ANIMA_COST_PER_UNIT: int = 2

#: Social fatigue added per accepted unit (tunable — Phase 12 may adjust).
_FATIGUE_COST_PER_UNIT: int = 1

#: Hard upper limit on units per scene (tunable baseline; formula below may lower it).
_PER_SCENE_CAP_HARD_MAX: int = 20


def _get_sinner_tether_thread(
    sinner_sheet: CharacterSheet,
    relationship: CharacterRelationship,
    resonance: Resonance,
) -> Thread | None:
    """Return the Sinner's RELATIONSHIP_CAPSTONE Thread for this bond + resonance, or None."""
    from world.magic.models import Thread  # noqa: PLC0415 — avoid circular at module level

    capstone = relationship.capstones.filter(
        relationship=relationship,
        is_ritual_capstone=True,
    ).first()
    if capstone is None:
        return None
    return Thread.objects.filter(
        owner=sinner_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone=capstone,
        resonance=resonance,
        retired_at__isnull=True,
    ).first()


def _compute_per_scene_sineating_cap(
    sinner_thread: Thread | None,
    relationship: CharacterRelationship,  # noqa: ARG001 — used for future formula tuning
) -> int:
    """Compute how many units can be Sineated in one scene.

    Formula (tunable — values are placeholders pending Phase 12 tuning):
        cap = min(_PER_SCENE_CAP_HARD_MAX, thread.level * 2 + 5)

    When no Sinner Thread exists the bond has no Hollow; cap is 0.
    The ``relationship`` parameter is accepted for future formula tuning
    (e.g., capping on ``developed_absolute_value``).

    Args:
        sinner_thread: The Sinner's RELATIONSHIP_CAPSTONE Thread for the bond
            in the relevant resonance, or None if absent.
        relationship: The active CharacterRelationship row (Sinner→Sineater
            direction). Accepted for future formula tuning.

    Returns:
        Maximum units that may be offered in one scene.
    """
    if sinner_thread is None:
        return 0
    return min(_PER_SCENE_CAP_HARD_MAX, sinner_thread.level * 2 + 5)


def _compute_hollow_max(sinner_thread: Thread) -> int:
    """Compute the Hollow's theoretical maximum for a given Thread.

    Placeholder formula (tunable — Phase 12 may adjust):
        hollow_max = thread.level * 10

    Args:
        sinner_thread: The Sinner's RELATIONSHIP_CAPSTONE Thread.

    Returns:
        The maximum number of units the Hollow can hold.
    """
    return max(0, sinner_thread.level * 10)


def _increment_stat_safe(
    character_sheet: CharacterSheet,
    stat_key: str,
    amount: int = 1,
) -> None:
    """Increment an achievement stat by key, no-op if StatDefinition not seeded yet.

    Phase 12 seeds StatDefinition rows for sineating.* stats.
    Until then this wrapper swallows DoesNotExist so the rest of the
    Sineating loop can proceed without the seed data.

    Args:
        character_sheet: The character whose stat to increment.
        stat_key: Dot-separated stat key (e.g., ``'sineating.units_accepted'``).
        amount: Amount to increment.
    """
    from world.achievements.models import StatDefinition  # noqa: PLC0415
    from world.achievements.services import increment_stat  # noqa: PLC0415

    try:
        stat_def = StatDefinition.objects.get(key=stat_key)
    except StatDefinition.DoesNotExist:
        return  # Phase 12 will seed the row; skip until then
    increment_stat(character_sheet, stat_def, amount)


# =============================================================================
# Public service: request_sineating
# =============================================================================


def request_sineating(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    resonance: Resonance,
    max_units: int,
    scene: Any,
) -> SineatingOffer:
    """Sinner-initiated Sineating request — validates gates and returns the offer (Spec B §7.2).

    Implementation note (Option B — synchronous path):
        The Spec describes firing a PROMPT_PLAYER Twisted Deferred to the
        Sineater. That mechanism is in-memory and process-local (see
        ``flows.execution.prompts``), which cannot survive service-layer unit
        tests without a running Twisted reactor. Phase 7 will wire the actual
        PROMPT_PLAYER step when the stage-advance handler is also being built.
        For now this function validates all prerequisites and returns the
        ``SineatingOffer`` payload directly. The caller (web API or @reply
        command) passes the offer to ``resolve_sineating``.

    Args:
        sinner_sheet: The character initiating the request (the Sinner).
        sineater_sheet: The character being asked to eat sins (the Sineater).
        resonance: The resonance to Sineat in. Must match a CharacterResonance
            row for the Sinner.
        max_units: How many units the Sinner is asking to have eaten.
        scene: The active Scene both characters are participating in. Pass
            ``None`` to represent "not in any scene" — the function will raise
            ``SineatingValidationError``.

    Returns:
        A frozen ``SineatingOffer`` dataclass describing the offer.

    Raises:
        SineatingValidationError: If any validation gate fails.
    """
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    # 1. Verify active tether between sinner and sineater (Sinner → Sineater direction).
    relationship: CharacterRelationship | None = CharacterRelationship.objects.filter(
        source=sinner_sheet,
        target=sineater_sheet,
        is_soul_tether=True,
    ).first()
    if relationship is None:
        raise SineatingValidationError(_MSG_NO_ACTIVE_TETHER)

    # 2. Both characters must be in the same scene.
    #    Scene is optional in the data model (audit row allows null) but mandatory
    #    for the Sineating action itself. ``None`` means "no active scene".
    if scene is None:
        raise SineatingValidationError(_MSG_NOT_IN_SAME_SCENE)
    # Both must have a SceneParticipation row in the same scene.
    if not _both_in_scene(sinner_sheet, sineater_sheet, scene):
        raise SineatingValidationError(_MSG_NOT_IN_SAME_SCENE)

    # 3. Resonance must be one the Sinner has a CharacterResonance row for.
    #    The Sinner can only be Sineated in resonances they actively accrue.
    sinner_has_resonance = CharacterResonance.objects.filter(
        character_sheet=sinner_sheet,
        resonance=resonance,
    ).exists()
    if not sinner_has_resonance:
        raise SineatingValidationError(_MSG_RESONANCE_NOT_ACCRUED)

    # 4. Look up the Sinner's RELATIONSHIP_CAPSTONE Thread for this bond + resonance.
    sinner_thread = _get_sinner_tether_thread(sinner_sheet, relationship, resonance)

    # 5. Compute per-scene cap.
    per_scene_cap = _compute_per_scene_sineating_cap(sinner_thread, relationship)
    if per_scene_cap == 0:
        raise SineatingValidationError(_MSG_PER_SCENE_CAP_REACHED)

    # 6. Clamp max_units to per-scene cap.
    max_units_offered = min(max_units, per_scene_cap)

    # 7. Compute current Hollow state.
    current_hollow = sinner_thread.hollow_current if sinner_thread is not None else 0
    hollow_max = _compute_hollow_max(sinner_thread) if sinner_thread is not None else 0

    # 8. Fire stat increment for "requests made" (no-op if StatDefinition not seeded).
    _increment_stat_safe(sinner_sheet, "sineating.requests_made", 1)

    return SineatingOffer(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        relationship=relationship,
        resonance=resonance,
        max_units_offered=max_units_offered,
        anima_cost_per_unit=_ANIMA_COST_PER_UNIT,
        fatigue_cost_per_unit=_FATIGUE_COST_PER_UNIT,
        current_hollow=current_hollow,
        hollow_max=hollow_max,
        sineater_current_strain_stage=0,  # TODO: Phase 6 — look up real Strain stage
    )


def _both_in_scene(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    scene: Any,
) -> bool:
    """Return True when both character sheets have active SceneParticipation rows in *scene*.

    Bridges CharacterSheet → RosterEntry → current RosterTenure → PlayerData → AccountDB.
    Returns False if either sheet has no active roster tenure (e.g., NPC without account).
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    def _account_id_for_sheet(sheet: CharacterSheet) -> int | None:
        try:
            entry = RosterEntry.objects.get(character_sheet_id=sheet.pk)
        except RosterEntry.DoesNotExist:
            return None
        tenure = entry.tenures.filter(end_date__isnull=True).first()
        if tenure is None:
            return None
        return tenure.player_data.account_id

    sinner_account_id = _account_id_for_sheet(sinner_sheet)
    sineater_account_id = _account_id_for_sheet(sineater_sheet)
    if sinner_account_id is None or sineater_account_id is None:
        return False
    # Both accounts must have a participation row — count equals the number of
    # participants we are checking (2 characters = 2 expected rows).
    _expected_participants = 2
    return (
        SceneParticipation.objects.filter(
            scene=scene, account_id__in=[sinner_account_id, sineater_account_id]
        ).count()
        == _expected_participants
    )


# =============================================================================
# Public service: resolve_sineating
# =============================================================================


def resolve_sineating(
    offer: SineatingOffer,
    units_accepted: int,
) -> SineatingResult:
    """Resolve a Sineating offer with the Sineater's chosen amount (Spec B §7.2).

    Implementation note (Option B — synchronous path):
        The signature differs from the spec stub (``prompt_id: str``) because
        this function accepts the ``SineatingOffer`` directly. Phase 7 will
        add a PROMPT_PLAYER wrapper that looks up the offer from the in-memory
        prompt registry and calls this function. The synchronous path is fully
        testable and represents the correct business logic regardless.

    Args:
        offer: The ``SineatingOffer`` returned by ``request_sineating``.
        units_accepted: How many units the Sineater accepts (0 = decline,
            positive = accept that many). Clamped to [0, max_units_offered].

    Returns:
        A frozen ``SineatingResult`` dataclass.
    """
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    # Clamp to valid range.
    units = max(0, min(units_accepted, offer.max_units_offered))
    declined = units == 0

    with transaction.atomic():
        anima_deducted = 0
        fatigue_deducted = 0
        new_hollow_current = offer.current_hollow
        new_lifetime_helped = 0

        if not declined:
            # 1. Deduct anima from Sineater.
            from world.magic.models import CharacterAnima  # noqa: PLC0415

            anima_cost = units * offer.anima_cost_per_unit
            try:
                anima_row = CharacterAnima.objects.select_for_update().get(
                    character=offer.sineater_sheet.character
                )
                anima_row.current = max(0, anima_row.current - anima_cost)
                anima_row.save(update_fields=["current"])
                anima_deducted = anima_cost
            except CharacterAnima.DoesNotExist:
                # Sineater has no anima row yet — skip deduction, log TODO.
                # TODO: Phase 12 — ensure CharacterAnima row is seeded at CG completion.
                pass

            # 2. Deduct social fatigue from Sineater.
            #    Sineating is a social/spiritual burden — social fatigue category.
            #    We add fatigue directly to the pool (fixed cost, no effort multiplier).
            from world.fatigue.models import FatiguePool  # noqa: PLC0415

            fatigue_cost = units * offer.fatigue_cost_per_unit
            try:
                pool = FatiguePool.objects.select_for_update().get(
                    character_sheet=offer.sineater_sheet
                )
                current_social = pool.get_current("social")
                pool.set_current("social", current_social + fatigue_cost)
                pool.save(update_fields=["social_current"])
                fatigue_deducted = fatigue_cost
            except FatiguePool.DoesNotExist:
                # Sineater has no fatigue pool yet — skip deduction, log TODO.
                # TODO: Phase 12 — ensure FatiguePool row is seeded at CG completion.
                pass

            # 3. Increment Sinner's Thread.hollow_current (clamp to hollow_max).
            sinner_thread = _get_sinner_tether_thread(
                offer.sinner_sheet, offer.relationship, offer.resonance
            )
            if sinner_thread is not None:
                hollow_max = _compute_hollow_max(sinner_thread)
                sinner_thread_locked = Thread.objects.select_for_update().get(pk=sinner_thread.pk)
                sinner_thread_locked.hollow_current = min(
                    hollow_max, sinner_thread_locked.hollow_current + units
                )
                sinner_thread_locked.save(update_fields=["hollow_current"])
                new_hollow_current = sinner_thread_locked.hollow_current

            # 4. Increment Sineater's CharacterResonance.lifetime_helped.
            #    Lazy-create the CharacterResonance row if absent.
            cr, _ = CharacterResonance.objects.select_for_update().get_or_create(
                character_sheet=offer.sineater_sheet,
                resonance=offer.resonance,
            )
            cr.lifetime_helped = cr.lifetime_helped + units
            cr.save(update_fields=["lifetime_helped"])
            new_lifetime_helped = cr.lifetime_helped

        # 5. Write Sineating audit row (always — including declines).
        from world.magic.models import Sineating  # noqa: PLC0415

        audit_row = Sineating.objects.create(
            sinner_sheet=offer.sinner_sheet,
            sineater_sheet=offer.sineater_sheet,
            relationship=offer.relationship,
            scene=None,  # TODO: Phase 7 — pass scene through offer payload
            resonance=offer.resonance,
            units_offered=offer.max_units_offered,
            units_accepted=units,
            anima_cost=anima_deducted,
            fatigue_cost=fatigue_deducted,
        )

    # 6. Fire stat increments (outside transaction — safe to no-op if rows absent).
    if not declined:
        _increment_stat_safe(offer.sineater_sheet, "sineating.units_accepted", units)
    else:
        _increment_stat_safe(offer.sineater_sheet, "sineating.units_declined", 1)

    return SineatingResult(
        audit_row=audit_row,
        units_accepted=units,
        declined=declined,
        new_hollow_current=new_hollow_current,
        new_lifetime_helped=new_lifetime_helped,
    )


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
