"""Idempotent seeds for the Sanctum subsystem (Plan 4 §F).

Seeds the five SERVICE Ritual rows (Homecoming, Purging, Personal and Covenant
Sanctification, Dissolution) wired to the dispatch paths in
``world.magic.services.sanctum_rituals`` and
``world.magic.services.sanctum_install``.  Per repo discipline (#683): seeds
live in code, called via ``get_or_create``.  NOT a committed fixture.

CheckType / CheckCategory authoring lives in ``world.magic.seeds_checks``
(#709); ``ensure_sanctum_rituals()`` creates the Ritual rows first, then calls
``seeds_checks.ensure_ritual_check_configs()`` to bind their check configs.
"""

from __future__ import annotations

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual
from world.seeds.sample_content import authored_or_sample

HOMECOMING_RITUAL_NAME = "Ritual of Homecoming"
PURGING_RITUAL_NAME = "Ritual of Purging"
SANCTIFICATION_PERSONAL_RITUAL_NAME = "Ritual of Thine Own Sanctum"
SANCTIFICATION_COVENANT_RITUAL_NAME = "Ritual of Blood Covenant Sanctification"
DISSOLUTION_RITUAL_NAME = "Ritual of Dissolution"


def ensure_homecoming_ritual() -> Ritual | None:
    """Look up (or, under ``SEED_SAMPLE_CONTENT``, invent) the Ritual of Homecoming row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_homecoming_ritual``
    at perform time. Single-actor (the leader) — covenant manager / personal
    owner per the service's own validation. Content-repo-owned (#2698): returns
    ``None`` when the row isn't authored and sample content is off.
    """
    return authored_or_sample(
        Ritual,
        {
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
        name=HOMECOMING_RITUAL_NAME,
    )


def ensure_purging_ritual() -> Ritual | None:
    """Look up (or, under ``SEED_SAMPLE_CONTENT``, invent) the Ritual of Purging row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_purging_ritual``.
    Changes the Sanctum's consecrated resonance type, draining grown
    resonance to a retention fraction. Content-repo-owned (#2698).
    """
    return authored_or_sample(
        Ritual,
        {
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
        name=PURGING_RITUAL_NAME,
    )


def ensure_sanctification_personal_ritual() -> Ritual | None:
    """Look up (or invent under the sample flag) ``Ritual of Thine Own Sanctum``.

    PLACEHOLDER prose throughout — author replaces in their voice.
    SERVICE-dispatched to
    ``world.magic.services.sanctum_install.perform_sanctification``;
    the service function sets ``owner_mode=PERSONAL`` from this ritual's
    invocation context. Content-repo-owned (#2698).
    """
    return authored_or_sample(
        Ritual,
        {
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
        name=SANCTIFICATION_PERSONAL_RITUAL_NAME,
    )


def ensure_sanctification_covenant_ritual() -> Ritual | None:
    """Look up (or invent under the sample flag) ``Ritual of Blood Covenant Sanctification``.

    SERVICE-dispatched; service function sets ``owner_mode=COVENANT``.
    Interim leader gate (any active covenant member) lives at the
    service layer until #708 ships proper org-ritual permissions.
    Content-repo-owned (#2698).
    """
    return authored_or_sample(
        Ritual,
        {
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
        name=SANCTIFICATION_COVENANT_RITUAL_NAME,
    )


def ensure_dissolution_ritual() -> Ritual | None:
    """Look up (or invent under the sample flag) ``Ritual of Dissolution``.

    SERVICE-dispatched. Service function rolls a ``Sanctum Dissolution``
    magical check (seeded via ``world.magic.seeds_checks``). Outcome tier
    determines fraction of imbued reservoir recovered. Content-repo-owned (#2698).
    """
    return authored_or_sample(
        Ritual,
        {
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
        name=DISSOLUTION_RITUAL_NAME,
    )


def _link_install_ritual_to_sanctum(ritual: Ritual | None, variant_label: str) -> None:
    """Idempotent RoomFeatureKindInstallRitual link from the magic side.

    No-ops when ``ritual`` is ``None`` — the content repo hasn't authored it
    and sample content is off (#2698); there's nothing to link yet.
    """
    if ritual is None:
        return
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
    the Sanctum ``RoomFeatureKind`` via ``RoomFeatureKindInstallRitual``, attaches
    the touchstone/reagent ``RitualComponentRequirement`` rows (#707) to both
    Sanctification rituals, then calls ``seeds_checks.ensure_ritual_check_configs()``
    to bind CheckType/RitualCheckConfig rows for all five rituals.

    Every Ritual row is content-repo-owned (#2698): each ``ensure_*_ritual()``
    call returns ``None`` (after logging) when the content repo hasn't authored
    it and ``SEED_SAMPLE_CONTENT`` is off, and the config wired to a missing
    ritual (its install link + component requirements) is skipped in step.
    """
    ensure_homecoming_ritual()
    ensure_purging_ritual()
    personal = ensure_sanctification_personal_ritual()
    covenant = ensure_sanctification_covenant_ritual()
    ensure_dissolution_ritual()
    _link_install_ritual_to_sanctum(personal, "Personal")
    _link_install_ritual_to_sanctum(covenant, "Covenant")

    from world.magic.seeds_touchstone_content import (  # noqa: PLC0415
        ensure_sanctification_requirements,
    )

    if personal is not None:
        ensure_sanctification_requirements(personal)
    if covenant is not None:
        ensure_sanctification_requirements(covenant)

    from world.magic.seeds_checks import ensure_ritual_check_configs  # noqa: PLC0415

    ensure_ritual_check_configs()
