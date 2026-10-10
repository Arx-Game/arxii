"""Magic as a public service on a live sheet (#4224, #3988 piece C).

``provision_magic`` is what character creation's ``finalize_magic_data`` does, taking
explicit picks instead of a draft, so finalize and staff edit mode's Grant magic share
one writer and one ordering. The ordering matters: the gift thread anchors to the CG
resonance, species gifts anchor to the same thread, the aura is recomputed once every
resonance source exists, and the anima ritual (the character's magical identity) carries
that resonance too. Finalize's draft-only steps (technique personalizations, the
Glimpse-born distinction links, the codex grants of the other CG choices) ride hooks
at the exact points they always ran.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction

from world.character_creation.sheet_writers import SheetWriteError, grant_codex_entries

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import Beginnings
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterAura, Gift, Resonance, Technique, Tradition
    from world.skills.models import Skill
    from world.species.models import Species
    from world.traits.models import Trait


@dataclass(frozen=True)
class MagicPicks:
    """Everything magic needs, as rows. ``origin`` stamps the gift and technique links.

    Staff granting a character's starting magic use ``CHARACTER_CREATION`` too: it is
    the same starting kit, and the ledger reads where the magic came from, not who typed.
    """

    tradition: Tradition
    gift: Gift | None
    techniques: Sequence[Technique]
    resonance: Resonance | None
    anima_stat: Trait | None
    anima_skill: Skill | None
    ritual_name: str
    account: AccountDB | None
    origin: str
    species: Species | None = None
    beginnings: Beginnings | None = None
    glimpse_story: str = ""
    glimpse_tag_ids: Sequence[int] = field(default_factory=tuple)


@dataclass(frozen=True)
class MagicHooks:
    """Finalize's draft-only steps, run where finalize always ran them."""

    after_languages: Callable[[], None] | None = None
    after_tradition_codex: Callable[[], None] | None = None
    after_aura: Callable[[CharacterAura], None] | None = None


def technique_pick_limit(sheet: CharacterSheet) -> int:
    """How many starting techniques a sheet may hold: 1 plus its distinctions' bonus.

    The same rule as ``CharacterDraft.starting_technique_picks``, read from the
    distinctions the sheet holds instead of a draft's picks.
    """
    from world.character_creation.constants import (  # noqa: PLC0415
        CG_MODIFIER_CATEGORY,
        STARTING_TECHNIQUE_PICKS_TARGET,
    )
    from world.distinctions.models import CharacterDistinction, DistinctionEffect  # noqa: PLC0415

    ranks: dict[int, list[int]] = {}
    for distinction_id, rank in CharacterDistinction.objects.filter(character=sheet).values_list(
        "distinction_id", "rank"
    ):
        ranks.setdefault(distinction_id, []).append(rank)
    if not ranks:
        return 1
    effects = DistinctionEffect.objects.filter(
        distinction_id__in=list(ranks),
        target__name=STARTING_TECHNIQUE_PICKS_TARGET,
        target__category__name=CG_MODIFIER_CATEGORY,
    )
    return 1 + sum(
        effect.get_value_at_rank(rank)
        for effect in effects
        for rank in ranks[effect.distinction_id]
    )


def _check_techniques(sheet: CharacterSheet, picks: MagicPicks, path: object) -> None:
    """Each technique from the gift's pool, the tradition or the species; finished; in limit."""
    from world.magic.services.cg_catalog import (  # noqa: PLC0415
        get_species_technique_options,
        get_technique_options,
    )

    def refuse(message: str) -> None:
        raise SheetWriteError(message)

    options = get_technique_options(
        path, picks.gift, picks.tradition, include_unready=True, exclude_gated=True
    )
    available = [
        *options.pool,
        *options.tradition,
        *get_species_technique_options(picks.species, include_unready=True),
    ]
    by_id = {technique.pk: technique for technique in available}
    if not picks.techniques:
        refuse("Choose at least one technique.")
    for technique in picks.techniques:
        if technique.pk not in by_id:
            refuse(f"{technique.name} is not available with this gift and tradition.")
        if not technique.action_template_id:
            refuse(f"{technique.name} is unfinished (no action template).")
    limit = technique_pick_limit(sheet)
    if len(picks.techniques) > limit:
        refuse(f"This character may start with at most {limit} techniques.")


