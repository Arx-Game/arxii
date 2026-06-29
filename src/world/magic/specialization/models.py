"""The shared specialization engine base (#1578, ADR-0055).

``AbstractSpecializedVariant`` holds the columns and behavior shared by every
resonance-specialized variant row (technique variants today; covenant sub-roles
after the refactor). One engine, not three per-entity bespoke systems (ADR-0016).

Concrete subclasses (``TechniqueVariant``, ``CovenantRole``) add only:
- a parent self-FK (``parent_technique`` / ``parent_role``),
- entity-specific override columns,
- a ``UniqueConstraint(parent, resonance, unlock_thread_level)``.

Derive-on-read (ADR-0014): the resolved variant is never snapshotted. The
resolver reads the thread's ``resonance`` + ``level`` each call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractCapabilityGrant,
    AbstractDamageProfile,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Resonance


class AbstractSpecializedVariant(SharedMemoryModel):
    """Abstract base for resonance×threshold-specialized variant rows.

    Shared columns (inherited by concrete subclasses — they keep their existing
    columns unchanged, so the CovenantRole refactor is a schema no-op):
    - ``resonance`` — the resonance this variant manifests.
    - ``unlock_thread_level`` — 0 = base/parent; >=3 = variant.
    - ``discovery_achievement`` — granted + global-first Discovery on first
      threshold crossing.
    - ``codex_entry`` — lore entry unlocked on manifestation.

    Shared behavior:
    - ``matching_variant`` — selection predicate (highest unlock_thread_level
      <= thread.level at the thread's resonance, fallback None).
    - ``newly_crossed_variants`` — threshold-crossing predicate (variants whose
      unlock_thread_level falls in (starting_level, new_level] at resonance_id).
    - ``discovery_narrative`` — entity-specific NarrativeMessage copy.

    The discovery *ceremony* (grant achievement -> unlock codex -> notify) is
    NOT on this base; it stays in ``world.covenants.discovery`` (generalized to
    ``fire_variant_discoveries``), which calls ``newly_crossed_variants`` +
    ``discovery_narrative``. See ADR-0055 + the anti-reinvention ledger.
    """

    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_subrole",
        help_text="Null for the base/parent row; set for variants.",
    )
    unlock_thread_level = models.PositiveIntegerField(
        default=0,
        help_text="0 = base/parent; >=3 = variant (thread level needed to unlock).",
    )
    discovery_achievement = models.ForeignKey(
        "achievements.Achievement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Variant only: achievement granted (+ global-first Discovery) on manifestation.",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Variant only: lore entry unlocked on manifestation.",
    )

    class Meta:
        abstract = True

    # ------------------------------------------------------------------
    # Shared resolution + threshold predicates
    # ------------------------------------------------------------------

    @classmethod
    def matching_variant(
        cls,
        parent: AbstractSpecializedVariant,
        *,
        resonance: Resonance,
        thread_level: int,
    ) -> AbstractSpecializedVariant | None:
        """Select the highest-unlock variant on ``parent`` whose
        ``resonance_id == resonance.pk`` and ``unlock_thread_level <= thread_level``.

        Returns ``None`` when no variant qualifies (caller falls back to ``parent``).
        Lifted verbatim from the proven ``resolve_effective_role`` loop
        (``covenants/services.py:584``). Single-depth: ``parent`` must itself be a
        base row (no variant-of-a-variant).
        """
        variants = cls._variant_queryset(parent, resonance=resonance)
        best: AbstractSpecializedVariant | None = None
        for var in variants:
            if var.unlock_thread_level <= thread_level and (
                best is None or var.unlock_thread_level > best.unlock_thread_level
            ):
                best = var
        return best

    @classmethod
    def newly_crossed_variants(
        cls,
        parent: AbstractSpecializedVariant,
        *,
        resonance_id: int,
        starting_level: int,
        new_level: int,
    ) -> Sequence[AbstractSpecializedVariant]:
        """Variants on ``parent`` whose ``unlock_thread_level`` falls in
        ``(starting_level, new_level]`` at ``resonance_id``.

        Lifted from ``fire_variant_discoveries``'s list-comp
        (``covenants/discovery.py:37-44``). The discovery ceremony calls this to
        find which variants to fire beats for on an imbue.
        """
        if new_level <= starting_level:
            return []
        variants = cls._variant_queryset(parent, resonance_id=resonance_id)
        return [v for v in variants if starting_level < v.unlock_thread_level <= new_level]

    @classmethod
    def _variant_queryset(
        cls,
        parent: AbstractSpecializedVariant,
        *,
        resonance: Resonance | None = None,
        resonance_id: int | None = None,
    ):
        """Return the variant rows for ``parent``. Subclasses bind the parent FK name.

        The default assumes a ``variants`` reverse relation (the related_name
        subclasses set on their parent self-FK). Subclasses may override if
        their parent FK uses a different related_name.
        """
        rid = resonance.pk if resonance is not None else resonance_id
        return parent.variants.filter(resonance_id=rid)

    def discovery_narrative(
        self,
        *,
        is_first: bool,
    ) -> tuple[Sequence[CharacterSheet], str]:
        """Entity-specific NarrativeMessage copy + recipients.

        ``is_first=True`` -> gamewide (first-ever manifestation); ``False`` ->
        personal. Each concrete subclass implements this (sub-role vs technique
        form prose). The base raises NotImplementedError to force an override.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete: TechniqueVariant (gift-technique specialization, #1578)
# ---------------------------------------------------------------------------


class TechniqueVariant(AbstractSpecializedVariant):
    """A resonance-specialized variant of a Technique.

    A parent ``Technique`` has variant rows keyed by ``(parent_technique,
    resonance, unlock_thread_level)``. When a character's GIFT thread crosses a
    variant's ``unlock_thread_level`` the resolver picks the variant (highest
    matching ``level <= thread.level`` at the thread's resonance); its
    name/intensity deltas + payload override or augment the parent's. Mirrors
    covenant sub-roles (single-depth only).

    The base ``_variant_queryset`` default resolves via ``parent.variants``
    (the ``related_name`` below); no override is needed.
    """

    parent_technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.CASCADE,
        related_name="variants",
        help_text="The parent technique this variant specializes.",
    )
    name_override = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name for this variant; blank = inherit parent's name.",
    )
    intensity_delta = models.SmallIntegerField(
        default=0,
        help_text="Added to the parent technique's intensity when this variant resolves.",
    )
    control_delta = models.SmallIntegerField(
        default=0,
        help_text="Added to the parent technique's control when this variant resolves.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent_technique", "resonance", "unlock_thread_level"],
                name="technique_variant_unique_parent_resonance_level",
            ),
        ]

    def __str__(self) -> str:
        label = self.name_override or f"variant of {self.parent_technique_id}"
        return f"{label} (res {self.resonance_id}, lvl {self.unlock_thread_level})"

    def discovery_narrative(
        self,
        *,
        is_first: bool,
    ) -> tuple[Sequence[CharacterSheet], str]:
        """Technique-form discovery copy + recipients.

        ``is_first=True`` -> gamewide recipients via
        ``active_player_character_sheets()`` + "first time" prose.
        ``is_first=False`` -> empty recipients ``[]``: the ceremony caller
        (``fire_variant_discoveries``) supplies ``[thread.owner]`` (mirrors
        ``_notify`` in ``covenants/discovery.py:114``) plus personal prose.
        """
        name = self.name_override or self.parent_technique.name
        if is_first:
            from world.roster.selectors import (  # noqa: PLC0415
                active_player_character_sheets,
            )

            recipients = active_player_character_sheets()
            body = (
                f"For the first time, a mage has manifested the {name} form — a "
                f"convergence of {self.resonance.name} and gift no one has "
                f"achieved before."
            )
        else:
            # Personal: the discovering sheet is supplied by the ceremony
            # caller (fire_variant_discoveries), which has thread.owner in
            # scope; it appends [thread.owner] when this returns [].
            recipients: list[CharacterSheet] = []
            body = (
                f"Your gift has deepened. You have manifested the {name} form, "
                f"channelled through {self.resonance.name}."
            )
        return recipients, body


