"""RitualSceneActionConfig: sidecar model for SCENE_ACTION rituals.

Holds the check specification a player's anima ritual fires when invoked.
Exists iff the parent Ritual.execution_kind is SCENE_ACTION.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class RitualSceneActionConfig(SharedMemoryModel):
    """Per-Ritual configuration for SCENE_ACTION dispatch.

    Holds the check spec a player's anima ritual fires when invoked. Exists
    iff the parent Ritual.execution_kind is SCENE_ACTION. The 1:1 relationship
    is enforced by the OneToOneField. The invariant that SCENE_ACTION rituals
    must have a sidecar (and non-SCENE_ACTION rituals must not) is enforced
    in Ritual.clean().

    FK paths mirror CharacterAnimaRitual: stat/skill → traits.Trait /
    skills.Skill, specialization → skills.Specialization,
    check_type → checks.CheckType.
    """

    ritual = models.OneToOneField(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="scene_action_config",
    )
    stat = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        limit_choices_to={"trait_type": "stat"},
        related_name="+",
        help_text="The primary stat used in this ritual's check.",
    )
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The skill used in this ritual's check.",
    )
    specialization = models.ForeignKey(
        "skills.Specialization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional specialization for this ritual's check.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional resonance filter for this ritual.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="CheckType used when rolling this ritual's check.",
    )
    target_difficulty = models.PositiveSmallIntegerField(
        default=3,
        help_text="Target difficulty for the check.",
    )

    class Meta:
        verbose_name = "Ritual Scene Action Config"
        verbose_name_plural = "Ritual Scene Action Configs"

    def __str__(self) -> str:
        return f"SceneActionConfig for {self.ritual_id}"
