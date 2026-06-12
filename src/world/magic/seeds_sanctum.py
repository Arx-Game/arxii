"""Idempotent seeds for the Sanctum subsystem (Plan 4 §F).

Seeds the five SERVICE Ritual rows (Homecoming, Purging, Personal and Covenant
Sanctification, Dissolution) wired to the dispatch paths in
``world.magic.services.sanctum_rituals`` and
``world.magic.services.sanctum_install``.  Per repo discipline (#683): seeds
live in code, called via ``get_or_create``.  NOT a committed fixture.

CheckType / CheckCategory authoring lives in ``world.magic.seeds_checks``
(#709); call ``ensure_sanctum_rituals()`` after the Ritual rows exist so
``seeds_checks.ensure_ritual_check_configs()`` can bind them.
"""

from __future__ import annotations

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual

HOMECOMING_RITUAL_NAME = "Ritual of Homecoming"
PURGING_RITUAL_NAME = "Ritual of Purging"
SANCTIFICATION_PERSONAL_RITUAL_NAME = "Ritual of Thine Own Sanctum"
SANCTIFICATION_COVENANT_RITUAL_NAME = "Ritual of Blood Covenant Sanctification"
DISSOLUTION_RITUAL_NAME = "Ritual of Dissolution"


def ensure_homecoming_ritual() -> Ritual:
    """Get-or-create the Ritual of Homecoming row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_homecoming_ritual``
    at perform time. Single-actor (the leader) — covenant manager / personal
    owner per the service's own validation.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=HOMECOMING_RITUAL_NAME,
        defaults={
            "description": (
                "Consecrate a Sanctum by sacrificing your own resonance into "
                "its grown reservoir. The Sanctum's per-day income to woven "
                "weavers grows as you imbue more, capped per your Path level."
            ),
            "narrative_prose": (
                "You kneel at the heart of the Sanctum. Resonance unspools "
                "from your soul like silk and settles into the room's "
                "ambient pool, thickening it. The walls drink in your "
                "intention; the Sanctum knows you a little better."
            ),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_rituals.perform_homecoming_ritual"
            ),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_purging_ritual() -> Ritual:
    """Get-or-create the Ritual of Purging row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_purging_ritual``.
    Changes the Sanctum's consecrated resonance type, draining grown
    resonance to a retention fraction.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=PURGING_RITUAL_NAME,
        defaults={
            "description": (
                "Re-consecrate a Sanctum to a different resonance type. "
                "Half of the imbued reservoir is destroyed; surviving threads "
                "adopt the new type."
            ),
            "narrative_prose": (
                "You burn the old pattern out of the Sanctum's bones. "
                "Resonance gutters and reignites in a foreign key. The room "
                "is the same room — and a different one."
            ),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_rituals.perform_purging_ritual"
            ),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_sanctification_personal_ritual() -> Ritual:
    """Get-or-create ``Ritual of Thine Own Sanctum`` (Personal Sanctification).

    PLACEHOLDER prose throughout — author replaces in their voice.
    SERVICE-dispatched to
    ``world.magic.services.sanctum_install.perform_sanctification``;
    the service function sets ``owner_mode=PERSONAL`` from this ritual's
    invocation context.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=SANCTIFICATION_PERSONAL_RITUAL_NAME,
        defaults={
            "description": (
                "PLACEHOLDER — Personal Sanctification: the witch declares a "
                "room as their own home and consecrates it."
            ),
            "narrative_prose": ("PLACEHOLDER — narrative prose for personal Sanctification."),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_install.perform_sanctification"
            ),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_sanctification_covenant_ritual() -> Ritual:
    """Get-or-create ``Ritual of Blood Covenant Sanctification``.

    SERVICE-dispatched; service function sets ``owner_mode=COVENANT``.
    Interim leader gate (any active covenant member) lives at the
    service layer until #708 ships proper org-ritual permissions.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=SANCTIFICATION_COVENANT_RITUAL_NAME,
        defaults={
            "description": (
                "PLACEHOLDER — Covenant Sanctification: a covenant rite "
                "consecrating a room as their sacred ground."
            ),
            "narrative_prose": ("PLACEHOLDER — narrative prose for covenant Sanctification."),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_install.perform_sanctification"
            ),
            "participation_rule": ParticipationRule.FORMATION,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_dissolution_ritual() -> Ritual:
    """Get-or-create ``Ritual of Dissolution``.

    SERVICE-dispatched. Service function rolls a ``Sanctum Dissolution``
    magical check (seeded via ``world.magic.seeds_checks``). Outcome tier
    determines fraction of imbued reservoir recovered.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=DISSOLUTION_RITUAL_NAME,
        defaults={
            "description": (
                "PLACEHOLDER — Dissolution: tear down a Sanctum, recovering "
                "a fraction of its imbued resonance as the witch's own."
            ),
            "narrative_prose": ("PLACEHOLDER — narrative prose for Dissolution."),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": ("world.magic.services.sanctum_install.perform_dissolution"),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def _link_install_ritual_to_sanctum(ritual: Ritual, variant_label: str) -> None:
    """Idempotent RoomFeatureKindInstallRitual link from the magic side."""
    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureKind,
        RoomFeatureKindInstallRitual,
    )
    from world.room_features.seeds import SANCTUM_KIND_NAME  # noqa: PLC0415

    sanctum_kind = RoomFeatureKind.objects.filter(name=SANCTUM_KIND_NAME).first()
    if sanctum_kind is None:
        return  # Sanctum kind not yet seeded; will link on next call
    RoomFeatureKindInstallRitual.objects.get_or_create(
        feature_kind=sanctum_kind,
        ritual=ritual,
        defaults={"variant_label": variant_label},
    )


def ensure_sanctum_rituals() -> None:
    """Seed all Sanctum Ritual rows + check content. Safe to call repeatedly.

    Seeds the five SERVICE Ritual rows, wires the two Sanctification rows to
    the Sanctum ``RoomFeatureKind`` via ``RoomFeatureKindInstallRitual``, then
    calls ``seeds_checks.ensure_ritual_check_configs()`` to bind
    CheckType/RitualCheckConfig rows for all five rituals.
    """
    ensure_homecoming_ritual()
    ensure_purging_ritual()
    personal = ensure_sanctification_personal_ritual()
    covenant = ensure_sanctification_covenant_ritual()
    ensure_dissolution_ritual()
    _link_install_ritual_to_sanctum(personal, "Personal")
    _link_install_ritual_to_sanctum(covenant, "Covenant")

    from world.magic.seeds_checks import ensure_ritual_check_configs  # noqa: PLC0415

    ensure_ritual_check_configs()
