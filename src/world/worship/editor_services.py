"""The Deity Editor's write path and its visibility read (#3780).

Staff author a being on one long page; ``save_being`` takes that page's data
and writes the being, its Codex page and its satellite rows in one
transaction. Small authored sets (nicknames, resonances, facets, feast days,
tarot cards, relationships) are replaced wholesale: the page is the truth.
Visibility is not a field on the being; it is the linked Codex entry's tier,
read through ``visibility_of`` and written through ``is_public`` plus an
``OrganizationCodexGrant`` for the Obscure tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from world.codex.models import CodexCategory, CodexEntry, CodexSubject, OrganizationCodexGrant
from world.worship.constants import (
    PANTHEON_CODEX_CATEGORY_NAME,
    PANTHEON_CODEX_SUBJECT_NAME,
    BeingVisibility,
)
from world.worship.models import (
    BeingFacet,
    BeingNickname,
    BeingRelationship,
    BeingResonance,
    WorshipFeastDay,
    WorshippedBeing,
)

if TYPE_CHECKING:
    from world.societies.models import Organization


def visibility_of(being: WorshippedBeing) -> str:
    entry = being.codex_entry
    if entry is None:
        return BeingVisibility.SECRET
    if entry.is_public:
        return BeingVisibility.PUBLIC
    if OrganizationCodexGrant.objects.filter(entry=entry).exists():
        return BeingVisibility.OBSCURE
    return BeingVisibility.SECRET


def obscure_organization_of(being: WorshippedBeing) -> Organization | None:
    """The organization whose membership knows the being's page, when one does."""
    if being.codex_entry_id is None:
        return None
    grant = (
        OrganizationCodexGrant.objects.filter(entry_id=being.codex_entry_id)
        .select_related("organization")
        .first()
    )
    return grant.organization if grant is not None else None


def ensure_codex_entry(being: WorshippedBeing) -> CodexEntry:
    """The being's Codex page, created under the pantheon subject when absent."""
    if being.codex_entry is not None:
        return being.codex_entry
    category, _ = CodexCategory.objects.get_or_create(name=PANTHEON_CODEX_CATEGORY_NAME)
    subject, _ = CodexSubject.objects.get_or_create(
        category=category, parent=None, name=PANTHEON_CODEX_SUBJECT_NAME
    )
    entry, _ = CodexEntry.objects.get_or_create(
        subject=subject,
        name=being.name,
        defaults={"summary": being.description[:300], "lore_content": being.description},
    )
    being.codex_entry = entry
    being.save(update_fields=["codex_entry"])
    return entry


@dataclass(frozen=True)
class ResonanceLine:
    resonance_id: int
    tier: str


@dataclass(frozen=True)
class FeastDayLine:
    ic_month: int
    ic_day: int
    name: str
    lore: str = ""


@dataclass(frozen=True)
class RelationshipLine:
    other_being_id: int
    valence: str
    public_story: str = ""


@dataclass(frozen=True)
class BeingPage:
    """Everything the edit page holds, validated by the serializer before it gets here."""

    name: str
    description: str
    domains: str
    tradition_id: int
    is_active: bool
    quote: str
    nicknames: list[str] = field(default_factory=list)
    resonances: list[ResonanceLine] = field(default_factory=list)
    facet_ids: list[int] = field(default_factory=list)
    feast_days: list[FeastDayLine] = field(default_factory=list)
    tarot_card_ids: list[int] = field(default_factory=list)
    relationships: list[RelationshipLine] = field(default_factory=list)
    visibility: str = BeingVisibility.SECRET
    organization_id: int | None = None
    gm_notes: str = ""


def save_being(page: BeingPage, *, being: WorshippedBeing | None = None) -> WorshippedBeing:
    """Write one edit page. Live at once; there is no draft gate pre-launch."""
    from world.codex.services import grant_organization_entry_to_members  # noqa: PLC0415

    with transaction.atomic():
        if being is None:
            being = WorshippedBeing(tradition_id=page.tradition_id)
        being.name = page.name.strip()
        being.description = page.description
        being.domains = page.domains
        being.tradition_id = page.tradition_id
        being.is_active = page.is_active
        being.gm_notes = page.gm_notes
        being.save()

        # The Codex page: a public or obscure being needs one; a secret being keeps
        # whatever it has (a quote alone does not conjure a page).
        entry = being.codex_entry
        if page.visibility != BeingVisibility.SECRET or (entry is None and page.quote.strip()):
            entry = ensure_codex_entry(being)
        if entry is not None:
            entry.quote = page.quote.strip()
            entry.is_public = page.visibility == BeingVisibility.PUBLIC
            if entry.name != being.name:
                entry.name = being.name
            entry.save(update_fields=["quote", "is_public", "name"])
            _sync_obscure_grant(entry, page, grant_organization_entry_to_members)

        _replace_nicknames(being, page.nicknames)
        _replace_resonances(being, page.resonances)
        _replace_facets(being, page.facet_ids)
        _replace_feast_days(being, page.feast_days)
        being.tarot_cards.set(page.tarot_card_ids)
        _replace_relationships(being, page.relationships)
    return being


