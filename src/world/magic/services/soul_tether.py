"""Soul Tether services (Spec B §16).

Public functions:
- accept_soul_tether: formation Ritual Capstone (§12).
- dissolve_soul_tether: stub dissolution (§13).
- (Sineating itself lives in ``services/sineating.py``, #5177.)
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

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from flows.constants import EventName
from flows.emit import emit_event
from world.character_sheets.models import CharacterSheet
from world.checks.constants import ModifierLane
from world.checks.modifier_values import level_baseline
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.constants import MagicActivity, SoulTetherRole, TargetKind
from world.magic.exceptions import (
    AffinityGateError,
    NoSoulTetherUnlockError,
    RescueValidationError,
    SineaterFallenError,
    SoulTetherFormationError,
    StageAdvanceBonusError,
)
from world.magic.models import CharacterThreadWeavingUnlock, Ritual
from world.magic.models.affinity import Affinity, Resonance
from world.magic.models.soul_tether_config import SoulTetherConfig
from world.magic.services.aura import ensure_aura
from world.magic.services.threads import thread_rung, weave_tether_bond_thread, weave_thread
from world.magic.types.corruption import CorruptionSource
from world.magic.types.soul_tether import (
    RescueOutcome,
    SoulTetherDissolvedPayload,
    SoulTetherRole as SoulTetherRoleEnum,
    StageAdvanceBonusOffer,
    StageAdvanceBonusResult,
)
from world.relationships.models import CharacterRelationship, RelationshipCapstone
from world.roster.services.npc_lending import played_by_one_account

if TYPE_CHECKING:
    from world.magic.models import Thread

logger = logging.getLogger(__name__)

# =============================================================================
# Config getter
# =============================================================================


def get_soul_tether_config() -> SoulTetherConfig:
    """Get-or-create the Soul Tether tuning config singleton (pk=1)."""
    with transaction.atomic():
        cfg = SoulTetherConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = SoulTetherConfig.objects.get_or_create(pk=1)
    return cfg


# =============================================================================
# Internal helpers
# =============================================================================

_MSG_SINEATER_GATE = "Sineater must be Celestial- or Primal-affinity primary."
_MSG_SINNER_GATE = "Sinner cannot be Celestial-affinity primary."
_MSG_DUPLICATE_TETHER = "An active Soul Tether already exists between these characters."
_MSG_NO_ACTIVE_TETHER = "No active Soul Tether exists between these characters."
_MSG_ONE_PLAYER_TETHER = "You cannot form a Soul Tether between two characters you play."
_MSG_NOT_IN_SAME_SCENE = "Both characters must be in the same scene to perform Sineating."
_MSG_RESONANCE_NOT_ACCRUED = "Resonance specified is not one the Sinner accrues."
_MSG_PER_SCENE_CAP_REACHED = "Per-scene Sineating cap reached for this bond."


def _resolve_primary_affinity(sheet: CharacterSheet) -> Affinity | None:
    """Return the sheet's dominant Affinity row.

    Reads CharacterAura.dominant_affinity via sheet.character (ObjectDB). An aura that
    holds no shares yet has no primary affinity (None), which matches neither gate.

    Raises AttributeError if the character has no CharacterAura row.
    """
    aura = sheet.character.aura  # OneToOne: ObjectDB → CharacterAura
    if not aura.cached_shares:
        return None
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

    if sineater_primary is not None and sineater_primary.pk == (
        Affinity.objects.get_abyssal_affinity().pk
    ):
        raise AffinityGateError(_MSG_SINEATER_GATE)
    if sinner_primary is not None and sinner_primary.pk == (
        Affinity.objects.get_celestial_affinity().pk
    ):
        raise AffinityGateError(_MSG_SINNER_GATE)


def sineater_has_fallen(sineater_sheet: CharacterSheet) -> bool:
    """True when the Sineater's aura is predominantly Abyssal (#5177).

    A fallen Sineater can carry no one's sins until they are predominantly something else.
    A sheet with no aura, or an aura with no shares yet, has not fallen.
    """
    aura = sineater_sheet.aura_or_none
    if aura is None or not aura.cached_shares:
        return False
    return aura.dominant_affinity.pk == Affinity.objects.get_abyssal_affinity().pk


def _refuse_fallen_sineater(sineater_sheet: CharacterSheet) -> None:
    """Raise ``SineaterFallenError`` when the Sineater has fallen."""
    if sineater_has_fallen(sineater_sheet):
        raise SineaterFallenError(sineater_sheet.primary_persona.name)


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


def accept_soul_tether(  # noqa: PLR0913 - the pair, the role, two resonances and components
    initiator_sheet: CharacterSheet,
    partner_sheet: CharacterSheet,
    sinner_role: SoulTetherRoleEnum,
    resonance: Resonance,
    ritual_components: list[Any],  # noqa: ARG001
    sineater_resonance: Resonance | None = None,
) -> RelationshipCapstone:
    """Form a Soul Tether bond (Spec B §12.4).

    Either the initiator or the partner is the Sinner; sinner_role determines
    which. The Sinner must be the one who is Abyssal- (or Primal-) primary and
    who holds the RELATIONSHIP_CAPSTONE Thread that carries the Hollow.

    Args:
        initiator_sheet: The character sheet of the person initiating the ritual.
        partner_sheet: The character sheet of the other party.
        sinner_role: Which role the INITIATOR has. If SINNER, initiator is the
            Sinner. If SINEATER, initiator is the Sineater (partner is Sinner).
        resonance: The Resonance the Sinner's Thread will channel.
        ritual_components: Items consumed by the ritual (validated by caller).
        sineater_resonance: The Resonance the Sineater's own Thread will channel (#5177).
            Defaults to the Sineater's strongest resonance of their main affinity (see
            ``default_sineater_resonance``); when they hold none the thread is left unwoven.

    Returns:
        The RelationshipCapstone created for this ritual formation event (the Sinner's
        side; the Sineater's thread sits on a capstone of their own side).

    Raises:
        AffinityGateError: Sineater is Abyssal-primary or Sinner is Celestial-primary.
        NoSoulTetherUnlockError: Sinner lacks a RELATIONSHIP_TRACK ThreadWeavingUnlock.
        SoulTetherFormationError: A Soul Tether already exists between these characters.
    """
    # 1. Determine Sinner/Sineater from sinner_role.
    if sinner_role == SoulTetherRoleEnum.SINNER:
        sinner_sheet, sineater_sheet = initiator_sheet, partner_sheet
    else:
        sinner_sheet, sineater_sheet = partner_sheet, initiator_sheet

    # 1b. One person on both sides could ask as one and perform as the other.
    if played_by_one_account(sinner_sheet, sineater_sheet):
        raise SoulTetherFormationError(_MSG_ONE_PLAYER_TETHER)

    # 2. Validate affinity gates (§3). A sheet with no aura (a minted story NPC) gets an
    #    empty one first; an aura with no shares passes both gates.
    ensure_aura(sinner_sheet)
    ensure_aura(sineater_sheet)
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

        # 7. Create the RelationshipCapstone (the ritual formation event) — a receipt,
        #    not authored content (#3957). No track/points/author/writeup/title fields
        #    exist anymore; the Thread woven in step 9 carries the mechanical power.
        capstone = RelationshipCapstone.objects.create(
            relationship=rel_outgoing,
            tier_claimed=rel_outgoing.tier,
            xp_spent=0,
            is_ritual_capstone=True,
            ritual=ritual,
        )

        # 8. Flag both directional relationship rows.
        rel_outgoing.is_soul_tether = True
        rel_outgoing.soul_tether_role = SoulTetherRole.SINNER
        rel_outgoing.save(update_fields=["is_soul_tether", "soul_tether_role"])

        rel_incoming.is_soul_tether = True
        rel_incoming.soul_tether_role = SoulTetherRole.SINEATER
        rel_incoming.save(update_fields=["is_soul_tether", "soul_tether_role"])

        # 9. Weave the Sinner's RELATIONSHIP_CAPSTONE Thread (§4.1).
        #    weave_thread validates the unlock again internally (coarse "any
        #    RELATIONSHIP_TRACK unlock" check, #3957); let a raise propagate.
        weave_thread(
            character_sheet=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target=capstone,
            resonance=resonance,
            name="Soul Tether Hollow",
            description=(
                f"The hollow woven between {sinner_sheet.primary_persona.name} and "
                f"{sineater_sheet.primary_persona.name}. "
                "Absorbs corruption before it reaches the Sinner's soul."
            ),
        )

        # 9b. Weave the Sineater's half of the bond (#5177). It sits on a ritual capstone of
        #     the Sineater's own side, the only anchor their weave can own.
        _weave_sineater_thread(
            rel_incoming,
            resonance=sineater_resonance or default_sineater_resonance(sineater_sheet),
            ritual=ritual,
            fresh_capstone=True,
        )

        # 10. Install the SoulTetherActive ConditionInstance on the Sinner if absent.
        #     Multiple tethers reuse the single ConditionInstance (no duplicate).
        active_template = ConditionTemplate.get_by_name("Soul Tether Active")
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

            # 11. Install the 2 Trigger rows (only on first tether; later tethers reuse them).
            _install_soul_tether_triggers(sinner_sheet, active_condition)

        # 12. Fire achievement stat increment for tether.formed (Spec B §14.3).
        _increment_stat_safe(sinner_sheet, "tether.formed", 1)

    return capstone


def default_sineater_resonance(sineater_sheet: CharacterSheet) -> Resonance | None:
    """The resonance a Sineater's thread channels when they name none (#5177).

    Their strongest resonance of their main affinity (the most lifetime earned), else the
    strongest they hold of any affinity, else None. A resonance is never invented.
    """
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415
    from world.magic.services.drift_correction import main_affinity_rows  # noqa: PLC0415

    main_rows = main_affinity_rows(sineater_sheet)
    if main_rows:
        return main_rows[0].resonance
    row = (
        CharacterResonance.objects.filter(character_sheet=sineater_sheet)
        .select_related("resonance")
        .order_by("-lifetime_earned", "resonance_id")
        .first()
    )
    return row.resonance if row is not None else None


def _live_sineater_thread(rel_incoming: CharacterRelationship) -> Thread | None:
    """The Sineater's live RELATIONSHIP_CAPSTONE thread on their own side of a tether."""
    from world.magic.models import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner_id=rel_incoming.source_id,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone__relationship=rel_incoming,
        target_capstone__is_ritual_capstone=True,
        retired_at__isnull=True,
    ).first()


