"""The flat Facet vocabulary's spelling rule, its near-matches and its merge (#4197).

The vocabulary is typed by many hands (staff on the deity page, players on Motif and
crafted items), so it drifts: Scythe, Scythes, Sickles, Scythe-like Weapons. Three
guards share one spelling rule, ``facet_key``: a picker shows the near-matches before it
offers to create; the create endpoint answers an existing facet (or alias) for a spelling
that already resolves; and when duplicates land anyway, ``merge_facets`` repoints every
binding to the survivor and retires the losers' names as aliases, so a merged spelling
never comes back as a new row.

The merge enumerates ``Facet``'s relations at run time and refuses to run when one has
no handler here (``UnmergedFacetRelation``): a binding added later can be forgotten by a
human, never stranded by the code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import re

from django.db import transaction
from django.db.models import Q

from world.magic.exceptions import UnmergedFacetRelation
from world.magic.models import Facet, FacetAlias

_NON_LETTERS = re.compile(r"[^a-z ]+")
_SPACES = re.compile(r" +")
#: The relations a merge moves, by the accessor name ``Facet._meta.related_objects``
#: reports. A new relation onto Facet must be added here (and to the test that asserts
#: this set equals the live one) before any merge will run.
HANDLED_RELATIONS: frozenset[str] = frozenset(
    {
        "motif_usages",  # MotifResonanceAssociation.facet, unique per motif resonance
        "signature_bonuses",  # SignatureMotifBonus.required_facet
        "anchored_threads",  # Thread.target_facet
        "inherent_on_templates",  # ItemTemplate.inherent_facets (M2M)
        "item_attachments",  # ItemFacet.facet, unique per item instance
        "vogue_momentum",  # FacetVogueMomentum.facet, unique per society
        "fashion_styles",  # FashionStyle.in_vogue_facets (M2M)
        "favored_by_beings",  # worship.BeingFacet.facet, unique per being
        "aliases",  # FacetAlias.facet: the losers' aliases follow the winner
    }
)


def facet_key(name: str) -> str:
    """The spelling two names share when they mean one facet.

    Casefold, letters and spaces only, one space between words, and the last word
    singular: ``"Scythes"`` and ``"scythe"`` both key to ``"scythe"``,
    ``"Scythe-like Weapons"`` to ``"scythe like weapon"``.
    """
    lowered = _NON_LETTERS.sub(" ", name.casefold().replace("-", " "))
    words = _SPACES.sub(" ", lowered).strip().split(" ")
    if words and words[-1]:
        words[-1] = _singular(words[-1])
    return " ".join(w for w in words if w)


#: Words this short are never plurals worth trimming ("ies", "bus", "gas").
_SHORTEST_IES_PLURAL = 5
_SHORTEST_ES_PLURAL = 5
_SHORTEST_S_PLURAL = 4


def _singular(word: str) -> str:
    if len(word) >= _SHORTEST_IES_PLURAL and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) >= _SHORTEST_ES_PLURAL and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) >= _SHORTEST_S_PLURAL and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def find_facet(name: str) -> Facet | None:
    """The facet a spelling already resolves to, by its own name or an alias."""
    key = facet_key(name)
    if not key:
        return None
    for facet in Facet.objects.all():
        if facet_key(facet.name) == key:
            return facet
    for alias in FacetAlias.objects.select_related("facet"):
        if facet_key(alias.name) == key:
            return alias.facet
    return None


def near_facets(name: str, *, limit: int = 6) -> list[Facet]:
    """The facets a picker shows before it offers to create ``name``.

    Equal key first, then a shared stem or containment either way, then one edit
    apart; aliases count for their facet. An empty name gives nothing.
    """
    key = facet_key(name)
    if not key:
        return []
    scored: dict[int, tuple[int, str, Facet]] = {}

    def consider(facet: Facet, candidate: str) -> None:
        other = facet_key(candidate)
        if not other:
            return
        if other == key:
            score = 0
        elif other.startswith(key) or key.startswith(other) or key in other or other in key:
            score = 1
        elif _edit_distance(other, key) <= 1:
            score = 2
        else:
            return
        current = scored.get(facet.pk)
        if current is None or score < current[0]:
            scored[facet.pk] = (score, facet.name, facet)

    for facet in Facet.objects.all():
        consider(facet, facet.name)
    for alias in FacetAlias.objects.select_related("facet"):
        consider(alias.facet, alias.name)
    ordered = sorted(scored.values(), key=lambda row: (row[0], row[1]))
    return [row[2] for row in ordered[:limit]]


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


@dataclass
class FacetMerge:
    """What a merge did: the survivor, the names it retired, and the row counts."""

    winner: Facet
    retired_names: list[str] = field(default_factory=list)
    #: Bindings repointed from a loser to the winner.
    moved: int = 0
    #: Bindings dropped because the winner already had the same one.
    dropped: int = 0


def merge_facets(winner: Facet, losers: Sequence[Facet]) -> FacetMerge:
    """Repoint every binding from each loser to ``winner``, retire the losers as aliases.

    One transaction. A repointed row that would collide with a unique constraint (an
    item that already carries the winner, a being that already favors it) is dropped
    rather than duplicated. Refuses to start when a relation onto Facet has no handler.
    """
    live = {rel.get_accessor_name() for rel in Facet._meta.related_objects}  # noqa: SLF001 - the relation set is the contract
    missing = live - HANDLED_RELATIONS
    if missing:
        detail = f"no merge handler for {sorted(missing)}"
        raise UnmergedFacetRelation(detail)
    losers = [loser for loser in losers if loser.pk != winner.pk]
    result = FacetMerge(winner=winner)
    with transaction.atomic():
        for loser in losers:
            _move_unique_fk(loser, winner, "motif_usages", "motif_resonance", result)
            _move_fk(loser, winner, "signature_bonuses", "required_facet", result)
            _move_fk(loser, winner, "anchored_threads", "target_facet", result)
            _move_m2m(loser, winner, "inherent_on_templates", "inherent_facets", result)
            _move_unique_fk(loser, winner, "item_attachments", "item_instance", result)
            _move_unique_fk(loser, winner, "vogue_momentum", "society", result)
            _move_m2m(loser, winner, "fashion_styles", "in_vogue_facets", result)
            _move_unique_fk(loser, winner, "favored_by_beings", "being", result)
            for alias in loser.aliases.all():
                alias.facet = winner
                alias.save(update_fields=["facet"])
            FacetAlias.objects.get_or_create(name=loser.name, defaults={"facet": winner})
            result.retired_names.append(loser.name)
            loser.delete()
    return result


def _move_fk(
    loser: Facet, winner: Facet, accessor: str, field_name: str, result: FacetMerge
) -> None:
    """Repoint rows with no uniqueness on the facet; row by row, so the identity map follows."""
    for row in getattr(loser, accessor).all():
        setattr(row, field_name, winner)
        row.save(update_fields=[field_name])
        result.moved += 1


def _move_unique_fk(
    loser: Facet, winner: Facet, accessor: str, owner_field: str, result: FacetMerge
) -> None:
    """Repoint rows unique per (owner, facet): an owner already on the winner keeps one."""
    rows = getattr(loser, accessor)
    model = rows.model
    facet_field = next(f.name for f in model._meta.fields if f.related_model is Facet)  # noqa: SLF001 - finds the FK by target
    taken = set(
        model.objects.filter(**{facet_field: winner}).values_list(f"{owner_field}_id", flat=True)
    )
    for row in rows.all():
        if getattr(row, f"{owner_field}_id") in taken:
            row.delete()
            result.dropped += 1
        else:
            setattr(row, facet_field, winner)
            row.save(update_fields=[facet_field])
            result.moved += 1


def _move_m2m(
    loser: Facet, winner: Facet, accessor: str, m2m_field: str, result: FacetMerge
) -> None:
    """Repoint an M2M: each owner gains the winner (once) and loses the loser."""
    owners = getattr(loser, accessor)
    for owner in owners.all():
        bound = getattr(owner, m2m_field)
        if bound.filter(pk=winner.pk).exists():
            result.dropped += 1
        else:
            bound.add(winner)
            result.moved += 1
        bound.remove(loser)


def _alias_filter(name: str) -> Q:
    """Rows whose name or alias is this spelling (for tests and admin search)."""
    return Q(name__iexact=name) | Q(aliases__name__iexact=name)
