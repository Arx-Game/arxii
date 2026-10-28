"""
CharacterEngagement — what a character is actively doing that has stakes.

Process modifiers (intensity_modifier, control_modifier) live here rather than
as CharacterModifier records because they are transient bonuses tied to the
engagement itself. They represent situational advantages from the current
activity (e.g., momentum in combat, focus during a challenge) and are
discarded when the engagement ends. Identity modifiers (from distinctions,
equipment, conditions) live in CharacterModifier and persist independently
of what the character is currently doing.
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.mechanics.constants import EngagementType


class CharacterEngagement(SharedMemoryModel):
    """
    First-class representation of a character's current stakes-bearing activity.

    A character can be engaged in at most one activity at a time (OneToOne).
    The engagement is observable by other characters and carries process
    modifier fields for transient intensity/control bonuses that apply only
    while the character is engaged.

    Process modifiers vs identity modifiers:
    - Process modifiers (intensity_modifier, control_modifier) are transient
      bonuses from the current activity — discarded when engagement ends.
    - Identity modifiers (CharacterModifier records) persist independently
      of engagement and come from distinctions, equipment, conditions, etc.
    """

    character = models.OneToOneField(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="engagement",
        help_text="The character who is engaged.",
    )
    engagement_type = models.CharField(
        max_length=20,
        choices=EngagementType.choices,
        help_text="What kind of stakes-bearing activity.",
    )
    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Content type of the engagement source.",
    )
    source_id = models.PositiveIntegerField(
        help_text="PK of the engagement source object.",
    )
    source = GenericForeignKey("source_content_type", "source_id")
    escalation_level = models.PositiveIntegerField(
        default=0,
        help_text="How much pressure has built up. Managed by the engaging system.",
    )
    intensity_modifier = models.IntegerField(
        default=0,
        help_text="Process-derived intensity bonus (escalation, Audere, combat events).",
    )
    control_modifier = models.IntegerField(
        default=0,
        help_text="Process-derived control bonus (process state only).",
    )
    free_dig_deeps = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Dig deeps this character may take in combat without paying fatigue, granted by "
            "an ally's successful Rally. Spent one per dig deep; ends with the engagement."
        ),
    )
    free_dig_deeps_given_by = models.ForeignKey(
        "arxii.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The ally whose encouragement most recently granted free dig deeps.",
    )
    last_dug_deep_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The combat round number in which this character last dug deep. Set by "
            "the dig deep service, which refuses a second dig deep in the same round whatever "
            "the roll or band gave."
        ),
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the engagement began.",
    )

    class Meta:
        verbose_name = "Character Engagement"
        verbose_name_plural = "Character Engagements"

    def __str__(self) -> str:
        return f"{self.character} \u2014 {self.get_engagement_type_display()}"