def validate_staff_magic(sheet: CharacterSheet, picks: MagicPicks) -> None:
    """The structural rules of the CG magic stage, without its costs (#4224).

    The gift must be one the tradition offers on the sheet's path; each technique from
    that gift's pool, the tradition's signatures or the species' gifts, finished (an
    action template), and no more than the pick limit; a resonance; an anima stat and
    skill (a ritual without both cannot be shown on the sheet). A sheet that already
    holds a gift is refused: changing magic is out of scope.
    """
    from world.magic.models import CharacterGift  # noqa: PLC0415
    from world.magic.services.cg_catalog import get_gift_options  # noqa: PLC0415
    from world.progression.models import CharacterPathHistory  # noqa: PLC0415

    def refuse(message: str) -> None:
        raise SheetWriteError(message)

    if CharacterGift.objects.filter(character=sheet).exists():
        refuse("This character already has a gift; changing magic is not part of edit mode.")
    path_row = CharacterPathHistory.objects.filter(character=sheet).order_by("-pk").first()
    if path_row is None:
        refuse("Give the character a path first.")
    path = path_row.path
    if picks.gift is None or picks.gift not in get_gift_options(picks.tradition, path):
        refuse("Choose a gift the tradition offers on this path.")
    _check_techniques(sheet, picks, path)
    if picks.resonance is None:
        refuse("Choose the gift's resonance.")
    if picks.anima_stat is None or picks.anima_skill is None:
        refuse("Choose the stat and skill the character's magic rolls.")


def link_gift_and_techniques(sheet: CharacterSheet, picks: MagicPicks) -> None:
    """The gift (and its latent thread) and the technique links, then one announcement."""
    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.achievements.discovery import announce_access_change  # noqa: PLC0415
    from world.magic.constants import AcquisitionOrigin  # noqa: PLC0415
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.cg_catalog import get_species_technique_options  # noqa: PLC0415
    from world.magic.specialization.services import grant_gift_to_character  # noqa: PLC0415

    if picks.gift is None:
        return
    grant_gift_to_character(sheet, picks.gift, resonance=picks.resonance, origin=picks.origin)
    species_ids = {
        technique.pk
        for technique in get_species_technique_options(picks.species, include_unready=True)
    }
    gained: list[Technique] = []
    for technique in picks.techniques:
        from_species = technique.pk in species_ids
        origin = AcquisitionOrigin.SPECIES_GRANT if from_species else picks.origin
        link, created = CharacterTechnique.objects.get_or_create(
            character=sheet, technique=technique, defaults={"origin": origin}
        )
        if from_species and not created and link.origin != AcquisitionOrigin.SPECIES_GRANT:
            link.origin = AcquisitionOrigin.SPECIES_GRANT
            link.save(update_fields=["origin"])
        if created:
            gained.append(technique)
    if gained:
        announce_access_change(
            sheet, gained=gained, lost=[], source=AccessChangeSource.CHARACTER_CREATION
        )


def _glimpse(sheet: CharacterSheet, picks: MagicPicks) -> CharacterAura:
    """The aura, its Glimpse tags by axis, and its prose (versioned through the services)."""
    from world.magic.constants import GlimpseTagAxis  # noqa: PLC0415
    from world.magic.models import CharacterAura, GlimpseTag  # noqa: PLC0415
    from world.magic.services.glimpse import set_glimpse_prose, set_glimpse_tags  # noqa: PLC0415

    aura = CharacterAura.objects.filter(character=sheet).first()
    if aura is None:
        aura = CharacterAura(character=sheet)
        aura.full_clean()
        aura.save()
    if picks.glimpse_tag_ids:
        tags = list(GlimpseTag.objects.filter(pk__in=list(picks.glimpse_tag_ids), is_active=True))
        for axis in GlimpseTagAxis:
            axis_tags = [tag for tag in tags if tag.axis == axis]
            if axis_tags:
                set_glimpse_tags(aura, axis_tags, axis=axis)
    set_glimpse_prose(aura, picks.glimpse_story)
    return aura