def _weave_sineater_thread(
    rel_incoming: CharacterRelationship,
    *,
    resonance: Resonance | None,
    ritual: Ritual | None,
    fresh_capstone: bool,
) -> Thread | None:
    """Weave the Sineater's thread on a ritual capstone of their own side.

    A formation passes ``fresh_capstone=True``: every formation is its own event, so it gets a
    capstone of its own, as the Sinner's side does (the capstone lookups read the newest). The
    backfill for a tether that has none passes False and reuses a capstone already there.
    None when there is no resonance to channel.
    """
    if resonance is None:
        return None
    capstone = (
        None if fresh_capstone else rel_incoming.capstones.filter(is_ritual_capstone=True).first()
    )
    if capstone is None:
        capstone = RelationshipCapstone.objects.create(
            relationship=rel_incoming,
            tier_claimed=rel_incoming.tier,
            xp_spent=0,
            is_ritual_capstone=True,
            ritual=ritual,
        )
    return weave_tether_bond_thread(
        rel_incoming.source,
        capstone,
        resonance,
        name="Soul Tether Burden",
        description=(
            f"The burden {rel_incoming.source.primary_persona.name} carries for "
            f"{rel_incoming.target.primary_persona.name}. "
            "Softens the corruption a Sineater takes on."
        ),
    )


def ensure_sineater_thread(
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance | None = None,
) -> Thread | None:
    """The Sineater's live thread on their tether with this Sinner, weaving it when absent.

    Tethers formed before #5177 have none. The thread channels ``resonance`` when given,
    else ``default_sineater_resonance``; with neither (the Sineater holds no resonance)
    nothing is woven and None comes back. An existing thread is returned as it is.

    Raises:
        SoulTetherFormationError: no active tether runs from this Sineater to this Sinner.
    """
    with transaction.atomic():
        rel_incoming = (
            CharacterRelationship.objects.select_for_update()
            .select_related("source", "target")
            .filter(
                source=sineater_sheet,
                target=sinner_sheet,
                is_soul_tether=True,
                soul_tether_role=SoulTetherRole.SINEATER,
            )
            .first()
        )
        if rel_incoming is None:
            raise SoulTetherFormationError(_MSG_NO_ACTIVE_TETHER)
        existing = _live_sineater_thread(rel_incoming)
        if existing is not None:
            return existing
        return _weave_sineater_thread(
            rel_incoming,
            resonance=resonance or default_sineater_resonance(sineater_sheet),
            ritual=Ritual.objects.filter(name="accept_soul_tether").first(),
            fresh_capstone=False,
        )


def _install_soul_tether_triggers(
    sinner_sheet: CharacterSheet,
    active_condition: ConditionInstance,
) -> None:
    """Install the two reactive Trigger rows on the Sinner's ObjectDB.

    Called only the first time a Sinner forms a tether (when the
    SoulTetherActiveTemplate ConditionInstance is first created). Later
    tethers reuse the existing Triggers.

    ``flows.TriggerDefinition`` is content-repo-owned (#2698) — seeded by
    ``wire_soul_tether_active_template()`` via ``authored_or_sample()``, which
    returns ``None`` (after logging) when the row isn't authored and
    ``SEED_SAMPLE_CONTENT`` is off. Formerly this looked the definition up with
    ``.get()`` and let a missing row raise ``DoesNotExist`` — now it skips that
    one Trigger (with a warning) rather than crashing tether formation; a
    partially-wired tether (missing the redirect and/or stage-advance
    subscriber) is a real degraded state, not silently papered over.
    """
    from flows.models.triggers import Trigger, TriggerDefinition  # noqa: PLC0415

    sinner_objectdb = sinner_sheet.character
    for definition_name in (
        "soul_tether_redirect",
        "soul_tether_stage_advance_prompt",
    ):
        trigger_def = TriggerDefinition.objects.filter(name=definition_name).first()
        if trigger_def is None:
            logger.warning(
                "TriggerDefinition %r not seeded; Soul Tether formed without this "
                "reactive subscriber (author it in the content repo, or set "
                "ARXII_SEED_SAMPLE_CONTENT=1 — see #2698).",
                definition_name,
            )
            continue
        trigger = Trigger.objects.create(
            obj=sinner_objectdb,
            trigger_definition=trigger_def,
            source_condition=active_condition,
        )
        # Invalidate the in-memory TriggerHandler cache so it picks up the new row.
        trigger_handler = sinner_objectdb.trigger_handler
        if trigger_handler is not None:
            trigger_handler.on_trigger_added(trigger)


# =============================================================================
# Stub functions (later phases)
# =============================================================================


def _sinner_has_other_active_tethers(
    sinner_sheet: CharacterSheet,
    exclude_outgoing_id: int,
) -> bool:
    """Return True if the Sinner has active tethers besides the one being dissolved.

    Args:
        sinner_sheet: The Sinner's CharacterSheet.
        exclude_outgoing_id: Primary key of the Sinner→Sineater relationship row
            that is being dissolved, so it is excluded from the check.

    Returns:
        True when at least one other active tether remains.
    """
    return (
        CharacterRelationship.objects.filter(
            source=sinner_sheet,
            is_soul_tether=True,
            soul_tether_role=SoulTetherRole.SINNER,
        )
        .exclude(pk=exclude_outgoing_id)
        .exists()
    )


