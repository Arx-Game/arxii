"""RitualCheckConfig: per-Ritual authored check specification.

Holds the check a ritual rolls when performed. SCENE_ACTION rituals
(player anima rituals) require one; other kinds (e.g. SERVICE sanctum
rituals) may carry one to source their CheckType and authored difficulty.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class RitualCheckConfig(SharedMemoryModel):
    """Per-Ritual check configuration.

    The 1:1 relationship is enforced by the OneToOneField. The invariant
    that SCENE_ACTION rituals must have a config (other kinds may) is
    enforced in Ritual.clean().

    FK paths mirror CharacterAnimaRitual: stat/skill → traits.Trait /
    skills.Skill, specialization → skills.Specialization,
    check_type → checks.CheckType. For SERVICE rituals, stat/skill are
    narrative/authoring hints — the roll's mechanics come entirely from
    check_type composition + the authored difficulty.
    """

    ritual = models.OneToOneField(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="check_config",
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
    non_founder_target_difficulty = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Authored difficulty when the actor lacks founder standing for the "
            "target (e.g. a non-founder dissolving a Sanctum). NULL = no distinction."
        ),
    )

    class Meta:
        verbose_name = "Ritual Check Config"
        verbose_name_plural = "Ritual Check Configs"

    def __str__(self) -> str:
        return f"CheckConfig for {self.ritual_id}"
