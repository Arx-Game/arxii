"""Specialization engine services (#1578, ADR-0055).

- ``provision_latent_gift_thread`` — CG provisioning of the latent level-0 GIFT thread.
- ``gift_resonances_for`` — the derive-on-read resonance seam (replaces
  ``technique.gift.resonances.all()`` at the four cast sites).
- ``resolve_specialized_variant`` — the single resolver (generalizes
  ``resolve_effective_role``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import TargetKind

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole
    from world.magic.models import Thread
    from world.magic.models.affinity import Resonance
    from world.magic.models.gifts import Gift
    from world.magic.models.techniques import Technique


def provision_latent_gift_thread(
    sheet: CharacterSheet,
    gift: Gift,
    *,
    resonance: Resonance,
) -> Thread:
    """Create the latent level-0 GIFT thread for ``gift`` at ``resonance``.

    Idempotent on (owner, gift): if an active GIFT thread for (owner, gift)
    already exists, return it unchanged. Write-once on resonance: calling this
    again with a different ``resonance`` returns the existing thread unchanged
    (the resonance param is ignored). This is intentional — one latent thread
    per gift. Acquiring a gift IS intuitively weaving a (latent) thread — the
    Glimpse. Weaving (Rite of Weaving) commits a resonance; imbuing raises the
    level; crossing a variant's unlock_thread_level resolves the variant.
    """
    from world.magic.models import Thread  # noqa: PLC0415

    existing = Thread.objects.filter(
        owner=sheet,
        target_kind=TargetKind.GIFT,
        target_gift=gift,
        retired_at__isnull=True,
    ).first()
    if existing is not None:
        return existing

    thread = Thread(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.GIFT,
        target_gift=gift,
        level=0,
    )
    thread.full_clean()
    with transaction.atomic():
        thread.save()
    return thread


def gift_resonances_for(character, gift: Gift) -> list[Resonance]:
    """The resonance(s) this gift manifests as FOR THIS character.

    Derived on read from the character's active GIFT thread on ``gift``. Falls
    back to ``gift.resonances`` (the supported set) when no thread exists
    (e.g. unowned gift, or pre-provisioning). Replaces
    ``technique.gift.resonances.all()`` at the four cast sites (#1578).
    """
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
    )

    sheet = _get_character_sheet(character)
    if sheet is not None:
        thread = (
            Thread.objects.filter(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_gift=gift,
                retired_at__isnull=True,
            )
            .select_related("resonance__affinity")
            .first()
        )
        if thread is not None:
            return [thread.resonance]
    # Fallback: the gift's supported set (authored M2M).
    return list(gift.resonances.select_related("affinity").all())


def resolve_specialized_variant(*, entity, character):
    """Return the resonance-specialized variant of ``entity`` for ``character``,
    else ``entity`` unchanged. Derive-on-read (ADR-0014).

    For a Technique: finds the character's active GIFT thread on the technique's
    gift, reads resonance + level, and returns a ``ResolvedTechnique`` wrapping
    the parent + matching variant (or just the parent). For a CovenantRole:
    reads the active COVENANT_ROLE thread via the cached ``character.threads``
    handler and returns the matching sub-role variant (proven path, #1578).
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    if isinstance(entity, Technique):
        return _resolve_technique_variant(entity, character)
    if isinstance(entity, CovenantRole):
        return _resolve_covenant_role_variant(entity, character)
    return entity


def _resolve_technique_variant(technique: Technique, character) -> object:
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
    )
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    sheet = _get_character_sheet(character)
    if sheet is None:
        return technique

    thread = (
        Thread.objects.filter(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=technique.gift_id,
            retired_at__isnull=True,
        )
        .select_related("resonance")
        .first()
    )
    if thread is None:
        return technique

    variant = TechniqueVariant.matching_variant(
        technique,
        resonance=thread.resonance,
        thread_level=thread.level,
    )
    if variant is None:
        return technique
    return _ResolvedTechnique(technique, variant=variant)


def _resolve_covenant_role_variant(role, character) -> CovenantRole:
    """Resonance-specialized sub-role for a base ``role`` (proven path, #1578).

    Single-depth: a role that is already a sub-role (has ``parent_role``) is
    returned unchanged — never re-promote. Reads the active COVENANT_ROLE
    thread via the cached ``character.threads`` handler (same read mechanism as
    the legacy ``resolve_effective_role``) to preserve cache coherence.
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if role.parent_role_id is not None:
        return role  # already a sub-role; never re-promote (single-depth)
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role_id == role.pk
            and t.retired_at is None
        ),
        None,
    )
    if thread is None:
        return role
    variant = CovenantRole.matching_variant(
        role, resonance=thread.resonance, thread_level=thread.level
    )
    return variant if variant is not None else role


class _ResolvedTechnique:
    """Derive-on-read view over a Technique + its resolved TechniqueVariant.

    Surfaces name/intensity/control/payload as parent + variant delta/override.
    Callers read these instead of ``technique.name`` / ``technique.intensity``.
    """

    def __init__(self, technique: Technique, *, variant) -> None:
        self.technique = technique
        self.variant = variant

    @property
    def name(self) -> str:
        if self.variant is not None and self.variant.name_override:
            return self.variant.name_override
        return self.technique.name

    @property
    def intensity(self) -> int:
        base = self.technique.intensity
        if self.variant is not None:
            return base + self.variant.intensity_delta
        return base

    @property
    def control(self) -> int:
        base = self.technique.control
        if self.variant is not None:
            return base + self.variant.control_delta
        return base

    # Payload accessors: variant's payload if it has any, else parent's.
    @property
    def damage_profiles(self):
        if self.variant is not None and self.variant.damage_profiles.exists():
            return self.variant.damage_profiles.all()
        return self.technique.damage_profiles.all()

    @property
    def capability_grants(self):
        if self.variant is not None and self.variant.capability_grants.exists():
            return self.variant.capability_grants.all()
        return self.technique.capability_grants.all()

    @property
    def condition_applications(self):
        if self.variant is not None and self.variant.condition_applications.exists():
            return self.variant.condition_applications.all()
        return self.technique.condition_applications.all()

    # Pass-through for the cast pipeline's other technique reads.
    def __getattr__(self, item):
        return getattr(self.technique, item)
