"""Which forms of a technique a specific caster can work (#2901).

#2898 gave every technique surface a shared ``effect_summary``, derived per
``Technique`` and cached on the row. That is right for the two catalog surfaces
(character creation, the magic API), which describe the authored technique with
no caster in scope. The two per-character surfaces need something else: **a
variant does not replace the technique, it makes an alternate version
available**, so a per-caster view that collapsed to one form would misreport
what the character can actually do.

Three rules hold this module together:

**One resolver, never a second selection rule.** Which variant applies is
answered by ``resolve_specialized_variant`` (ADR-0055/ADR-0016), called once per
candidate resonance. Re-deriving ``matching_variant``'s predicate here would
drift from the cast the first time either side changed.

**The default marker comes from the resolver too.** A bare ``cast <tech>``
resolves with ``preferred_resonance=None``, a path that folds in the active
alt-self resonance override. Assuming "default = the thread's own resonance"
mislabels a shifted character, so the marker is read off that call and no other.

**No per-caster cache is needed.** A resolved form is fully determined by
``(parent_technique, variant)``, so its summary caches on the ``TechniqueVariant``
row (``cached_effect_summary``) exactly as the base one caches on the
``Technique`` row. The only per-caster work is deciding *which* forms are
reachable, and that reads two already-cached lists: ``character.threads`` (a
cached handler) and ``technique.cached_variants``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import TargetKind
from world.magic.types.technique_effects import (
    TechniqueFormPayload,
    TechniqueSignaturePayload,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.techniques import CharacterTechnique, Technique
    from world.magic.models.threads import Thread


def _candidate_threads(character, technique: Technique, character_technique) -> list[Thread]:
    """The threads whose resonance and level decide this technique's forms.

    Mirrors the branch in ``_resolve_technique_variant`` so enumeration and
    resolution agree about which thread is in play:

    - A role-granted technique (``CharacterTechnique.role_source`` set, #2022)
      specializes by the vow's depth, so the COVENANT_ROLE thread is the only
      candidate.
    - Otherwise every active GIFT thread on the technique's gift is a candidate
      (a multi-resonance character holds more than one, #1619).

    Read through the cached ``character.threads`` handler with a list-comp, never
    a fresh ``Thread.objects.filter()`` (project cached-property rule).
    """
    if character_technique is not None and character_technique.role_source_id is not None:
        role_source = character_technique.role_source
        return [
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role_id == role_source.covenant_role_id
            and t.retired_at is None
        ]
    return [
        t
        for t in character.threads.all()
        if t.target_kind == TargetKind.GIFT
        and t.target_gift_id == technique.gift_id
        and t.retired_at is None
    ]


def _base_form(technique: Technique, *, is_default: bool) -> TechniqueFormPayload:
    """The always-available unspecialized form (``cast <tech> base``)."""
    return TechniqueFormPayload(
        variant_id=None,
        name=technique.name,
        resonance_id=None,
        resonance_name="",
        intensity=technique.intensity,
        control=technique.control,
        is_default=is_default,
        is_locked=False,
        unlock_thread_level=0,
        thread_level=0,
        effect_summary=technique.cached_effect_summary,
    )


def _variant_form(
    technique: Technique,
    variant,
    *,
    thread_level: int,
    is_default: bool,
    is_locked: bool,
) -> TechniqueFormPayload:
    """One specialized form, unlocked or not.

    ``effect_summary`` is read off ``variant.cached_effect_summary`` rather than
    re-summarised here: the resolved form takes no caster input, so the build is
    shared by every character who reaches this variant.
    """
    return TechniqueFormPayload(
        variant_id=variant.pk,
        name=variant.name_override or technique.name,
        resonance_id=variant.resonance_id,
        resonance_name=variant.resonance.name if variant.resonance_id else "",
        intensity=technique.intensity + variant.intensity_delta,
        control=technique.control + variant.control_delta,
        is_default=is_default,
        is_locked=is_locked,
        unlock_thread_level=variant.unlock_thread_level,
        thread_level=thread_level,
        effect_summary=variant.cached_effect_summary,
    )


def _next_locked_variant(technique: Technique, *, resonance_id: int, thread_level: int):
    """The nearest form this thread has not reached yet, or ``None``.

    One step ahead per resonance, not the whole ladder: the lowest
    ``unlock_thread_level`` strictly above the thread's current level. Filters
    the already-cached ``technique.cached_variants`` list rather than querying.
    """
    ahead = [
        v
        for v in technique.cached_variants
        if v.resonance_id == resonance_id and v.unlock_thread_level > thread_level
    ]
    if not ahead:
        return None
    return min(ahead, key=lambda v: v.unlock_thread_level)


def available_technique_forms(
    character,
    technique: Technique,
    *,
    character_technique: CharacterTechnique | None = None,
    sheet: CharacterSheet | None = None,
) -> list[TechniqueFormPayload]:
    """Every form of ``technique`` that ``character`` can work, plus the next locked one.

    The base form always leads. Each specialized form the caster has unlocked
    follows, at most one per thread resonance (``matching_variant`` picks the
    highest qualifying variant per resonance, so lower tiers are shadowed rather
    than listed alongside). Locked entries come last and carry ``is_locked=True``.

    A caster with no thread on the technique's gift gets the base form alone,
    marked default. So does a sheetless character (an NPC), which has no threads
    at all.

    ``sheet`` lets a caller that already holds the ``CharacterSheet`` — the two
    display surfaces both do, and both call this once per known technique — hand
    it in rather than have every call re-``SELECT`` the row it is standing on.
    """
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415
    from world.magic.specialization.services import (  # noqa: PLC0415
        _ResolvedTechnique,
        resolve_specialized_variant,
    )

    if sheet is None:
        sheet = _get_character_sheet(character)
    if sheet is None:
        return [_base_form(technique, is_default=True)]

    # What a bare ``cast <tech>`` works right now — the alt-self override lives
    # on this path, so the default marker must come from here.
    default = resolve_specialized_variant(
        entity=technique,
        character=character,
        character_technique=character_technique,
        _sheet=sheet,
    )
    default_variant_id = (
        default.variant.pk if isinstance(default, _ResolvedTechnique) else None  # type: ignore[union-attr]
    )

    threads = _candidate_threads(character, technique, character_technique)
    forms: list[TechniqueFormPayload] = [
        _base_form(technique, is_default=default_variant_id is None)
    ]

    seen_variant_ids: set[int] = set()
    locked: list[TechniqueFormPayload] = []
    for thread in threads:
        resolved = resolve_specialized_variant(
            entity=technique,
            character=character,
            character_technique=character_technique,
            preferred_resonance=thread.resonance,
            _sheet=sheet,
        )
        if isinstance(resolved, _ResolvedTechnique) and resolved.variant.pk not in seen_variant_ids:
            seen_variant_ids.add(resolved.variant.pk)
            forms.append(
                _variant_form(
                    technique,
                    resolved.variant,
                    thread_level=thread.level,
                    is_default=resolved.variant.pk == default_variant_id,
                    is_locked=False,
                )
            )

        ahead = _next_locked_variant(
            technique, resonance_id=thread.resonance_id, thread_level=thread.level
        )
        if ahead is not None and ahead.pk not in seen_variant_ids:
            seen_variant_ids.add(ahead.pk)
            locked.append(
                _variant_form(
                    technique,
                    ahead,
                    thread_level=thread.level,
                    is_default=False,
                    is_locked=True,
                )
            )

    return forms + locked


def technique_signature_payload(
    character, technique: Technique
) -> TechniqueSignaturePayload | None:
    """The signature flourish riding whichever form is chosen, or ``None``.

    Additive, never a sibling form (ADR-0072), so this is returned beside the
    form list rather than as an entry inside it. Delegates the lookup to the
    existing ``signature_bonus_for`` — the same read the cast wiring makes.
    """
    from world.magic.services.signature import signature_bonus_for  # noqa: PLC0415

    bonus = signature_bonus_for(character, technique)
    if bonus is None:
        return None
    return TechniqueSignaturePayload(
        name=bonus.name,
        narrative_snippet=bonus.narrative_snippet,
        intensity_delta=bonus.flat_intensity_delta,
    )
