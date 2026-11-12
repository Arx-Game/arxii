"""The technique picker (#4341): a player chooses which bound being or companion her
manifesting technique brings into a fight.

A manifesting technique is one with ``TechniqueManifestOption`` rows. The character's
pick is her ``CharacterManifestation`` row for that technique; combat reads it when the
technique manifests (``effect_handlers``). These services only list the options and
write the pick. An option is choosable while its bond holds: an active patronage with
the being, or one of her own unreleased companions of the archetype.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.exceptions import ManifestChoiceError
from world.magic.types.manifestation import ManifestChoice, ManifestOptionChoice

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.companions.models import Companion
    from world.magic.models import CharacterManifestation, Technique, TechniqueManifestOption

MSG_UNKNOWN_TECHNIQUE = "You know no technique by that name that brings anything into a fight."
MSG_UNKNOWN_OPTION = "That technique cannot bring that."
MSG_BEING_TAKES_NO_COMPANION = "A being comes on its own; it takes no companion."
MSG_NOT_YOUR_COMPANION = "That is not one of your companions of that kind."


@dataclass(frozen=True)
class _KnownTechnique:
    technique: Technique
    name: str


@dataclass
class _Bonds:
    """What the character is bound to, read once for a set of options."""

    patron_being_ids: frozenset[int]
    unreleased: dict[int, list[Companion]] = field(default_factory=dict)
    released_archetype_ids: frozenset[int] = frozenset()

    @classmethod
    def for_sheet(cls, sheet: CharacterSheet, archetype_ids: Iterable[int]) -> _Bonds:
        from world.companions.models import Companion  # noqa: PLC0415
        from world.worship.services import active_patronage_for  # noqa: PLC0415

        patron_ids = frozenset(s.being_id for s in active_patronage_for(sheet))
        archetype_ids = set(archetype_ids)
        unreleased: dict[int, list[Companion]] = defaultdict(list)
        released: set[int] = set()
        if archetype_ids:
            for companion in Companion.objects.filter(
                owner=sheet, archetype_id__in=archetype_ids
            ).order_by("name", "pk"):
                if companion.released_at is None:
                    unreleased[companion.archetype_id].append(companion)
                else:
                    released.add(companion.archetype_id)
        return cls(
            patron_being_ids=patron_ids,
            unreleased=dict(unreleased),
            released_archetype_ids=frozenset(released),
        )

    def refusal(self, option: TechniqueManifestOption) -> str:
        """Why ``option``'s bond does not hold, as a lowercase phrase; "" when it holds."""
        if option.being_id is not None:
            if option.being_id in self.patron_being_ids:
                return ""
            return f"you have no patronage with {option.being.name}"
        if self.unreleased.get(option.archetype_id):
            return ""
        archetype = option.archetype.name
        if option.archetype_id in self.released_archetype_ids:
            return f"your {archetype} companion was released"
        return f"you have no {archetype} companion"

    def companion_for(
        self, option: TechniqueManifestOption, preferred: Companion | None = None
    ) -> Companion | None:
        """The companion an archetype option brings: ``preferred`` if still bound, else the
        first unreleased one by name."""
        if option.archetype_id is None:
            return None
        candidates = self.unreleased.get(option.archetype_id, [])
        if preferred is not None and any(c.pk == preferred.pk for c in candidates):
            return preferred
        return candidates[0] if candidates else None


def _sentence(phrase: str) -> str:
    return f"{phrase[0].upper()}{phrase[1:]}." if phrase else ""


def _known_manifesting(sheet: CharacterSheet) -> list[_KnownTechnique]:
    """Every technique the character knows (held or a known ultimate) that has options."""
    from world.magic.models import CharacterTechnique, KnownUltimate  # noqa: PLC0415

    known: dict[int, _KnownTechnique] = {}
    for hold in (
        CharacterTechnique.objects.filter(
            character=sheet, technique__manifest_options__isnull=False
        )
        .select_related("technique")
        .distinct()
    ):
        known[hold.technique_id] = _KnownTechnique(hold.technique, hold.display_name)
    for ultimate in (
        KnownUltimate.objects.filter(character=sheet, technique__manifest_options__isnull=False)
        .select_related("technique")
        .distinct()
    ):
        known.setdefault(
            ultimate.technique_id, _KnownTechnique(ultimate.technique, ultimate.technique.name)
        )
    return sorted(known.values(), key=lambda k: (k.name.lower(), k.technique.pk))


def _label(option: TechniqueManifestOption, bonds: _Bonds, companion: Companion | None) -> str:
    if option.being_id is not None:
        if option.being_id in bonds.patron_being_ids:
            return f"{option.being.name} (your patron)"
        return option.being.name
    if companion is not None:
        return f"{companion.name} (your {option.archetype.name})"
    return option.archetype.name


