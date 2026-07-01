"""Post-CG gift acquisition models (#1587).

GiftUnlock is the authored XP-gate catalog (which Minor Gifts are
purchasable, at what cost). CharacterGiftUnlock is the per-character
receipt. TechniqueTeachingOffer is the teacher-facing offer (mirrors
CodexTeachingOffer / ThreadWeavingTeachingOffer). GiftAcquisitionConfig
is the singleton tuning config.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import GiftKind


class GiftUnlock(SharedMemoryModel):
    """Authored catalog of XP-purchasable Minor Gifts (ADR-0053).

    One row per acquirable gift. ``gift.kind`` must be ``MINOR`` — enforced
    in ``clean()``. XP cost is the gate; acquisition is a separate step
    behind this gate (accepting a TechniqueTeachingOffer).
    """

    gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        related_name="gift_unlocks",
        help_text="The Minor Gift this unlock gates. Must be kind=MINOR.",
    )
    xp_cost = models.PositiveIntegerField(
        help_text="Base XP cost; multiplied by out_of_path_multiplier when out-of-Path.",
    )
    paths = models.ManyToManyField(
        "classes.Path",
        related_name="gift_unlocks",
        blank=True,
        help_text="Paths that treat this unlock as in-band (full xp_cost). Blank = all paths.",
    )
    out_of_path_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.0"),
        help_text="Cost multiplier applied when buyer's Path is not in `paths`.",
    )

    class Meta:
        verbose_name = "Gift Unlock"
        verbose_name_plural = "Gift Unlocks"

    def __str__(self) -> str:
        return f"GiftUnlock: {self.gift.name if self.gift_id else '—'}"

    def clean(self) -> None:
        """Enforce gift.kind == MINOR."""
        if self.gift_id and self.gift.kind != GiftKind.MINOR:
            raise ValidationError(
                {
                    "gift": (
                        f"GiftUnlock requires a MINOR gift; {self.gift.name} is {self.gift.kind}."
                    )
                },
            )


class CharacterGiftUnlock(SharedMemoryModel):
    """Per-character XP-purchase receipt for a GiftUnlock.

    One row per (character, unlock). Records the actual XP paid and
    optionally the teacher who facilitated. The existence of this row
    is the gate — it permits acquisition of the gift via
    ``accept_technique_offer``.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="gift_unlocks",
        help_text="Character who purchased this unlock.",
    )
    unlock = models.ForeignKey(
        GiftUnlock,
        on_delete=models.PROTECT,
        related_name="character_purchases",
        help_text="Authored unlock the character purchased.",
    )
    xp_spent = models.PositiveIntegerField(
        help_text="Actual XP paid (in-Path: xp_cost; out-of-Path: xp_cost * multiplier).",
    )
    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gift_unlocks_taught",
        help_text="Teacher RosterTenure when applicable; audit only.",
    )
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("character", "unlock"),)
        verbose_name = "Character Gift Unlock"
        verbose_name_plural = "Character Gift Unlocks"

    def __str__(self) -> str:
        return f"CharacterGiftUnlock<{self.character_id} -> {self.unlock_id}>"


class TechniqueTeachingOffer(SharedMemoryModel):
    """Teacher-side offer to teach a specific technique (#1587).

    Mirrors CodexTeachingOffer / ThreadWeavingTeachingOffer. The teacher
    commits AP upfront (banked); the learner pays AP + optional gold on
    acceptance. If the learner doesn't yet have the technique's gift,
    acceptance implicitly acquires it (via grant_gift_to_character).
    """

    teacher = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="technique_teaching_offers",
        help_text="Tenure (player-character instance) offering to teach.",
    )
    technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        related_name="teaching_offers",
        help_text="The technique being offered.",
    )
    pitch = models.TextField(
        help_text="Player-written description of what they're offering to teach.",
    )
    learn_ap_cost = models.PositiveIntegerField(
        default=5,
        help_text="AP the learner pays to accept. Teacher sets this per offer.",
    )
    gold_cost = models.PositiveIntegerField(
        default=0,
        help_text="Optional gold payment required from learner.",
    )
    banked_ap = models.PositiveIntegerField(
        help_text="AP committed from teacher's pool.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Technique Teaching Offer"
        verbose_name_plural = "Technique Teaching Offers"

    def __str__(self) -> str:
        return f"{self.teacher} teaches {self.technique.name if self.technique_id else '—'}"

    def cancel(self) -> int:
        """Cancel offer, return banked AP to teacher.

        Returns:
            Amount of AP actually restored to teacher's pool.
        """
        from world.action_points.models import ActionPointPool  # noqa: PLC0415

        pool = ActionPointPool.get_or_create_for_character(self.teacher.character)
        restored = pool.unbank(self.banked_ap)
        self.delete()
        return restored


class GiftAcquisitionConfig(SharedMemoryModel):
    """Singleton tuning config for gift acquisition (#1587).

    Fields are staff-tunable via admin; lazy-created by
    ``get_gift_acquisition_config()`` in services/gift_acquisition.py.
    """

    techniques_per_thread_level = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Max techniques a character can learn per gift per thread level. Variants excluded."
        ),
    )
    first_technique_ap_multiplier = models.PositiveIntegerField(
        default=3,
        help_text="AP cost multiplier for the first technique from a not-yet-acquired gift.",
    )
    major_gift_ap_multiplier = models.PositiveIntegerField(
        default=1,
        help_text="AP cost multiplier for techniques from a MAJOR gift (1 = same as Minor).",
    )

    class Meta:
        verbose_name = "Gift Acquisition Config"
        verbose_name_plural = "Gift Acquisition Config"

    def __str__(self) -> str:
        return f"GiftAcquisitionConfig(pk={self.pk})"
