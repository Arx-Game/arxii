"""Whether a character is fighting their combat style's way, roll by roll (#4884).

A ``CombatStyle`` adds its own skill to the Strike, to a technique's hit roll and to the
defense roll, but only while the character fights the way it teaches. The bonus lapses:

- on an attack roll (a Strike or a technique), when the weapon used is not one of the
  style's weapon kinds, or a held vow is not on the style's list. A technique cast with no
  weapon in hand has no weapon to test; only the vow test applies;
- on a defense roll, when any worn armor piece's kind is not one of the style's armor
  kinds, or a held vow is not on the list.

Bare hands are the Unarmed weapon kind. A "held vow" is every engaged PRIMARY covenant
role (``currently_engaged_primary_roles``); a sub-role counts as listed when it or its
anchor vow is. Holding no vow never lapses. A lapse drops the style skill only: the hit
stat and the defense type still apply, and the style's armor share is unchanged (owner
rulings, 2026-11-01). A character with no style, or a style with no skill, has no style
term at all.

``StyleFit`` is what a roll needs: the term to add (or none), the style's hit stat, and,
when lapsed, the reason as the roll's breakdown says it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from world.covenants.constants import STYLE_LAPSE_GEAR_WORDS, StyleLapse
from world.items.constants import ARMOR_ARCHETYPES, WEAPON_ARCHETYPES, GearArchetype

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typeclasses.characters import Character
    from world.checks.models import CheckType
    from world.checks.types import ExtraTraitTerm
    from world.covenants.models import CombatStyle, CovenantRole

#: The style skill counts once, like a weapon skill.
STYLE_SKILL_WEIGHT = Decimal(1)


@dataclass(frozen=True)
class StyleFit:
    """A character's combat style on one roll (#4884).

    ``style`` is None when the character has no style. ``lapse`` is None while the style
    fits; set, the style skill does not count and ``lapse_note`` says why ("two-handed
    weapons are not this style's").
    """

    style: CombatStyle | None
    lapse: StyleLapse | None = None
    lapse_note: str = ""

    @property
    def has_skill_term(self) -> bool:
        """Whether the style has an active skill a roll could add (fitting or not)."""
        return (
            self.style is not None and self.style.skill is not None and self.style.skill.is_active
        )

    @property
    def counts(self) -> bool:
        """Whether the style skill counts on this roll."""
        return self.has_skill_term and self.lapse is None

    @property
    def hit_stat_name(self) -> str | None:
        """The stat a Strike hits with under this style (lapsed or not), or None."""
        if self.style is None or self.style.hit_stat is None:
            return None
        return self.style.hit_stat.name

    def extra_traits(
        self, check_type: CheckType | None = None, counted: Sequence[ExtraTraitTerm] = ()
    ) -> list[ExtraTraitTerm]:
        """The style skill as a roll term while it counts, else an empty list.

        Never a second time: when the roll already counts the style skill's trait, through
        ``check_type``'s own trait rows or one of the ``counted`` terms (a Path, Gift or
        technique skill that is also a style's skill), the style adds nothing more.
        """
        if not self.counts:
            return []
        from world.checks.types import ExtraTraitTerm  # noqa: PLC0415

        trait = self.style.skill.trait
        if any(term.trait.pk == trait.pk for term in counted):
            return []
        if check_type is not None and check_type.traits.filter(trait_id=trait.pk).exists():
            return []
        return [ExtraTraitTerm(trait=trait, weight=STYLE_SKILL_WEIGHT)]


def _style_of(character: Character) -> CombatStyle | None:
    sheet = character.character_sheet if hasattr(character, "character_sheet") else None
    return sheet.combat_style if sheet is not None else None


def _held_vows(character: Character) -> list[CovenantRole]:
    if not hasattr(character, "covenant_roles"):
        return []
    return list(character.covenant_roles.currently_engaged_primary_roles())


def _unlisted_vow(style: CombatStyle, character: Character) -> CovenantRole | None:
    """The first held vow the style does not list (a sub-role counts by its anchor)."""
    held = _held_vows(character)
    if not held:
        return None
    listed = set(style.compatible_roles.values_list("pk", flat=True))
    for role in held:
        if role.pk not in listed and role.parent_role_id not in listed:
            return role
    return None


def _gear_note(archetype: str) -> str:
    words = STYLE_LAPSE_GEAR_WORDS.get(archetype)
    if words is None:
        words = f"{GearArchetype(archetype).label.lower()} is"
    return f"{words} not this style's"


def _fit(
    character: Character,
    gear_test: frozenset[str],
    kinds_used: list[str],
    lapse_kind: StyleLapse,
) -> StyleFit:
    """The style fit when ``kinds_used`` must all be in the style's ``gear_test`` kinds."""
    style = _style_of(character)
    if style is None or style.skill is None or not style.skill.is_active:
        return StyleFit(style=style)
    listed = (
        {kind for kind in style.gear.values_list("gear_archetype", flat=True) if kind in gear_test}
        if kinds_used
        else set()
    )
    for kind in kinds_used:
        if kind not in listed:
            return StyleFit(style=style, lapse=lapse_kind, lapse_note=_gear_note(kind))
    vow = _unlisted_vow(style, character)
    if vow is not None:
        return StyleFit(
            style=style, lapse=StyleLapse.VOW, lapse_note=f"{vow.name} is not this style's vow"
        )
    return StyleFit(style=style)


def style_fit_for_attack(character: Character, weapon_archetype: str | None) -> StyleFit:
    """The style fit for an attack made with ``weapon_archetype``.

    A Strike always names its kind (bare hands are ``UNARMED``). ``None`` is a technique
    cast with no weapon in hand: there is no weapon to test, so only the vow test applies
    and a caster keeps the style skill on every spell.
    """
    kinds = [weapon_archetype] if weapon_archetype is not None else []
    return _fit(character, WEAPON_ARCHETYPES, kinds, StyleLapse.WEAPON)


def worn_armor_kinds(character: Character) -> list[str]:
    """The gear kind of each armor piece ``character`` wears, in equipped order, once each."""
    kinds: list[str] = []
    for equipped in character.equipped_items:
        kind = equipped.item_instance.template.gear_archetype
        if kind in ARMOR_ARCHETYPES and kind not in kinds:
            kinds.append(kind)
    return kinds


def style_fit_for_defense(character: Character) -> StyleFit:
    """The style fit for a defense roll in what ``character`` wears now."""
    if not hasattr(character, "equipped_items"):
        return _fit(character, ARMOR_ARCHETYPES, [], StyleLapse.ARMOR)
    return _fit(character, ARMOR_ARCHETYPES, worn_armor_kinds(character), StyleLapse.ARMOR)
