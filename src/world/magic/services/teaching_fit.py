"""Tradition teaching fit (slice 2 of #4659)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import GiftKind
from world.magic.models import (
    Affinity,
    CharacterGift,
    Gift,
    Tradition,
    TraditionGiftGrant,
    TraditionTeachingConfig,
)
from world.magic.types.teaching_fit import StudentTraits, TeachingFit

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_teaching_config() -> TraditionTeachingConfig:
    """Lazily create and return the singleton TraditionTeachingConfig (pk=1)."""
    config = TraditionTeachingConfig.objects.cached_singleton()
    if config is None:
        config, _ = TraditionTeachingConfig.objects.get_or_create(pk=1)
    return config


def teaching_fit(
    tradition: Tradition | None,
    gift: Gift | None,
    affinity: Affinity | None,
) -> TeachingFit:
    """Resolve how well ``tradition`` teaches ``gift`` to someone whose Gift is of ``affinity``.

    Gift fit: a TraditionGiftGrant(tradition, gift) exists. Affinity fit: ``affinity``
    is one of the Tradition's ``favored_affinities`` (matched by pk). The aura-based fit
    is deferred to #4672.
    """
    if tradition is None:
        return TeachingFit(None, False, False, None, None)
    gift_name = None
    if (
        gift is not None
        and TraditionGiftGrant.objects.filter(tradition=tradition, gift=gift).exists()
    ):
        gift_name = gift.name
    affinity_name = None
    if affinity is not None and tradition.favored_affinities.filter(pk=affinity.pk).exists():
        affinity_name = affinity.name
    return TeachingFit(
        tradition=tradition,
        gift_fit=gift_name is not None,
        affinity_fit=affinity_name is not None,
        favored_gift_name=gift_name,
        favored_affinity_name=affinity_name,
    )


def major_gift_for(sheet: CharacterSheet) -> Gift | None:
    """The sheet's Major Gift (the CharacterGift whose Gift is MAJOR), None when it has none."""
    row = (
        CharacterGift.objects.filter(character=sheet, gift__kind=GiftKind.MAJOR)
        .select_related("gift")
        .order_by("pk")
        .first()
    )
    return row.gift if row is not None else None


def gift_affinity_for(sheet: CharacterSheet, gift: Gift | None) -> Affinity | None:
    """The affinity of the resonance on the sheet's active GIFT thread for ``gift``.

    None when there is no Gift or no such thread. Reads the cached thread handler
    through ``gift_threads_for`` (a direct hold on ``gift`` sorts first). An active
    alternate self's resonance is deliberately not read: fit follows the student's own
    Gift thread, and ``gift_resonances_for`` would fall back to every resonance the Gift
    supports when there is no thread.
    """
    from world.magic.specialization.services import gift_threads_for  # noqa: PLC0415

    if gift is None:
        return None
    threads = gift_threads_for(sheet.character, gift)
    return threads[0].resonance.affinity if threads else None


def student_traits(sheet: CharacterSheet) -> StudentTraits:
    """The sheet's Major Gift and its Gift thread's affinity, what teaching fit reads."""
    gift = major_gift_for(sheet)
    return StudentTraits(major_gift=gift, affinity=gift_affinity_for(sheet, gift))


def student_fit(tradition: Tradition | None, student: StudentTraits) -> TeachingFit:
    """How well ``tradition`` teaches this student; no fit when there is no Tradition.

    The Academy's one entry point: the session ease (``npc_services.effects``) and the
    menu's fit line (``npc_services.services``) both call it.
    """
    return teaching_fit(tradition, student.major_gift, student.affinity)
