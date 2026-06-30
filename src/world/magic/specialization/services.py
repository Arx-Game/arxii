"""Specialization engine services (#1578, ADR-0055; #1582, ADR-0056).

- ``provision_latent_gift_thread`` — CG provisioning of the latent level-0 GIFT thread.
- ``gift_resonances_for`` — the derive-on-read resonance seam (replaces
  ``technique.gift.resonances.all()`` at the four cast sites).
- ``signature_thread_for_technique`` — look up an active TECHNIQUE-thread
  (signature) on a specific technique for a character (#1582, ADR-0056).
- ``cast_resonances_for`` — cast-time resonance override: returns the
  signature thread's resonance when one exists, else falls back to
  ``gift_resonances_for``. This is the per-technique seam that lets a
  discordant signature manifest one technique as a different affinity.
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
    from world.magic.models.gifts import CharacterGift, Gift
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
    # Read the active thread through the cached ``character.threads`` handler
    # (the same cached queryset the resolver + passive bonuses read), not a
    # fresh ``Thread.objects.filter()`` — per project cached-property rule.
    # The handler's list is already filtered to retired_at__isnull=True.
    character = sheet.character
    existing = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
        ),
        None,
    )
    if existing is not None:
        return existing

    from world.magic.models import Thread  # noqa: PLC0415

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
    # Invalidate the cached thread list so the new row is visible to the next
    # read through ``character.threads`` (mirrors the covenant-role invalidation
    # contract in covenants/services._invalidate_role_caches).
    character.threads.invalidate()
    return thread


def grant_gift_to_character(
    sheet: CharacterSheet, gift: Gift, *, resonance: Resonance | None
) -> tuple[CharacterGift, bool]:
    """Mint (idempotently) the CharacterGift link + the latent GIFT thread.

    The shared gift-acquisition primitive: a character gains a gift by linking it
    (``CharacterGift``) and provisioning its latent level-0 GIFT thread. Used by the
    path-crossing grant (#1579) and species-gift provisioning (#1580) so there is
    one place that does this, not a per-source copy.

    ``resonance`` is the already-resolved resonance for the latent thread — each
    caller applies its own resonance-selection policy; ``None`` skips thread
    provisioning (e.g. a gift that supports no resonances). Returns
    ``(character_gift, created)``.
    """
    from world.magic.models import CharacterGift  # noqa: PLC0415

    character_gift, created = CharacterGift.objects.get_or_create(character=sheet, gift=gift)
    if resonance is not None:
        provision_latent_gift_thread(sheet, gift, resonance=resonance)
    return character_gift, created


def gift_resonances_for(character, gift: Gift) -> list[Resonance]:
    """The resonance(s) this gift manifests as FOR THIS character.

    Derived on read from the character's active GIFT thread on ``gift``: the
    thread's resonance if one exists, else ``gift.resonances`` (the supported
    set). Replaces ``technique.gift.resonances.all()`` at the four cast sites
    (#1578).

    Reads the thread through the cached ``character.threads`` handler (the
    single cached queryset for a character's threads) with a list-comp filter,
    not a fresh ``Thread.objects.filter()`` — per project cached-property rule.

    A sheetless ``Character`` (e.g. an NPC) has no GIFT thread, so it manifests
    the supported set; the sheet guard handles that precondition rather than
    catching the ``sheet_data`` raise from the handler. A non-Character object
    (no ``.threads``) is a caller bug and is left to raise ``AttributeError``
    rather than papered over with a ``hasattr`` check.
    """
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
    )

    if _get_character_sheet(character) is None:
        return gift.cached_resonances
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
        ),
        None,
    )
    if thread is not None:
        return [thread.resonance]
    return gift.cached_resonances


def signature_thread_for_technique(character, technique: Technique) -> Thread | None:
    """Return the active signature (TECHNIQUE) thread on ``technique``, or None.

    A signature thread is a ``TargetKind.TECHNIQUE`` thread — optional extra
    depth invested in a single technique above its gift baseline (ADR-0056).
    It carries its own resonance, which usually matches the gift but may
    deliberately diverge (a *discordant signature*).

    Reads the thread through the cached ``character.threads`` handler (the same
    cached queryset the GIFT-thread path reads), not a fresh
    ``Thread.objects.filter()`` — per project cached-property rule. The
    handler's list is already filtered to ``retired_at__isnull=True``.

    A sheetless ``Character`` (e.g. an NPC) has no signature threads; the sheet
    guard handles that precondition rather than catching the handler's raise.
    """
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
    )

    if _get_character_sheet(character) is None:
        return None
    return next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.TECHNIQUE and t.target_technique_id == technique.pk
        ),
        None,
    )


def cast_resonances_for(character, technique: Technique) -> list[Resonance]:
    """Resonances a technique manifests as for this character at cast time.

    The per-technique derive-on-read seam (ADR-0056). When the character has an
    active signature (TECHNIQUE) thread on ``technique``, the signature's
    resonance **overrides** the gift's for this one technique — letting a
    single technique manifest as a different affinity than its gift (a
    *discordant signature*). When no signature exists, falls back to
    ``gift_resonances_for`` (the gift-thread resonance, or the gift's supported
    set).

    This is the function the cast pipeline should call instead of
    ``gift_resonances_for(character, technique.gift)`` — it accounts for the
    per-technique signature override that ``gift_resonances_for`` (which is
    gift-scoped) cannot.
    """
    sig = signature_thread_for_technique(character, technique)
    if sig is not None:
        return [sig.resonance]
    return gift_resonances_for(character, technique.gift)


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


def _resolve_technique_variant(technique: Technique, character) -> Technique | _ResolvedTechnique:
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
    )
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    # Read threads through the cached ``character.threads`` handler (the same
    # cached queryset the covenant path reads), not a fresh
    # ``Thread.objects.filter()`` — per project cached-property rule. A sheetless
    # Character (e.g. an NPC) has no threads, so it gets the parent technique
    # unchanged; the sheet guard handles that precondition rather than catching
    # the handler's ``sheet_data`` raise. A non-Character object has no
    # ``.threads`` and is left to raise ``AttributeError``.
    if _get_character_sheet(character) is None:
        return technique

    # A signature (TECHNIQUE) thread on *this* technique overrides the gift's
    # resonance for variant matching (ADR-0056). The signature's resonance may
    # deliberately diverge from the gift's (a *discordant signature*), and the
    # effective variant-matching level is the gift baseline + signature depth
    # ("gift baseline + optional signature delta").
    sig_thread = signature_thread_for_technique(character, technique)

    gift_thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == technique.gift_id
        ),
        None,
    )

    if sig_thread is not None:
        # Signature overrides: match variant on the signature's resonance, using
        # cumulative level (gift baseline + signature delta). A gift thread at
        # level 0 (latent) contributes nothing; the signature alone drives the
        # variant unlock in that case.
        effective_level = (gift_thread.level if gift_thread is not None else 0) + sig_thread.level
        variant = TechniqueVariant.matching_variant(
            technique,
            resonance=sig_thread.resonance,
            thread_level=effective_level,
        )
        if variant is None:
            return _ResolvedTechnique(technique, variant=None)
        return _ResolvedTechnique(technique, variant=variant)

    # No signature — fall back to gift-thread specialization (existing path).
    if gift_thread is None:
        return technique

    variant = TechniqueVariant.matching_variant(
        technique,
        resonance=gift_thread.resonance,
        thread_level=gift_thread.level,
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

    # Payload accessors: variant's payload if it has any, else parent's. Each
    # reads its source's single ``cached_<payload>`` list once (mirrors the
    # ``cached_restrictions`` convention in techniques.py) rather than issuing a
    # ``.exists()`` + ``.all()`` pair per access. To invalidate after a payload
    # mutation: ``del instance.cached_<payload>`` on the mutated owner.
    @property
    def damage_profiles(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_damage_profiles
            if payload:
                return payload
        return self.technique.cached_damage_profiles

    @property
    def capability_grants(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_capability_grants
            if payload:
                return payload
        return self.technique.cached_capability_grants

    @property
    def condition_applications(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_condition_applications
            if payload:
                return payload
        return self.technique.cached_condition_applications

    # Pass-through for the cast pipeline's other technique reads.
    def __getattr__(self, item):
        return getattr(self.technique, item)
