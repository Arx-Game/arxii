"""Sineating: a ritual with a roll, framed by poses in a shared scene (#5177).

The Sinner's plea (``request_sineating``) is written when the pose that carries it is posted.
The Sineater performs the ritual (``perform_sineating``) in the pose that answers it: they
choose how many of the offered units to take on, and the configured check is rolled. The
chosen units move corruption from the Sinner onto the Sineater whatever the roll; the roll's
outcome tier scales what each of them earns, in the resonance of their own half of the bond.

Every refusal runs before anything is written. A pose is checked the same way before it is
posted (``pending_sineating_from``) and the Sineating is carried out after it is
(``record_pending_sineating``), as a reflection is (#5124).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import QuerySet

from world.character_sheets.models import CharacterSheet
from world.checks.services import difficulty_points, perform_check_with_modifiers
from world.magic.constants import (
    GainSource,
    MagicActivity,
    SineatingPoseRole,
    SoulTetherRole,
    TargetKind,
)
from world.magic.exceptions import SineatingValidationError, SoulTetherError
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import Sineating, SineatingPendingOffer
from world.magic.models.soul_tether_config import SineatingOutcomeAward, SoulTetherConfig
from world.magic.services.corruption import get_corruption_config
from world.magic.services.mire import corruption_that_can_move, take_on_corruption
from world.magic.services.soul_tether import (
    _MSG_NO_ACTIVE_TETHER,
    _MSG_NOT_IN_SAME_SCENE,
    _MSG_PER_SCENE_CAP_REACHED,
    _MSG_RESONANCE_NOT_ACCRUED,
    _compute_hollow_max,
    _compute_per_scene_sineating_cap,
    _get_sinner_tether_thread,
    _in_scene_together,
    _increment_stat_safe,
    _refuse_fallen_sineater,
    ensure_sineater_thread,
    get_soul_tether_config,
    live_scene_at,
    send_stored_notice,
    shared_active_scene,
)
from world.magic.types.soul_tether import (
    PendingSineating,
    SineatingLines,
    SineatingOffer,
    SineatingOption,
    SineatingResult,
)
from world.relationships.models import CharacterRelationship
from world.roster.services.npc_lending import played_by_one_account
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from world.magic.models import Thread
    from world.scenes.models import Scene

_MSG_NO_PENDING_OFFER = "No pending Sineating offer found."
_MSG_OFFER_STALE = "This offer expired because you are no longer in the same scene."
_MSG_NOT_SET_UP = "Sineating has not been set up yet."
_MSG_CARRY_TOO_MUCH = "You carry too much of the Mire to take on more. Settle some of it first."
_MSG_NO_TETHER_THREAD = "The Soul Tether is missing its resonance thread."
_MSG_PARTNER_NOT_FOUND = "That character cannot be found."
_MSG_ONE_PLAYER_SINEATING = "You cannot perform Sineating between two characters you play."
_MSG_POSE_FIELDS_INCOMPLETE = "Sineating needs a role, a partner and a number of units."
BOTH_REFLECTION_AND_SINEATING = "A pose can carry a reflection or a Sineating, not both."

_NO_SINEATER_RESONANCE_LINE = (
    "You hold no resonance for your side of the bond to channel, so you earn none."
)
_CUT_LINE = "You could take on only part of it; settle some of the Mire to carry more."

# The pose fields a Sineating rides in (the serializer mixin and the telnet parser use them).
POSE_FIELDS = ("sineating_role", "sineating_partner_id", "sineating_units")


def _name(sheet: CharacterSheet) -> str:
    return sheet.primary_persona.name


# =============================================================================
# Readiness (the Required content page reads the same conditions)
# =============================================================================


def outcome_tiers_without_a_sineating_award() -> QuerySet[CheckOutcome]:
    """Every ``CheckOutcome`` with no ``SineatingOutcomeAward`` row.

    The roll can land on any tier, so one missing here leaves Sineating unready. The Required
    content probe lists these by name; ``sineating_is_ready`` asks whether any exist.
    """
    return CheckOutcome.objects.exclude(
        pk__in=SineatingOutcomeAward.objects.values("outcome_tier_id")
    )


def sineating_is_ready(config: SoulTetherConfig | None = None) -> bool:
    """Whether Sineating can be performed: a check type and an award for every outcome tier.

    Costs one query (the award check), and none when the check type is unset. While this is
    false the ritual refuses with "Sineating has not been set up yet." Pass the ``config`` the
    caller already holds to skip fetching it again.
    """
    if config is None:
        config = get_soul_tether_config()
    if config.sineating_check_type_id is None:
        return False
    return not outcome_tiers_without_a_sineating_award().exists()


def _sineater_max_stage() -> int | None:
    """The corruption stage a Sineater's Mire may not climb past (#5177).

    Staff set it on ``CorruptionConfig.sineater_max_stage``, normally the Compulsion stage.
    The ritual takes on only what fits below the top of that stage.
    """
    return get_corruption_config().sineater_max_stage


# =============================================================================
# The plea
# =============================================================================


def _tether_relationship(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet
) -> CharacterRelationship:
    relationship = CharacterRelationship.objects.filter(
        source=sinner_sheet,
        target=sineater_sheet,
        is_soul_tether=True,
        soul_tether_role=SoulTetherRole.SINNER,
    ).first()
    if relationship is None:
        raise SineatingValidationError(_MSG_NO_ACTIVE_TETHER)
    return relationship


def _tether_thread(sinner_sheet: CharacterSheet, relationship: CharacterRelationship) -> Thread:
    """The Sinner's live thread on this tether; its resonance is the tether's."""
    from world.magic.models import Thread  # noqa: PLC0415

    capstone = relationship.capstones.filter(is_ritual_capstone=True).first()
    thread = (
        Thread.objects.filter(
            owner=sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            retired_at__isnull=True,
        ).first()
        if capstone is not None
        else None
    )
    if thread is None:
        raise SineatingValidationError(_MSG_NO_TETHER_THREAD)
    return thread


def _refuse_one_player_on_both_sides(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet
) -> None:
    """One account that plays both characters could ask as one and perform as the other."""
    if played_by_one_account(sinner_sheet, sineater_sheet):
        raise SineatingValidationError(_MSG_ONE_PLAYER_SINEATING)


def _refuse_if_performed(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet, scene: Scene, partner: str
) -> None:
    """A pair performs Sineating once per scene, counted from the audit rows."""
    if Sineating.objects.filter(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        scene=scene,
        units_accepted__gt=0,
    ).exists():
        msg = f"You have already performed Sineating with {partner} in this scene."
        raise SineatingValidationError(msg)


def _checked_plea(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet, units: int
) -> tuple[CharacterRelationship, Thread, Scene, int]:
    """Validate a plea and return its relationship, tether thread, scene and clamped units."""
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    relationship = _tether_relationship(sinner_sheet, sineater_sheet)
    _refuse_one_player_on_both_sides(sinner_sheet, sineater_sheet)
    _refuse_fallen_sineater(sineater_sheet)
    scene = shared_active_scene(sinner_sheet, sineater_sheet)
    if scene is None:
        raise SineatingValidationError(_MSG_NOT_IN_SAME_SCENE)
    _refuse_if_performed(sinner_sheet, sineater_sheet, scene, _name(sineater_sheet))
    thread = _tether_thread(sinner_sheet, relationship)
    if not CharacterResonance.objects.filter(
        character_sheet=sinner_sheet, resonance=thread.resonance
    ).exists():
        raise SineatingValidationError(_MSG_RESONANCE_NOT_ACCRUED)
    cap = _compute_per_scene_sineating_cap(thread, relationship)
    if cap == 0:
        raise SineatingValidationError(_MSG_PER_SCENE_CAP_REACHED)
    return relationship, thread, scene, max(1, min(units, cap))


def request_sineating(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet, units: int
) -> SineatingOffer:
    """Record the Sinner's plea for Sineating: ``units`` offered, clamped to the scene's cap.

    The resonance is the Sinner's tether thread's. A repeat plea replaces the waiting one.

    Raises:
        SineatingValidationError: no tether, a fallen Sineater, not in one active scene, the
            pair already performed Sineating in this scene, no thread, or no capacity.
    """
    relationship, thread, scene, offered = _checked_plea(sinner_sheet, sineater_sheet, units)
    SineatingPendingOffer.objects.update_or_create(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        defaults={
            "relationship": relationship,
            "scene": scene,
            "resonance": thread.resonance,
            "units_offered": offered,
        },
    )
    _increment_stat_safe(sinner_sheet, "sineating.requests_made", 1)
    return SineatingOffer(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        relationship=relationship,
        resonance=thread.resonance,
        max_units_offered=offered,
        current_hollow=thread.hollow_current,
        hollow_max=_compute_hollow_max(thread),
        sineater_current_strain_stage=sineater_sheet.get_tether_strain_stage(),
        scene=scene,
    )


# =============================================================================
# The ritual
# =============================================================================


def _checked_performance(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet, units: int
) -> tuple[SineatingPendingOffer, int, SoulTetherConfig]:
    """Every refusal the ritual can make before the roll, in order, writing nothing.

    Returns the waiting plea, the units after clamping to 1..offered, and the config. A plea
    that has gone stale (they no longer share the active scene it was made in) is cleaned up
    here, outside any transaction so the delete is not rolled back with the refusal.
    """
    pending = (
        SineatingPendingOffer.objects.select_related("relationship", "resonance", "scene")
        .filter(sinner_sheet=sinner_sheet, sineater_sheet=sineater_sheet)
        .first()
    )
    if pending is None:
        raise SineatingValidationError(_MSG_NO_PENDING_OFFER)
    if not _in_scene_together(sinner_sheet, sineater_sheet, pending.scene):
        SineatingPendingOffer.objects.filter(pk=pending.pk).delete()
        raise SineatingValidationError(_MSG_OFFER_STALE)
    _refuse_one_player_on_both_sides(sinner_sheet, sineater_sheet)
    _refuse_fallen_sineater(sineater_sheet)
    _refuse_if_performed(sinner_sheet, sineater_sheet, pending.scene, _name(sinner_sheet))
    cfg = get_soul_tether_config()
    if not sineating_is_ready(cfg):
        raise SineatingValidationError(_MSG_NOT_SET_UP)
    chosen = max(1, min(units, pending.units_offered))
    carried, fits = corruption_that_can_move(
        sineater_sheet=sineater_sheet,
        sinner_sheet=sinner_sheet,
        resonance=pending.resonance,
        amount=chosen * cfg.corruption_per_unit,
        max_stage=_sineater_max_stage(),
    )
    if carried > 0 and fits == 0:
        raise SineatingValidationError(_MSG_CARRY_TOO_MUCH)
    return pending, chosen, cfg


def _earned(units: int, cfg: SoulTetherConfig, share: Decimal) -> int:
    return int(Decimal(units * cfg.resonance_per_unit) * Decimal(share))


def _refill_hollow(sinner_sheet: CharacterSheet, pending: SineatingPendingOffer, units: int) -> int:
    """Refill the Sinner's Hollow by ``units`` (capped at its maximum); return what it reads."""
    from world.magic.models import Thread  # noqa: PLC0415

    thread = _get_sinner_tether_thread(sinner_sheet, pending.relationship, pending.resonance)
    if thread is None:
        return 0
    locked = Thread.objects.select_for_update().get(pk=thread.pk)
    locked.hollow_current = min(_compute_hollow_max(thread), locked.hollow_current + units)
    locked.save(update_fields=["hollow_current"])
    return locked.hollow_current