def _sync_obscure_grant(entry: CodexEntry, page: BeingPage, grant_members) -> None:
    grants = OrganizationCodexGrant.objects.filter(entry=entry)
    if page.visibility != BeingVisibility.OBSCURE or page.organization_id is None:
        grants.delete()
        return
    grants.exclude(organization_id=page.organization_id).delete()
    grant, created = OrganizationCodexGrant.objects.get_or_create(
        entry=entry, organization_id=page.organization_id
    )
    if created:
        grant_members(grant)


def _replace_nicknames(being: WorshippedBeing, names: list[str]) -> None:
    wanted = [name.strip() for name in names if name.strip()]
    being.nicknames.exclude(name__in=wanted).delete()
    existing = set(being.nicknames.values_list("name", flat=True))
    fresh = [name for name in dict.fromkeys(wanted) if name not in existing]
    BeingNickname.objects.bulk_create([BeingNickname(being=being, name=name) for name in fresh])


def _replace_resonances(being: WorshippedBeing, lines: list[ResonanceLine]) -> None:
    by_id = {line.resonance_id: line.tier for line in lines}
    being.resonances.exclude(resonance_id__in=by_id).delete()
    for row in being.resonances.all():
        if row.tier != by_id[row.resonance_id]:
            row.tier = by_id[row.resonance_id]
            row.save(update_fields=["tier"])
    existing = set(being.resonances.values_list("resonance_id", flat=True))
    BeingResonance.objects.bulk_create(
        [
            BeingResonance(being=being, resonance_id=rid, tier=tier)
            for rid, tier in by_id.items()
            if rid not in existing
        ]
    )


def _replace_facets(being: WorshippedBeing, facet_ids: list[int]) -> None:
    wanted = set(facet_ids)
    rows = BeingFacet.objects.filter(being=being)
    rows.exclude(facet_id__in=wanted).delete()
    existing = set(rows.values_list("facet_id", flat=True))
    BeingFacet.objects.bulk_create(
        [BeingFacet(being=being, facet_id=fid) for fid in wanted if fid not in existing]
    )


def _replace_feast_days(being: WorshippedBeing, lines: list[FeastDayLine]) -> None:
    by_date = {(line.ic_month, line.ic_day): line for line in lines}
    for row in being.feast_days.all():
        line = by_date.get((row.ic_month, row.ic_day))
        if line is None:
            row.delete()
        elif (row.name, row.lore) != (line.name, line.lore):
            row.name, row.lore = line.name, line.lore
            row.save(update_fields=["name", "lore"])
    existing = {(m, d) for m, d in being.feast_days.values_list("ic_month", "ic_day")}
    WorshipFeastDay.objects.bulk_create(
        [
            WorshipFeastDay(being=being, ic_month=m, ic_day=d, name=line.name, lore=line.lore)
            for (m, d), line in by_date.items()
            if (m, d) not in existing
        ]
    )


def _replace_relationships(being: WorshippedBeing, lines: list[RelationshipLine]) -> None:
    """Relationships are stored once per pair in canonical id order; this being's
    page owns every pair it is part of."""
    wanted = {line.other_being_id: line for line in lines if line.other_being_id != being.pk}
    rows = BeingRelationship.objects.filter(Q(being_a=being) | Q(being_b=being))
    for row in rows:
        other_id = row.being_b_id if row.being_a_id == being.pk else row.being_a_id
        line = wanted.pop(other_id, None)
        if line is None:
            row.delete()
        elif (row.valence, row.public_story) != (line.valence, line.public_story):
            row.valence, row.public_story = line.valence, line.public_story
            row.save(update_fields=["valence", "public_story"])
    for other_id, line in wanted.items():
        a, b = sorted((being.pk, other_id))
        BeingRelationship.objects.create(
            being_a_id=a, being_b_id=b, valence=line.valence, public_story=line.public_story
        )
