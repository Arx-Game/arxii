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
from evennia.utils.idmapper.models import SharedMemoryModel

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
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="engagement",
    )
    engagement_type = models.CharField(
        max_length=20,
        choices=EngagementType.choices,
    )
    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    source_id = models.PositiveIntegerField()
    source = GenericForeignKey("source_content_type", "source_id")
    escalation_level = models.PositiveIntegerField(default=0)
    intensity_modifier = models.IntegerField(default=0)
    control_modifier = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.character} \u2014 {self.get_engagement_type_display()}"