def _count_lifetime_helped(sineater_sheet: CharacterSheet, resonance: Resonance, units: int) -> int:
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    row, _ = CharacterResonance.objects.select_for_update().get_or_create(
        character_sheet=sineater_sheet, resonance=resonance
    )
    row.lifetime_helped += units
    row.save(update_fields=["lifetime_helped"])
    return row.lifetime_helped


def perform_sineating(
    sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet, units: int
) -> SineatingResult:
    """The Sineater performs the ritual for the plea the Sinner made (#5177).

    The configured check is rolled. ``units`` (clamped to 1..offered) move
    ``corruption_per_unit`` each of the Sinner's corruption onto the Sineater, as much as fits
    under the Mire's stage cap, whatever the roll. The Hollow refills by the units. The roll's
    outcome tier sets each party's earnings: ``units x resonance_per_unit x earned_share`` of
    their own thread's resonance (the Sinner's thread's for the Sinner, the Sineater's own
    for the Sineater, who earns nothing while they hold no resonance for a thread to channel).

    Raises:
        SineatingValidationError: no plea waits, the pair has left the plea's scene, the
            Sineater has fallen, the pair already performed Sineating in this scene,
            Sineating is not set up, or the Sineater carries too much to take on any.
    """
    pending, chosen, cfg = _checked_performance(sinner_sheet, sineater_sheet, units)
    resonance = pending.resonance
    with transaction.atomic():
        # A concurrent performance deletes the plea; lock it so only one gets through.
        if not SineatingPendingOffer.objects.select_for_update().filter(pk=pending.pk).exists():
            raise SineatingValidationError(_MSG_NO_PENDING_OFFER)
        # The thread comes first: it is what gives the Sineater's resistance something to act on.
        sineater_thread = ensure_sineater_thread(sineater_sheet, sinner_sheet)
        check = perform_check_with_modifiers(
            sineater_sheet.character,
            cfg.sineating_check_type,
            difficulty_points(cfg.sineating_difficulty_level),
            extra_traits=_sineating_skill_terms(),
        )
        outcome = check.outcome
        award = (
            SineatingOutcomeAward.objects.filter(outcome_tier=outcome).first()
            if outcome is not None
            else None
        )
        if award is None:
            raise SineatingValidationError(_MSG_NOT_SET_UP)

        amount = chosen * cfg.corruption_per_unit
        carried = amount
        transfer = None
        if amount > 0:
            carried, _fits = corruption_that_can_move(
                sineater_sheet=sineater_sheet,
                sinner_sheet=sinner_sheet,
                resonance=resonance,
                amount=amount,
                max_stage=_sineater_max_stage(),
            )
            transfer = take_on_corruption(
                sineater_sheet=sineater_sheet,
                sinner_sheet=sinner_sheet,
                resonance=resonance,
                amount=amount,
                max_stage=_sineater_max_stage(),
            )
        left_sinner = transfer.left_sinner if transfer is not None else 0
        taken = transfer.arrived if transfer is not None else 0
        new_hollow = _refill_hollow(sinner_sheet, pending, chosen)
        lifetime_helped = _count_lifetime_helped(sineater_sheet, resonance, chosen)

        earned = _earned(chosen, cfg, award.earned_share)
        sineater_resonance = sineater_thread.resonance if sineater_thread is not None else None
        sinner_earned = _grant(sinner_sheet, resonance, earned)
        sineater_earned = (
            _grant(sineater_sheet, sineater_resonance, earned)
            if sineater_resonance is not None
            else 0
        )

        audit_row = Sineating.objects.create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            relationship=pending.relationship,
            scene=pending.scene,
            resonance=resonance,
            units_offered=pending.units_offered,
            units_accepted=chosen,
            corruption_moved=left_sinner,
            corruption_taken=taken,
            outcome=outcome,
            sinner_resonance_earned=sinner_earned,
            sineater_resonance_earned=sineater_earned,
        )
        SineatingPendingOffer.objects.filter(pk=pending.pk).delete()

    _increment_stat_safe(sineater_sheet, "sineating.units_accepted", chosen)
    return SineatingResult(
        audit_row=audit_row,
        units_accepted=chosen,
        declined=False,
        new_hollow_current=new_hollow,
        new_lifetime_helped=lifetime_helped,
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        resonance=resonance,
        corruption_left_sinner=left_sinner,
        corruption_taken=taken,
        cut_by_ceiling=left_sinner < carried,
        outcome_name=outcome.name,
        sinner_resonance_earned=sinner_earned,
        sineater_resonance=sineater_resonance,
        sineater_resonance_earned=sineater_earned,
    )