def manifest_choices_for(sheet: CharacterSheet) -> list[ManifestChoice]:
    """Each manifesting technique the character knows, its options and her current pick.

    Options whose bond does not hold are listed too, unavailable, with the reason.
    A fixed number of queries whatever the count of techniques and options.
    """
    from world.magic.models import (  # noqa: PLC0415
        CharacterManifestation,
        TechniqueManifestOption,
    )

    known = _known_manifesting(sheet)
    if not known:
        return []
    technique_ids = [k.technique.pk for k in known]
    options_by_technique: dict[int, list[TechniqueManifestOption]] = defaultdict(list)
    for option in (
        TechniqueManifestOption.objects.filter(technique_id__in=technique_ids)
        .select_related("being", "archetype")
        .order_by("pk")
    ):
        options_by_technique[option.technique_id].append(option)
    current: dict[int, CharacterManifestation] = {
        m.technique_id: m
        for m in CharacterManifestation.objects.filter(
            character=sheet, technique_id__in=technique_ids
        ).select_related("option", "companion")
    }
    bonds = _Bonds.for_sheet(
        sheet,
        (
            o.archetype_id
            for options in options_by_technique.values()
            for o in options
            if o.archetype_id is not None
        ),
    )

    choices: list[ManifestChoice] = []
    for entry in known:
        pick = current.get(entry.technique.pk)
        rows: list[ManifestOptionChoice] = []
        for option in options_by_technique[entry.technique.pk]:
            preferred = pick.companion if pick is not None and pick.option_id == option.pk else None
            companion = bonds.companion_for(option, preferred)
            reason = bonds.refusal(option)
            rows.append(
                ManifestOptionChoice(
                    option=option,
                    label=_label(option, bonds, companion),
                    available=not reason,
                    reason=reason,
                    companion=companion,
                )
            )
        choices.append(
            ManifestChoice(
                technique=entry.technique,
                technique_name=entry.name,
                options=tuple(rows),
                chosen=pick.option if pick is not None else None,
                chosen_companion=pick.companion if pick is not None else None,
            )
        )
    return choices


def manifesting_technique_named(sheet: CharacterSheet, name: str) -> Technique | None:
    """A manifesting technique the character knows, by catalog name or her own name for it."""
    wanted = name.strip().lower()
    if not wanted:
        return None
    for entry in _known_manifesting(sheet):
        if wanted in (entry.name.lower(), entry.technique.name.lower()):
            return entry.technique
    return None


def manifesting_technique_by_id(sheet: CharacterSheet, technique_id: int) -> Technique | None:
    """A manifesting technique the character knows, by id."""
    for entry in _known_manifesting(sheet):
        if entry.technique.pk == technique_id:
            return entry.technique
    return None


def manifest_option_named(
    sheet: CharacterSheet, technique: Technique, name: str
) -> tuple[TechniqueManifestOption, Companion | None] | None:
    """The technique's option named ``name``: a being's or archetype's name, or the name of
    one of the character's own companions of an optioned archetype (then that companion)."""
    from world.companions.models import Companion  # noqa: PLC0415

    wanted = name.strip().lower()
    if not wanted:
        return None
    options = list(technique.manifest_options.select_related("being", "archetype"))
    for option in options:
        entity = option.being or option.archetype
        if entity is not None and entity.name.lower() == wanted:
            return option, None
    by_archetype = {o.archetype_id: o for o in options if o.archetype_id is not None}
    if by_archetype:
        companion = (
            Companion.objects.filter(
                owner=sheet,
                archetype_id__in=list(by_archetype),
                name__iexact=name.strip(),
                released_at__isnull=True,
            )
            .order_by("pk")
            .first()
        )
        if companion is not None:
            return by_archetype[companion.archetype_id], companion
    return None


def _choosable_companion(
    sheet: CharacterSheet,
    technique: Technique,
    option: TechniqueManifestOption,
    companion: Companion | None,
) -> Companion | None:
    """Refuse (``ManifestChoiceError``) unless ``option`` can be chosen; return the
    companion it brings (None for a being option)."""
    if manifesting_technique_by_id(sheet, technique.pk) is None:
        raise ManifestChoiceError(MSG_UNKNOWN_TECHNIQUE)
    if option.technique_id != technique.pk:
        raise ManifestChoiceError(MSG_UNKNOWN_OPTION)
    if option.being_id is not None and companion is not None:
        raise ManifestChoiceError(MSG_BEING_TAKES_NO_COMPANION)
    bonds = _Bonds.for_sheet(sheet, [option.archetype_id] if option.archetype_id else [])
    if option.archetype_id is not None and companion is not None:
        if companion.owner_id != sheet.pk or companion.archetype_id != option.archetype_id:
            raise ManifestChoiceError(MSG_NOT_YOUR_COMPANION)
        if companion.released_at is not None:
            raise ManifestChoiceError(
                _sentence(f"your {option.archetype.name} companion was released")
            )
    reason = bonds.refusal(option)
    if reason:
        raise ManifestChoiceError(_sentence(reason))
    if option.archetype_id is not None and companion is None:
        return bonds.companion_for(option)
    return companion


def set_character_manifestation(
    sheet: CharacterSheet,
    technique: Technique,
    option: TechniqueManifestOption,
    companion: Companion | None = None,
) -> CharacterManifestation:
    """Make ``option`` what ``technique`` brings into a fight for this character.

    Refuses (``ManifestChoiceError`` with the reason) when she does not know the
    technique, the option is another technique's, or the bond does not hold. For an
    archetype option with no ``companion`` given, her first unreleased companion of that
    archetype by name goes. Upserts the one row per (character, technique).
    """
    from world.magic.models import CharacterManifestation  # noqa: PLC0415

    companion = _choosable_companion(sheet, technique, option, companion)

    # Built unsaved and checked before any write, so a refusal never leaves values on a
    # shared (identity-mapped) row the database never held.
    candidate = CharacterManifestation(
        character=sheet, technique=technique, option=option, companion=companion
    )
    try:
        candidate.clean()
    except ValidationError as exc:
        raise ManifestChoiceError from exc

    with transaction.atomic():
        existing = (
            CharacterManifestation.objects.select_for_update()
            .filter(character=sheet, technique=technique)
            .first()
        )
        if existing is None:
            candidate.save()
            return candidate
        existing.option = option
        existing.companion = companion
        existing.save(update_fields=["option", "companion"])
        return existing
