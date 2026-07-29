"""Species-gift provisioning (#1580, ADR-0050). Called from CG finalize."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.conditions.services import (
    advance_condition_severity,
    apply_condition,
    decay_condition_severity,
    has_condition,
    remove_condition,
)
from world.scenes.round_services import ensure_round_for_acute_condition
from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.gifts import CharacterGift

logger = logging.getLogger(__name__)


def reconcile_sun_exposure_safely(character) -> None:
    """Best-effort reconcile for hook/cron call sites (#2846).

    Skips non-characters cheaply; isolates any reconcile failure so an equip,
    position change, or cron sweep never breaks on a bad row. Log-and-continue
    is the interim policy (#1164) — never a silent suppress.
    """
    try:
        sheet = character.character_sheet
    except AttributeError:
        return
    if sheet is None:
        return
    try:
        reconcile_sunlight_exposure(character, character.location)
    except Exception:  # the ONE ratcheted broad guard shared by every hook site
        logger.exception("sun-exposure reconcile failed for character pk=%s", character.pk)


def reconcile_sunlight_exposure(character, room) -> None:
    """Reconcile the Sunlight Exposure condition to the character's felt sun exposure
    (#1588, #1744, graded #2846).

    Sensitivity is distinction-anchored (``sun_sensitivity_for`` — the sun-bane /
    sun-allergy DistinctionTags), never species-probed: innate and voluntarily-taken
    tiers behave identically. The tier maps the felt-exposure breakdown
    (``felt_sun_exposure``) to a target condition severity; severity drives the
    template's stages, so low severities only impair while Burning+ carries the
    radiant DoT. Sustained exposure escalates: continuous IC hours under the
    condition add severity up to a cap.

    When the condition sits in a damaging stage, ensures a danger scene round (the
    plummet pattern) so the existing round-tick processes the DoT through the peril
    pipeline — AFK-safety (ADR-0004/ADR-0049) holds unchanged: an unconscious victim
    flows into ``abandonment_environmental``, never a raw death.

    No-op for characters without a sheet; removes any stale condition when the
    character no longer holds a sun-sensitivity distinction.

    Args:
        character: the ObjectDB character whose exposure to reconcile.
        room: the room the character is in (may be None — treated as indoor).
    """
    from world.species.factories import ensure_sunlight_exposure_content  # noqa: PLC0415
    from world.species.sun_exposure import felt_sun_exposure  # noqa: PLC0415
    from world.species.sun_sensitivity import (  # noqa: PLC0415
        SunSensitivity,
        sun_sensitivity_for,
        sun_severity,
    )

    sheet = character.character_sheet
    if sheet is None:
        return
    tier = sun_sensitivity_for(sheet)
    if tier == SunSensitivity.NONE:
        # Cheap path for the hot hooks (movement/equip): no content-ensure unless
        # a stale condition actually needs clearing.
        from world.conditions.models import ConditionTemplate  # noqa: PLC0415
        from world.species.factories import SUNLIGHT_EXPOSURE_NAME  # noqa: PLC0415

        template = ConditionTemplate.objects.filter(name=SUNLIGHT_EXPOSURE_NAME).first()
        if template is not None and has_condition(character, template):
            remove_condition(character, template)
        return
    template = ensure_sunlight_exposure_content()
    exposure = felt_sun_exposure(character, room)
    target_severity = sun_severity(tier, exposure)
    instance = _active_sunlight_instance(character, template)
    if instance is not None and target_severity > 0:
        target_severity += _sun_escalation_bonus(instance)
    instance = _sync_condition_severity(character, template, instance, target_severity)
    if instance is not None and _in_damaging_stage(instance):
        ensure_round_for_acute_condition(sheet)


def _sync_condition_severity(character, template, instance, target_severity: int):
    """Move the active instance's severity to *target_severity* (apply/advance/decay/remove).

    Returns the (possibly newly created) active instance, or None when the
    condition ended at severity 0.
    """
    if target_severity <= 0:
        if instance is not None:
            remove_condition(character, template)
        return None
    if instance is None:
        # Apply at severity 1, then advance to target: apply_condition always starts
        # at the FIRST stage regardless of severity, while advance_condition_severity
        # re-picks the stage by threshold — one code path keeps stage and severity
        # consistent.
        apply_condition(character, template, severity=1)
        instance = _active_sunlight_instance(character, template)
        if instance is not None and target_severity > 1:
            advance_condition_severity(instance, target_severity - 1)
        return instance
    if target_severity > instance.severity:
        advance_condition_severity(instance, target_severity - instance.severity)
    elif target_severity < instance.severity:
        decay_condition_severity(instance, instance.severity - target_severity)
    return instance


def _active_sunlight_instance(character, template):
    """The unresolved Sunlight Exposure ConditionInstance for *character*, or None."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character, condition=template, resolved_at__isnull=True
    ).first()


def _sun_escalation_bonus(instance) -> int:
    """Extra severity from sustained exposure: +1 per ESCALATION_IC_HOURS, capped.

    Derived from the instance's ``applied_at`` age in IC time — deterministic,
    no extra state; leaving the sun resets it because the instance is removed.
    """
    from world.game_clock.services import get_ic_date_for_real_time, get_ic_now  # noqa: PLC0415
    from world.species.sun_constants import (  # noqa: PLC0415
        ESCALATION_CAP,
        ESCALATION_IC_HOURS,
    )

    ic_now = get_ic_now()
    ic_applied = get_ic_date_for_real_time(instance.applied_at)
    if ic_now is None or ic_applied is None:
        return 0
    elapsed_hours = max(0.0, (ic_now - ic_applied).total_seconds() / 3600.0)
    return min(ESCALATION_CAP, int(elapsed_hours // ESCALATION_IC_HOURS))


def _in_damaging_stage(instance) -> bool:
    """Whether the instance's current stage carries the radiant DoT (Burning+)."""
    from world.species.sun_constants import BURNING_SEVERITY_THRESHOLD  # noqa: PLC0415

    return instance.severity >= BURNING_SEVERITY_THRESHOLD


def _species_and_ancestors(species):
    """Return [species, parent, grandparent, ...] walking the parent chain.

    Assumes an acyclic parent chain (data-hygiene invariant); the while is bounded.
    """
    chain, node = [], species
    while node is not None:
        chain.append(node)
        node = node.parent
    return chain


def _own_and_inheritable_ancestor_pks(species):
    """Return (own_pk, ancestor_pks) for the species parent chain.

    own_pk is the species' own PK (all grants fetched, inheritable or not).
    ancestor_pks is the list of ancestor PKs (only inheritable=True grants fetched).
    """
    chain = _species_and_ancestors(species)
    own_pk = chain[0].pk
    ancestor_pks = [s.pk for s in chain[1:]]
    return own_pk, ancestor_pks


def _inheritable_grant_filter(species):
    """Build a Q filter for SpeciesGiftGrant that respects the inheritable flag.

    Own species: all grants (including non-inheritable).
    Ancestor species: only inheritable=True grants.
    """
    own_pk, ancestor_pks = _own_and_inheritable_ancestor_pks(species)
    from django.db.models import Q  # noqa: PLC0415

    return Q(species_id=own_pk) | Q(species_id__in=ancestor_pks, inheritable=True)


def _apply_permanent_condition_once(character, condition) -> None:
    """Apply *condition* to *character* once, idempotently (drawback/benefit conditions)."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    already_applied = ConditionInstance.objects.filter(
        target=character,
        condition=condition,
        resolved_at__isnull=True,
    ).exists()
    if not already_applied:
        apply_condition(character, condition)


def _grant_species_distinction_once(sheet, distinction) -> None:
    """Mint *distinction* on the sheet as a species-forced drawback, idempotently.

    Uses the canonical grant seam; explicit rank=1 makes a re-finalize a no-op
    (set-only, never a rank-up) so double provisioning cannot escalate the price.
    """
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    grant_distinction(sheet, distinction, origin=DistinctionOrigin.SPECIES, rank=1)


def total_species_gift_cost(species) -> int:
    """Total CG-point cost of a species' gift grants, summed over it and its ancestors.

    Mirrors provision_species_gifts' species+ancestor walk so a subspecies is charged
    for a parent's costed grant. Returns 0 for a species with no costed grants.
    """
    from django.db.models import Sum  # noqa: PLC0415

    return (
        SpeciesGiftGrant.objects.filter(_inheritable_grant_filter(species))
        .aggregate(total=Sum("cg_point_cost"))
        .get("total")
        or 0
    )


def provision_species_gifts(sheet: CharacterSheet, *, resonance=None) -> list[CharacterGift]:
    """Mint the species' Minor Gift(s) + latent GIFT thread + any drawback. Idempotent.

    ``resonance`` is the player's CG-chosen gift resonance (the same value the Major-gift
    block resolves). When None, falls back to each gift's first supported resonance.

    Called from finalize_magic_data after the Major-gift block so the species
    gift thread anchors to the same resonance as the player's Major-gift thread.
    """
    from world.magic.specialization.services import grant_gift_to_character  # noqa: PLC0415

    if sheet.species_id is None:
        return []

    grants = SpeciesGiftGrant.objects.filter(
        _inheritable_grant_filter(sheet.species)
    ).select_related("gift", "drawback_condition", "benefit_condition", "drawback_distinction")
    minted: list[CharacterGift] = []
    for grant in grants:
        res = resonance or grant.gift.resonances.first()
        cg, _ = grant_gift_to_character(sheet, grant.gift, resonance=res)
        minted.append(cg)
        if grant.drawback_condition_id is not None:
            _apply_permanent_condition_once(sheet.character, grant.drawback_condition)
        if grant.benefit_condition_id is not None:
            _apply_permanent_condition_once(sheet.character, grant.benefit_condition)
        if grant.drawback_distinction_id is not None:
            _grant_species_distinction_once(sheet, grant.drawback_distinction)
    return minted