def _sineating_skill_terms() -> Any:
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    return activity_skill_terms(MagicActivity.SINEATING)


def _grant(sheet: CharacterSheet, resonance: Resonance, amount: int) -> int:
    """Grant ``amount`` of ``resonance`` under SINEATING; 0 grants nothing.

    Returns the amount the ledger row recorded, which is ``amount`` scaled by the character's
    earn rate (#5181), so the result lines and the audit row report what was really earned.
    """
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    if amount <= 0:
        return 0
    ledger: list = []
    grant_resonance(sheet, resonance, amount, source=GainSource.SINEATING, ledger_out=ledger)
    return ledger[-1].amount


def decline_sineating(sinner_sheet: CharacterSheet, sineater_sheet: CharacterSheet) -> Sineating:
    """The Sineater turns the plea down: the plea is removed and a declined audit row is kept.

    Raises:
        SineatingValidationError: no plea waits.
    """
    with transaction.atomic():
        pending = (
            SineatingPendingOffer.objects.select_for_update()
            .filter(sinner_sheet=sinner_sheet, sineater_sheet=sineater_sheet)
            .first()
        )
        if pending is None:
            raise SineatingValidationError(_MSG_NO_PENDING_OFFER)
        audit_row = Sineating.objects.create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            relationship=pending.relationship,
            scene=pending.scene,
            resonance=pending.resonance,
            units_offered=pending.units_offered,
            units_accepted=0,
        )
        pending.delete()
    _increment_stat_safe(sineater_sheet, "sineating.units_declined", 1)
    return audit_row


