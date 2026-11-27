"""Magic as a public service on a live sheet (#4224, #3988 piece C).

``provision_magic`` is what character creation's ``finalize_magic_data`` does, taking
explicit picks instead of a draft, so finalize and staff edit mode's Grant magic share
one writer and one ordering. The ordering matters: the gift thread holds the CG picks
(heaviest leading), species gifts hold the same picks, the picks are seeded as lifetime
resonance so the aura and the settled self come from their weights, and the anima ritual
(the character's magical identity) carries the heaviest pick. Finalize's draft-only
steps (technique personalizations, the Glimpse-born distinction links, the codex grants
of the other CG choices) ride hooks at the exact points they always ran.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.character_creation.sheet_writers import SheetWriteError, grant_codex_entries
from world.magic.constants import AFFINITY_PRIMAL, GlimpseMemory

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import Beginnings
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import Path
    from world.magic.models import CharacterAura, Gift, Resonance, Technique, Tradition
    from world.skills.models import Skill
    from world.species.models import Species
    from world.traits.models import Trait


@dataclass(frozen=True)
class WeightedResonance:
    """A creation resonance pick and the creation points the player spread onto it."""

    resonance: Resonance
    weight: int


@dataclass(frozen=True)
class MagicPicks:
    """Everything magic needs, as rows. ``origin`` stamps the gift and technique links.

    Staff granting a character's starting magic use ``CHARACTER_CREATION`` too: it is
    the same starting kit, and the ledger reads where the magic came from, not who typed.
    """

    tradition: Tradition
    gift: Gift | None
    techniques: Sequence[Technique]
    resonances: Sequence[WeightedResonance]
    anima_stat: Trait | None
    anima_skill: Skill | None
    ritual_name: str
    account: AccountDB
    origin: str
    species: Species | None = None
    beginnings: Beginnings | None = None
    glimpse_story: str = ""
    #: The answers to write, already narrowed to the ones asked (#5292).
    glimpse_tag_ids: Sequence[int] = field(default_factory=tuple)
    #: How much of the Glimpse is remembered (#5292); ``GlimpseMemory``. A Glimpse left
    #: for later is stored on the character as remembered.
    glimpse_memory: str = GlimpseMemory.REMEMBERED

    @property
    def ordered_resonances(self) -> list[WeightedResonance]:
        """The picks heaviest first: the first one leads.

        A tie goes to the Primal pick, so an even split reads Primal everywhere the main
        affinity does; two tied picks of one affinity keep the order given.
        """
        return sorted(
            self.resonances,
            key=lambda pick: (-pick.weight, pick.resonance.affinity.name != AFFINITY_PRIMAL),
        )

    @property
    def lead_resonance(self) -> Resonance | None:
        """The heaviest pick: the one resonance creation needs where it can use only one."""
        ordered = self.ordered_resonances
        return ordered[0].resonance if ordered else None

    @property
    def primal_resonance(self) -> Resonance | None:
        """The heaviest Primal pick: what the anima ritual grows for its performer, or None."""
        return next(
            (
                pick.resonance
                for pick in self.ordered_resonances
                if pick.resonance.affinity.name == AFFINITY_PRIMAL
            ),
            None,
        )

    @property
    def outward_resonance(self) -> Resonance | None:
        """The heaviest Celestial or Abyssal pick: what the anima ritual reaches for in its
        partner, or None."""
        return next(
            (
                pick.resonance
                for pick in self.ordered_resonances
                if pick.resonance.affinity.name != AFFINITY_PRIMAL
            ),
            None,
        )


@dataclass(frozen=True)
class MagicHooks:
    """Finalize's draft-only steps, run where finalize always ran them."""

    after_languages: Callable[[], None] | None = None
    after_tradition_codex: Callable[[], None] | None = None
    after_aura: Callable[[CharacterAura], None] | None = None


# Starting techniques before any distinction adds to them (a sheet with none, or an
# NPC the form has not made yet, #4418).
BASE_TECHNIQUE_PICKS = 1


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
        return BASE_TECHNIQUE_PICKS
    effects = DistinctionEffect.objects.filter(
        distinction_id__in=list(ranks),
        target__name=STARTING_TECHNIQUE_PICKS_TARGET,
        target__category__name=CG_MODIFIER_CATEGORY,
    )
    return BASE_TECHNIQUE_PICKS + sum(
        effect.get_value_at_rank(rank)
        for effect in effects
        for rank in ranks[effect.distinction_id]
    )