def _anima(sheet: CharacterSheet, picks: MagicPicks) -> None:
    """Anima and fatigue pools, max anima by level, and the player anima ritual."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.fatigue.services import get_or_create_fatigue_pool  # noqa: PLC0415
    from world.magic.models import CharacterAnima  # noqa: PLC0415
    from world.magic.services.anima import (  # noqa: PLC0415
        provision_player_anima_ritual,
        recompute_max_anima,
    )

    CharacterAnima.objects.get_or_create(character=sheet, defaults={"current": 10, "maximum": 10})
    get_or_create_fatigue_pool(sheet)
    recompute_max_anima(sheet)
    try:
        roster_entry = sheet.roster_entry
    except ObjectDoesNotExist:
        return
    provision_player_anima_ritual(
        account=picks.account,
        character_sheet=sheet,
        roster_entry=roster_entry,
        ritual_name=picks.ritual_name,
        stat=picks.anima_stat,
        skill=picks.anima_skill,
        resonance=picks.resonance,
    )


@transaction.atomic
def provision_magic(
    sheet: CharacterSheet,
    picks: MagicPicks,
    *,
    hooks: MagicHooks | None = None,
    require_roster_entry: bool = False,
) -> None:
    """Give a sheet its magic, in finalize's order (see the module docstring).

    ``require_roster_entry`` (CG's finalize) makes a codex grant on a sheet with no roster
    entry raise rather than skip, as it always has there.
    """
    from world.codex.models import TraditionCodexGrant  # noqa: PLC0415
    from world.magic.models import CharacterTradition  # noqa: PLC0415
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415
    from world.magic.services.glimpse import apply_glimpse_affinity_nudge  # noqa: PLC0415
    from world.species.services import (  # noqa: PLC0415
        provision_species_gifts,
        provision_starting_languages,
    )

    hooks = hooks or MagicHooks()
    link_gift_and_techniques(sheet, picks)
    provision_species_gifts(sheet, resonance=picks.resonance)
    provision_starting_languages(sheet, beginnings=picks.beginnings)
    if hooks.after_languages:
        hooks.after_languages()
    CharacterTradition.objects.get_or_create(character=sheet, tradition=picks.tradition)
    academy_entrance_obligation(sheet, picks.tradition)
    grant_codex_entries(
        sheet,
        TraditionCodexGrant.objects.filter(tradition=picks.tradition).values_list(
            "entry_id", flat=True
        ),
        require_roster_entry=require_roster_entry,
    )
    if hooks.after_tradition_codex:
        hooks.after_tradition_codex()
    aura = _glimpse(sheet, picks)
    if hooks.after_aura:
        hooks.after_aura(aura)
    recompute_aura(sheet)
    apply_glimpse_affinity_nudge(aura)
    _anima(sheet, picks)
    if picks.resonance is not None and picks.resonance.codex_entry_id is not None:
        grant_codex_entries(
            sheet,
            [picks.resonance.codex_entry_id],
            require_roster_entry=require_roster_entry,
        )


def academy_entrance_obligation(sheet: CharacterSheet, tradition: Tradition) -> None:
    """The Golden Hare owed to (or settled with) Shroudwatch Academy at entrance (#2428).

    Unbound (self-taught) Prospects owe it; a sponsored tradition settled it for them.
    Idempotent on (debtor, creditor, origin); a logged skip when the Academy is unseeded.
    """
    import logging  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME  # noqa: PLC0415
    from world.character_creation.offers import tradition_is_self_taught  # noqa: PLC0415
    from world.societies.constants import ObligationOrigin, ObligationState  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationObligation  # noqa: PLC0415

    academy = Organization.objects.filter(name=SHROUDWATCH_ACADEMY_NAME).first()
    if academy is None:
        logging.getLogger(__name__).warning(
            "Skipping Academy entrance obligation: %r org is not seeded.",
            SHROUDWATCH_ACADEMY_NAME,
        )
        return
    if tradition_is_self_taught(tradition):
        defaults = {"state": ObligationState.OWED}
    else:
        defaults = {"state": ObligationState.SETTLED_BY_SPONSOR, "settled_at": timezone.now()}
    OrganizationObligation.objects.get_or_create(
        debtor=sheet,
        creditor=academy,
        origin=ObligationOrigin.ACADEMY_ENTRANCE,
        defaults=defaults,
    )


def resolve_rows(model: type, ids: Iterable[int]) -> list:
    """Rows by id in the order given; unknown ids dropped."""
    ids = list(ids)
    found = {row.pk: row for row in model.objects.filter(pk__in=ids)}
    return [found[pk] for pk in ids if pk in found]