# =============================================================================
# What each party is told
# =============================================================================


def sineating_lines(result: SineatingResult) -> SineatingLines:
    """The lines the Sinner and the Sineater each read after a Sineating.

    Telnet and the web both use this, so they say the same thing.
    """
    sinner_name = _name(result.sinner_sheet)
    sineater_name = _name(result.sineater_sheet)
    carried_in = result.resonance.name
    if result.corruption_left_sinner > 0:
        sinner = [
            f"{sineater_name} takes on your sins: your corruption in {carried_in} falls by "
            f"{result.corruption_left_sinner}."
        ]
        sineater = [
            f"You take {result.corruption_taken} of {sinner_name}'s corruption into the Mire."
        ]
    else:
        sinner = [f"{sineater_name} takes on your sins, but you carried no corruption to shed."]
        sineater = [f"You take on {sinner_name}'s sins, but they carried no corruption to shed."]
    if result.sinner_resonance_earned > 0:
        sinner[-1] += f" Your {carried_in} grows by {result.sinner_resonance_earned}."
    if result.sineater_resonance is None:
        sineater.append(_NO_SINEATER_RESONANCE_LINE)
    elif result.sineater_resonance_earned > 0:
        sineater[-1] += (
            f" Your {result.sineater_resonance.name} grows by {result.sineater_resonance_earned}."
        )
    if result.cut_by_ceiling:
        sineater.append(_CUT_LINE)
        sinner.append(f"{sineater_name} could take on only part of it.")
    return SineatingLines(sinner=tuple(sinner), sineater=tuple(sineater))


