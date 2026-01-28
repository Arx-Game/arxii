"""
Action Points system models.

Action points represent time and effort characters invest in activities.
Characters have a pool with current/banked/maximum values, with regeneration
via cron (daily per game day, weekly).
"""

from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class ActionPointConfig(NaturalKeyMixin, SharedMemoryModel):
    """
    Global configuration for action point economy.

    Staff-editable settings for default values and regeneration rates.
    Only one config should be active at a time.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name for this configuration (e.g., 'Default', 'Event Mode').",
    )
    default_maximum = models.PositiveIntegerField(
        default=200,
        help_text="Default maximum AP for new characters.",
    )
    daily_regen = models.PositiveIntegerField(
        default=5,
        help_text="AP regenerated per game day via cron.",
    )
    weekly_regen = models.PositiveIntegerField(
        default=100,
        help_text="AP regenerated at weekly cron reset.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this config is currently active.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Action Point Config"
        verbose_name_plural = "Action Point Configs"

    def __str__(self) -> str:
        active = " (Active)" if self.is_active else ""
        return f"{self.name}{active}"

    @classmethod
    def get_active(cls) -> ActionPointConfig | None:
        """Get the currently active configuration."""
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def get_default_maximum(cls) -> int:
        """Get the default maximum AP from active config, or fallback."""
        config = cls.get_active()
        return config.default_maximum if config else 200

    @classmethod
    def get_daily_regen(cls) -> int:
        """Get daily regen amount from active config, or fallback."""
        config = cls.get_active()
        return config.daily_regen if config else 5

    @classmethod
    def get_weekly_regen(cls) -> int:
        """Get weekly regen amount from active config, or fallback."""
        config = cls.get_active()
        return config.weekly_regen if config else 100


class ActionPointPool(SharedMemoryModel):
    """
    A character's action point pool.

    Tracks current available AP, banked AP (committed to offers), and maximum.
    Provides methods for spending, banking, and regeneration.

    Behavior:
    - current: Available to spend on activities
    - banked: Committed to teaching offers, not spendable elsewhere
    - maximum: Cap for current (can be modified by distinctions)

    Regeneration fills current up to maximum. Banked is separate and
    does not block regeneration.

    Unbankng (cancelling offers) returns AP to current, capped at maximum.
    Any excess over maximum is lost.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="action_points",
        help_text="The character this pool belongs to.",
    )
    current = models.PositiveIntegerField(
        default=200,
        help_text="Currently available action points.",
    )
    maximum = models.PositiveIntegerField(
        default=200,
        help_text="Maximum action points (can be modified by distinctions).",
    )
    banked = models.PositiveIntegerField(
        default=0,
        help_text="Action points committed to pending offers.",
    )
    last_daily_regen = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of last daily regeneration.",
    )

    class Meta:
        verbose_name = "Action Point Pool"
        verbose_name_plural = "Action Point Pools"

    def __str__(self) -> str:
        return f"{self.character}: {self.current}/{self.maximum} (banked: {self.banked})"

    def spend(self, amount: int) -> bool:
        """
        Spend action points from current pool.

        Uses select_for_update to prevent race conditions.

        Args:
            amount: Number of AP to spend.

        Returns:
            True if successful, False if insufficient AP.
        """
        if amount < 0:
            return False

        with transaction.atomic():
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)
            if pool.current < amount:
                return False
            pool.current -= amount
            pool.save(update_fields=["current"])
            self.current = pool.current
        return True

    def bank(self, amount: int) -> bool:
        """
        Move action points from current to banked (for teaching offers).

        Uses select_for_update to prevent race conditions.

        Args:
            amount: Number of AP to bank.

        Returns:
            True if successful, False if insufficient current AP.
        """
        if amount < 0:
            return False

        with transaction.atomic():
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)
            if pool.current < amount:
                return False
            pool.current -= amount
            pool.banked += amount
            pool.save(update_fields=["current", "banked"])
            self.current = pool.current
            self.banked = pool.banked
        return True

    def unbank(self, amount: int) -> int:
        """
        Return banked AP to current pool, capped at effective maximum.

        When an offer is cancelled, the banked AP returns to current.
        If current is already at or near maximum, excess is lost.

        Uses select_for_update to prevent race conditions.
        Respects modifier-adjusted maximum (e.g., Efficient increases cap).

        Args:
            amount: Number of AP to unbank.

        Returns:
            Amount actually restored to current. May be less than amount
            if current was near maximum, or if amount > banked.
        """
        if amount < 0:
            return 0

        effective_max = self.get_effective_maximum()

        with transaction.atomic():
            # Lock row for update
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)

            # Can only unbank what's actually banked
            to_unbank = min(amount, pool.banked)

            # Can only restore up to effective maximum
            space_available = effective_max - pool.current
            actually_restored = min(to_unbank, max(0, space_available))

            # Full amount leaves banked (even if some is lost)
            pool.banked -= to_unbank
            # Only what fits goes to current
            pool.current += actually_restored
            pool.save(update_fields=["current", "banked"])

            # Update self to reflect changes
            self.current = pool.current
            self.banked = pool.banked

        return actually_restored

    def consume_banked(self, amount: int) -> bool:
        """
        Consume banked AP (when an offer is accepted).

        Unlike unbank, this removes from banked without returning to current.
        Uses select_for_update to prevent race conditions.

        Args:
            amount: Number of banked AP to consume.

        Returns:
            True if successful, False if insufficient banked AP.
        """
        if amount < 0:
            return False

        with transaction.atomic():
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)
            if pool.banked < amount:
                return False
            pool.banked -= amount
            pool.save(update_fields=["banked"])
            self.banked = pool.banked
        return True

    def regenerate(self, amount: int) -> int:
        """
        Add action points to current, capped at effective maximum.

        Banked AP is separate and does not affect regeneration.
        Uses select_for_update to prevent race conditions.
        Respects modifier-adjusted maximum (e.g., Efficient increases cap).

        Args:
            amount: Number of AP to add.

        Returns:
            Amount actually added (may be less if near maximum).
        """
        if amount < 0:
            return 0

        effective_max = self.get_effective_maximum()

        with transaction.atomic():
            # Lock row for update
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)

            space_available = effective_max - pool.current
            actually_added = min(amount, max(0, space_available))

            if actually_added > 0:
                pool.current += actually_added
                pool.save(update_fields=["current"])
                self.current = pool.current

        return actually_added

    def apply_daily_regen(self) -> int:
        """
        Apply daily regeneration and update timestamp.

        Called by cron job for daily AP regeneration.
        Uses select_for_update to prevent race conditions.
        Applies character modifiers (e.g., Indolent reduces regen, Efficient increases cap).

        Returns:
            Amount actually added (may be less if near maximum or 0 if modifiers reduce to 0).
        """
        base_regen = ActionPointConfig.get_daily_regen()
        regen_modifier = self._get_ap_modifier("ap_daily_regen")
        regen_amount = max(0, base_regen + regen_modifier)  # Floor at 0
        effective_max = self.get_effective_maximum()

        with transaction.atomic():
            pool = ActionPointPool.objects.select_for_update().get(pk=self.pk)

            space_available = effective_max - pool.current
            actually_added = min(regen_amount, max(0, space_available))

            pool.current += actually_added
            pool.last_daily_regen = timezone.now()
            pool.save(update_fields=["current", "last_daily_regen"])

            self.current = pool.current
            self.last_daily_regen = pool.last_daily_regen

        return actually_added

    def apply_weekly_regen(self) -> int:
        """
        Apply weekly regeneration.

        Called by cron job for weekly AP regeneration.
        Uses select_for_update to prevent race conditions.
        Applies character modifiers (e.g., Indolent reduces regen, Efficient increases cap).

        Returns:
            Amount actually added (may be less if near maximum or 0 if modifiers reduce to 0).
        """
        base_regen = ActionPointConfig.get_weekly_regen()
        regen_modifier = self._get_ap_modifier("ap_weekly_regen")
        regen_amount = max(0, base_regen + regen_modifier)  # Floor at 0
        return self.regenerate(regen_amount)

    def can_afford(self, amount: int) -> bool:
        """Check if character has enough current AP to spend."""
        return self.current >= amount

    def can_bank(self, amount: int) -> bool:
        """Check if character has enough current AP to bank."""
        return self.current >= amount

    def _get_ap_modifier(self, modifier_type_name: str) -> int:
        """
        Get the total modifier for an AP type from character's distinctions etc.

        Args:
            modifier_type_name: "ap_daily_regen", "ap_weekly_regen", or "ap_maximum"

        Returns:
            Total modifier value (can be negative). Returns 0 if no sheet or modifiers.
        """
        # Import here to avoid circular imports
        from world.mechanics.services import (  # noqa: PLC0415
            get_modifier_for_character,
        )

        return get_modifier_for_character(self.character, "action_points", modifier_type_name)

    def get_effective_maximum(self) -> int:
        """
        Get the effective maximum AP including modifiers.

        The stored `maximum` is the base value. This adds any modifiers
        from distinctions like Efficient.

        Returns:
            Effective maximum AP (base + modifiers, minimum 1).
        """
        modifier = self._get_ap_modifier("ap_maximum")
        return max(1, self.maximum + modifier)

    @classmethod
    def get_or_create_for_character(cls, character: ObjectDB) -> ActionPointPool:
        """
        Get or create an action point pool for a character.

        Uses default maximum from active config.
        """
        pool, _ = cls.objects.get_or_create(
            character=character,
            defaults={
                "maximum": ActionPointConfig.get_default_maximum(),
                "current": ActionPointConfig.get_default_maximum(),
            },
        )
        return pool
