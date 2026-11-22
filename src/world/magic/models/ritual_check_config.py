"""RitualCheckConfig: per-Ritual authored check specification.

Holds the check a ritual rolls when performed. SCENE_ACTION rituals
(player anima rituals) require one; other kinds (e.g. SERVICE sanctum
rituals) may carry one to source their CheckType and authored difficulty.
"""

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import AFFINITY_PRIMAL


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

    An anima ritual also carries two resonance picks (#5280): ``primal_resonance`` is the
    Primal resonance that grows for the performer, and ``outward_resonance`` is the
    Celestial or Abyssal resonance the ritual reaches for in its partner. ``clean()``
    holds each pick to its affinity.
    """

    ritual = models.OneToOneField(
        "arxii.Ritual",
        on_delete=models.CASCADE,
        related_name="check_config",
    )
    stat = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        limit_choices_to={"trait_type": "stat"},
        related_name="+",
        help_text="The primary stat used in this ritual's check.",
    )
    skill = models.ForeignKey(
        "arxii.Skill",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The skill used in this ritual's check.",
    )
    specialization = models.ForeignKey(
        "arxii.Specialization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional specialization for this ritual's check.",
    )
    primal_resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The Primal resonance this anima ritual grows for its performer. Must be a "
            "Primal-affinity resonance."
        ),
    )
    outward_resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The Celestial or Abyssal resonance this anima ritual reaches for in its "
            "partner. Must not be a Primal-affinity resonance."
        ),
    )
    check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="CheckType used when rolling this ritual's check.",
    )
    target_difficulty_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Target difficulty for the check. Authored as a level (0 = no difficulty): "
            "the roll meets that level's baseline."
        ),
    )
    non_founder_target_difficulty_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Authored difficulty when the actor lacks founder standing for the target "
            "(e.g. a non-founder dissolving a Sanctum). NULL = no distinction. Authored "
            "as a level (0 = no difficulty): the roll meets that level's baseline."
        ),
    )
    sustained_rounds = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Rounds this ritual takes to conduct when performed inside a combat "
            "encounter (#2705). 0 (default) fires immediately, as every ritual does "
            "today. > 0 creates a SustainedAction that matures this many rounds later "
            "and can be broken by landing hits."
        ),
    )

    class Meta:
        verbose_name = "Ritual Check Config"
        verbose_name_plural = "Ritual Check Configs"

    def __str__(self) -> str:
        return f"CheckConfig for {self.ritual_id}"

    def clean(self) -> None:
        """Hold the Primal pick to a Primal resonance and the outward pick to a non-Primal one."""
        super().clean()
        errors: dict[str, str] = {}
        if self.primal_resonance_id and self.primal_resonance.affinity.name != AFFINITY_PRIMAL:
            errors["primal_resonance"] = "The Primal pick must be a Primal-affinity resonance."
        if self.outward_resonance_id and self.outward_resonance.affinity.name == AFFINITY_PRIMAL:
            errors["outward_resonance"] = (
                "The outward pick must be a Celestial or Abyssal resonance, not a Primal one."
            )
        if errors:
            raise ValidationError(errors)