def plea_line(offer: SineatingOffer) -> str:
    """What the Sineater is told when a plea is recorded."""
    return (
        f"{_name(offer.sinner_sheet)} asks you to take on their sins "
        f"({offer.max_units_offered} offered). Answer with a pose."
    )


# =============================================================================
# Carried by a pose
# =============================================================================


def pending_sineating_from(sheet: CharacterSheet, params: Any) -> PendingSineating | None:
    """The Sineating a pose asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``sineating_role``
    (``entreat`` or ``perform``), ``sineating_partner_id`` (the other character's sheet id) and
    ``sineating_units``. All absent means no Sineating. Nothing is written.

    Raises:
        SoulTetherError: the fields are incomplete, the partner is not found, or the plea or
            the ritual cannot happen (the same refusals ``request_sineating`` and
            ``perform_sineating`` make).
    """
    role = params.get("sineating_role")
    partner_id = params.get("sineating_partner_id")
    units = params.get("sineating_units")
    if not role and partner_id is None and units is None:
        return None
    if role not in SineatingPoseRole.values or partner_id is None or units is None:
        raise SineatingValidationError(_MSG_POSE_FIELDS_INCOMPLETE)
    partner = CharacterSheet.objects.filter(pk=partner_id).first()
    if partner is None:
        raise SineatingValidationError(_MSG_PARTNER_NOT_FOUND)
    if role == SineatingPoseRole.ENTREAT:
        _, _, _, offered = _checked_plea(sheet, partner, int(units))
        return PendingSineating(role, sheet, partner, offered)
    _, chosen, _ = _checked_performance(partner, sheet, int(units))
    return PendingSineating(role, partner, sheet, chosen)


