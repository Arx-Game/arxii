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
    from world.magic.models.gifts import CharacterGift, Gift
    from world.magic.models.techniques import Technique


# Sentinel: caller has not yet fetched the sheet (distinct from None = "no sheet").
_SHEET_UNSET: object = object()


def provision_latent_gift_thread(
    sheet: CharacterSheet,
    gift: Gift,
    *,
    resonance: Resonance,
) -> Thread:
    """Create the latent level-0 GIFT thread for ``gift`` at ``resonance``.

    Idempotent on ``(owner, gift, resonance)``: if an active GIFT thread for
    that triple already exists, return it unchanged. Multi-resonance (#1619):
    a character may hold multiple active GIFT threads on the same gift at
    different resonances. The first call provisions the "primary" thread;
    additional resonances are added via ``provision_additional_gift_thread``.

    Acquiring a gift IS intuitively weaving a (latent) thread — the Glimpse.
    Weaving (Rite of Weaving) commits a resonance; imbuing raises the level;
    crossing a variant's unlock_thread_level resolves the variant.
    """
    character = sheet.character
    # Check for an existing thread at this exact resonance — idempotent.
    existing = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT
            and t.target_gift_id == gift.pk
            and t.resonance_id == resonance.pk
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


def provision_additional_gift_thread(
    sheet: CharacterSheet,
    gift: Gift,
    *,
    resonance: Resonance,
) -> Thread:
    """Add a second (or subsequent) resonance to an existing GIFT thread set.

    For multi-resonance characters (#1619): a character who already has a GIFT
    thread on ``gift`` at one resonance may add another at a different
    resonance. The new thread starts at level 0 (the Glimpse) and must be
    independently woven and imbued.

    Validates that the resonance is in the gift's supported set. Raises
    ``UnsupportedGiftResonanceError`` if not. If a thread at this resonance
    already exists, returns it unchanged (idempotent — delegates to
    ``provision_latent_gift_thread``).
    """
    from world.magic.exceptions import UnsupportedGiftResonanceError  # noqa: PLC0415

    if not any(r.pk == resonance.pk for r in gift.cached_resonances):
        raise UnsupportedGiftResonanceError

    return provision_latent_gift_thread(sheet, gift, resonance=resonance)


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


def _active_alt_self_resonance(sheet: CharacterSheet) -> Resonance | None:
    """Return the resonance of the character's active alternate self, if any.

    When a character has assumed an ``AlternateSelf`` that carries a
    ``resonance`` FK, that resonance overrides the GIFT thread's own
    resonance for variant resolution (#1619). The thread's *level* still
    gates which variant tier unlocks — only the resonance axis shifts.

    Derive-on-read (ADR-0014): no snapshot, no write-on-assume. Uses a
    direct DB query rather than the cached reverse OneToOne accessor
    (``sheet.active_alternate_self``) because the sheet object may have
    been loaded before the ``ActiveAlternateSelf`` row was created — the
    cached accessor would return stale ``None``/``DoesNotExist`` in that
    case. A single ``select_related`` query is cheap and always fresh.

    Returns ``None`` when no alt-self is active, the active alt-self has no
    ``resonance`` set, or the lookup raises (defensive — never blocks casting).
    """
    from world.forms.models import ActiveAlternateSelf  # noqa: PLC0415

    try:
        active = (
            ActiveAlternateSelf.objects.select_related("alternate_self__resonance")
            .filter(character_id=sheet.pk, alternate_self__isnull=False)
            .first()
        )
    except ActiveAlternateSelf.DoesNotExist:
        return None
    if active is None or active.alternate_self_id is None:
        return None
    alt = active.alternate_self
    if alt is None:
        return None
    return alt.resonance