def dissolve_soul_tether(
    relationship_id: int,
    initiator_sheet: CharacterSheet,  # noqa: ARG001
) -> None:
    """Dissolve a Soul Tether — MVP stub (Spec B §13).

    Flips ``is_soul_tether=False`` and clears roles on both directional
    CharacterRelationship rows, soft-retires all RELATIONSHIP_CAPSTONE Threads
    anchored to ritual capstones on this relationship, and removes the
    SoulTetherActive ConditionInstance from the Sinner only when no other
    active tethers remain (Trigger rows cascade-delete via the FK).

    Args:
        relationship_id: Primary key of *either* directional relationship row.
            The function finds the outgoing (Sinner→Sineater, role=SINNER)
            direction automatically.
        initiator_sheet: The CharacterSheet initiating dissolution. Reserved
            for future permission/validation logic; not currently validated
            against allowed initiators.

    Notes:
        - Idempotent: if the tether is already dissolved, returns immediately.
        - ``lifetime_helped`` on the Sineater's CharacterResonance is NOT
          cleared — it persists as a permanent record of the bond per §13.
        - Strain ConditionInstance on the Sineater is NOT cleared — it decays
          naturally via ``passive_decay_per_day`` (§6, §11).
        - Sineating and SoulTetherRescue audit rows are NOT deleted — they are
          permanent historical records.
        - Trigger rows for the two reactive subscribers cascade-delete with the
          SoulTetherActive ConditionInstance (``source_condition`` FK has
          ``on_delete=CASCADE``); no manual Trigger cleanup is needed.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.magic.models import Thread  # noqa: PLC0415

    # Resolve the outgoing (Sinner→Sineater, SINNER) row.  The caller may pass
    # either direction's ID; we determine which is which from soul_tether_role.
    raw = CharacterRelationship.objects.get(pk=relationship_id)

    if raw.soul_tether_role == SoulTetherRole.SINNER:
        # Passed the outgoing (Sinner→Sineater) row.
        outgoing = raw
        incoming = CharacterRelationship.objects.get(
            source=raw.target,
            target=raw.source,
        )
    else:
        # Passed the incoming (Sineater→Sinner, SINEATER) row.
        incoming = raw
        outgoing = CharacterRelationship.objects.get(
            source=raw.target,
            target=raw.source,
        )

    dissolved_sinner_sheet: CharacterSheet | None = None
    dissolved_sineater_sheet: CharacterSheet | None = None
    dissolved_relationship: CharacterRelationship | None = None

    with transaction.atomic():
        # Re-fetch with locks to prevent races.
        outgoing = CharacterRelationship.objects.select_for_update().get(pk=outgoing.pk)
        incoming = CharacterRelationship.objects.select_for_update().get(pk=incoming.pk)

        # Idempotent: already dissolved.
        if not outgoing.is_soul_tether:
            return

        # The Sinner is the source of the outgoing (SINNER) row; Sineater is the target.
        sinner_sheet: CharacterSheet = outgoing.source
        sineater_sheet: CharacterSheet = outgoing.target

        # Capture for post-atomic emit.
        dissolved_sinner_sheet = sinner_sheet
        dissolved_sineater_sheet = sineater_sheet
        dissolved_relationship = outgoing

        # 1. Flip flags on both directional rows.
        for rel in (outgoing, incoming):
            rel.is_soul_tether = False
            rel.soul_tether_role = ""
            rel.save(update_fields=["is_soul_tether", "soul_tether_role"])

        # 2. Soft-retire all RELATIONSHIP_CAPSTONE Threads anchored to ritual
        #    capstones on either directional row.
        #    Materialize capstone IDs to avoid nested-subquery issues with some
        #    PostgreSQL query planners when __in receives a lazy queryset.
        ritual_capstone_ids = list(
            RelationshipCapstone.objects.filter(
                relationship_id__in=[outgoing.pk, incoming.pk],
                is_ritual_capstone=True,
            ).values_list("pk", flat=True)
        )
        if ritual_capstone_ids:
            Thread.objects.filter(
                target_capstone_id__in=ritual_capstone_ids,
                retired_at__isnull=True,
            ).update_with_reason(
                reason="issue #3817: intentional atomic write",
                retired_at=timezone.now(),
            )

        # 3. Remove the SoulTetherActive ConditionInstance from the Sinner only
        #    if no other tethers remain.  Trigger rows cascade-delete automatically
        #    because Trigger.source_condition has on_delete=CASCADE.
        if not _sinner_has_other_active_tethers(sinner_sheet, exclude_outgoing_id=outgoing.pk):
            from world.conditions.models import ConditionInstance  # noqa: PLC0415

            ConditionInstance.objects.filter(
                target=sinner_sheet.character,
                condition__name="Soul Tether Active",
            ).delete()

            # Invalidate the Sinner's in-memory TriggerHandler so the
            # cascade-deleted Trigger rows leave the cache on commit (#964).
            trigger_handler = sinner_sheet.character.trigger_handler
            if trigger_handler is not None:
                trigger_handler.invalidate()

    # NOTE: lifetime_helped on CharacterResonance persists (§13 — permanent record).
    # NOTE: TetherStrain ConditionInstance on the Sineater persists (decays naturally).
    # NOTE: Sineating and SoulTetherRescue audit rows persist (immutable history).
    # NOTE: Trigger rows are cascade-deleted with ConditionInstance; invalidate() above
    #       drops them from the in-memory cache on commit.

    # Emit the dissolution event after the atomic block so the DB state is visible
    # to any reactive subscribers.  Resolve location from the Sinner's current position.
    if dissolved_sinner_sheet is not None:
        sinner_character = dissolved_sinner_sheet.character
        location = sinner_character.location
        if location is not None:
            dissolved_payload = SoulTetherDissolvedPayload(
                sinner_sheet=dissolved_sinner_sheet,
                sineater_sheet=dissolved_sineater_sheet,  # type: ignore[arg-type]
                relationship=dissolved_relationship,  # type: ignore[arg-type]
            )
            emit_event(EventName.SOUL_TETHER_DISSOLVED, dissolved_payload, location=location)


# =============================================================================
# Sineating helpers
# =============================================================================


def _get_sinner_tether_thread(
    sinner_sheet: CharacterSheet,
    relationship: CharacterRelationship,
    resonance: Resonance,
) -> Thread | None:
    """Return the Sinner's RELATIONSHIP_CAPSTONE Thread for this bond + resonance, or None.

    The thread matches when ``resonance`` has a row on it, not only when it leads (#5231).
    """
    from world.magic.models import Thread  # noqa: PLC0415

    capstone = relationship.capstones.filter(
        relationship=relationship,
        is_ritual_capstone=True,
    ).first()
    if capstone is None:
        return None
    return (
        Thread.objects.filter(
            owner=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            resonance_rows__resonance=resonance,
            retired_at__isnull=True,
        )
        .distinct()
        .first()
    )


def sineater_thread_resonance(sineater_side: CharacterRelationship) -> Resonance | None:
    """The resonance the Sineater's thread on this tether channels (#5177), or None.

    ``sineater_side`` is the Sineater's own side toward the Sinner. It is the resonance of their
    live thread when they have one, else the one ``ensure_sineater_thread`` would weave
    (``default_sineater_resonance``). None when the tether is dissolved or the Sineater holds no
    resonance. Reads only; nothing is woven.
    """
    if not sineater_side.is_soul_tether:
        return None
    thread = _live_sineater_thread(sineater_side)
    if thread is not None:
        return thread.resonance
    return default_sineater_resonance(sineater_side.source)


def sinner_thread_resonance(sineater_side: CharacterRelationship) -> Resonance | None:
    """The resonance of the Sinner's live thread on this tether (#5177), or None.

    ``sineater_side`` is the Sineater's own side toward the Sinner; the Sinner's side is the
    row pointing back. None when the tether is dissolved or the Sinner's thread is gone.
    """
    from world.magic.models import Thread  # noqa: PLC0415

    sinner_side = CharacterRelationship.objects.filter(
        source=sineater_side.target, target=sineater_side.source, is_soul_tether=True
    ).first()
    if sinner_side is None:
        return None
    thread = (
        Thread.objects.filter(
            owner_id=sinner_side.source_id,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone__relationship=sinner_side,
            target_capstone__is_ritual_capstone=True,
            retired_at__isnull=True,
        )
        .select_related("resonance")
        .order_by("pk")
        .first()
    )
    return thread.resonance if thread is not None else None


def _compute_per_scene_sineating_cap(
    sinner_thread: Thread | None,
    relationship: CharacterRelationship,  # noqa: ARG001
) -> int:
    """Compute how many units can be Sineated in one scene.

    Formula (tunable via SoulTetherConfig singleton and the SOUL_TETHER_SCENE_CAP lane):
        cap = min(cfg.per_scene_cap_hard_max,
                  baseline(rung) + cfg.per_scene_cap_base)

    ``rung`` is ``thread_rung(level)``, whole steps of 10 thread levels (an internal
    step, #5091), and ``baseline`` its ``ModifierLevelBaseline`` row on the
    SOUL_TETHER_SCENE_CAP lane (#5093), 0 below rung 1: the hard max of 20 is reached around
    thread level 80 on the seeded rows.

    The seeded rows reproduce original behaviour (hard_max=20, 2 per rung, base=5).
    When no Sinner Thread exists the bond has no Hollow; cap is 0.
    The ``relationship`` parameter is accepted for future formula tuning
    (e.g. capping on the tie's pair depth).

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
    cfg = get_soul_tether_config()
    return min(
        cfg.per_scene_cap_hard_max,
        _rung_baseline(sinner_thread, ModifierLane.SOUL_TETHER_SCENE_CAP) + cfg.per_scene_cap_base,
    )


def _rung_baseline(sinner_thread: Thread, lane: str) -> int:
    """``lane``'s baseline at the Sinner's thread rung, 0 below rung 1 (#5093)."""
    rung = thread_rung(sinner_thread.level)
    return level_baseline(rung, lane) if rung >= 1 else 0


def _compute_hollow_max(sinner_thread: Thread) -> int:
    """Compute the Hollow's theoretical maximum for a given Thread.

    The HOLLOW_MAX lane's baseline at the thread's rung (#5093): ``thread_rung(level)``,
    whole steps of 10 thread levels (#5091), 0 below rung 1. The seeded rows are 10 per
    rung, reproducing the original behaviour.

    Args:
        sinner_thread: The Sinner's RELATIONSHIP_CAPSTONE Thread.

    Returns:
        The maximum number of units the Hollow can hold.
    """
    return max(0, _rung_baseline(sinner_thread, ModifierLane.HOLLOW_MAX))


def send_stored_notice(sheet: CharacterSheet, line: str, *, ooc_note: str) -> None:
    """Tell ``sheet`` a private line once the surrounding transaction commits, and keep it.

    The line is a stored narrative message: a puppeted character gets it at once, and a
    character who is offline (or whose web player reloads) gets it at their next login, the way
    a kindled deed's "You earned" line does. Used for what a Sinner learns about a Sineater's
    doing, which happens when they may not be there.
    """

    def _send() -> None:
        from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
        from world.narrative.services import send_narrative_message  # noqa: PLC0415

        send_narrative_message(
            recipients=[sheet],
            body=line,
            category=NarrativeCategory.SYSTEM,
            ooc_note=ooc_note,
        )

    transaction.on_commit(_send)


def _increment_stat_safe(
    character_sheet: CharacterSheet,
    stat_key: str,
    amount: int = 1,
) -> None:
    """Increment an achievement stat by key, no-op if StatDefinition is absent.

    StatDefinition rows for sineating.* stats are seeded via
    ``wire_soul_tether_stat_definitions`` in factories.  The DoesNotExist guard
    below is a defensive wrapper for environments where that seed data has not
    been loaded (e.g. minimal test setups); it does not indicate pending work.

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
        return  # Defensive guard: seed data not loaded in this environment; skip.
    increment_stat(character_sheet, stat_def, amount)


def shared_active_scene(
    first_sheet: CharacterSheet,
    second_sheet: CharacterSheet,
) -> Any | None:
    """The active scene two characters are both in, or None (#5177).

    Answers by character, not by pairing the players' accounts: both characters stand in the
    same place and that place has a live scene. A character with no player tenure (an NPC a
    GM runs under their own account) therefore takes part when it is physically there.

    Used by Sineating, the rescue and the stage-advance offer.
    """
    first_location = first_sheet.character.location
    second_location = second_sheet.character.location
    if first_location is None or second_location is None:
        return None
    if first_location.pk != second_location.pk:
        return None
    return live_scene_at(first_location)


def live_scene_at(location: Any) -> Any | None:
    """The live scene at ``location``, or None: a scene that is active and not finished (#5177).

    The one rule for "a scene Sineating can happen in". ``shared_active_scene`` and the pose
    picker both read it, so they cannot disagree about what is live.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    scene = get_active_scene(location)
    if scene is None or not scene.is_active or scene.is_finished:
        return None
    return scene


def _in_scene_together(
    first_sheet: CharacterSheet,
    second_sheet: CharacterSheet,
    scene: Any | None,
) -> bool:
    """True when ``scene`` is given and is the active scene both characters are in."""
    if scene is None:
        return False
    shared = shared_active_scene(first_sheet, second_sheet)
    return shared is not None and shared.pk == scene.pk


def perform_soul_tether_rescue(
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
    components: list[Any],  # noqa: ARG001
    scene: Any = None,
) -> RescueOutcome:
    """Perform a stage-3+ rescue ritual (Spec B §9.4).

    The Sineater performs a climactic rescue ritual to pull the Sinner back from
    advancing Corruption stages. This is the primary narrative beat of the Soul
    Tether bond.

    Gates (in order, each raises RescueValidationError on failure):
    1. Sinner has Corruption stage >= 3 in the given resonance.
    2. Active Soul Tether exists between Sineater and Sinner.
    3. Both characters are in the same scene (scene must not be None).
    4. Sineater is not in an active CharacterEngagement.
    5. No prior rescue this scene for this (sineater, sinner) pair.
    6. Sineater has sufficient CharacterResonance.balance for the ritual cost.

    Costs (paid before effect resolution):
    - Strain severity added to Sineater's TetherStrain ConditionInstance
      (scaled to Sinner's current stage — stage 3=5, stage 4=10, stage 5=18).
    - Resonance deducted from Sineater's CharacterResonance.balance
      (stage 3=10, stage 4=20, stage 5=35).

    Effect:
    - Rolls Magical Endurance check (using existing CheckType row).
    - Budget = severity to reduce (function of check outcome × sinner stage).
    - Calls reduce_corruption() with budget.
    - Increments Sineater's lifetime_helped by severity_reduced.
    - Writes SoulTetherRescue audit row.
    - Fires safe stat increments (graceful no-op if StatDefinition absent).
    - If Sinner drops from stage 5 below threshold, is_protagonism_locked lifts
      automatically via reduce_corruption's cleanup logic.

    Tuning placeholders (TODO Phase 14 — surface via SoulTetherConfig):
    - Strain cost: stage 3 = 5, stage 4 = 10, stage 5 = 18
    - Resonance cost: stage 3 = 10, stage 4 = 20, stage 5 = 35
    - Budget: check.success_level × (stage * 5) + 10, capped at 1 stage worth

    Args:
        sineater_sheet: CharacterSheet of the character performing the ritual.
        sinner_sheet: CharacterSheet of the Sinner being rescued.
        resonance: The Resonance whose corruption is being reduced.
        components: Ritual components consumed by the ritual.
        scene: The active Scene (required; raises if None or missing participation).

    Returns:
        RescueOutcome dataclass with full audit data.

    Raises:
        RescueValidationError: If any validation gate fails.
    """
    from world.conditions.services import advance_condition_severity  # noqa: PLC0415
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415
    from world.magic.models.soul_tether import SoulTetherRescue  # noqa: PLC0415
    from world.magic.services.corruption import reduce_corruption  # noqa: PLC0415
    from world.magic.types.corruption import CorruptionRecoverySource  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    with transaction.atomic():
        # 1. Gate: Sinner must be at corruption stage 3+
        sinner_stage_at_start = sinner_sheet.get_corruption_stage(resonance)
        if sinner_stage_at_start < _RESCUE_MIN_STAGE:
            msg = "Sinner must be at corruption stage 3 or higher to be rescued."
            raise RescueValidationError(msg)

        # 2. Gate: Active Soul Tether must exist (Sineater→Sinner direction: Sineater is source,
        #    target is Sinner). The Sineater-side relationship has soul_tether_role=SINEATER.
        relationship: CharacterRelationship | None = CharacterRelationship.objects.filter(
            source=sineater_sheet,
            target=sinner_sheet,
            is_soul_tether=True,
            soul_tether_role=SoulTetherRole.SINEATER,
        ).first()
        if relationship is None:
            msg = "No active Soul Tether exists between these characters."
            raise RescueValidationError(msg)

        # 2b. Gate: a fallen Sineater carries no one's sins (#5177).
        _refuse_fallen_sineater(sineater_sheet)

        # 3. Gate: Both characters must be in the same active scene, found by the
        #    characters themselves (an NPC a GM runs counts) (#5177).
        scene = _rescue_scene(sinner_sheet, sineater_sheet, scene)

        # 4. Gate: Sineater must not be in active engagement.
        if CharacterEngagement.objects.filter(character=sineater_sheet).exists():
            msg = "Rescue ritual cannot be performed during combat."
            raise RescueValidationError(msg)

        # 5. Gate: One rescue per (sineater, sinner) pair per scene.
        if SoulTetherRescue.objects.filter(
            sineater_sheet=sineater_sheet,
            sinner_sheet=sinner_sheet,
            scene=scene,
        ).exists():
            msg = "Rescue ritual already performed for this Sinner this scene."
            raise RescueValidationError(msg)

        # 6. Compute costs for this stage.
        sineater_strain_taken = _compute_strain_cost(sinner_stage_at_start)
        resonance_cost = _compute_resonance_cost(sinner_stage_at_start)

        # 7. Gate: Sineater must have sufficient resonance balance.
        sineater_resonance, _ = CharacterResonance.objects.select_for_update().get_or_create(
            character_sheet=sineater_sheet,
            resonance=resonance,
        )
        if sineater_resonance.balance < resonance_cost:
            msg = "Sineater has insufficient resonance for the ritual cost."
            raise RescueValidationError(msg)

        # 8. Roll Magical Endurance check.
        check_result = _perform_rescue_check(sineater_sheet)
        check_outcome = check_result.outcome

        # 9. Compute budget from check outcome + sinner stage.
        # TODO: Phase 14: surface tuning knobs via SoulTetherConfig singleton.
        thread_level = _get_sineater_thread_level(sineater_sheet, relationship)
        budget = _compute_rescue_budget(
            check_result.success_level, sinner_stage_at_start, thread_level
        )

        # 10. Apply Strain to Sineater (lazy-create instance if first dramatic moment).
        strain_instance = _get_or_create_tether_strain_instance(sineater_sheet)
        advance_condition_severity(strain_instance, sineater_strain_taken)

        # 11. Deduct resonance from Sineater balance.
        sineater_resonance.balance -= resonance_cost
        sineater_resonance.save(update_fields=["balance"])

        # 12. Reduce Sinner's corruption (Scope 7 primitive handles stage retreat,
        #     condition cleanup, and is_protagonism_locked lift when crossing stage 5).
        reduction_result = reduce_corruption(
            character_sheet=sinner_sheet,
            resonance=resonance,
            amount=budget,
            source=CorruptionRecoverySource.SPEC_B_RESCUE,
        )
        severity_reduced = reduction_result.amount_reduced

        # 13. Increment Sineater's lifetime_helped by severity actually reduced.
        #     No refresh_from_db needed — reduce_corruption only mutates the Sinner's
        #     CharacterResonance row; sineater_resonance's balance deduction (step 11)
        #     is still valid. Just add lifetime_helped on top of the already-mutated row.
        sineater_resonance.lifetime_helped += severity_reduced
        sineater_resonance.save(update_fields=["lifetime_helped"])

        # 14. Determine end stage + whether protagonism lock was lifted.
        sinner_stage_at_end = reduction_result.stage_after
        protagonism_lock_lifted = (
            sinner_stage_at_start == _RESCUE_TERMINAL_STAGE
            and sinner_stage_at_end < _RESCUE_TERMINAL_STAGE
        )

        # 15. Write audit row.
        rescue_row = SoulTetherRescue.objects.create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            relationship=relationship,
            scene=scene,
            resonance=resonance,
            sinner_stage_at_start=sinner_stage_at_start,
            sinner_stage_at_end=sinner_stage_at_end,
            severity_reduced=severity_reduced,
            sineater_strain_taken=sineater_strain_taken,
            check_outcome=check_outcome,
        )

    # 16. Fire stat increments (outside transaction — graceful no-op if rows absent).
    _increment_stat_safe(sineater_sheet, "rescue.performed", 1)
    if sinner_stage_at_start == _RESCUE_TERMINAL_STAGE:
        _increment_stat_safe(sineater_sheet, "rescue.stage5_save", 1)
    _increment_stat_safe(sineater_sheet, "rescue.severity_reduced", severity_reduced)

    return RescueOutcome(
        audit_row=rescue_row,
        severity_reduced=severity_reduced,
        sinner_stage_at_start=sinner_stage_at_start,
        sinner_stage_at_end=sinner_stage_at_end,
        sineater_strain_taken=sineater_strain_taken,
        protagonism_lock_lifted=protagonism_lock_lifted,
    )


# =============================================================================
# Rescue ritual internal helpers
# =============================================================================

#: Minimum Sinner corruption stage eligible for the rescue ritual (Spec B §9.2).
_RESCUE_MIN_STAGE: int = 3

#: Terminal corruption stage at which protagonism is locked (mirrors corruption.py).
_RESCUE_TERMINAL_STAGE: int = 5

#: Success level constants mirroring anima.py pattern.
_RESCUE_CRIT_SUCCESS_LEVEL = 2
_RESCUE_SUCCESS_LEVEL = 1
_RESCUE_PARTIAL_LEVEL = 0


def _rescue_scene(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    scene: Any | None,
) -> Any:
    """The active scene the rescue happens in, or ``RescueValidationError``.

    A scene passed in must be the one both characters are in; none passed means that one.
    """
    shared = shared_active_scene(sinner_sheet, sineater_sheet)
    if shared is None or (scene is not None and scene.pk != shared.pk):
        msg = "Both characters must be in the same scene for the rescue ritual."
        raise RescueValidationError(msg)
    return shared


def _compute_strain_cost(sinner_stage: int) -> int:
    """Return Strain severity the Sineater takes for a rescue at *sinner_stage*.

    Values are read from the ``SoulTetherConfig`` singleton (pk=1), defaulting to
    stage 3 = 5, stage 4 = 10, stage 5 = 18.

    Args:
        sinner_stage: Corruption stage (3-5) the Sinner is at.

    Returns:
        Strain severity amount to apply to the Sineater.
    """
    cfg = get_soul_tether_config()
    if sinner_stage == 3:  # noqa: PLR2004 — corruption stage literal
        return cfg.rescue_strain_stage3
    if sinner_stage == 4:  # noqa: PLR2004 — corruption stage literal
        return cfg.rescue_strain_stage4
    return cfg.rescue_strain_stage5


def _compute_resonance_cost(sinner_stage: int) -> int:
    """Return Resonance balance cost the Sineater pays for a rescue at *sinner_stage*.

    Values are read from the ``SoulTetherConfig`` singleton (pk=1), defaulting to
    stage 3 = 10, stage 4 = 20, stage 5 = 35.

    Args:
        sinner_stage: Corruption stage (3-5) the Sinner is at.

    Returns:
        Resonance balance amount to deduct from the Sineater.
    """
    cfg = get_soul_tether_config()
    if sinner_stage == 3:  # noqa: PLR2004 — corruption stage literal
        return cfg.rescue_resonance_stage3
    if sinner_stage == 4:  # noqa: PLR2004 — corruption stage literal
        return cfg.rescue_resonance_stage4
    return cfg.rescue_resonance_stage5


def _compute_rescue_budget(
    success_level: int,
    sinner_stage: int,
    thread_level: int,
) -> int:
    """Compute severity-reduction budget for the rescue ritual outcome.

    All tuning knobs are read from the ``SoulTetherConfig`` singleton (pk=1).
    Default formula (reproduces original behaviour):
        base = {3: 60, 4: 120, 5: 250}[stage]
        multiplier = 1.0 + success_level * 0.5 + (RESCUE_BUDGET_THREAD baseline at rung) / 100
        budget = max(1, int(base * multiplier))

    The thread term is the ``RESCUE_BUDGET_THREAD`` lane's baseline at the Sineater's thread
    rung (``thread_rung(thread_level)``, #5093), in hundredths, and 0 below rung 1. The seeded
    rows give 50 a rung, the 0.05 a thread level the old coefficient gave at each whole rung.

    The formula ensures:
    - Critical success significantly boosts budget.
    - A higher thread rung gives a small but meaningful bonus.
    - Failure still provides some minimum recovery (budget >= 1).

    Args:
        success_level: Integer success level from CheckResult (0=partial, 1=success, 2=crit).
        sinner_stage: Corruption stage (3-5) the Sinner is at.
        thread_level: The Sineater's RELATIONSHIP_CAPSTONE Thread level for this bond,
            or 0 if no Sineater Thread exists.

    Returns:
        Integer severity budget to pass to reduce_corruption.
    """
    cfg = get_soul_tether_config()
    if sinner_stage == 3:  # noqa: PLR2004 — corruption stage literal
        base = cfg.rescue_budget_base_stage3
    elif sinner_stage == 4:  # noqa: PLR2004 — corruption stage literal
        base = cfg.rescue_budget_base_stage4
    else:
        base = cfg.rescue_budget_base_stage5
    rung = thread_rung(thread_level)
    thread_hundredths = level_baseline(rung, ModifierLane.RESCUE_BUDGET_THREAD) if rung >= 1 else 0
    multiplier = (
        cfg.rescue_budget_base_mult_tenths / 10
        + success_level * cfg.rescue_budget_success_mult_tenths / 10
        + thread_hundredths / 100
    )
    return max(1, int(base * multiplier))


def _get_sineater_thread_level(
    sineater_sheet: CharacterSheet,
    relationship: CharacterRelationship,
) -> int:
    """Return the level of the Sineater's thread on this bond, or 0 when they have none.

    The Sineater's thread channels the Sineater's own resonance, which is rarely the
    resonance being rescued, so the lookup goes by the bond and not by resonance (#5177).

    Args:
        sineater_sheet: The Sineater's CharacterSheet.
        relationship: The Sineater's own CharacterRelationship side toward the Sinner.
    """
    from world.magic.models import Thread  # noqa: PLC0415

    thread = Thread.objects.filter(
        owner=sineater_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        retired_at__isnull=True,
        target_capstone__relationship=relationship,
    ).first()
    return thread.level if thread is not None else 0


def _perform_rescue_check(sineater_sheet: CharacterSheet) -> Any:
    """Roll a Magical Endurance check for the rescue ritual.

    Uses the canonical 'Magical Endurance' CheckType seeded by
    ``world.magic.seeds_checks.ensure_magic_check_types``.  Raises
    ``CheckType.DoesNotExist`` loudly when the seed has not run — a
    genuine misconfiguration that should not be masked.

    Difficulty is 0 (the stage itself is the gate; difficulty is implicit
    in the high Strain + Resonance cost).

    Args:
        sineater_sheet: The Sineater's CharacterSheet.

    Returns:
        CheckResult dataclass from perform_check.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.seeds_checks import MAGICAL_ENDURANCE_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    check_type = CheckType.objects.get(name=MAGICAL_ENDURANCE_CHECK_TYPE_NAME)
    return perform_check_with_modifiers(
        sineater_sheet.character,
        check_type=check_type,
        target_difficulty=0,
        extra_traits=activity_skill_terms(MagicActivity.SOUL_TETHER_RESCUE),
    )


# =============================================================================
# Redirect handler helper
# =============================================================================


def _get_sinner_tether_threads_for_resonance(
    sheet: CharacterSheet,
    resonance: Resonance,
) -> list[Any]:
    """Return all active Sinner-side RELATIONSHIP_CAPSTONE Threads holding ``resonance``.

    A thread holds it when the resonance has a row on the thread, led by it or not (#5231).
    Only Abyssal resonances corrupt, so this is any Abyssal resonance on the thread.

    "Sinner-side" means the Thread's target_capstone belongs to a
    CharacterRelationship where sheet is the source AND soul_tether_role is
    SINNER.  Only non-retired Threads are returned.

    Args:
        sheet: The character sheet whose Threads to search.
        resonance: The resonance to match.

    Returns:
        List of Thread instances (may be empty).
    """
    from world.magic.models import Thread  # noqa: PLC0415

    return list(
        Thread.objects.filter(
            owner=sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance_rows__resonance=resonance,
            retired_at__isnull=True,
            # Capstone must belong to a soul-tether relationship where sheet is the Sinner.
            target_capstone__relationship__source=sheet,
            target_capstone__relationship__is_soul_tether=True,
            target_capstone__relationship__soul_tether_role=SoulTetherRole.SINNER,
        )
        .select_related("target_capstone__relationship")
        .distinct()
    )


# =============================================================================
# Reactive subscriber: soul_tether_redirect_handler
# =============================================================================


def soul_tether_redirect_handler(*, payload: Any) -> None:
    """Subscriber for CORRUPTION_ACCRUING — drains Hollow, absorbs what it can (Spec B §5.2).

    Called by the flows trigger pipeline when CORRUPTION_ACCRUING fires for any
    character.  Exits immediately if the character has no active Sinner-side
    Threads matching the resonance.

    Absorption mechanic:
    - Iterates active Sinner Threads for the resonance in descending Thread.level
      order (highest-level Thread absorbs first).
    - Drains hollow_current from each Thread up to the remaining amount.
    - Mutates payload.amount to the unabsorbed remainder.  When payload.amount
      reaches 0 (fully absorbed), accrue_corruption short-circuits after dispatch.
    - Recursion guard: if payload.redirect_origin is set, this is an overflow
      re-call; skip without touching the Hollow.

    Args:
        payload: CorruptionAccruingPayload (mutable dataclass).
    """
    from world.magic.models import Thread  # noqa: PLC0415

    # Recursion guard: overflow accrual from this handler must not re-enter.
    if payload.redirect_origin is not None:
        return

    # Corruption a Sineater carries for a Sinner arrives whole, and so does what a character
    # adds by giving in to a Compulsion; the carrier's own Hollow (if they are a Sinner too)
    # absorbs neither (#5177).
    if payload.source in (CorruptionSource.SINEATING_CARRIED, CorruptionSource.INDULGED):
        return

    sinner_sheet: CharacterSheet = payload.character_sheet
    resonance: Resonance = payload.resonance
    accruing_amount: int = payload.amount

    # Drain across threads in priority order (highest level first).
    remaining = accruing_amount
    with transaction.atomic():
        sinner_threads = _get_sinner_tether_threads_for_resonance(sinner_sheet, resonance)
        if not sinner_threads:
            return  # No active tether for this resonance — pass through normally.

        for thread in sorted(sinner_threads, key=lambda t: -t.level):
            if remaining <= 0:
                break
            # Re-fetch with lock to prevent race conditions from concurrent casts.
            locked_thread = Thread.objects.select_for_update().get(pk=thread.pk)
            absorbed = min(locked_thread.hollow_current, remaining)
            if absorbed <= 0:
                continue
            locked_thread.hollow_current -= absorbed
            locked_thread.save(update_fields=["hollow_current"])
            remaining -= absorbed

    # Mutate the payload amount to the unabsorbed remainder.
    # accrue_corruption checks payload.amount after dispatch; 0 → full no-op.
    payload.amount = remaining


# =============================================================================
# Stage-advance prompt helpers
# =============================================================================

#: In-memory registry of pending stage-advance bonus offers (Spec B §8.1).
#: Keyed on offer_id (str UUID). Ephemeral — lost on process restart.
#: Offer values are ``StageAdvanceBonusOffer`` instances.
_pending_stage_advance_offers: dict[str, StageAdvanceBonusOffer] = {}

#: Strain severity added to the Sineater per unit committed (tunable).
_STRAIN_SEVERITY_PER_UNIT: int = 1

#: How long a PendingStageAdvanceOffer row remains valid after the prompt fires (Task 1.7).
#: Stage-advance prompts are time-sensitive; a 60-second window is generous enough for
#: a human to click Accept but short enough to avoid accumulating ghost rows.
STAGE_ADVANCE_OFFER_TTL: timedelta = timedelta(seconds=60)

#: Safe error message constants for StageAdvanceBonusError (Task 1.7).
_MSG_NO_PENDING_STAGE_ADVANCE_OFFER = "No pending stage-advance offer found."
_MSG_STAGE_ADVANCE_OFFER_EXPIRED = "This stage-advance prompt expired before you could respond."
_MSG_STAGE_ADVANCE_OFFER_STALE = (
    "This stage-advance prompt expired; you are no longer in the same scene."
)


def _active_soul_tethers_for_sinner(
    sinner_sheet: CharacterSheet,
) -> list[Any]:
    """Return all active Sinner-side CharacterRelationship rows for *sinner_sheet*.

    "Sinner-side" means source=sinner_sheet, is_soul_tether=True,
    soul_tether_role=SINNER.  Only active (non-soft-retired) tethers.

    Args:
        sinner_sheet: The Sinner's CharacterSheet.

    Returns:
        List of CharacterRelationship instances (may be empty).
    """
    return list(
        CharacterRelationship.objects.filter(
            source=sinner_sheet,
            is_soul_tether=True,
            soul_tether_role=SoulTetherRole.SINNER,
        ).select_related("target")
    )


def _find_sineater_in_location(
    tethers: list[Any],
    sinner_location: Any,
) -> CharacterSheet | None:
    """Return the first Sineater partner sharing *sinner_location*, or None.

    Iterates the Sinner's active tethers and checks whether the Sineater's
    character ObjectDB is in the same Evennia room as the Sinner.

    Args:
        tethers: Active Sinner-side CharacterRelationship rows
            (from ``_active_soul_tethers_for_sinner``).
        sinner_location: The Sinner's current Evennia room ObjectDB.

    Returns:
        The first Sineater's CharacterSheet whose character is in the same
        room, or ``None`` if no partner is co-located.
    """
    for tether in tethers:
        sineater_sheet: CharacterSheet = tether.target
        try:
            sineater_location = sineater_sheet.character.location
        except AttributeError:
            # No character ObjectDB on this sheet — skip.
            continue
        if sineater_location is not None and sineater_location == sinner_location:
            return sineater_sheet
    return None


def _total_hollow_across_sinner_tethers(
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
) -> int:
    """Sum of hollow_current across all active Sinner Threads in *resonance*.

    Args:
        sinner_sheet: The Sinner's CharacterSheet.
        resonance: The Resonance to filter on.

    Returns:
        Integer total hollow available (0 if no Threads or all hollow=0).
    """
    threads = _get_sinner_tether_threads_for_resonance(sinner_sheet, resonance)
    return sum(t.hollow_current for t in threads)


def _get_or_create_tether_strain_instance(
    sineater_sheet: CharacterSheet,
) -> ConditionInstance:
    """Get or create the Sineater's TetherStrain ConditionInstance.

    TetherStrainTemplate is a single authored ConditionTemplate.  Each Sineater
    has at most one row per resonance, but because TetherStrain is not
    per-resonance at the DB level (it is a single ConditionTemplate), we use
    one shared ConditionInstance per Sineater character.

    Lazy-creates via ``apply_condition`` on first call.

    Args:
        sineater_sheet: The Sineater's CharacterSheet.

    Returns:
        The active ConditionInstance for the Sineater's TetherStrain.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    strain_template = ConditionTemplate.get_by_name("Tether Strain")
    sineater_objectdb = sineater_sheet.character

    existing = ConditionInstance.objects.filter(
        target=sineater_objectdb,
        condition=strain_template,
        resolved_at__isnull=True,
    ).first()

    if existing is not None:
        return existing

    # Lazy-create: apply with severity=0 as a placeholder (advance_condition_severity
    # will add the actual amount).  ``apply_condition`` creates the row.
    result = apply_condition(
        sineater_objectdb,
        strain_template,
        severity=1,
        source_description="Soul Tether Strain — first dramatic moment",
    )
    # apply_condition returns an ApplyConditionResult; instance may be a new row.
    if result.instance is not None:
        # We over-applied by 1 severity as seed; caller will add real amount.
        # Reset to 0 then let caller advance properly.
        result.instance.severity = 0
        result.instance.save(update_fields=["severity"])
        return result.instance

    # Fallback: re-query in case apply_condition merged into an existing resolved row.
    return ConditionInstance.objects.get(
        target=sineater_objectdb,
        condition=strain_template,
        resolved_at__isnull=True,
    )


# =============================================================================
# Reactive subscriber: soul_tether_stage_advance_prompt
# =============================================================================


def soul_tether_stage_advance_prompt(*, payload: Any) -> None:
    """Subscriber for CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (Spec B §8.1).

    Called synchronously by the flows trigger pipeline when a Corruption
    condition is about to fire a stage-advance resist check.  Exits immediately
    if any of the fast-exit conditions apply.

    Synchronous dispatch architecture (documented decision):
        emit_event() and the resist check in ``_perform_advancement_resist_check``
        are both synchronous.  There is no Twisted Deferred suspension of the
        resist check — it fires immediately after this handler returns.  The
        Sineater therefore CANNOT respond in real time to influence THIS check.

        Instead this handler:
        1. Records a ``StageAdvanceBonusOffer`` in ``_pending_stage_advance_offers``.
        2. Notifies the Sineater (Evennia msg) of the pending offer.
        3. Returns immediately — the resist check fires at its unmodified difficulty.

        The Sineater calls ``resolve_stage_advance_prompt(offer_id, units)`` later
        (via the web API or ``@reply`` command) to deduct Hollow + add Strain.
        The commitment is noted as a retroactive resource for the current arc;
        it does NOT change the already-resolved check.

    Args:
        payload: ``ConditionStageAdvanceCheckPayload`` (mutable dataclass).
            Fields accessed: ``payload.instance`` (ConditionInstance) and
            ``payload.instance.condition`` (ConditionTemplate).
    """
    instance = payload.instance
    condition_template = instance.condition

    # 1. Filter — only Corruption conditions are ours (Spec B §8.1).
    if condition_template.corruption_resonance is None:
        return

    resonance: Resonance = condition_template.corruption_resonance

    # 2. Resolve the Sinner's CharacterSheet from the condition target (ObjectDB).
    try:
        sinner_sheet = CharacterSheet.objects.get(character=instance.target)
    except CharacterSheet.DoesNotExist:
        # Target is not a player character — skip.
        return

    # 3. Find active Sinner-side tethers.
    tethers = _active_soul_tethers_for_sinner(sinner_sheet)
    if not tethers:
        return

    # 4. Get Sinner's location.
    sinner_location = instance.target.location
    if sinner_location is None:
        return

    # 5. Find a Sineater partner in the same room.
    sineater_sheet = _find_sineater_in_location(tethers, sinner_location)
    if sineater_sheet is None:
        return  # No Sineater in scene — resist check proceeds normally (7.4 path).

    # 6. Calculate total hollow available across all matching tethers.
    max_hollow = _total_hollow_across_sinner_tethers(sinner_sheet, resonance)

    # 7. Record the pending offer.
    offer = StageAdvanceBonusOffer(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        resonance=resonance,
        max_hollow_to_spend=max_hollow,
    )
    _pending_stage_advance_offers[offer.offer_id] = offer

    # 7a. Persist the pending offer to DB so the UI can poll it (Task 1.7).
    #     Only write a row when a shared active scene can be verified — the scene FK is
    #     NOT NULL, and the resolve path requires it for the co-location check.
    #     If no shared scene is found the PROMPT_PLAYER msg above still fires, but the
    #     in-memory offer is the only state left (ephemeral; no inbox entry for the UI).
    from world.magic.models.soul_tether import PendingStageAdvanceOffer  # noqa: PLC0415

    relationship = tethers[0]  # First active tether (matches _find_sineater_in_location logic).
    shared_scene = shared_active_scene(sinner_sheet, sineater_sheet)
    if shared_scene is not None:
        current_stage_obj = instance.current_stage
        current_stage_number = current_stage_obj.stage_order if current_stage_obj is not None else 0
        PendingStageAdvanceOffer.objects.update_or_create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            defaults={
                "relationship": relationship,
                "scene": shared_scene,
                "resonance": resonance,
                "sinner_corruption_stage": current_stage_number,
                "commit_units_max": max_hollow,
                "strain_cost_per_unit": _STRAIN_SEVERITY_PER_UNIT,
                "expires_at": timezone.now() + STAGE_ADVANCE_OFFER_TTL,
            },
        )

    # 8. Notify the Sineater.  Evennia msg is fire-and-forget.
    current_stage = instance.current_stage
    current_stage_name = current_stage.name if current_stage is not None else "stage 0"
    target_stage = payload.target_stage
    target_stage_name = target_stage.name if target_stage is not None else "next stage"

    sineater_objectdb = sineater_sheet.character
    sineater_objectdb.msg(
        f"|ySOUL TETHER — Stage Advance Alert|n\n"
        f"{sinner_sheet} is resisting a corruption advance "
        f"from {current_stage_name} to {target_stage_name}. "
        f"You may commit up to {max_hollow} Hollow units to support them. "
        f"Use |w@soul-tether-bonus {offer.offer_id} <units>|n to commit. "
        f"(Offer ID: {offer.offer_id})"
    )


# =============================================================================
# Resolve service: resolve_stage_advance_prompt
# =============================================================================


def resolve_stage_advance_prompt(
    offer_id: str,
    units_committed: int,
) -> StageAdvanceBonusResult:
    """Resolve a stage-advance bonus offer with the Sineater's commitment (Spec B §8.1).

    Retroactive commitment (documented design deviation):
        Because the resist check resolves synchronously before the Sineater can
        respond, this function cannot modify the already-resolved check.  The
        committed Hollow + Strain is consumed as an acknowledgment of the
        Sineater's support.  Phase 13 integration tests will verify end-to-end
        behavior; Phase 11 API surfaces this via a dedicated endpoint.

    Args:
        offer_id: UUID string from the ``StageAdvanceBonusOffer``.
        units_committed: How many Hollow units the Sineater commits (0 = decline,
            1..max = commit that many). Clamped to [0, max_hollow_to_spend].

    Returns:
        A frozen ``StageAdvanceBonusResult``.

    Raises:
        StageAdvanceBonusError: If the offer_id is unknown or units exceed max.
    """
    from world.conditions.services import advance_condition_severity  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    offer = _pending_stage_advance_offers.get(offer_id)
    if offer is None:
        raise StageAdvanceBonusError

    # Remove from pending registry regardless of accept/decline.
    del _pending_stage_advance_offers[offer_id]

    # Clamp to valid range.
    units = max(0, min(units_committed, offer.max_hollow_to_spend))
    declined = units == 0

    if declined:
        return StageAdvanceBonusResult(
            offer_id=offer_id,
            units_committed=0,
            hollow_drained=0,
            strain_severity_added=0,
            declined=True,
        )

    hollow_drained = 0
    strain_severity_added = 0

    with transaction.atomic():
        # Drain Hollow across Sinner's tethers (highest-level Thread first).
        # Same multi-tether priority pattern from Phase 6's race-fix.
        sinner_threads = _get_sinner_tether_threads_for_resonance(
            offer.sinner_sheet, offer.resonance
        )
        remaining = units
        for thread in sorted(sinner_threads, key=lambda t: -t.level):
            if remaining <= 0:
                break
            locked_thread = Thread.objects.select_for_update().get(pk=thread.pk)
            absorbed = min(locked_thread.hollow_current, remaining)
            if absorbed <= 0:
                continue
            locked_thread.hollow_current -= absorbed
            locked_thread.save(update_fields=["hollow_current"])
            hollow_drained += absorbed
            remaining -= absorbed

        # Add Strain severity to the Sineater's TetherStrain ConditionInstance.
        strain_instance = _get_or_create_tether_strain_instance(offer.sineater_sheet)
        strain_amount = units * _STRAIN_SEVERITY_PER_UNIT
        advance_condition_severity(strain_instance, strain_amount)
        strain_severity_added = strain_amount

    return StageAdvanceBonusResult(
        offer_id=offer_id,
        units_committed=units,
        hollow_drained=hollow_drained,
        strain_severity_added=strain_severity_added,
        declined=False,
    )


# =============================================================================
# Public service: resolve_stage_advance_prompt_from_db (Task 1.7)
# =============================================================================


def resolve_stage_advance_prompt_from_db(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    units_committed: int,
) -> StageAdvanceBonusResult:
    """Resolve a stage-advance bonus offer fetched from the database (Task 1.7).

    Parallel to ``perform_sineating``. Looks up the ``PendingStageAdvanceOffer``
    row, validates TTL and co-location, then delegates to ``resolve_stage_advance_prompt``.

    TTL check: If ``expires_at < now()``, the offer is stale — delete the row and raise.
    Co-location check: If either PC is no longer a participant of the offer's scene,
    the offer is stale — delete the row and raise.

    Transaction pattern (matches Task 1.6 fix-up):
      Step 1: Plain lookup in autocommit mode — ``select_for_update`` illegal outside a
              transaction.
      Step 2: TTL check (autocommit) — delete + raise if expired.
      Step 3: Co-location check (autocommit) — delete + raise if stale.
      Step 4: Re-fetch with SELECT FOR UPDATE inside ``transaction.atomic()``, then
              resolve and delete.

    Args:
        sinner_sheet: The Sinner's CharacterSheet.
        sineater_sheet: The Sineater's CharacterSheet (must be the caller).
        units_committed: How many Hollow units to commit (0 = decline, positive = commit).

    Returns:
        A frozen ``StageAdvanceBonusResult`` dataclass.

    Raises:
        StageAdvanceBonusError: If the offer is missing, expired, or stale.
    """
    from world.magic.models.soul_tether import PendingStageAdvanceOffer  # noqa: PLC0415

    # Step 1: Plain lookup in autocommit mode.
    try:
        pending = PendingStageAdvanceOffer.objects.select_related(
            "scene", "resonance", "relationship"
        ).get(sinner_sheet=sinner_sheet, sineater_sheet=sineater_sheet)
    except PendingStageAdvanceOffer.DoesNotExist as exc:
        raise StageAdvanceBonusError(_MSG_NO_PENDING_STAGE_ADVANCE_OFFER) from exc

    # Step 2: TTL check (autocommit). Delete the row first, then raise.
    # filter().delete() issues an immediate DELETE that commits without needing
    # a wrapping transaction; if we did this inside atomic(), the rollback would
    # un-delete the row and leave a ghost in the inbox.
    if pending.expires_at < timezone.now():
        PendingStageAdvanceOffer.objects.filter(pk=pending.pk).delete()
        raise StageAdvanceBonusError(_MSG_STAGE_ADVANCE_OFFER_EXPIRED)

    # Step 3: Co-location check (autocommit). Scene is guaranteed non-null on persisted rows
    # (soul_tether_stage_advance_prompt only writes a row when shared_active_scene
    # returned a valid scene), so no null-check is needed here.
    if not _in_scene_together(pending.sinner_sheet, pending.sineater_sheet, pending.scene):
        PendingStageAdvanceOffer.objects.filter(pk=pending.pk).delete()
        raise StageAdvanceBonusError(_MSG_STAGE_ADVANCE_OFFER_STALE)

    # Step 4: Re-fetch with lock inside transaction.atomic(), then resolve.
    # The re-fetch guards against a concurrent caller who raced between our
    # plain get() above and this point.
    with transaction.atomic():
        try:
            locked_pending = PendingStageAdvanceOffer.objects.select_for_update().get(pk=pending.pk)
        except PendingStageAdvanceOffer.DoesNotExist as exc:
            # Another caller resolved (and deleted) the offer between our check and lock.
            raise StageAdvanceBonusError(_MSG_NO_PENDING_STAGE_ADVANCE_OFFER) from exc

        # Reconstruct the in-memory offer and seed the module-level registry so
        # ``resolve_stage_advance_prompt`` can look it up. The registry entry is
        # created here and consumed (deleted) by the call below.
        import uuid  # noqa: PLC0415

        synthetic_offer_id = str(uuid.uuid4())
        offer = StageAdvanceBonusOffer(
            offer_id=synthetic_offer_id,
            sinner_sheet=locked_pending.sinner_sheet,
            sineater_sheet=locked_pending.sineater_sheet,
            resonance=locked_pending.resonance,
            max_hollow_to_spend=locked_pending.commit_units_max,
        )
        _pending_stage_advance_offers[synthetic_offer_id] = offer

        try:
            result = resolve_stage_advance_prompt(
                offer_id=synthetic_offer_id,
                units_committed=units_committed,
            )
        finally:
            # Clean up if resolve_stage_advance_prompt raised before removing the entry.
            _pending_stage_advance_offers.pop(synthetic_offer_id, None)

        locked_pending.delete()

    return result


# =============================================================================
# Bilateral session wrapper: accept_soul_tether_via_session
# =============================================================================

_BILATERAL_PARTICIPANT_COUNT = 2


def accept_soul_tether_via_session(*, session: Any) -> Any:
    """Dispatched on Soul Tether BILATERAL fire (Slice B §4.15).

    The SoulTetherRole choice lives in participant_kwargs["soul_tether_role"]
    (scalar enum, JSON is the right home for discriminating-scalar choices per
    the Slice B spec discriminator-FK split).

    Reads exactly two ACCEPTED participants, maps each to their role, then
    delegates to accept_soul_tether with the canonical initiator/partner shape.

    Session kwargs:
        "resonance_id" (int): PK of the Resonance the Sinner's Thread will
            channel. Required; raises RequiredReferenceMissingError if absent
            or invalid.
        "ritual_components" (list): Component items (validated by caller).
            Optional; defaults to [].
        "sineater_resonance_id" (int): PK of the Resonance the Sineater's own Thread
            will channel (#5177). Optional; defaults to the Sineater's strongest
            resonance of their main affinity.

    NOTE (Slice B scope): resonance comes from session_kwargs as a scalar ID
    value. The frontend draft dialog (Phase 9) will populate it via the session
    draft. No session_reference kinds exist yet for Resonance objects — if that
    changes, this wrapper should be updated to read from references instead.

    Raises:
        RequiredReferenceMissingError: If participant count != 2, any
            participant lacks a valid soul_tether_role choice, or resonance_id
            is missing/invalid.
        BilateralRoleConflictError: If both participants chose the same role.
    """
    from world.magic.constants import ParticipantState  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        BilateralRoleConflictError,
        RequiredReferenceMissingError,
    )
    from world.magic.models.affinity import Resonance  # noqa: PLC0415
    from world.magic.types.soul_tether import SoulTetherRole as SoulTetherRoleEnum  # noqa: PLC0415

    valid_roles = {SoulTetherRoleEnum.SINNER, SoulTetherRoleEnum.SINEATER}

    # 1. Verify exactly two ACCEPTED participants.
    participants = list(session.participants.filter(state=ParticipantState.ACCEPTED))
    if len(participants) != _BILATERAL_PARTICIPANT_COUNT:
        raise RequiredReferenceMissingError

    # 2. Map each participant's declared role to their CharacterSheet.
    role_to_sheet: dict[str, Any] = {}
    for p in participants:
        role = p.participant_kwargs.get("soul_tether_role")
        if role not in valid_roles:
            raise RequiredReferenceMissingError
        if role in role_to_sheet:
            raise BilateralRoleConflictError
        role_to_sheet[role] = p.character_sheet

    # 3. Extract session-level scalar kwargs.
    resonance_id: int | None = session.session_kwargs.get("resonance_id")
    if resonance_id is None:
        raise RequiredReferenceMissingError
    try:
        resonance = Resonance.objects.get(pk=resonance_id)
    except Resonance.DoesNotExist as exc:
        raise RequiredReferenceMissingError from exc

    ritual_components: list[Any] = session.session_kwargs.get("ritual_components", [])

    # The Sineater's own thread resonance is optional; absent falls back to their default.
    sineater_resonance: Resonance | None = None
    sineater_resonance_id: int | None = session.session_kwargs.get("sineater_resonance_id")
    if sineater_resonance_id is not None:
        try:
            sineater_resonance = Resonance.objects.get(pk=sineater_resonance_id)
        except Resonance.DoesNotExist as exc:
            raise RequiredReferenceMissingError from exc

    # 4. Build the accept_soul_tether call using its initiator/partner + sinner_role shape.
    #    We treat the sinner as the "initiator" (arbitrary — the function uses sinner_role
    #    to resolve which sheet is which, not the argument name).
    return accept_soul_tether(
        initiator_sheet=role_to_sheet[SoulTetherRoleEnum.SINNER],
        partner_sheet=role_to_sheet[SoulTetherRoleEnum.SINEATER],
        sinner_role=SoulTetherRoleEnum.SINNER,
        resonance=resonance,
        ritual_components=ritual_components,
        sineater_resonance=sineater_resonance,
    )