def _check_techniques(sheet: CharacterSheet, picks: MagicPicks, path: Path, gift: Gift) -> None:
    """Each technique from the gift's pool, the tradition or the species; finished; in limit."""
    from world.magic.services.cg_catalog import (  # noqa: PLC0415
        get_species_technique_options,
        get_technique_options,
    )

    def refuse(message: str) -> None:
        raise SheetWriteError(message)

    options = get_technique_options(
        path, gift, picks.tradition, include_unready=True, exclude_gated=True
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
    gift = picks.gift
    if gift is None or gift not in get_gift_options(picks.tradition, path):
        msg = "Choose a gift the tradition offers on this path."
        raise SheetWriteError(msg)
    _check_techniques(sheet, picks, path, gift)
    if not picks.resonances:
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
    grant_gift_to_character(
        sheet,
        picks.gift,
        resonances=[pick.resonance for pick in picks.ordered_resonances],
        origin=picks.origin,
    )
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
    """The aura row, its Glimpse tags by axis, and its prose (versioned through the services).

    The shares come later: the settled self and the seeded resonance (``_seed_resonances``).
    """
    from world.magic.constants import GLIMPSE_AXIS_CONFIG, GlimpseTagAxis  # noqa: PLC0415
    from world.magic.models import CharacterAura, GlimpseTag  # noqa: PLC0415
    from world.magic.services.glimpse import (  # noqa: PLC0415
        keep_stand_alone,
        refresh_glimpse_state,
        set_glimpse_prose,
        set_glimpse_tags,
    )

    aura = CharacterAura.objects.filter(character=sheet).first()
    memory = (
        GlimpseMemory.REMEMBERED
        if picks.glimpse_memory == GlimpseMemory.LATER
        else GlimpseMemory(picks.glimpse_memory)
    )
    if aura is None:
        aura = CharacterAura(character=sheet, glimpse_memory=memory)
        aura.full_clean()
        aura.save()
    elif aura.glimpse_memory != memory:
        aura.glimpse_memory = memory
        aura.save()
    if picks.glimpse_tag_ids:
        by_id = {
            tag.pk: tag
            for tag in GlimpseTag.objects.filter(pk__in=list(picks.glimpse_tag_ids), is_active=True)
        }
        # In the order the picks came in, so "the first" below is the caller's first.
        tags = [by_id[pk] for pk in picks.glimpse_tag_ids if pk in by_id]
        for axis in GlimpseTagAxis:
            # A list that reached here unchecked (a GM's draft, a fixture) never fails
            # the finalize: a tag that stands alone is kept alone (#5193), and an axis
            # that takes one answer keeps the first (#5292).
            axis_tags = keep_stand_alone([tag for tag in tags if tag.axis == axis])
            if not GLIMPSE_AXIS_CONFIG[axis].multi:
                axis_tags = axis_tags[:1]
            if axis_tags:
                set_glimpse_tags(aura, axis_tags, axis=axis)
    # An unchanged Glimpse (a blank one, at CG) writes no version; the state is still
    # recomputed, since the tags above may have moved it.
    if picks.glimpse_story != aura.glimpse_story:
        set_glimpse_prose(aura, picks.glimpse_story)
    else:
        refresh_glimpse_state(aura)
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
        primal_resonance=picks.primal_resonance,
        outward_resonance=picks.outward_resonance,
    )