class TechniqueVariantCapabilityGrant(AbstractCapabilityGrant):
    """Capability granted by a TechniqueVariant (mirrors TechniqueCapabilityGrant)."""

    variant = models.ForeignKey(
        TechniqueVariant,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )
    prerequisite = models.ForeignKey(
        "mechanics.Prerequisite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_variant_grants",
        help_text="Source-specific prerequisite.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "capability"],
                name="technique_variant_cap_grant_unique",
            ),
        ]


class TechniqueVariantDamageProfile(AbstractDamageProfile):
    """Damage profile for a TechniqueVariant (mirrors TechniqueDamageProfile)."""

    variant = models.ForeignKey(
        TechniqueVariant,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "damage_type"],
                condition=Q(damage_type__isnull=False),
                name="technique_variant_damage_profile_per_type",
            ),
            models.UniqueConstraint(
                fields=["variant"],
                condition=Q(damage_type__isnull=True),
                name="technique_variant_untyped_damage_profile",
            ),
        ]


class TechniqueVariantAppliedCondition(AbstractAppliedCondition):
    """Applied condition for a TechniqueVariant (mirrors TechniqueAppliedCondition)."""

    variant = models.ForeignKey(
        TechniqueVariant,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "condition", "target_kind"],
                name="technique_variant_applied_condition_unique",
            ),
        ]
