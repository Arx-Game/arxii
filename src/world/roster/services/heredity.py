"""Parent Dominance / heredity service (#2815).

Species inheritance is magical and maternal by default: a child is the
mother's species unless the father's power band strictly exceeds hers, and a
chimeric (unique authored halfbreed species) child is possible only when both
parents are Grand+ (level 16+). Roles are derived at computation time, never
stored (ADR-0097 retired mother/father slots): BIOLOGICAL edges derive the
maternal role from parent gender; TREE_OF_SOULS edges carry it via
``ParentageEdge.is_ritual_invoker`` — the invoker is the dominant line
regardless of gender.

Validation built on this service is one-directional and creation-time only:
a flip/chimeric/off-palette outcome requires supporting bands *now*; a GM
later powering-up a parent contradicts nothing (expression is chance).

Named "heredity" deliberately — "lineage" already means the CG Lineage stage,
display-only lineage in appearance docs, and roadmap "lineage powers".
"""

from dataclasses import dataclass

from world.forms.models import FormTrait, FormTraitOption
from world.forms.services import get_cg_form_options
from world.roster.constants import ParentageKind, PowerBand
from world.roster.models import Kinsperson, KinspersonTraitValue, ParentageEdge
from world.species.models import Species

_FEMALE_GENDER_KEY = "female"

# Every band below PUISSANT is one dominance tier — the finer sub-Puissant
# bands (quiescent/prospect/potential) matter for story, never for species.
DOMINANCE_TIER: dict[str | None, int] = {
    None: 0,
    PowerBand.QUIESCENT: 0,
    PowerBand.PROSPECT: 0,
    PowerBand.POTENTIAL: 0,
    PowerBand.PUISSANT: 1,
    PowerBand.TRUE: 2,
    PowerBand.GRAND: 3,
    PowerBand.TRANSCENDENT: 4,
}
CHIMERIC_MIN_TIER = DOMINANCE_TIER[PowerBand.GRAND]

_HEREDITY_KINDS = (ParentageKind.BIOLOGICAL, ParentageKind.TREE_OF_SOULS)

# Family-look narrowing needs both sides of the parentage recorded — a single
# recorded parent means the other side is simply unknown, which keeps the
# species palette open (lazy definition: unknown = free).
_MIN_LINES_FOR_NARROWING = 2


@dataclass(frozen=True)
class ParentLine:
    """One parent's contribution to heredity math.

    ``kinsperson`` is None for a CG-invented parent that has no node yet;
    ``species``/``band`` carry the declared values in that case.
    """

    kinsperson: Kinsperson | None
    species: Species | None
    band: str | None
    is_dominant_role: bool


@dataclass(frozen=True)
class SpeciesDerivation:
    """Outcome set for a child: maternal always first; flips appended."""

    allowed: list[Species]
    chimeric_possible: bool


@dataclass(frozen=True)
class InheritedTraitOptions:
    """Cross-line options for one trait, tagged with their source parent."""

    trait: FormTrait
    options: list[FormTraitOption]
    source: str


def dominance_tier(band: str | None) -> int:
    """Collapse a PowerBand (or None = unspecified) to its dominance tier."""
    return DOMINANCE_TIER.get(band, 0)


def derive_lines_for_child(child: Kinsperson) -> list[ParentLine]:
    """Build ParentLines from a child's true heredity edges, kind-aware.

    Dominant role: a TREE_OF_SOULS invoker wins outright; otherwise the
    single female-gendered biological parent; otherwise the first edge's
    parent (ambiguous authored data — GM cleanup territory, not a crash).
    """
    edges = list(
        ParentageEdge.objects.filter(
            child=child, is_true=True, kind__in=_HEREDITY_KINDS
        ).select_related("parent__gender", "parent__species")
    )
    if not edges:
        return []

    dominant_edge = next((edge for edge in edges if edge.is_ritual_invoker), None)
    if dominant_edge is None:
        female_edges = [
            edge
            for edge in edges
            if edge.parent.gender is not None and edge.parent.gender.key == _FEMALE_GENDER_KEY
        ]
        dominant_edge = female_edges[0] if len(female_edges) == 1 else edges[0]

    return [
        ParentLine(
            kinsperson=edge.parent,
            species=edge.parent.species,
            band=edge.parent.power_band,
            is_dominant_role=edge is dominant_edge,
        )
        for edge in edges
    ]


def derivable_species(lines: list[ParentLine], *, fallback_maternal: Species) -> SpeciesDerivation:
    """Species a child of these parents may legally be, per Parent Dominance.

    The dominant (maternal/invoker) line's species is always allowed — falling
    back to ``fallback_maternal`` (the child's chosen species) when that
    parent is undeclared, per back-inference. A non-dominant parent's species
    is additionally allowed when their tier strictly exceeds the dominant
    parent's. Chimeric is possible when both sides are Grand+ and differ.
    """
    dominant = next((line for line in lines if line.is_dominant_role), None)
    maternal_species = (
        dominant.species
        if dominant is not None and dominant.species is not None
        else fallback_maternal
    )
    maternal_tier = dominance_tier(dominant.band) if dominant is not None else 0

    allowed: list[Species] = [maternal_species]
    chimeric_possible = False
    for species, line_tier in _competing_lines(lines, maternal_species):
        if line_tier > maternal_tier and species not in allowed:
            allowed.append(species)
        if line_tier >= CHIMERIC_MIN_TIER and maternal_tier >= CHIMERIC_MIN_TIER:
            chimeric_possible = True
    return SpeciesDerivation(allowed=allowed, chimeric_possible=chimeric_possible)


