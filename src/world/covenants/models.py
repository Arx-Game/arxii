"""Models for the covenants system.

Covenants are magically-empowered oaths — blood rituals that bind participants
to shared roles and goals. This app owns role definitions and their mechanical
properties (like combat speed rank). The full covenant lifecycle (formation,
membership, progression) is future work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.covenants.constants import CovenantType, RoleArchetype
from world.items.constants import GearArchetype

if TYPE_CHECKING:
    from world.covenants.handlers import CovenantMembershipHandler


class Covenant(SharedMemoryModel):
    """The foundational social/magical structure that binds members under a sworn oath.

    Per-kind extension of Organization for kind=COVENANT. Each Covenant has a
    backing Organization auto-created in save() if not provided. Covenant.pk
    equals organization.pk.

    Slice A scope: identity, type, level (placeholder until Slice D), formed/dissolved
    timestamps, free-text sworn objective.

    Deferred fields (future slices):
    - durance_focus_FK / battle_encounter_FK — Slice E (type-specific data)
    - structured sworn_objective_FK → SwornObjective — Slice C (replaces TextField)
    - xp, milestone progression fields — Slice D
    - description, crest, motto, cosmetic fields — post-MVP polish
    - dissolution_reason, dissolution_kind — Slice B
    """

    organization = models.OneToOneField(
        "societies.Organization",
        null=True,  # auto-populated in Covenant.save() — None only in-memory pre-save
        on_delete=models.CASCADE,
        related_name="covenant",
        # NOTE: NOT primary_key=True — Covenant keeps its own auto-id pk.
        # The OneToOne is just a relationship; pk-using code (views, serializers,
        # FKs from CovenantLegendCredit etc.) continues to work unchanged.
    )
    name = models.CharField(max_length=120, unique=True)
    covenant_type = models.CharField(
        max_length=20,
        choices=CovenantType.choices,
        default=CovenantType.DURANCE,
    )
    level = models.PositiveIntegerField(
        default=1,
        help_text="Group progression tier (Slice D will drive growth).",
    )
    sworn_objective = models.TextField(
        blank=False,
        help_text="Free text in Slice A; structured in Slice C.",
    )
    formed_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args: object, **kwargs: object) -> None:
        if self.organization_id is None:
            # Lazy import to avoid circular dependency.
            from world.covenants.constants import COVENANT_ORG_KIND  # noqa: PLC0415
            from world.societies.models import Organization  # noqa: PLC0415

            self.organization = Organization.objects.create(
                name=self.name,
                society=None,
                kind=COVENANT_ORG_KIND,
            )
        super().save(*args, **kwargs)

    @cached_property
    def member_roster(self) -> CovenantMembershipHandler:
        from world.covenants.handlers import CovenantMembershipHandler  # noqa: PLC0415, I001 — avoids circular import (handlers imports models)

        return CovenantMembershipHandler(self)

    def __str__(self) -> str:
        state = "active" if self.dissolved_at is None else "dissolved"
        return f"{self.name} ({self.get_covenant_type_display()}, {state})"


class CovenantRole(SharedMemoryModel):
    """A role that a character can hold within a covenant.

    Lookup table — staff-authored, cached via SharedMemoryModel.
    Different covenant types may have different role sets; the
    covenant_type field scopes which roles are available.

    Combat reads ``speed_rank`` directly from this model during resolution
    order calculation.
    """

    name = models.CharField(max_length=60, help_text="Display name, e.g. 'Vanguard'.")
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Stable identifier for code references, e.g. 'vanguard'.",
    )
    covenant_type = models.CharField(
        max_length=20,
        choices=CovenantType.choices,
        default=CovenantType.DURANCE,
        help_text="Which covenant type this role belongs to.",
    )
    archetype = models.CharField(
        max_length=20,
        choices=RoleArchetype.choices,
        help_text="Foundational archetype: Sword (offense), Shield (defense), Crown (support).",
    )
    speed_rank = models.PositiveIntegerField(
        help_text="Combat resolution order. Lower is faster (1 = fastest).",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of the role's identity and combat style.",
    )

    parent_role = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sub_roles",
        help_text="Null for primary roles. Set for sub-roles.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="covenant_subroles",
        help_text="Null for primary roles. Set for sub-roles.",
    )
    unlock_thread_level = models.PositiveIntegerField(
        default=0,
        help_text="0 for primary roles; 3+ for sub-roles (Thread level needed to unlock).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_type", "name"],
                name="unique_role_name_per_covenant_type",
            ),
            models.UniqueConstraint(
                fields=["parent_role", "resonance", "unlock_thread_level"],
                condition=models.Q(parent_role__isnull=False),
                name="covenant_subrole_unique_per_parent_resonance_level",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        has_parent = self.parent_role_id is not None
        has_resonance = self.resonance_id is not None

        # XOR rule: both must be set (sub-role) or both must be null (primary role)
        if has_parent != has_resonance:
            msg = (
                "parent_role and resonance must both be set (sub-role) or both be null "
                "(primary role)."
            )
            raise ValidationError({"parent_role": msg, "resonance": msg})

        if has_parent and has_resonance:
            # Sub-role rules
            if self.unlock_thread_level == 0:
                raise ValidationError(
                    {"unlock_thread_level": "Sub-roles must have unlock_thread_level > 0."}
                )
            parent = self.parent_role
            if parent.covenant_type != self.covenant_type:
                raise ValidationError(
                    {
                        "covenant_type": (
                            "Sub-role covenant_type must match parent_role.covenant_type."
                        )
                    }
                )
            if parent.archetype != self.archetype:
                raise ValidationError(
                    {"archetype": "Sub-role archetype must match parent_role.archetype."}
                )
            if parent.parent_role_id is not None:
                raise ValidationError(
                    {"parent_role": "Sub-sub-roles are not allowed (single-depth only)."}
                )
        # Primary role rules
        elif self.unlock_thread_level != 0:
            raise ValidationError(
                {
                    "unlock_thread_level": (
                        "Primary roles (no parent_role/resonance) must have unlock_thread_level=0."
                    )
                }
            )

    def __str__(self) -> str:
        return f"{self.name} ({self.get_covenant_type_display()})"


class GearArchetypeCompatibility(SharedMemoryModel):
    """Existence-only join: which roles are compatible with which archetypes.

    Spec D §4.4. Row present = role bonuses add to mundane gear stats on
    that archetype. Row absent = incompatible (max(role, gear) per slot).
    """

    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.CASCADE,
        related_name="gear_compatibilities",
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "gear_archetype"],
                name="covenants_unique_role_archetype_compat",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.covenant_role.name} compatible with {self.get_gear_archetype_display()}"


class CharacterCovenantRole(SharedMemoryModel):
    """Per-character record of a covenant role assignment.

    Slice A §3.3, §3.6. A character may hold the same CovenantRole across
    multiple covenants (memberships are non-exclusive), so the active-
    uniqueness key is (character_sheet, covenant) — not (character_sheet,
    covenant_role).

    Lifecycle:
    - active row: left_at IS NULL
    - historical row: left_at IS NOT NULL
    - engaged row: engaged=True, active (left_at IS NULL)

    The ``engaged`` flag marks runtime context — the covenant whose role
    bonuses are currently active and which is eligible for COVENANT_ROLE
    Thread pulls. At most one engaged active row per (character_sheet,
    covenant.covenant_type) is enforced by clean() and the service layer
    (a partial-index WHERE on a joined column is not expressible in Postgres).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="covenant_role_assignments",
    )
    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.PROTECT,
        related_name="character_assignments",
    )
    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    engaged = models.BooleanField(
        default=False,
        help_text=(
            "True when the character is currently 'fulfilling' this role for this "
            "covenant. At most one engaged active row per (character_sheet, "
            "covenant.covenant_type) — service-enforced + clean()-enforced. "
            "Drives role bonuses (modifier pipeline) and COVENANT_ROLE Thread pull "
            "eligibility. See spec 2026-05-09 §3.6."
        ),
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "covenant"],
                condition=models.Q(left_at__isnull=True),
                name="covenants_one_active_role_per_covenant",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.engaged and self.left_at is not None:
            raise ValidationError({"engaged": "Engaged row cannot have left_at set."})
        if self.engaged:
            same_type_engaged = (
                CharacterCovenantRole.objects.filter(
                    character_sheet=self.character_sheet,
                    covenant__covenant_type=self.covenant.covenant_type,
                    engaged=True,
                    left_at__isnull=True,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if same_type_engaged:
                raise ValidationError(
                    {
                        "engaged": (
                            "Another engaged active membership of the same covenant type "
                            "exists for this character."
                        ),
                    }
                )

    def __str__(self) -> str:
        state = "active" if self.left_at is None else "ended"
        return f"{self.character_sheet}: {self.covenant_role.name} ({state})"


class CovenantLevelThreshold(SharedMemoryModel):
    """Legend total required to reach each covenant level. Authored content."""

    level = models.PositiveIntegerField(unique=True)
    required_legend = models.PositiveIntegerField()

    class Meta:
        ordering = ["level"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="covenant_level_threshold_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"Level {self.level} (≥ {self.required_legend} legend)"