def gift_resonances_for(character, gift: Gift) -> list[Resonance]:
    """The resonance(s) this gift manifests as FOR THIS character.

    Derived on read from the character's active GIFT thread on ``gift``: the
    thread's resonance if one exists, else ``gift.resonances`` (the supported
    set). Replaces ``technique.gift.resonances.all()`` at the four cast sites
    (#1578).

    When an ``AlternateSelf`` with a ``resonance`` is active, that resonance
    overrides the thread's (#1619) — the gift manifests as the alt-self's
    resonance, not the thread's own.

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

    sheet = _get_character_sheet(character)
    if sheet is None:
        return gift.cached_resonances

    # #1619: If an alt-self with a resonance is active, it overrides the
    # thread's resonance for all gift-resonance reads.
    alt_resonance = _active_alt_self_resonance(sheet)
    if alt_resonance is not None:
        return [alt_resonance]

    # #1619: Multi-resonance — return all GIFT thread resonances for this
    # gift. When only one exists (the common case), this is a single-element
    # list (same shape as before). When multiple exist, the caller gets the
    # full set and may present a cast-time picker.
    gift_threads = [
        t
        for t in character.threads.all()
        if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
    ]
    if gift_threads:
        return [t.resonance for t in gift_threads]
    return gift.cached_resonances


def resolve_specialized_variant(
    *,
    entity,
    character,
    character_technique=None,
    preferred_resonance: Resonance | None = None,
    _sheet: object = _SHEET_UNSET,
):
    """Return the resonance-specialized variant of ``entity`` for ``character``,
    else ``entity`` unchanged. Derive-on-read (ADR-0014).

    For a Technique: finds the character's active GIFT thread on the technique's
    gift, reads resonance + level, and returns a ``ResolvedTechnique`` wrapping
    the parent + matching variant (or just the parent). For a CovenantRole:
    reads the active COVENANT_ROLE thread via the cached ``character.threads``
    handler and returns the matching sub-role variant (proven path, #1578).

    ``character_technique`` (#2022): when the technique being resolved was
    role-granted (``CharacterTechnique.role_source`` is set), the resolver reads
    the COVENANT_ROLE thread level instead of the GIFT thread level — so a
    role-granted technique specializes by the vow's depth, not the personal
    gift's depth.

    ``preferred_resonance`` (#1619): when the character holds multiple GIFT
    threads on the same gift at different resonances, the caller may pass the
    resonance the player chose at cast time. This takes priority over the
    alt-self resonance override and the thread's own resonance. The thread
    *level* is read from the GIFT thread at the preferred resonance (or the
    first GIFT thread on the gift if none matches — level is shared across
    resonances for the same gift in the common case).

    ``_sheet`` is an internal optimisation parameter: callers that have already
    fetched the ``CharacterSheet`` for ``character`` may pass it here to avoid a
    redundant DB round-trip inside the variant resolver.  Pass the sentinel
    ``_SHEET_UNSET`` (the default) to let the resolver fetch it itself.
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    if isinstance(entity, Technique):
        return _resolve_technique_variant(
            entity,
            character,
            character_technique=character_technique,
            preferred_resonance=preferred_resonance,
            _sheet=_sheet,
        )
    if isinstance(entity, CovenantRole):
        return _resolve_covenant_role_variant(entity, character)
    return entity


def _resolve_technique_variant(
    technique: Technique,
    character,
    *,
    character_technique=None,
    preferred_resonance: Resonance | None = None,
    _sheet: object = _SHEET_UNSET,
) -> Technique | _ResolvedTechnique:
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    # #2022: When the technique was role-granted (CharacterTechnique.role_source
    # is set), resolve the variant using the COVENANT_ROLE thread level instead
    # of the GIFT thread level. The role-granted technique specializes by the
    # vow's depth, not the personal gift's depth.
    use_role_thread = (
        character_technique is not None and character_technique.role_source_id is not None
    )

    # Read the active GIFT thread through the cached ``character.threads``
    # handler (the same cached queryset the covenant path reads), not a fresh
    # ``Thread.objects.filter()`` — per project cached-property rule. A sheetless
    # Character (e.g. an NPC) has no GIFT thread, so it gets the parent technique
    # unchanged; the sheet guard handles that precondition rather than catching
    # the handler's ``sheet_data`` raise. A non-Character object has no
    # ``.threads`` and is left to raise ``AttributeError``.
    #
    # ``_sheet`` may be a pre-fetched CharacterSheet (or explicit None for NPCs)
    # from the caller; use it directly to avoid a redundant DB round-trip.
    if _sheet is _SHEET_UNSET:
        from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

        sheet = _get_character_sheet(character)
    else:
        sheet = _sheet  # type: ignore[assignment]  # caller verified type
    if sheet is None:
        return technique

    if use_role_thread:
        # Read the COVENANT_ROLE thread for the role that granted this technique.
        role_source = character_technique.role_source
        thread = next(
            (
                t
                for t in character.threads.all()
                if t.target_kind == TargetKind.COVENANT_ROLE
                and t.target_covenant_role_id == role_source.covenant_role_id
                and t.retired_at is None
            ),
            None,
        )
    # #1619: When preferred_resonance is set (cast-time picker), find the
    # GIFT thread at that resonance. Fall back to the first GIFT thread on
    # the gift if none matches (so the level is still read).
    elif preferred_resonance is not None:
        thread = next(
            (
                t
                for t in character.threads.all()
                if t.target_kind == TargetKind.GIFT
                and t.target_gift_id == technique.gift_id
                and t.resonance_id == preferred_resonance.pk
            ),
            None,
        )
        if thread is None:
            # No thread at the preferred resonance — fall back to any
            # GIFT thread on this gift (the level is still meaningful).
            thread = next(
                (
                    t
                    for t in character.threads.all()
                    if t.target_kind == TargetKind.GIFT and t.target_gift_id == technique.gift_id
                ),
                None,
            )
    else:
        thread = next(
            (
                t
                for t in character.threads.all()
                if t.target_kind == TargetKind.GIFT and t.target_gift_id == technique.gift_id
            ),
            None,
        )
    if thread is None:
        return technique

    # #1619: Resonance priority for variant resolution:
    # 1. preferred_resonance (cast-time picker) — highest priority
    # 2. active alt-self resonance (alt-self shift)
    # 3. thread's own resonance (default)
    if preferred_resonance is not None:
        effective_resonance = preferred_resonance
    else:
        effective_resonance = _active_alt_self_resonance(sheet)
        if effective_resonance is None:
            effective_resonance = thread.resonance

    variant = TechniqueVariant.matching_variant(
        technique,
        resonance=effective_resonance,
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