def _competing_lines(
    lines: list[ParentLine], maternal_species: Species
) -> list[tuple[Species, int]]:
    """(species, dominance tier) per non-dominant line that could widen the allowed set.

    Only a line with a *declared* species differing from the maternal line's
    can add a species or open the chimeric door; the dominant line and
    undeclared parents contribute nothing.
    """
    competing: list[tuple[Species, int]] = []
    for line in lines:
        species = line.species
        if line.is_dominant_role or species is None or species == maternal_species:
            continue
        competing.append((species, dominance_tier(line.band)))
    return competing


def _line_pins(line: ParentLine) -> dict[int, FormTraitOption]:
    """A parent line's pinned values by trait pk (empty for undefined parents)."""
    if line.kinsperson is None:
        return {}
    return {
        pin.trait_id: pin.option
        for pin in KinspersonTraitValue.objects.filter(kinsperson=line.kinsperson).select_related(
            "option__trait"
        )
    }


def base_trait_options(
    child_species: Species, lines: list[ParentLine]
) -> dict[FormTrait, list[FormTraitOption]]:
    """The child's own-line options per trait, narrowed to the family look.

    Children of *defined* parents work from their parents' actual colors,
    defaulting to the mother's: when EVERY parent line carries a pin for a
    trait, that trait's options collapse to the same-species parents' pinned
    values (dominant line first — the UI's default ordering). An unpinned
    side keeps the species palette open (lazy definition: unknown = free),
    as does a family with fewer than two recorded parent lines.
    Cross-species parents' pins are NOT folded in here — they surface via
    ``inherited_options`` with their source label, so the UI grouping and
    the no-duplicate invariant both hold.
    """
    palette = get_cg_form_options(child_species)
    if len(lines) < _MIN_LINES_FOR_NARROWING:
        return palette

    ordered = sorted(lines, key=lambda line: not line.is_dominant_role)
    pins_by_line = [(line, _line_pins(line)) for line in ordered]

    result: dict[FormTrait, list[FormTraitOption]] = {}
    for trait, options in palette.items():
        pinned = [(line, pins.get(trait.pk)) for line, pins in pins_by_line]
        if all(option is not None for _, option in pinned):
            family_look: list[FormTraitOption] = []
            for line, option in pinned:
                if (
                    option is not None
                    and line.species == child_species
                    and option not in family_look
                ):
                    family_look.append(option)
            result[trait] = family_look or list(options)
        else:
            result[trait] = list(options)
    return result


def _parent_palette(
    line: ParentLine, trait_pins: dict[int, FormTraitOption]
) -> dict[FormTrait, list[FormTraitOption]]:
    """A cross-line parent's offerable options per trait: pins win outright;
    unpinned traits stay free and expose the parent species' full palette."""
    palette = get_cg_form_options(line.species) if line.species is not None else {}
    result: dict[FormTrait, list[FormTraitOption]] = {}
    for trait, options in palette.items():
        pinned = trait_pins.get(trait.pk)
        result[trait] = [pinned] if pinned is not None else list(options)
    # A pin on a trait outside the current CG palette still constrains/offers.
    for trait_pk, option in trait_pins.items():
        if not any(trait.pk == trait_pk for trait in result):
            result[option.trait] = [option]
    return result


def inherited_options(
    child_species: Species, lines: list[ParentLine]
) -> list[InheritedTraitOptions]:
    """Cross-line options a child of ``child_species`` may take, per parent.

    Only options *outside* the child's own palette appear — a parent whose
    colors all fall inside it leaves no visible tell (hidden ancestry stays
    hideable). Pinned parent values constrain; unpinned expose the parent
    species' palette (the first child to draw on one defines it).
    """
    own_palette = get_cg_form_options(child_species)
    own_by_trait = {trait.pk: {opt.pk for opt in options} for trait, options in own_palette.items()}

    result: list[InheritedTraitOptions] = []
    for line in lines:
        if line.is_dominant_role or line.species is None or line.species == child_species:
            continue
        trait_pins = _line_pins(line)
        has_real_name = line.kinsperson is not None and bool(
            line.kinsperson.name or line.kinsperson.sheet_id
        )
        source = line.kinsperson.display_name if has_real_name else f"{line.species.name} parent"
        for trait, options in _parent_palette(line, trait_pins).items():
            own_option_pks = own_by_trait.get(trait.pk, set())
            novel = [opt for opt in options if opt.pk not in own_option_pks]
            if novel:
                result.append(InheritedTraitOptions(trait=trait, options=novel, source=source))
    return result
