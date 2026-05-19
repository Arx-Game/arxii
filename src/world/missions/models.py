"""Missions data models (Phase 1).

Phase 1 builds the *affordance registry* and the authored-once
descriptor→affordance bindings.

Design recap: a mission challenge declares which *affordances* it accepts
(e.g. ``distraction``, ``lethal``). Any durable descriptor a character owns
that is *tagged* (bound) with a matching affordance auto-surfaces as an
option. The binding is authored ONCE per (descriptor, affordance) and
globally reused; it records whether the option produces a narrative BRANCH
(no check) or a CHECK (which ``checks.CheckType`` + base risk), the thin IC
framing line, and an optional reusable ``checks.Consequence`` "rider".

The check/consequence substrate is reused wholesale — bindings FK directly
to ``checks.CheckType`` / ``checks.Consequence``; this app introduces no new
check or consequence models.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.missions.constants import OptionProduces

# Discriminator value -> typed FK field name. Authored-once bindings point at
# a single durable-descriptor model; the discriminator selects which typed FK
# is active (validated by DiscriminatorMixin). ``source_technique`` is
# intentionally absent — see the class docstring on AffordanceBinding.
SOURCE_TRAIT = "trait"
SOURCE_DISTINCTION = "distinction"
SOURCE_ACHIEVEMENT = "achievement"
SOURCE_CAPABILITY = "capability"
SOURCE_CONDITION = "condition"


class SourceKind(models.TextChoices):
    """Which durable-descriptor family a binding is authored against."""

    TRAIT = SOURCE_TRAIT, "Trait"
    DISTINCTION = SOURCE_DISTINCTION, "Distinction"
    ACHIEVEMENT = SOURCE_ACHIEVEMENT, "Achievement"
    CAPABILITY = SOURCE_CAPABILITY, "Capability"
    CONDITION = SOURCE_CONDITION, "Condition"


class AffordanceManager(NaturalKeyManager):
    """Manager for Affordance with natural-key support."""


class Affordance(NaturalKeyMixin, SharedMemoryModel):
    """A capability-category a mission challenge can accept.

    Examples: ``distraction``, ``lethal``, ``stealth``, ``social``. A
    challenge declares the set of affordances it will accept; any descriptor
    a character owns that is bound to one of those affordances surfaces as a
    player option. Pure lookup table — mirrors ``mechanics.ModifierCategory``.
    """

    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Affordance name (e.g., 'distraction', 'lethal').",
    )
    description = models.TextField(
        blank=True,
        help_text="What kind of approach this affordance represents.",
    )

    objects = AffordanceManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class AffordanceBinding(DiscriminatorMixin, SharedMemoryModel):
    """Authored-once link from a durable descriptor to an affordance.

    Exactly one typed ``source_*`` FK is set, selected by ``source_kind``
    (enforced by :class:`~core.mixins.DiscriminatorMixin`). When a character
    owns that descriptor and a challenge accepts ``affordance``, this binding
    surfaces as one player option carrying its ``produces`` mode, optional
    ``check_type`` + ``base_risk``, the thin ``ic_framing`` line, and an
    optional reusable ``rider`` consequence.

    ``source_technique`` is intentionally omitted. ``magic.Technique`` is a
    *per-character* instance (``Technique.name`` is explicitly non-unique and
    techniques are "unique per character and not shared"), so a globally
    authored-once binding cannot point at one technique without binding to a
    single character's instance; Phase 0 also ships no technique-ownership
    resolver to reuse. Deferred until the magic technique catalog model is
    confirmed.
    # DESIGN: technique source deferred — verify magic technique model
    """

    DISCRIMINATOR_FIELD = "source_kind"
    DISCRIMINATOR_MAP = {
        SOURCE_TRAIT: "source_trait",
        SOURCE_DISTINCTION: "source_distinction",
        SOURCE_ACHIEVEMENT: "source_achievement",
        SOURCE_CAPABILITY: "source_capability",
        SOURCE_CONDITION: "source_condition",
    }

    source_kind = models.CharField(
        max_length=20,
        choices=SourceKind.choices,
        help_text="Which durable-descriptor family this binding is authored against.",
    )
    source_trait = models.ForeignKey(
        "traits.Trait",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_distinction = models.ForeignKey(
        "distinctions.Distinction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_achievement = models.ForeignKey(
        "achievements.Achievement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_capability = models.ForeignKey(
        "conditions.CapabilityType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )

    affordance = models.ForeignKey(
        Affordance,
        on_delete=models.PROTECT,
        related_name="bindings",
        help_text="The affordance this descriptor satisfies.",
    )
    produces = models.CharField(
        max_length=10,
        choices=OptionProduces.choices,
        help_text="Whether this option is a narrative branch or a resolved check.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
        help_text="Resolved when produces=check; must be null when produces=branch.",
    )
    base_risk = models.PositiveSmallIntegerField(
        default=0,
        help_text="Authored base risk for the surfaced option.",
    )
    ic_framing = models.CharField(
        max_length=200,
        help_text="Thin in-character one-liner describing the approach.",
    )
    rider = models.ForeignKey(
        "checks.Consequence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional reusable consequence attached to this option.",
    )

    def clean(self) -> None:
        super().clean()
        if self.produces == OptionProduces.CHECK and self.check_type_id is None:
            raise ValidationError({"check_type": "Required when produces is 'check'."})
        if self.produces == OptionProduces.BRANCH and self.check_type_id is not None:
            raise ValidationError({"check_type": "Must be null when produces is 'branch'."})

    def __str__(self) -> str:
        return f"{self.get_active_target_name()} → {self.affordance.name}"
