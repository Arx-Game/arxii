"""Boon: a structured social ask riding SceneActionRequest (#2540).

A Boon names what an asker wants from a target — money, a held item, a vault item, or a
deed — and attaches to the ``SceneActionRequest`` that carries the persuade/con/seduce/
intimidate roll. On a successful roll the Boon action fulfills it (mirroring how
``BlackmailAction`` mints Leverage on a successful press). Specifying the ask up front is
what lets a piloted target gauge whether it's an easy "just no."

Every kind fulfills: ``MONEY`` through the single currency mutation point, ``HELD_ITEM``
through a lean sheet-level hand-over, ``VAULT_ITEM`` through the org vault's audited
withdraw, and ``DEED`` is RP-only (no mechanical transfer, RP resolution only). The
per-Boon affection cost (each granted Boon stacks) is charged by the ``boon`` resolver —
see ``boon_services.py`` and the umbrella spec #2540.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.action_constants import BoonKind, BoonSumTier


class Boon(SharedMemoryModel):
    """The payload of a structured social ask, attached to its ``SceneActionRequest``."""

    action_request = models.OneToOneField(
        "arxii.SceneActionRequest",
        on_delete=models.CASCADE,
        related_name="boon",
    )
    kind = models.CharField(max_length=20, choices=BoonKind.choices)
    sum_tier = models.CharField(
        max_length=20,
        choices=BoonSumTier.choices,
        blank=True,
        default="",
        help_text=(
            "The relative sum asked, for MONEY boons (#2540 ruling) — minor/fair/great "
            "*to the target*. The concrete coppers freeze into ``amount`` at ask time."
        ),
    )
    amount = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers asked, for MONEY boons — derived from sum_tier at ask time.",
    )
    item_instance = models.ForeignKey(
        "arxii.ItemInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The named item asked, for HELD_ITEM / VAULT_ITEM boons.",
    )
    deed_text = models.TextField(
        blank=True, help_text="The deed asked, for DEED boons (RP; no mechanical transfer)."
    )
    material_category = models.ForeignKey(
        "arxii.MaterialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Crafting-equivalence class asked for material-boon completion (#2540 slice "
            "3, consumed by Task 2). Null when the ask is not material-scoped."
        ),
    )
    fulfilled_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when a successful Boon has been fulfilled."
    )

    class Meta:
        app_label = "arxii"

    def __str__(self) -> str:
        return f"Boon({self.kind}) on request {self.action_request_id}"
