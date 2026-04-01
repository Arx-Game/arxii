"""
Random Scene models for the progression system.

Players receive 5 weekly target personas to RP with. Claiming a target
awards XP. The completion record is permanent and tracks who you have
completed with, to weight future targets toward strangers and award
first-time bonuses.

Targets use Persona (the IC identity to meet), while the claimer side
uses RosterEntry (the OOC player-character link).
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel


class RandomSceneTarget(SharedMemoryModel):
    """A weekly target persona assigned to a player for the Random Scene system.

    Each account gets up to 5 target slots per week. Claiming a slot awards XP.
    """

    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="random_scene_targets",
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="targeted_for_random_scene",
        help_text="The persona (IC identity) to RP with",
    )
    week_start = models.DateField(
        help_text="Monday of the RS week (ISO week start)",
    )
    slot_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    claimed = models.BooleanField(default=False)
    claimed_at = models.DateTimeField(null=True, blank=True)
    first_time = models.BooleanField(
        default=False,
        help_text="First RS completion with this target ever",
    )
    rerolled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "week_start", "slot_number"],
                name="unique_rs_target_per_slot",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"RS target: {self.account} → {self.target_persona}"
            f" (week {self.week_start}, slot {self.slot_number})"
        )


class RandomSceneCompletion(SharedMemoryModel):
    """Permanent record of an account completing a Random Scene with a target persona.

    Only one completion record exists per (account, target_persona) pair,
    used to weight future target selection toward strangers and determine
    first-time bonuses.
    """

    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="random_scene_completions",
    )
    claimer_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="random_scene_claimed_as",
        help_text="Which of the claimer's characters they were playing",
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="random_scene_completed_by",
        help_text="The target persona that was RP'd with",
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "target_persona"],
                name="unique_rs_completion_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"RS completion: {self.claimer_entry} → {self.target_persona}"
