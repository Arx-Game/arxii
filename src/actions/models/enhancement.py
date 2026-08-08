"""Action enhancement model — database entities that modify base actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import EnhancementSourceType
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

if TYPE_CHECKING:
    from actions.types import ActionContext


class ActionEnhancement(NaturalKeyMixin, SharedMemoryModel):
    """A relationship record: "this source modifies this base action in this way."

    The source (a technique, distinction, condition) gates *whether* the
    enhancement activates (via ``should_apply_enhancement``). This model
    owns *what* the enhancement does via effect config rows and ``apply()``.

    Exactly one source FK must be non-null, matching ``source_type``.

    Carries ``NaturalKeyMixin`` (#3034) so an enhancement can be authored in
    the lore repo — e.g. the six social-magic enhancements (Intimidate,
    Persuade, Deceive, Flirt, Perform, Entrance) #2973 requires but which no
    production seeder creates. ``(base_action_key, variant_name)`` is the
    identity: it is already the de facto key every production call site
    (``world.conditions.berserk_content.ensure_restore_to_sense_effect``,
    ``MagicContent.create_all()``) uses in its own ``get_or_create`` lookup,
    and it is the "this base action, in this way" pair the class docstring
    above already names as the row's meaning. No DB ``UniqueConstraint``
    backs it (mirrors ``conditions.ConditionCheckModifier`` — a natural key
    does not require DB enforcement) since several tests create rows via
    ``ActionEnhancement.objects.create(...)`` directly and a new constraint
    would risk colliding with those.
    """

    base_action_key = models.CharField(max_length=100, db_index=True)
    variant_name = models.CharField(max_length=100)
    is_involuntary = models.BooleanField(default=False)

    source_type = models.CharField(
        max_length=20,
        choices=EnhancementSourceType.choices,
    )

    # === Source FKs — exactly one must be non-null, matching source_type ===
    distinction = models.ForeignKey(
        "arxii.Distinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )
    condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )
    technique = models.ForeignKey(
        "arxii.Technique",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["base_action_key", "variant_name"]

    class Meta:
        app_label = "arxii"
        indexes = [
            models.Index(fields=["base_action_key", "is_involuntary"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="action_enhancement_exactly_one_source",
                condition=(
                    models.Q(
                        source_type=EnhancementSourceType.DISTINCTION,
                        distinction__isnull=False,
                        condition__isnull=True,
                        technique__isnull=True,
                    )
                    | models.Q(
                        source_type=EnhancementSourceType.CONDITION,
                        distinction__isnull=True,
                        condition__isnull=False,
                        technique__isnull=True,
                    )
                    | models.Q(
                        source_type=EnhancementSourceType.TECHNIQUE,
                        distinction__isnull=True,
                        condition__isnull=True,
                        technique__isnull=False,
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant_name} ({self.base_action_key})"

    @property
    def source(self) -> object | None:
        """Return the source model instance based on source_type."""
        if self.source_type == EnhancementSourceType.DISTINCTION:
            return self.distinction
        if self.source_type == EnhancementSourceType.CONDITION:
            return self.condition
        if self.source_type == EnhancementSourceType.TECHNIQUE:
            return self.technique
        return None

    def apply(self, context: ActionContext) -> None:
        """Dispatch all effect configs for this enhancement."""
        from actions.effects import apply_effects  # noqa: PLC0415

        apply_effects(self, context)