def record_pending_sineating(pending: PendingSineating) -> tuple[str, ...]:
    """Carry out a ``pending_sineating_from`` result once its pose is posted.

    Returns the lines the pose writer reads. The other party is told privately: the Sineater
    that a plea waits (a live line: the plea itself persists and shows in their picker and
    ``sineater pleas``), the Sinner what the ritual did (a stored message, so they read it
    whenever they next log in). The room sees only the pose.

    Raises:
        SoulTetherError: the plea or the ritual is refused after all (a race); the pose
            stands, and the caller tells the writer why nothing happened.
    """
    if pending.role == SineatingPoseRole.ENTREAT:
        offer = request_sineating(pending.sinner_sheet, pending.sineater_sheet, pending.units)
        pending.sineater_sheet.character.msg(plea_line(offer))
        return (
            f"You entreat {_name(pending.sineater_sheet)} to take on your sins. "
            f"{offer.max_units_offered} are offered.",
        )
    result = perform_sineating(pending.sinner_sheet, pending.sineater_sheet, pending.units)
    lines = sineating_lines(result)
    for line in lines.sinner:
        send_stored_notice(pending.sinner_sheet, line, ooc_note="Sineating")
    return lines.sineater


def _same_location(sheet: CharacterSheet, location: Any) -> bool:
    """Whether ``sheet``'s character stands in ``location`` (a sheet with no character: no)."""
    try:
        other = sheet.character.location
    except ObjectDoesNotExist:
        return False
    return other is not None and other.pk == location.pk


def sineating_options_for(sheet: CharacterSheet) -> list[SineatingOption]:
    """What ``sheet`` can attach to a pose right now (#5177), for the composer's picker.

    A plea to make to each Sineater bonded to them who is here, and a plea to answer for each
    one waiting for them. Each is listed only when the pose could be posted: the pair share
    the active scene, the Sineater has not fallen, and they have not performed it there yet.

    The composer polls this, so the cheap exits come first: a character with no location or
    no live scene there gets ``[]`` before any bond is read. A partner who is not in the same
    place is skipped before the checks. The per-bond checks that follow are the pose path's
    own (``_checked_plea`` and ``_checked_performance``), so the picker never offers what the
    pose would refuse; they run once per bond and once per waiting plea, a handful at most.
    """
    try:
        location = sheet.character.location
    except ObjectDoesNotExist:
        return []
    if location is None or live_scene_at(location) is None:
        return []
    options: list[SineatingOption] = []
    tethers = CharacterRelationship.objects.filter(
        source=sheet, is_soul_tether=True, soul_tether_role=SoulTetherRole.SINNER
    ).select_related("target", "target__character")
    for relationship in tethers:
        if not _same_location(relationship.target, location):
            continue
        try:
            _, thread, _, cap = _checked_plea(sheet, relationship.target, 1_000_000)
        except SoulTetherError:
            continue
        options.append(
            SineatingOption(
                SineatingPoseRole.ENTREAT,
                relationship.target.pk,
                _name(relationship.target),
                cap,
                thread.resonance.name,
            )
        )
    pleas = SineatingPendingOffer.objects.filter(sineater_sheet=sheet).select_related(
        "sinner_sheet", "resonance", "scene"
    )
    for plea in pleas:
        # A plea gone stale is skipped here, not cleaned up: a read writes nothing.
        if not _same_location(plea.sinner_sheet, location):
            continue
        if not _in_scene_together(plea.sinner_sheet, sheet, plea.scene):
            continue
        try:
            _checked_performance(plea.sinner_sheet, sheet, plea.units_offered)
        except SoulTetherError:
            continue
        options.append(
            SineatingOption(
                SineatingPoseRole.PERFORM,
                plea.sinner_sheet.pk,
                _name(plea.sinner_sheet),
                plea.units_offered,
                plea.resonance.name,
            )
        )
    return options


def pose_failure_line(exc: SoulTetherError) -> str:
    """What the writer reads when the pose posted but the Sineating then did not happen."""
    return f"Your pose was posted, but the Sineating did not happen: {exc.user_message}"