def _split_by_weight(total: int, weights: list[int]) -> list[int]:
    """``total`` shared out by ``weights`` (largest remainder), every part at least 1.

    The caller guarantees ``total`` is at least ``len(weights)``.
    """
    weight_sum = sum(weights)
    parts = [total * weight // weight_sum for weight in weights]
    by_remainder = sorted(
        range(len(weights)), key=lambda i: (-(total * weights[i] % weight_sum), i)
    )
    for i in by_remainder[: total - sum(parts)]:
        parts[i] += 1
    for i, part in enumerate(parts):
        if part == 0:
            parts[parts.index(max(parts))] -= 1
            parts[i] = 1
    return parts


def _seed_resonances(sheet: CharacterSheet, picks: MagicPicks, aura: CharacterAura) -> None:
    """Settle who the character is, then seed each pick's lifetime to match it (#5123).

    The settled shares start as the picks' weights (over any lifetime the sheet already
    holds), the Glimpse nudge moves them (the one place that nudge is written), and the
    lifetime is seeded from the nudged settled shares: each affinity's resonance gets its
    settled share of the total, split across that affinity's picks by weight. So a fresh
    character's aura is their settled self, they read no unsettled steps (a nudge of two
    same-affinity tags included), and their first gain extends the aura rather than wiping
    it. With no nudge a pick's lifetime is exactly its weight x ``creation_seed_per_point``.
    """
    from decimal import ROUND_HALF_UP, Decimal  # noqa: PLC0415

    from world.magic.models import CharacterResonance  # noqa: PLC0415
    from world.magic.services.aura import recompute_aura, set_settled_shares  # noqa: PLC0415
    from world.magic.services.drift import get_drift_config  # noqa: PLC0415
    from world.magic.services.glimpse import apply_glimpse_affinity_nudge  # noqa: PLC0415
    from world.magic.services.resonance import seed_creation_resonance  # noqa: PLC0415
    from world.magic.types import AffinityShare  # noqa: PLC0415

    per_point = get_drift_config().creation_seed_per_point
    affinities = {}
    existing: dict[int, int] = {}
    for row in CharacterResonance.objects.filter(character_sheet=sheet).select_related(
        "resonance__affinity"
    ):
        affinity = row.resonance.affinity
        affinities[affinity.pk] = affinity
        existing[affinity.pk] = existing.get(affinity.pk, 0) + row.lifetime_earned
    by_affinity: dict[int, list[WeightedResonance]] = {}
    for pick in picks.ordered_resonances:
        affinities[pick.resonance.affinity.pk] = pick.resonance.affinity
        by_affinity.setdefault(pick.resonance.affinity_id, []).append(pick)
    base = {
        pk: existing.get(pk, 0) + sum(pick.weight for pick in by_affinity.get(pk, ())) * per_point
        for pk in affinities
    }
    grand_total = sum(base.values())
    if grand_total == 0:
        return
    set_settled_shares(
        aura,
        [
            AffinityShare(affinity=affinities[pk], percent=Decimal(total) * 100 / grand_total)
            for pk, total in base.items()
            if total
        ],
    )
    apply_glimpse_affinity_nudge(aura)
    settled = {share.affinity_id: share.settled_percent for share in aura.cached_shares}
    denominator = sum(settled.get(pk, Decimal(0)) for pk in base if base[pk]) or Decimal(100)
    for pk, group in by_affinity.items():
        target = Decimal(grand_total) * settled.get(pk, Decimal(0)) / denominator
        wanted = int((target - existing.get(pk, 0)).to_integral_value(ROUND_HALF_UP))
        amounts = _split_by_weight(max(wanted, len(group)), [pick.weight for pick in group])
        for pick, amount in zip(group, amounts, strict=True):
            seed_creation_resonance(sheet, pick.resonance, amount)
    recompute_aura(sheet)


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
    from world.species.services import (  # noqa: PLC0415
        provision_species_gifts,
        provision_starting_languages,
    )

    hooks = hooks or MagicHooks()
    link_gift_and_techniques(sheet, picks)
    provision_species_gifts(sheet, resonances=[pick.resonance for pick in picks.ordered_resonances])
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
    _seed_resonances(sheet, picks, aura)
    _anima(sheet, picks)
    codex_entry_ids = [
        pick.resonance.codex_entry_id
        for pick in picks.ordered_resonances
        if pick.resonance.codex_entry_id is not None
    ]
    if codex_entry_ids:
        grant_codex_entries(sheet, codex_entry_ids, require_roster_entry=require_roster_entry)


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


def resolve_weighted_resonances(draft_data: Mapping[str, Any]) -> list[WeightedResonance]:
    """The draft's resonance picks as rows with their weights, heaviest first.

    A pick whose resonance no longer exists is dropped; the stage validated them all, so
    that only happens when the catalog changed under the draft.
    """
    from world.character_creation.resonance_weights import (  # noqa: PLC0415
        draft_resonance_weights,
    )
    from world.magic.models import Resonance  # noqa: PLC0415

    weights = draft_resonance_weights(draft_data)
    by_id = Resonance.objects.in_bulk([pick.resonance_id for pick in weights])
    return [
        WeightedResonance(by_id[pick.resonance_id], pick.weight)
        for pick in weights
        if pick.resonance_id in by_id
    ]


def resolve_rows(model: type, ids: Iterable[int]) -> list:
    """Rows by id in the order given; unknown ids dropped."""
    ids = list(ids)
    found = {row.pk: row for row in model.objects.filter(pk__in=ids)}
    return [found[pk] for pk in ids if pk in found]
