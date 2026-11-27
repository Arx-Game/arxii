"""The waiting sheet: a submitted draft laid out as the in-game sheet will read (#5206).

``build_waiting_sheet(draft)`` returns the keys ``CharacterSheetSerializer`` returns, in the
same typed sections (``world.character_sheets.types``), as the character's owner reads their
own sheet: every privileged part included, every visibility tier open. It is built from the
draft alone and only reads: nothing here saves the draft, creates a row or calls a writer.
Where finalize computes a value with a function that writes, the read half lives beside the
writer and both call it (``strongest_path_aspect``, ``starting_grant_for``,
``item_grants_for``, ``starting_languages``, ``planned_introductions``, ``whisper_lines``,
``starting_locked_xp``, ``creation_affinity_base`` / ``creation_seed_amounts``,
``creation_technique_forms``, ``origin_story_state_for``).

Three groups of keys:

* filled from the draft: what approval writes for a new character (``WAITING_FILLED_KEYS``);
* always empty for a new character (``covenants``, ``looks``, ``worn``, ``mentors``,
  ``ties``, ``ties_ap_this_week``, ``profile_picture``);
* never built: ``staff_edit`` (staff only). ``can_edit`` is false, ``id`` is None (there is
  no character yet), and ``theming`` and ``plate_ink`` are what a new character starts with.

Plus the keys only the waiting page reads: ``awaiting`` (the application's state) and the
Estate, Growth and Knowledge tabs' contents (``purse``, ``carried``, ``xp_ledger``,
``languages``, ``secrets``), each shaped like the endpoint the in-game tab reads.

A row approval will create has no id yet; this module numbers such rows below zero
(``-1``, ``-2``, ...) so a list keeps distinct keys and no id is mistaken for a real row.

A piece the draft does not hold (a draft mid-revision: no path, a removed card, a stage
failing validation) leaves its part empty and never raises. ``draft_data["crime"]`` is never
read: the crime note it becomes is staff-only.

Also mirrored, each through the read half finalize itself calls: the Glimpse's nudge on the
settled self (``glimpse_nudged_shares``), an early form and a flourish bought in creation
(``creation_technique_forms``, ``creation_next_signature``), the species' gifts, drawback
cards and natural weapons with their inherent facets (``species_gift_grants``). A property
house a Beginnings grants (``grant_property``) adds no key-holding row, so the keyring has
nothing for it in play either. Not mirrored: a species drawback *condition*, which changes
nothing a new character's sheet shows unless its effects reach a stat.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import count
from typing import TYPE_CHECKING, Any, cast

from django.utils import timezone

from world.character_creation.constants import (
    ACTOR_SHEET_QUESTIONS,
    ALTER_EGO_KEY,
    BACKGROUND_KEY,
    ENEMY_REPUTATION_SEED,
    GIFT_FACETS_KEY,
    OFFICIALLY_DEAD_FACE_NAME,
    OFFICIALLY_DEAD_KEY,
    ORGANIZATIONS_KEY,
    PRESTIGE_STORIES_KEY,
    TECHNIQUE_PERSONALIZATIONS_KEY,
    TIE_KIND,
    TIE_ORGANIZATION_ID,
    TIES_KEY,
    ApplicationStatus,
    FamilyPath,
    FinalTouchesPrompt,
    OriginStoryState,
    QuestionKind,
    TieKind,
)
from world.character_creation.types import (
    AwaitingSection,
    CarriedItemEntry,
    PurseSection,
    StartingLanguageEntry,
    WaitingSheetPayload,
    XpLedgerSection,
)
from world.character_sheets.types import (
    ActorSheetSection,
    AnimaRitualSection,
    AppearanceSection,
    AuraData,
    AuraShareEntry,
    AuraThemingData,
    BeatEntry,
    BonusGroupEntry,
    CombatStyleSection,
    DistinctionEntry,
    EnemyEntry,
    FormTraitEntry,
    GiftEntry,
    GlimpseTagEntry,
    GoalEntry,
    IdentitySection,
    IdNameRef,
    IntroductionEntry,
    KeyringEntry,
    MagicSection,
    MotifResonanceEntry,
    MotifSection,
    NaturalWeaponEntry,
    OrgDomainEntry,
    OrgMembershipEntry,
    OrgReputationEntry,
    OriginSlotEntry,
    OwnSecretEntry,
    PathDetailSection,
    PathHistoryEntry,
    PersonaEntry,
    PlateInk,
    PronounsData,
    ResonanceBalanceEntry,
    SkillEntry,
    SkillRef,
    SpecializationEntry,
    StandingSection,
    StorySection,
    TechniqueEntry,
    ThemingSection,
    VacancyRef,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB
    from evennia.objects.objects import DefaultObject

    from evennia_extensions.models import RoomProfile
    from world.character_creation.magic_writer import MagicPicks
    from world.character_creation.models import CharacterDraft, DraftApplication, DraftMarking
    from world.character_creation.offers import BeatMarks
    from world.checks.modifier_values import ValueTable
    from world.distinctions.models import Distinction
    from world.forms.models import FormTrait
    from world.magic.models import Gift, GlimpseTag, Resonance, Technique
    from world.magic.types.technique_effects import TechniqueSignaturePayload
    from world.mechanics.models import ModifierTarget
    from world.mechanics.services import DerivedAmountReader
    from world.mechanics.types import HeldEffect, HeldEffectsValuation
    from world.roster.models import Family
    from world.societies.models import Organization, OrganizationRank
    from world.traits.models import Trait

#: The application states a waiting sheet is shown in (ruling 9 of #5206).
WAITING_STATUSES: tuple[str, ...] = (
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.IN_REVIEW,
    ApplicationStatus.REVISIONS_REQUESTED,
)


@dataclass
class _Holding:
    """One card the new character will hold, as finalize's ``_create_distinctions`` makes
    it (one per distinction and feature), with what finalize writes onto it after."""

    distinction: Distinction
    rank: int
    notes: str
    feature_trait: FormTrait | None = None
    feature_marking: DraftMarking | None = None
    is_secret: bool = False
    is_cover: bool = False
    from_glimpse: bool = False
    #: A card the species forces (``SpeciesGiftGrant.drawback_distinction``), granted
    #: through ``grant_distinction``: no inheritance, keepsake or Secret comes with it.
    from_species: bool = False

    @property
    def feature(self) -> str:
        if self.feature_marking is not None:
            return self.feature_marking.name
        if self.feature_trait is not None:
            return self.feature_trait.display_name
        return ""


@dataclass
class _Membership:
    organization: Organization
    rank: OrganizationRank | None
    vacancy: Any = None


@dataclass
class _Plan:
    """What the draft says approval writes, read once and shared by every section."""

    draft: CharacterDraft
    full_name: str
    family: Family | None
    family_ref: IdNameRef | None
    holdings: list[_Holding]
    worn_face: str
    hidden_face: str
    memberships: list[_Membership]
    starting_room: ObjectDB | None
    picks: MagicPicks | None
    ids: Iterator[int] = field(default_factory=lambda: count(-1, -1))

    def next_id(self) -> int:
        """An id for a row approval will create: -1, -2, ... in the order asked."""
        return next(self.ids)


def waiting_sheet_application(draft: CharacterDraft) -> DraftApplication | None:
    """The draft's application when it is in a state a waiting sheet is shown in, else None."""
    from world.character_creation.models import DraftApplication  # noqa: PLC0415

    application = DraftApplication.objects.filter(draft=draft).first()
    if application is None or application.status not in WAITING_STATUSES:
        return None
    return application


def build_waiting_sheet(draft: CharacterDraft) -> WaitingSheetPayload:
    """The in-game sheet's payload built from ``draft``, as its owner will read it (#5206).

    Only reads. See the module docstring for which keys are filled, empty and never built.
    """
    plan = _plan(draft)
    stats, buffed = _stat_sections(plan)
    application = waiting_sheet_application(draft)
    awaiting = AwaitingSection(
        status=application.status if application is not None else "",
        status_label=application.get_status_display() if application is not None else "",
    )
    magic = _magic(plan)
    return WaitingSheetPayload(
        id=None,
        can_edit=False,
        identity=_identity(plan),
        appearance=_appearance(plan),
        staff_edit=None,
        stats=stats,
        buffed_stats=buffed,
        bonuses=_bonuses(plan),
        skills=_skills(plan),
        path=_path(plan),
        distinctions=_distinctions(plan),
        magic=magic,
        story=_story(plan),
        goals=_goals(plan),
        beats=_beats(plan),
        standing=_standing(plan),
        covenants=[],
        actor_sheet=_actor_sheet(plan),
        personas=_personas(plan),
        theming=_theming(magic),
        profile_picture=None,
        viewer_is_friend=True,
        current_residence=_current_residence(plan),
        looks=[],
        plate_ink=PlateInk.EMBER,
        worn=[],
        natural_weapons=_natural_weapons(plan),
        combat_style=_combat_style(plan),
        mentors=[],
        domains=_domains(plan),
        keyring=_keyring(plan),
        ties=[],
        ties_ap_this_week=0,
        awaiting=awaiting,
        purse=_purse(plan),
        carried=_carried(plan),
        xp_ledger=_xp_ledger(plan),
        languages=_languages(plan),
        secrets=_secrets(plan),
    )


# --- The plan -------------------------------------------------------------------------


def _plan(draft: CharacterDraft) -> _Plan:
    from world.character_creation.offers import final_touches_prompts  # noqa: PLC0415

    family, family_ref, surname = _family(draft)
    first_name = str(draft.draft_data.get("first_name", ""))
    full_name = f"{first_name} {surname}" if surname else first_name
    asked = final_touches_prompts(draft)
    worn_face = (
        _face_name(draft, OFFICIALLY_DEAD_KEY)
        if FinalTouchesPrompt.OFFICIALLY_DEAD in asked
        else ""
    )
    hidden_face = _face_name(draft, ALTER_EGO_KEY) if FinalTouchesPrompt.ALTER_EGO in asked else ""
    plan = _Plan(
        draft=draft,
        full_name=full_name,
        family=family,
        family_ref=family_ref,
        holdings=[],
        worn_face=worn_face,
        hidden_face=hidden_face,
        memberships=[],
        starting_room=_starting_room(draft),
        picks=_magic_picks(draft),
    )
    plan.holdings = _holdings(plan)
    plan.memberships = _memberships(plan)
    return plan


def _family(draft: CharacterDraft) -> tuple[Family | None, IdNameRef | None, str]:
    """The family the sheet will name and the surname the character's name takes.

    Mirrors ``_materialize_named_family`` then ``_build_character_full_name``: a claimed
    family's name; a family the draft founds (named only, it is made at approval, so its
    id is -1 here); else the drawn tarot card's surname.
    """
    if draft.family is not None:
        return (
            draft.family,
            IdNameRef(id=draft.family.pk, name=draft.family.name),
            draft.family.name,
        )
    if draft.resolve_family_path() == FamilyPath.NAMED:
        name = str(draft.draft_data.get("new_family_name", "")).strip()
        if name:
            return None, IdNameRef(id=-1, name=name), name
    return None, None, draft._tarot_surname()  # noqa: SLF001 - the draft's own surname rule


def _face_name(draft: CharacterDraft, key: str) -> str:
    face = draft.draft_data.get(key) or {}
    if not isinstance(face, dict):
        return ""
    return str(face.get(OFFICIALLY_DEAD_FACE_NAME) or "").strip()


def _starting_room(draft: CharacterDraft) -> ObjectDB | None:
    """``CharacterDraft.get_starting_room`` without its fallback room's log lines."""
    if draft.selected_beginnings and draft.selected_beginnings.starting_room_override:
        return draft.selected_beginnings.starting_room_override.objectdb
    if draft.selected_area and draft.selected_area.default_starting_room:
        return draft.selected_area.default_starting_room.objectdb
    from world.character_creation.services import resolve_fallback_starting_room  # noqa: PLC0415

    return resolve_fallback_starting_room()


@dataclass
class _CardLookups:
    """What ``_holdings`` reads once for every pick: the rows its keys name and the marks
    the life page left on the draft."""

    distinctions: dict[int, Distinction]
    traits: dict[str, FormTrait]
    markings: dict[int, DraftMarking]
    marks: Any
    marked: set[int]
    stories: dict
    figures: dict[int, str]
    picked: set[int]
    glimpse_ids: set[int]


def _holdings(plan: _Plan) -> list[_Holding]:
    """The cards approval writes, in the order it writes them (``_create_distinctions``).

    One holding per distinction and feature; a feature that no longer resolves drops its
    card, as finalize does. Notes take the figure's name and the prestige story the way
    ``_name_figures`` and ``_write_prestige_stories`` set them. Covers follow the picks.
    """
    draft = plan.draft
    entries_by_key = _draft_entries_by_key(draft)
    if not entries_by_key:
        return []
    lookups = _card_lookups(draft, entries_by_key)
    holdings = [
        holding
        for key, entry in entries_by_key.items()
        if (holding := _holding_for(key, entry, lookups)) is not None
    ]
    holdings.extend(_covers(lookups.marks, lookups.picked, {h.distinction.pk for h in holdings}))
    holdings.extend(_species_drawbacks(draft, holdings))
    return holdings


def _draft_entries_by_key(draft: CharacterDraft) -> dict[tuple, dict]:
    """The draft's card entries by distinction and feature (``feature_key``), the last
    entry for a key winning, as ``_create_distinctions`` keys them."""
    from world.distinctions.types import feature_key  # noqa: PLC0415

    entries = [
        entry
        for entry in draft.draft_data.get("distinctions") or []
        if isinstance(entry, dict) and entry.get("distinction_id")
    ]
    return {feature_key(entry): entry for entry in entries}


def _card_lookups(draft: CharacterDraft, entries_by_key: dict[tuple, dict]) -> _CardLookups:
    """The rows and marks every pick reads, each fetched once."""
    from world.character_creation.models import DraftMarking  # noqa: PLC0415
    from world.character_creation.offers import beat_marks, picked_offer_ids  # noqa: PLC0415
    from world.character_creation.services import (  # noqa: PLC0415
        _secret_distinction_ids,
    )
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.forms.models import FormTrait  # noqa: PLC0415

    trait_names = {key[1] for key in entries_by_key if key[1]}
    marking_ids = {key[2] for key in entries_by_key if key[2]}
    marks = beat_marks(draft)
    picked = picked_offer_ids(draft)
    return _CardLookups(
        distinctions=Distinction.objects.in_bulk({key[0] for key in entries_by_key}),
        traits=(
            {t.name: t for t in FormTrait.objects.filter(name__in=trait_names)}
            if trait_names
            else {}
        ),
        markings=(
            DraftMarking.objects.filter(draft=draft).in_bulk(marking_ids) if marking_ids else {}
        ),
        marks=marks,
        marked=_secret_distinction_ids(entries_by_key, marks),
        stories=draft.draft_data.get(PRESTIGE_STORIES_KEY) or {},
        figures=_figure_names(entries_by_key, marks),
        picked=picked,
        glimpse_ids=_glimpse_distinction_ids(picked),
    )


def _figure_names(entries_by_key: dict[tuple, dict], marks: BeatMarks) -> dict[int, str]:
    """Distinction id to the figure name a beat gave one of its picked offers
    (``_name_figures``), the first one found."""
    figures: dict[int, str] = {}
    for (distinction_id, _trait, _marking), entry in entries_by_key.items():
        for offer_id in entry.get("offer_ids", []):
            if isinstance(offer_id, int) and offer_id in marks.figures:
                figures.setdefault(distinction_id, marks.figures[offer_id])
    return figures


def _glimpse_distinction_ids(picked: set[int]) -> set[int]:
    """The distinctions a picked offer born of the Glimpse grants
    (``_link_glimpse_distinctions``)."""
    from world.character_creation.models import DistinctionOffer  # noqa: PLC0415

    if not picked:
        return set()
    return set(
        DistinctionOffer.objects.filter(pk__in=picked, glimpse_tag__isnull=False).values_list(
            "distinction_id", flat=True
        )
    )


def _holding_for(key: tuple, entry: dict, lookups: _CardLookups) -> _Holding | None:
    """One pick's holding, or None when its card is gone or its feature no longer
    resolves (``_build_character_distinctions``)."""
    distinction_id, trait_name, marking_id = key
    distinction = lookups.distinctions.get(distinction_id)
    if distinction is None:
        return None
    trait = lookups.traits.get(trait_name) if trait_name else None
    marking = lookups.markings.get(marking_id) if marking_id else None
    if (trait_name and trait is None) or (marking_id and marking is None):
        return None
    return _Holding(
        distinction=distinction,
        rank=int(entry.get("rank", 1) or 1),
        notes=_card_notes(distinction, entry, lookups),
        feature_trait=trait,
        feature_marking=marking,
        is_secret=distinction.secret_by_default or distinction_id in lookups.marked,
        from_glimpse=distinction_id in lookups.glimpse_ids,
    )


def _card_notes(distinction: Distinction, entry: dict, lookups: _CardLookups) -> str:
    """A pick's notes as finalize leaves them: the entry's own, else the figure's name on a
    card that asks for one (``_name_figures``), else the prestige story
    (``_write_prestige_stories``)."""
    notes = str(entry.get("notes", "") or "")
    figure = lookups.figures.get(distinction.pk)
    if figure and distinction.asks_figure_name and not notes:
        notes = figure
    if not notes and distinction.prestige_grant_or_none is not None:
        notes = str(lookups.stories.get(str(distinction.pk)) or "").strip()
    return notes


def _species_drawbacks(draft: CharacterDraft, held: list[_Holding]) -> list[_Holding]:
    """The cards the species forces, as ``provision_species_gifts`` grants them after the
    picks (``_grant_species_distinction_once``: rank 1, nothing when already held plain)."""
    from world.species.services import species_gift_grants  # noqa: PLC0415

    plain = {h.distinction.pk for h in held if h.feature == ""}
    out: list[_Holding] = []
    for grant in species_gift_grants(draft.selected_species):
        card = grant.drawback_distinction
        if card is None or card.pk in plain:
            continue
        plain.add(card.pk)
        out.append(_Holding(distinction=card, rank=1, notes="", from_species=True))
    return out


def _covers(marks: BeatMarks, picked: set[int], held: set[int]) -> list[_Holding]:
    """The cover stories ``_write_cover_stories`` holds behind a secret answer (#4872)."""
    from world.character_creation.models import DistinctionOffer  # noqa: PLC0415

    wanted = {
        beat_id: cover_id
        for beat_id, cover_id in marks.cover.items()
        if marks.secret.get(beat_id, set()) & picked
    }
    if not wanted:
        return []
    by_id = {
        offer.pk: offer
        for offer in DistinctionOffer.objects.filter(
            pk__in=set(wanted.values()), beat_id__in=set(wanted), is_active=True
        ).select_related("distinction")
    }
    covers: list[_Holding] = []
    for beat_id, cover_id in wanted.items():
        offer = by_id.get(cover_id)
        if (
            offer is None
            or offer.beat_id != beat_id
            or cover_id in picked
            or offer.distinction_id in held
        ):
            continue
        covers.append(_Holding(distinction=offer.distinction, rank=1, notes="", is_cover=True))
        held.add(offer.distinction_id)
    return covers


def _memberships(plan: _Plan) -> list[_Membership]:
    """The organizations approval seats the primary face in, in the order it seats them.

    The vacancy (``_bind_vacancy``), then the cards' organization grants
    (``_join_card_organizations``), then the ties a card opens as memberships
    (``_write_card_ties``). A second seat in one organization is refused at approval, so
    it is left out here. A rank the grant does not name is the organization's base rank.
    """
    from world.societies.membership_services import base_rank_for_organization  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    draft = plan.draft
    wanted: list[tuple[Organization, OrganizationRank | None, Any]] = []
    vacancy = draft.selected_vacancy
    if vacancy is not None:
        wanted.append((vacancy.organization, vacancy.rank, vacancy))
    wanted.extend((org, rank, None) for org, rank in _card_organizations(draft))
    tie_orgs = Organization.objects.in_bulk(
        [org_id for org_id, kind in _answered_ties(draft) if kind == TieKind.MEMBERSHIP]
    )
    wanted.extend((org, None, None) for org in tie_orgs.values())
    seats: list[_Membership] = []
    seated: set[int] = set()
    for org, asked_rank, held_vacancy in wanted:
        if org.pk in seated:
            continue
        seated.add(org.pk)
        rank = (
            asked_rank
            if asked_rank is not None and asked_rank.organization_id == org.pk
            else base_rank_for_organization(org)
        )
        seats.append(_Membership(organization=org, rank=rank, vacancy=held_vacancy))
    return seats


def _card_organizations(
    draft: CharacterDraft,
) -> list[tuple[Organization, OrganizationRank | None]]:
    """Each held card's organization grant: its own organization, or the one picked at Final
    Touches from the realm's list (``_join_card_organizations``), with the grant's rank."""
    from world.character_creation.offers import held_cards, organization_choices  # noqa: PLC0415

    grants = [
        (card, card.organization_grant_or_none)
        for card in held_cards(draft)
        if card.organization_grant_or_none is not None
    ]
    if not grants:
        return []
    picked = draft.draft_data.get(ORGANIZATIONS_KEY) or {}
    choices = {org.pk: org for org in organization_choices(draft)}
    out: list[tuple[Organization, OrganizationRank | None]] = []
    for card, grant in grants:
        org = grant.organization if grant.organization_id else choices.get(picked.get(str(card.pk)))
        if org is not None:
            out.append((org, grant.rank))
    return out


def _answered_ties(draft: CharacterDraft) -> list[tuple[int, str]]:
    """``(organization id, TieKind)`` for each tie a held card asks and the draft answered
    with one of its choices (``_write_card_ties``)."""
    from world.character_creation.offers import final_touches_cards  # noqa: PLC0415

    answers = draft.draft_data.get(TIES_KEY) or {}
    if not answers:
        return []
    out: list[tuple[int, str]] = []
    for ask in final_touches_cards(draft):
        if ask.prompt != FinalTouchesPrompt.TIE:
            continue
        answer = answers.get(str(ask.distinction_id)) or {}
        org_id = answer.get(TIE_ORGANIZATION_ID)
        if org_id is not None and org_id in {c.id for c in ask.choices}:
            out.append((org_id, answer.get(TIE_KIND, "")))
    return out


def _magic_picks(draft: CharacterDraft) -> MagicPicks | None:
    """The magic picks ``finalize_magic_data`` gives ``provision_magic``; None without a gift."""
    from world.character_creation.magic_writer import (  # noqa: PLC0415
        MagicPicks,
        resolve_rows,
        resolve_weighted_resonances,
    )
    from world.magic.constants import AcquisitionOrigin  # noqa: PLC0415
    from world.magic.models import Gift, Technique  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait  # noqa: PLC0415

    data = draft.draft_data
    gift_id = data.get("selected_gift_id")
    gift = Gift.objects.filter(pk=gift_id).first() if gift_id else None
    if gift is None or draft.selected_tradition is None:
        return None

    def by_id(model: Any, key: str) -> Any:
        pk = data.get(key)
        return model.objects.filter(pk=pk).first() if pk else None

    character_name = data.get("first_name", "Character")
    return MagicPicks(
        tradition=draft.selected_tradition,
        gift=gift,
        techniques=resolve_rows(Technique, data.get("selected_technique_ids") or []),
        resonances=resolve_weighted_resonances(data),
        anima_stat=by_id(Trait, "anima_check_stat_id"),
        anima_skill=by_id(Skill, "anima_check_skill_id"),
        ritual_name=data.get("anima_ritual_name") or f"{character_name}'s Anima Ritual",
        account=draft.account,
        origin=AcquisitionOrigin.CHARACTER_CREATION,
        species=draft.selected_species,
        beginnings=draft.selected_beginnings,
        glimpse_story=data.get("glimpse_story", ""),
        glimpse_tag_ids=data.get("glimpse_tag_ids", []),
    )


# --- Identity, appearance, personas ---------------------------------------------------


def _presented_name(plan: _Plan) -> str:
    """The plate's name as the owner reads it: the worn face's with the true one beside it
    (``_resolve_presented_identity``), else the character's own."""
    if plan.worn_face:
        return f"{plan.worn_face} ({plan.full_name})"
    return plan.full_name


def _identity(plan: _Plan) -> IdentitySection:
    """Mirrors ``_build_identity`` for the owner (``world.character_sheets.serializers``)."""
    from world.character_sheets.serializers import compose_fullname  # noqa: PLC0415
    from world.game_clock.services import format_ic_month_day  # noqa: PLC0415

    draft = plan.draft
    data = draft.draft_data
    beginnings = draft.selected_beginnings
    age = draft.age or 18
    gender = draft.selected_gender
    realm = draft.selected_area.realm if draft.selected_area is not None else None
    # ``set_worship_declaration`` writes a row whenever either being is picked; a CG row's
    # public faith is sincere by default (``WorshipDeclaration.public_is_sincere``).
    declared = draft.public_worship is not None or draft.secret_worship is not None
    has_birthday = bool(draft.birthday_month and draft.birthday_day)
    return IdentitySection(
        name=_presented_name(plan),
        fullname=compose_fullname(
            plan.full_name, plan.family_ref["name"] if plan.family_ref else ""
        ),
        concept=str(data.get("concept") or ""),
        quote=str(data.get("quote") or ""),
        age=age,
        birthday=(
            format_ic_month_day(draft.birthday_month, draft.birthday_day) if has_birthday else None
        ),
        chronological_age=_chronological_age(draft),
        biological_age=age,
        withered_years=0,
        gender=IdNameRef(id=gender.pk, name=gender.display_name) if gender is not None else None,
        pronouns=_pronouns(gender),
        species=_ref(draft.selected_species),
        heritage=_heritage(draft),
        beginnings=[IdNameRef(id=beginnings.pk, name=beginnings.name)] if beginnings else [],
        family=plan.family_ref,
        tarot_card=_tarot_card(data),
        origin=_ref(realm),
        path=_ref(draft.selected_path),
        worship=_ref(draft.public_worship) if declared else None,
        worship_sincere=True if declared else None,
        current_mood=None,
        vacancy=_vacancy_ref(draft.selected_vacancy),
    )


def _heritage(draft: CharacterDraft) -> IdNameRef:
    """``_set_heritage``: the Beginnings' heritage, else "Normal", which approval creates if
    no row exists yet (an id below zero until then)."""
    from world.character_sheets.models import Heritage  # noqa: PLC0415

    beginnings = draft.selected_beginnings
    row = (
        beginnings.heritage
        if beginnings is not None and beginnings.heritage is not None
        else Heritage.objects.filter(name="Normal").first()
    )
    return (
        IdNameRef(id=row.pk, name=row.name) if row is not None else IdNameRef(id=-1, name="Normal")
    )


def _chronological_age(draft: CharacterDraft) -> int | None:
    """Years since the IC birth year approval writes (``_derive_ic_birth_year``), or None
    when it is unknowable (a Sleeper, no game clock) or the draft has no age."""
    from world.character_creation.services import _derive_ic_birth_year  # noqa: PLC0415
    from world.game_clock.services import get_ic_now  # noqa: PLC0415

    if not draft.age:
        return None
    birth_year = _derive_ic_birth_year(draft)
    if birth_year is None:
        return None
    ic_now = get_ic_now()
    return ic_now.year - birth_year if ic_now is not None else None


def _pronouns(gender: Any) -> PronounsData:
    """The pronouns ``set_pronouns_from_gender`` writes: by the gender's key, else
    they/them/their."""
    from world.character_creation.sheet_writers import (  # noqa: PLC0415
        _PRONOUNS_BY_GENDER_KEY,
    )

    default = ("they", "them", "their")
    subject, obj, possessive = (
        _PRONOUNS_BY_GENDER_KEY.get(gender.key, default) if gender is not None else default
    )
    return PronounsData(subject=subject, object=obj, possessive=possessive)


def _tarot_card(data: dict) -> IdNameRef | None:
    """The drawn tarot card (``_set_tarot_card``), when its name still names a card."""
    card_name = data.get("tarot_card_name")
    if not card_name:
        return None
    from world.tarot.models import TarotCard  # noqa: PLC0415

    card = TarotCard.objects.filter(name=card_name).first()
    return IdNameRef(id=card.pk, name=card.name) if card is not None else None


def _vacancy_ref(vacancy: Any) -> VacancyRef | None:
    """The held seat as the owner reads it (``_resolve_vacancy``, privileged)."""
    if vacancy is None:
        return None
    return VacancyRef(
        name=vacancy.name,
        presumed_importance=vacancy.presumed_importance,
        importance=vacancy.importance,
    )


def _ref(obj: Any) -> IdNameRef | None:
    return IdNameRef(id=obj.pk, name=obj.name) if obj is not None else None


def _appearance(plan: _Plan) -> AppearanceSection:
    """Mirrors ``_build_appearance`` for the owner: the true form's traits overlaid with the
    primary face's descriptors (``_apply_form_trait_descriptors``)."""
    from world.character_creation.offers import opened_feature_traits  # noqa: PLC0415
    from world.character_creation.services import (  # noqa: PLC0415
        _resolve_form_trait_selections,
    )
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415
    from world.forms.services import get_height_band  # noqa: PLC0415

    draft = plan.draft
    data = draft.draft_data
    form_traits = data.get("form_traits") or {}
    selections = (
        _resolve_form_trait_selections(form_traits, FormTrait, FormTraitOption)
        if isinstance(form_traits, dict) and form_traits
        else {}
    )
    descriptors: dict[str, str] = {}
    raw = data.get("form_trait_descriptors") or {}
    if isinstance(raw, dict) and not plan.worn_face:
        opened = opened_feature_traits(data)
        descriptors = {
            name: text.strip()
            for name, text in raw.items()
            if name in opened and isinstance(text, str) and text.strip()
        }
    band = get_height_band(draft.height_inches) if draft.height_inches else None
    return AppearanceSection(
        height_inches=draft.height_inches or None,
        height_band=band.display_name if band is not None else None,
        build=(
            IdNameRef(id=draft.build.pk, name=draft.build.display_name)
            if draft.build is not None
            else None
        ),
        description=str(data.get("description") or ""),
        form_traits=[
            FormTraitEntry(
                trait=trait.display_name,
                value=descriptors.get(trait.name) or option.display_name,
            )
            for trait, option in selections.items()
        ],
    )


def _personas(plan: _Plan) -> list[PersonaEntry]:
    """Mirrors ``_build_personas`` for the owner: the primary face, then a worn or hidden
    second face (``_write_officially_dead``, ``_write_alter_ego``)."""
    from world.conditions.thumbnail_services import placeholder_portrait_url  # noqa: PLC0415

    faces = [PersonaEntry(id=plan.next_id(), name=plan.full_name, thumbnail=None)]
    faces.extend(
        PersonaEntry(id=plan.next_id(), name=name, thumbnail=placeholder_portrait_url())
        for name in (plan.worn_face, plan.hidden_face)
        if name
    )
    return faces


# --- Stats, skills, bonuses -----------------------------------------------------------


def _held_by_target(
    plan: _Plan, *, category: str | None = None
) -> tuple[dict[int, ModifierTarget], dict[int, list]]:
    """Each target the cards reach (resonance-category effects excepted, as finalize skips
    them), with the cards on it in the order finalize writes their modifier rows."""
    from world.distinctions.models import DistinctionEffect  # noqa: PLC0415
    from world.mechanics.bonuses import TARGET_RELATIONS, card_label  # noqa: PLC0415
    from world.mechanics.constants import RESONANCE_CATEGORY_NAME  # noqa: PLC0415
    from world.mechanics.types import HeldCardBonus, HeldEffect  # noqa: PLC0415

    real = [h for h in plan.holdings if not h.is_cover]
    if not real:
        return {}, {}
    effects = DistinctionEffect.objects.filter(
        distinction_id__in={h.distinction.pk for h in real}
    ).select_related(*(f"target__{relation}" for relation in TARGET_RELATIONS), "distinction")
    if category is not None:
        effects = effects.filter(target__category__name=category)
    by_distinction: dict[int, list[DistinctionEffect]] = defaultdict(list)
    for effect in effects.order_by("pk"):
        if effect.target.category.name == RESONANCE_CATEGORY_NAME:
            continue
        by_distinction[effect.distinction_id].append(effect)
    targets: dict[int, ModifierTarget] = {}
    cards: dict[int, list[HeldCardBonus]] = defaultdict(list)
    for holding in real:
        for effect in by_distinction.get(holding.distinction.pk, []):
            targets[effect.target_id] = effect.target
            cards[effect.target_id].append(
                HeldCardBonus(
                    label=card_label(
                        holding.distinction.name, feature=holding.feature, rank=holding.rank
                    ),
                    held=HeldEffect(
                        effect=effect,
                        rank=holding.rank,
                        value=effect.get_value_at_rank(holding.rank),
                    ),
                )
            )
    return targets, cards


def _draft_derived_reader() -> DerivedAmountReader:
    """A derived amount for a character with no sheet yet: the stored per-step value times
    nothing it can count, so 0. A new character has none of what a derived amount counts
    (threads past level 0, imbued resonance, renown)."""
    return lambda _effect, _per_step: 0


def _new_character_level(table: ValueTable | None) -> int | None:
    """The level approval gives a new character (``_stamp_default_class_level``: 1), when a
    sized effect reads a table (``sheet_valuation_level``)."""
    return 1 if table is not None else None


def _bonuses(plan: _Plan) -> list[BonusGroupEntry]:
    """The Bonuses band through the in-game builder (``bonus_groups``), from the cards and
    the home's comfort. Capable Mentor's path-aspect row has no effect template, and the
    in-game band leaves such a row out (bug #5316), so it is left out here too."""
    from world.character_sheets.serializers import bonus_group_entries  # noqa: PLC0415
    from world.mechanics.bonuses import bonus_groups  # noqa: PLC0415

    targets, cards = _held_by_target(plan)
    flats: dict[int, list] = {}
    comfort = _comfort_flats(plan)
    for target, flat in comfort:
        targets[target.pk] = target
        flats[target.pk] = [flat]
    return bonus_group_entries(
        bonus_groups(
            targets,
            cards=cards,
            flats=flats,
            equipment=lambda _target: [],
            level_for=_new_character_level,
            derived_reader=_draft_derived_reader(),
        )
    )


def _comfort_flats(plan: _Plan) -> list[tuple[ModifierTarget, Any]]:
    """The home comfort rows ``recompute_comfort_regen_modifier`` writes at approval: the
    starting room's comfort shifted by the cards' comfort lever, less neutral, on each AP
    regen target that exists. Nothing without a starting room or at neutral comfort."""
    from world.locations.constants import (  # noqa: PLC0415
        AP_MODIFIER_CATEGORY,
        AP_REGEN_TARGET_NAMES,
        COMFORT_LEVEL_MAX,
        COMFORT_LEVEL_MIN,
        COMFORT_LEVEL_NEUTRAL,
    )
    from world.locations.services import comfort_level  # noqa: PLC0415
    from world.mechanics.bonuses import TARGET_RELATIONS  # noqa: PLC0415
    from world.mechanics.constants import (  # noqa: PLC0415
        COMFORT_CATEGORY_NAME,
        COMFORT_TARGET_NAME,
    )
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.types import BonusSource  # noqa: PLC0415

    room = plan.starting_room
    if room is None:
        return []
    shift = 0
    targets, cards = _held_by_target(plan, category=COMFORT_CATEGORY_NAME)
    for target_id, target in targets.items():
        if target.name == COMFORT_TARGET_NAME:
            # ``lever_total`` reads ``get_modifier_total``, which sums the cards flat.
            shift += _draft_valuation([card.held for card in cards[target_id]], None).total
    room_level = comfort_level(cast("DefaultObject", room)) + shift
    level = max(COMFORT_LEVEL_MIN, min(COMFORT_LEVEL_MAX, room_level))
    delta = level - COMFORT_LEVEL_NEUTRAL
    if not delta:
        return []
    rows = ModifierTarget.objects.filter(
        category__name=AP_MODIFIER_CATEGORY, name__in=AP_REGEN_TARGET_NAMES
    ).select_related(*TARGET_RELATIONS)
    return [(target, BonusSource(label="Residence comfort", value=delta)) for target in rows]


def _draft_valuation(held: list[HeldEffect], lane: str | None) -> HeldEffectsValuation:
    """A new character's held effects on one target, valued as the sheet values them
    (``value_held_effects``): a sized effect reads ``lane``'s table at the level approval
    gives (``_new_character_level``), none when ``lane`` is None (a flat sum, as
    ``get_modifier_total`` reads it), and a derived amount counts nothing yet."""
    from world.checks.modifier_values import load_value_table  # noqa: PLC0415
    from world.mechanics.services import value_held_effects  # noqa: PLC0415

    table = None
    if lane is not None and any(item.effect.modifier_size is not None for item in held):
        table = load_value_table(lane)
    return value_held_effects(
        held,
        level=_new_character_level(table),
        value_table=table,
        derived_reader=_draft_derived_reader(),
    )


def _trait_modifiers(plan: _Plan, traits: list[Trait]) -> dict[int, int]:
    """Trait pk to the modifier a roll on it gets, as ``TraitHandler.get_trait_modifier``
    computes it for a new character: each card's share in the stat lane at level 1, one
    CHARACTER contribution each, tapered by the stat lane's rules when two or more pile up
    (``modifier_target_contributions``, ``_get_stat_modifier``)."""
    from collections import Counter  # noqa: PLC0415

    from world.checks.constants import ModifierLane, ModifierSourceKind  # noqa: PLC0415
    from world.checks.modifier_values import load_taper_rules  # noqa: PLC0415
    from world.checks.types import ModifierBreakdown, ModifierContribution  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    _targets, cards = _held_by_target(plan)
    out: dict[int, int] = {}
    for trait in traits:
        target = ModifierTarget.get_for_trait(trait)
        if target is None or target.pk not in cards:
            continue
        valuation = _draft_valuation([card.held for card in cards[target.pk]], ModifierLane.STAT)
        contributions = [
            ModifierContribution(
                source_kind=ModifierSourceKind.CHARACTER,
                source_label=detail.source_name,
                value=detail.final_value,
                level=detail.level,
                size=detail.size,
            )
            for detail in valuation.sources
            if not detail.blocked_by_immunity and detail.final_value != 0
        ]
        kinds = Counter(c.source_kind for c in contributions)
        tapers = load_taper_rules(ModifierLane.STAT) if any(n >= 2 for n in kinds.values()) else {}  # noqa: PLR2004
        out[trait.pk] = ModifierBreakdown(contributions=contributions, tapers=tapers).total
    return out


def _stat_sections(plan: _Plan) -> tuple[dict[str, int], dict[str, int]]:
    """``stats`` and ``buffed_stats`` as ``_build_stats`` / ``_build_buffed_stats`` read a
    new character: the allocation as written (``_create_stat_values`` plus
    ``_apply_post_cg_bonuses``), and the stats a card changes."""
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    data = plan.draft.draft_data
    allocation = data.get("stats") or {}
    if not isinstance(allocation, dict) or not allocation:
        return {}, {}
    traits = {
        t.name: t
        for t in Trait.objects.filter(name__in=list(allocation), trait_type=TraitType.STAT)
    }
    bonuses = data.get("stats_post_cg_bonuses") or {}
    stats = {
        name: int(value) + int(bonuses.get(name, 0) if isinstance(bonuses, dict) else 0)
        for name, value in allocation.items()
        if name in traits
    }
    modifiers = _trait_modifiers(plan, [traits[name] for name in stats])
    buffed = {
        name: value + modifiers[traits[name].pk]
        for name, value in stats.items()
        if modifiers.get(traits[name].pk, 0) != 0
    }
    return stats, buffed


def _skill_allocation(plan: _Plan) -> dict[int, int]:
    """Skill pk to rating as ``_create_skill_values`` writes it: the skills, then the
    Magic skills, each above 0 and still a skill."""
    from world.skills.models import Skill  # noqa: PLC0415

    data = plan.draft.draft_data
    wanted: dict[int, int] = {}
    for key in ("skills", "magic_skills"):
        raw = data.get(key) or {}
        if isinstance(raw, dict):
            wanted.update({int(pk): int(v) for pk, v in raw.items() if int(v) > 0})
    found = set(Skill.objects.filter(pk__in=list(wanted)).values_list("pk", flat=True))
    return {pk: value for pk, value in wanted.items() if pk in found}


def _skills(plan: _Plan) -> list[SkillEntry]:
    """Mirrors ``_build_skills`` for a new character."""
    from world.skills.models import Specialization  # noqa: PLC0415
    from world.skills.services import is_skill_at_xp_boundary  # noqa: PLC0415
    from world.traits.models import Trait  # noqa: PLC0415

    allocation = _skill_allocation(plan)
    if not allocation:
        return []
    traits = Trait.objects.in_bulk(list(allocation))
    raw_specs = plan.draft.draft_data.get("specializations") or {}
    spec_values = (
        {int(pk): int(v) for pk, v in raw_specs.items() if int(v) > 0}
        if isinstance(raw_specs, dict)
        else {}
    )
    specs = Specialization.objects.in_bulk(list(spec_values))
    by_skill: dict[int, list[SpecializationEntry]] = {}
    for pk, value in spec_values.items():
        spec = specs.get(pk)
        if spec is not None:
            by_skill.setdefault(spec.parent_skill_id, []).append(
                SpecializationEntry(id=spec.pk, name=spec.name, value=value)
            )
    ordered = [traits[pk] for pk in allocation if pk in traits]
    modifiers = _trait_modifiers(plan, ordered)
    return [
        SkillEntry(
            skill=SkillRef(id=trait.pk, name=trait.name, category=trait.category),
            value=allocation[trait.pk] + modifiers.get(trait.pk, 0),
            modifier=modifiers.get(trait.pk, 0),
            at_boundary=is_skill_at_xp_boundary(allocation[trait.pk]),
            specializations=by_skill.get(trait.pk, []),
        )
        for trait in ordered
    ]


# --- Path, distinctions, story, beats, goals, actor sheet -----------------------------


def _path(plan: _Plan) -> PathDetailSection | None:
    """Mirrors ``_build_path_detail``: the chosen path, its one history row dated today
    (approval writes it on the day it runs)."""
    from world.classes.models import PathStage  # noqa: PLC0415

    path = plan.draft.selected_path
    if path is None:
        return None
    tier = PathStage(path.stage).label
    return PathDetailSection(
        id=path.pk,
        name=path.name,
        stage=path.stage,
        tier=tier,
        history=[
            PathHistoryEntry(
                path=path.name,
                stage=path.stage,
                tier=tier,
                date=timezone.localdate().isoformat(),
            )
        ],
    )


def _distinctions(plan: _Plan) -> list[DistinctionEntry]:
    """Mirrors ``_build_distinctions`` for the owner: every card, a card held on two
    features twice, the secret and cover flags as approval sets them, in the sheet's order
    (``held_distinction_sort_key``)."""
    from world.distinctions.types import held_distinction_sort_key  # noqa: PLC0415

    return [
        DistinctionEntry(
            id=plan.next_id(),
            name=holding.distinction.name,
            rank=holding.rank,
            notes=holding.notes,
            is_secret=holding.is_secret,
            is_from_glimpse=holding.from_glimpse,
            is_cover=holding.is_cover,
            feature=holding.feature,
        )
        for holding in sorted(
            plan.holdings,
            key=lambda h: held_distinction_sort_key(h.distinction.name, h.feature),
        )
    ]


def _origin_slot_entries(plan: _Plan) -> list[OriginSlotEntry]:
    """The Upbringing answers ``_finalize_origin_slots`` writes, as ``_build_story`` lists
    them (by the question's sort order)."""
    from world.character_creation.models import (  # noqa: PLC0415
        OriginTemplateSlot,
        OriginTemplateSlotChoice,
    )
    from world.character_creation.questionnaire import DraftAnswers, anchor_for  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    draft = plan.draft
    answers = DraftAnswers.from_draft(draft)
    visible = draft.visible_origin_slot_ids()
    slot_ids = (
        set(answers.texts) | set(answers.picks) | set(answers.anchors) | set(answers.figures)
    ) & visible
    if not slot_ids:
        return []
    slots = {s.pk: s for s in OriginTemplateSlot.objects.filter(pk__in=slot_ids)}
    anchors = {sid: anchor_for(slots[sid], draft, answers) for sid in slot_ids if sid in slots}
    orgs = Organization.objects.in_bulk({pk for pk in anchors.values() if pk is not None})
    choices = OriginTemplateSlotChoice.objects.in_bulk(
        [answers.picks[sid] for sid in slot_ids if sid in answers.picks]
    )
    ordered = sorted(slots.values(), key=lambda slot: (slot.sort_order, slot.pk))
    return [
        entry
        for slot in ordered
        if (
            entry := _origin_slot_entry(
                slot,
                answers,
                choice=choices.get(answers.picks.get(slot.pk, 0)),
                org=orgs.get(anchors.get(slot.pk)),
            )
        )
        is not None
    ]


def _origin_slot_entry(
    slot: Any, answers: Any, *, choice: Any, org: Organization | None
) -> OriginSlotEntry | None:
    """One answered question as ``_build_story`` lists it, or None when it holds nothing
    ``set_origin_slot`` would write (no text, pick, anchor or figure). A pick from another
    question is ignored, as ``_finalize_origin_slots`` ignores it."""
    if choice is not None and choice.slot_id != slot.pk:
        choice = None
    figure = answers.figures.get(slot.pk, "") if slot.kind == QuestionKind.PERSON else ""
    value = answers.texts.get(slot.pk, "")
    if not value and choice is None and org is None and not figure:
        return None
    return OriginSlotEntry(
        slot_id=slot.pk,
        slot_name=slot.name,
        slot_prompt=slot.prompt,
        value=value,
        kind=slot.kind,
        connection_kind=slot.connection_kind,
        life_stage=slot.life_stage,
        choice_name=choice.name if choice is not None else "",
        choice_description=choice.description if choice is not None else "",
        organization_id=org.pk if org is not None else None,
        organization_name=org.name if org is not None else "",
        figure_name=figure,
    )


def _story(plan: _Plan) -> StorySection:
    """Mirrors ``_build_story`` for the owner. The origin story's state is the one
    ``refresh_origin_story_state`` settles at approval, which runs only when the draft
    answered an Upbringing question (``_apply_sheet_demographics``)."""
    from world.character_creation.offers import beats_for  # noqa: PLC0415
    from world.character_creation.services import origin_story_state_for  # noqa: PLC0415

    data = plan.draft.draft_data
    raw = data.get(BACKGROUND_KEY)
    background = raw.strip() if isinstance(raw, str) else ""
    slots = _origin_slot_entries(plan)
    answered = any(
        data.get(k) for k in ("origin_slots", "origin_choices", "origin_anchors", "origin_figures")
    )
    state = OriginStoryState.NOT_STARTED
    if answered:
        has_beats = any(entry.taken for entry in beats_for(plan.draft))
        state = origin_story_state_for(
            has_slots=bool(slots) or has_beats, has_prose=bool(background)
        )
    return StorySection(background=background, origin_story_state=state, origin_slots=slots)


def _beats(plan: _Plan) -> list[BeatEntry]:
    """Mirrors ``_build_beats``: the beats the draft took (``_finalize_beats``), each with
    the held cards that answer it."""
    from world.character_creation.models import LifeBeat  # noqa: PLC0415
    from world.character_creation.offers import LIFE_STAGE_ORDER, beats_for  # noqa: PLC0415

    taken = [entry for entry in beats_for(plan.draft) if entry.taken]
    if not taken:
        return []
    beats = LifeBeat.objects.in_bulk([entry.beat_id for entry in taken])
    held = {h.distinction.pk: h.distinction.name for h in plan.holdings}
    rows = [(entry, beats[entry.beat_id]) for entry in taken if entry.beat_id in beats]
    rows.sort(key=lambda r: (LIFE_STAGE_ORDER.get(r[1].life_stage, 99), r[1].sort_order))
    return [
        BeatEntry(
            beat_id=beat.pk,
            name=beat.name,
            life_stage=beat.life_stage,
            prompt=beat.prompt,
            unknown=entry.unknown,
            line=entry.line,
            answers=[
                held[offer.distinction_id] for offer in beat.answers if offer.distinction_id in held
            ],
        )
        for entry, beat in rows
    ]


def _goals(plan: _Plan) -> list[GoalEntry]:
    """Mirrors ``_build_goals`` for the goals ``_build_and_create_goals`` writes."""
    from world.goals.constants import GoalHorizon  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    goals_data = plan.draft.draft_data.get("goals") or []
    if not isinstance(goals_data, list):
        return []
    domains = ModifierTarget.objects.in_bulk(
        [g.get("domain_id") for g in goals_data if isinstance(g, dict) and g.get("domain_id")]
    )
    next_ordinal: dict[str, int] = {}
    goals: list[GoalEntry] = []
    for g in goals_data:
        if not isinstance(g, dict) or g.get("domain_id") not in domains:
            continue
        points = g.get("points", 0) or 0
        notes = (g.get("notes") or "").strip()
        if points <= 0 and not notes:
            continue
        horizon = g.get("horizon") or GoalHorizon.SHORT_TERM
        if horizon not in GoalHorizon.values:
            horizon = GoalHorizon.SHORT_TERM
        next_ordinal[horizon] = next_ordinal.get(horizon, 0) + 1
        goals.append(
            GoalEntry(
                domain=domains[g["domain_id"]].name,
                horizon=horizon,
                ordinal=next_ordinal[horizon],
                points=points,
                notes=notes,
            )
        )
    goals.sort(key=lambda goal: (goal["horizon"], goal["ordinal"]))
    return goals


def _actor_sheet(plan: _Plan) -> ActorSheetSection:
    """Mirrors ``_build_actor_sheet`` for the owner: the three answers, the enemy
    ``resolve_enemy`` prices (``_create_enemy``) and the Introductions
    (``planned_introductions``)."""
    from world.character_creation.enemies import resolve_enemy  # noqa: PLC0415
    from world.character_creation.services import planned_introductions  # noqa: PLC0415
    from world.character_sheets.types import EnemyKind  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    data = plan.draft.draft_data
    answers = {key: str(data.get(key) or "") for key, _copy in ACTOR_SHEET_QUESTIONS}
    resolved = resolve_enemy(plan.draft)
    enemy = None
    if resolved is not None:
        org = (
            Organization.objects.filter(pk=resolved.organization_id).first()
            if resolved.organization_id
            else None
        )
        name = resolved.figure_name
        if resolved.kind != EnemyKind.PERSON and org is not None:
            name = org.name
        enemy = EnemyEntry(
            kind=resolved.kind,
            name=name,
            power_tier=resolved.power_tier,
            reach=resolved.reach,
            degree=resolved.degree,
            price=resolved.price,
            why=resolved.why,
            public_line=resolved.public_line,
            status=resolved.status,
            has_secret=False,
        )
    now = timezone.now().isoformat()
    return ActorSheetSection(
        never_do=answers.get("never_do", ""),
        protect=answers.get("protect", ""),
        fear=answers.get("fear", ""),
        enemy_public_line=enemy["public_line"] if enemy is not None else "",
        enemy=enemy,
        introductions=[
            IntroductionEntry(
                id=plan.next_id(),
                kind=entry.kind,
                title=entry.title,
                body=entry.body,
                created_at=now,
            )
            for entry in planned_introductions(plan.draft, fallback_name=plan.full_name)
        ],
    )


# --- Standing, estate -----------------------------------------------------------------


def _reputation_bumps(plan: _Plan) -> list[tuple[Organization, int]]:
    """The opinions approval seeds, in its order: each picked Upbringing answer's seed
    (``_seed_connection_reputation``), the enemy group's (``_create_enemy``), a tie a card
    opens as renown (``_write_card_ties``)."""
    from world.character_creation.enemies import resolve_enemy  # noqa: PLC0415
    from world.character_creation.models import OriginTemplateSlotChoice  # noqa: PLC0415
    from world.character_creation.questionnaire import DraftAnswers, anchor_for  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415
    from world.societies.types import FAVORED_FLOOR  # noqa: PLC0415

    draft = plan.draft
    bumps: list[tuple[int, int]] = []
    template = draft.selected_origin_template
    if template is not None:
        answers = DraftAnswers.from_draft(draft)
        visible = draft.visible_origin_slot_ids()
        choices = (
            OriginTemplateSlotChoice.objects.filter(
                pk__in=[cid for sid, cid in answers.picks.items() if sid in visible],
                slot__template=template,
                is_active=True,
            )
            .exclude(reputation_seed=0)
            .select_related("slot")
        )
        for choice in choices:
            org_id = anchor_for(choice.slot, draft, answers)
            if org_id is not None:
                bumps.append((org_id, choice.reputation_seed))
    resolved = resolve_enemy(draft)
    if resolved is not None and resolved.organization_id:
        bumps.append((resolved.organization_id, ENEMY_REPUTATION_SEED[resolved.degree]))
    bumps.extend(
        (org_id, FAVORED_FLOOR) for org_id, kind in _answered_ties(draft) if kind == TieKind.RENOWN
    )
    orgs = Organization.objects.in_bulk({org_id for org_id, _ in bumps})
    return [(orgs[org_id], delta) for org_id, delta in bumps if org_id in orgs and delta]


def _standing(plan: _Plan) -> StandingSection:
    """Mirrors ``_build_standing`` for the owner. It reads the presented face, so a
    character presenting a worn face shows that face's standing, which is none."""
    from world.societies.constants import (  # noqa: PLC0415
        REASON_LINES_SHOWN,
        OrganizationReputationCause,
    )
    from world.societies.models import (  # noqa: PLC0415
        REPUTATION_MAX,
        REPUTATION_MIN,
        OrganizationReputationEvent,
    )
    from world.societies.reputation_reasons import copy_by_cause, reason_line  # noqa: PLC0415
    from world.societies.types import ReputationTier  # noqa: PLC0415

    if plan.worn_face:
        return StandingSection(memberships=[], reputations=[])
    memberships = sorted(plan.memberships, key=lambda m: m.organization.name)
    values: dict[int, int] = {}
    orgs: dict[int, Organization] = {}
    lines: dict[int, list[str]] = defaultdict(list)
    copy = copy_by_cause()
    for org, delta in _reputation_bumps(plan):
        orgs[org.pk] = org
        before = values.get(org.pk, 0)
        after = max(REPUTATION_MIN, min(REPUTATION_MAX, before + delta))
        values[org.pk] = after
        if after != before:
            event = OrganizationReputationEvent(
                cause=OrganizationReputationCause.CHARACTER_CREATION,
                tier_after=ReputationTier.from_value(after).value,
            )
            lines[org.pk].insert(0, reason_line(event, copy))
    return StandingSection(
        memberships=[
            OrgMembershipEntry(
                organization_id=m.organization.pk,
                organization=m.organization.name,
                title=(m.organization.get_rank_title(m.rank.tier) if m.rank is not None else ""),
                favor="",
                favor_note="",
            )
            for m in memberships
        ],
        reputations=[
            OrgReputationEntry(
                organization_id=pk,
                organization=orgs[pk].name,
                tier=ReputationTier.from_value(values[pk]).value,
                reasons=lines[pk][:REASON_LINES_SHOWN],
            )
            for pk in sorted(orgs, key=lambda pk: orgs[pk].name)
        ],
    )


def _residence_room(plan: _Plan) -> RoomProfile | None:
    """The room profile approval makes the character's home: the starting room, when the
    starting area grants a residence and the room has a profile
    (``_grant_cg_residence_tenancy``)."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    area = plan.draft.selected_area
    room = plan.starting_room
    if area is None or room is None or not area.grants_residence_tenancy:
        return None
    try:
        return room.room_profile
    except RoomProfile.DoesNotExist:
        return None


def _current_residence(plan: _Plan) -> IdNameRef | None:
    """Mirrors ``_build_current_residence``: the home the residence grant defaults."""
    profile = _residence_room(plan)
    if profile is None:
        return None
    return IdNameRef(id=profile.pk, name=profile.objectdb.db_key)


def _keyring(plan: _Plan) -> list[KeyringEntry]:
    """Mirrors ``_build_keyring`` for the owner: the home's tenant key, then every open
    grant an organization the character joins already holds, by place."""
    rows = _home_key(plan) + _organization_keys(plan)
    rows.sort(key=lambda pair: pair[0])
    return [entry for _, entry in rows]


def _home_key(plan: _Plan) -> list[tuple[tuple[str, str], KeyringEntry]]:
    """The tenant key to the home the residence grant makes, with its sort key."""
    from world.locations.constants import LocationRole  # noqa: PLC0415

    profile = _residence_room(plan)
    if profile is None:
        return []
    entry = KeyringEntry(
        id=plan.next_id(),
        place=profile.objectdb.db_key,
        where=profile.area.name if profile.area else "",
        rung=LocationRole(LocationRole.TENANT).label,
        through="",
        granted_by="",
    )
    return [((profile.objectdb.db_key, ""), entry)]


def _organization_keys(plan: _Plan) -> list[tuple[tuple[str, str], KeyringEntry]]:
    """The open grants the organizations the character joins already hold, as
    ``_keyring_entry`` shapes them, each with its sort key."""
    from django.db import models  # noqa: PLC0415

    from world.character_sheets.serializers import _keyring_entry  # noqa: PLC0415
    from world.locations.models import LocationTenancy  # noqa: PLC0415

    org_ids = [m.organization.pk for m in plan.memberships]
    if not org_ids:
        return []
    grants = (
        LocationTenancy.objects.filter(tenant_organization_id__in=org_ids)
        .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=timezone.now()))
        .select_related(
            "room_profile__objectdb",
            "room_profile__area",
            "area",
            "tenant_organization",
            "granted_by",
        )
    )
    return [
        (
            (
                grant.room_profile.objectdb.db_key if grant.room_profile else "",
                grant.area.name if grant.area else "",
            ),
            entry,
        )
        for grant in grants
        if (entry := _keyring_entry(grant)) is not None
    ]


def _domains(plan: _Plan) -> list[OrgDomainEntry]:
    """Mirrors ``_build_domains`` for the owner: land the joined organizations hold."""
    from world.societies.houses.models import Domain  # noqa: PLC0415

    org_ids = [m.organization.pk for m in plan.memberships]
    if not org_ids:
        return []
    domains = (
        Domain.objects.filter(owner_org_id__in=org_ids)
        .select_related("area", "owner_org")
        .order_by("owner_org__name", "name")
    )
    return [
        OrgDomainEntry(
            id=domain.pk,
            name=domain.name,
            organization=domain.owner_org.name if domain.owner_org_id else "",
            where=domain.area.name,
        )
        for domain in domains
    ]


def _purse(plan: _Plan) -> PurseSection:
    """The purse ``/api/status/purse`` reads after approval: every held card's inheritance
    (``apply_starting_grant``, once per card held, a card on two features twice)."""
    from world.currency.services import starting_grant_for  # noqa: PLC0415

    balance = 0
    for holding in plan.holdings:
        if holding.is_cover or holding.from_species:
            continue
        grant = starting_grant_for(holding.distinction)
        if grant is not None:
            balance += grant.coppers
    return PurseSection(balance=balance)


def _carried(plan: _Plan) -> list[CarriedItemEntry]:
    """What the inventory lists after approval: each held card's keepsakes
    (``apply_item_grants``). ``id`` is below zero, since no item exists yet."""
    from world.items.services.narrative_grants import item_grants_for  # noqa: PLC0415

    return [
        CarriedItemEntry(
            id=plan.next_id(),
            display_name=grant.item_template.name,
            quality_tier=None,
            suggested_value=None,
        )
        for holding in plan.holdings
        if not holding.is_cover and not holding.from_species
        for grant in item_grants_for(holding.distinction)
    ]


# --- Growth, Knowledge ----------------------------------------------------------------


def _xp_ledger(plan: _Plan) -> XpLedgerSection:
    """The XP ledger after approval (``character_xp_ledger``): the unspent creation points
    as locked XP (``starting_locked_xp``), nothing earned or spent yet."""
    from world.character_creation.services import starting_locked_xp  # noqa: PLC0415

    return XpLedgerSection(earned=0, spent=0, locked=starting_locked_xp(plan.draft))


def _languages(plan: _Plan) -> list[StartingLanguageEntry]:
    """The languages ``/api/species/my-languages/`` lists after approval
    (``starting_languages``, fluent), by name."""
    from world.species.language_constants import FLUENT_GRANT_VALUE, fluency_band  # noqa: PLC0415
    from world.species.services import starting_languages  # noqa: PLC0415

    band = fluency_band(FLUENT_GRANT_VALUE).value
    languages = [
        lang
        for lang in starting_languages(plan.draft.selected_species, plan.draft.selected_beginnings)
        if lang.trait_id is not None
    ]
    languages.sort(key=lambda lang: lang.name)
    return [
        StartingLanguageEntry(
            language_id=lang.pk,
            name=lang.name,
            fluency=FLUENT_GRANT_VALUE,
            band=band,
            is_current=False,
            effective_fluency=FLUENT_GRANT_VALUE,
            effective_band=band,
            temporary_sources=[],
        )
        for lang in languages
    ]


def _secrets(plan: _Plan) -> list[OwnSecretEntry]:
    """The character's own secrets as the sheet shows them to its player
    (``world.secrets.own``), in the order approval makes them and then the own shelf's
    order: each card relocated into a Secret (``_mint_distinction_secrets``), a secret
    worship (``mint_worship_secret``), a covert seat taken through the vacancy
    (``sync_covert_membership_secret``), each Whispers line (``_seed_whispers``), then a
    covert seat a card or a tie opens."""
    from world.character_creation.services import whisper_lines  # noqa: PLC0415
    from world.secrets.constants import SecretLevel, SecretProvenance  # noqa: PLC0415
    from world.secrets.own import own_secret_entry, own_shelf_order  # noqa: PLC0415
    from world.societies.membership_services import (  # noqa: PLC0415
        covert_membership_secret_level,
        covert_membership_secret_words,
    )
    from world.worship.constants import WORSHIP_SECRET_DEFAULT_LEVEL  # noqa: PLC0415
    from world.worship.secrets import worship_secret_content  # noqa: PLC0415

    def row(
        level: int, content: str, provenance: str, *, author: str = "", consequences: str = ""
    ) -> tuple[int, OwnSecretEntry]:
        return level, own_secret_entry(
            secret_id=plan.next_id(),
            level=level,
            content=content,
            provenance=provenance,
            subject=plan.full_name,
            author=author,
            consequences=consequences,
        )

    def covert(membership: _Membership) -> tuple[int, OwnSecretEntry]:
        content, consequences = covert_membership_secret_words(
            plan.full_name, membership.organization
        )
        return row(
            covert_membership_secret_level(membership.rank),
            content,
            SecretProvenance.GM_AUTHORED,
            consequences=consequences,
        )

    made: list[tuple[int, OwnSecretEntry]] = [
        row(
            holding.distinction.default_secret_level,
            holding.distinction.name,
            SecretProvenance.GM_AUTHORED,
        )
        for holding in plan.holdings
        if holding.is_secret and not holding.is_cover and not holding.from_species
    ]
    draft = plan.draft
    secret_being = draft.secret_worship
    if secret_being is not None and (
        draft.public_worship is None or draft.public_worship.pk != secret_being.pk
    ):
        made.append(
            row(
                WORSHIP_SECRET_DEFAULT_LEVEL,
                worship_secret_content(secret_being),
                SecretProvenance.GM_AUTHORED,
            )
        )
    covert_seats = [m for m in plan.memberships if m.organization.is_covert]
    made.extend(covert(m) for m in covert_seats if m.vacancy is not None)
    made.extend(
        row(
            SecretLevel.UNCOMMON_KNOWLEDGE,
            line,
            SecretProvenance.PLAYER_FLAVOR,
            author=plan.full_name,
        )
        for line in whisper_lines(draft)
    )
    made.extend(covert(m) for m in covert_seats if m.vacancy is None)
    return own_shelf_order(made)


# --- Magic, combat --------------------------------------------------------------------


def _magic(plan: _Plan) -> MagicSection | None:
    """Mirrors ``_build_magic`` for the owner, from the picks ``provision_magic`` writes."""
    picks = plan.picks
    if picks is None:
        return None
    tags = _glimpse_tags(picks)
    seeds, settled = _resonance_seeds(picks, tags)
    return MagicSection(
        gifts=_gifts(plan, picks),
        motif=_motif(plan, picks),
        anima_ritual=_anima_ritual(plan, picks),
        aura=_aura(plan, seeds, settled, tags),
        resonances=sorted(
            (
                ResonanceBalanceEntry(name=resonance.name, balance=0, lifetime_earned=amount)
                for resonance, amount in seeds
            ),
            key=lambda row: row["name"],
        ),
        ultimates=[],
    )


def _glimpse_tags(picks: MagicPicks) -> list[GlimpseTag]:
    """The Glimpse tags ``_glimpse`` sets: active ones, by axis, a stand-alone tag alone."""
    from world.magic.constants import GlimpseTagAxis  # noqa: PLC0415
    from world.magic.models import GlimpseTag  # noqa: PLC0415
    from world.magic.services.glimpse import keep_stand_alone  # noqa: PLC0415

    if not picks.glimpse_tag_ids:
        return []
    rows = list(
        GlimpseTag.objects.filter(
            pk__in=list(picks.glimpse_tag_ids), is_active=True
        ).select_related("affinity")
    )
    tags: list[GlimpseTag] = []
    for axis in GlimpseTagAxis:
        tags.extend(keep_stand_alone([tag for tag in rows if tag.axis == axis]))
    return tags


def _resonance_seeds(
    picks: MagicPicks, tags: list[GlimpseTag]
) -> tuple[list[tuple[Resonance, int]], dict[int, tuple[Any, Decimal]]]:
    """Each pick's starting lifetime and the settled self, as ``_seed_resonances`` writes
    them on a sheet holding none: the weights' shares, the Glimpse's nudge
    (``glimpse_nudged_shares``), then the seeds from the nudged shares."""
    from world.character_creation.magic_writer import (  # noqa: PLC0415
        creation_affinity_base,
        creation_seed_amounts,
    )
    from world.magic.services.aura import rounded_aura_shares  # noqa: PLC0415
    from world.magic.services.drift import get_drift_config  # noqa: PLC0415
    from world.magic.services.glimpse import glimpse_nudged_shares  # noqa: PLC0415
    from world.magic.types import AffinityShare  # noqa: PLC0415

    affinities: dict[int, Any] = {}
    base = creation_affinity_base(picks, {}, affinities, get_drift_config().creation_seed_per_point)
    grand_total = sum(base.values())
    if grand_total == 0:
        return [], {}
    settled = rounded_aura_shares(
        [
            AffinityShare(affinity=affinities[pk], percent=Decimal(total) * 100 / grand_total)
            for pk, total in base.items()
            if total
        ]
    )
    nudged = glimpse_nudged_shares(settled, tags)
    if nudged is not None:
        settled = rounded_aura_shares(nudged)
    percents = {pk: pct for pk, (_affinity, pct) in settled.items()}
    seeds = [
        (pick.resonance, amount)
        for pick, amount in creation_seed_amounts(picks, base, {}, percents)
    ]
    return seeds, settled


def _aura(
    plan: _Plan,
    seeds: list[tuple[Resonance, int]],
    settled: dict[int, tuple[Any, Decimal]],
    tags: list[GlimpseTag],
) -> AuraData | None:
    """Mirrors ``_build_magic_aura``: the shares ``recompute_aura`` derives from the seeds
    (an affinity settled above 0 with no resonance keeps its row at 0, as
    ``set_aura_shares`` keeps it), and the Glimpse ``_glimpse`` writes."""
    from world.magic.constants import GlimpseState  # noqa: PLC0415
    from world.magic.models import CharacterAuraShare  # noqa: PLC0415
    from world.magic.models.aura import share_lead_key  # noqa: PLC0415
    from world.magic.services.aura import rounded_aura_shares  # noqa: PLC0415
    from world.magic.types import AffinityShare  # noqa: PLC0415

    picks = plan.picks
    shares: list[CharacterAuraShare] = []
    totals: dict[int, int] = defaultdict(int)
    affinities: dict[int, Any] = {}
    for resonance, amount in seeds:
        totals[resonance.affinity_id] += amount
        affinities[resonance.affinity_id] = resonance.affinity
    grand_total = sum(totals.values())
    if grand_total:
        rounded = rounded_aura_shares(
            [
                AffinityShare(
                    affinity=affinities[pk], percent=Decimal(t) / Decimal(grand_total) * 100
                )
                for pk, t in sorted(totals.items())
                if t
            ]
        )
        shares = [
            CharacterAuraShare(affinity=affinity, percent=pct) for affinity, pct in rounded.values()
        ]
        shares.extend(
            CharacterAuraShare(affinity=affinity, percent=Decimal("0.00"))
            for pk, (affinity, pct) in settled.items()
            if pk not in rounded and pct > 0
        )
    shares.sort(key=lambda share: share_lead_key(share, share.percent))
    story = picks.glimpse_story or ""
    if story.strip():
        state = GlimpseState.COMPLETE
    elif tags:
        state = GlimpseState.TAGS_ONLY
    else:
        state = GlimpseState.NOT_STARTED
    return AuraData(
        id=plan.next_id(),
        shares=[
            AuraShareEntry(
                affinity_id=share.affinity_id,
                affinity_name=share.affinity.name,
                percent=share.percent,
            )
            for share in shares
        ],
        dominant_affinity=shares[0].affinity.name if shares else "",
        glimpse_story=story,
        glimpse_state=state,
        glimpse_tags=[
            GlimpseTagEntry(id=tag.pk, axis=tag.axis, name=tag.name, description=tag.description)
            for tag in tags
        ],
        can_finish_glimpse=state != GlimpseState.COMPLETE,
    )


def _theming(magic: MagicSection | None) -> ThemingSection:
    """Mirrors ``_build_theming``: the new character's aura, for the page's colours."""
    aura = magic["aura"] if magic is not None else None
    if aura is None:
        return ThemingSection(aura=None)
    return ThemingSection(
        aura=AuraThemingData(shares=aura["shares"], dominant_affinity=aura["dominant_affinity"])
    )


@dataclass
class _TechniquePicks:
    """What every technique entry reads, fetched once: the path's style, each technique's
    personalization pick and the rows its ids name, and the gift thread's resonances."""

    style: str
    personal: dict[int, Any]
    prices: dict[int, Any]
    bonuses: dict[int, Any]
    early_forms: dict[int, Any]
    components: Any
    resonance_ids: list[int]
    lead: Resonance | None


def _gifts(plan: _Plan, picks: MagicPicks) -> list[GiftEntry]:
    """Mirrors ``_build_magic_gifts``: the major gift with its techniques (as each pick's
    personalization names and prices it), then the species' gifts."""
    from world.species.services import species_gift_grants  # noqa: PLC0415

    major = picks.gift
    if major is None:
        return []
    context = _technique_picks(plan, picks)
    gifts = [
        _gift_entry(
            major,
            [_technique_entry(t, context) for t in picks.techniques if t.gift_id == major.pk],
        )
    ]
    seen = {major.pk}
    for grant in species_gift_grants(plan.draft.selected_species):
        if grant.gift_id not in seen:
            seen.add(grant.gift_id)
            gifts.append(_gift_entry(grant.gift, []))
    return gifts


def _technique_picks(plan: _Plan, picks: MagicPicks) -> _TechniquePicks:
    """The personalization picks ``apply_creation_personalizations`` writes, and the
    prices, flourishes and early forms they name, each read once."""
    from world.magic.models import Restriction, SignatureMotifBonus  # noqa: PLC0415
    from world.magic.services.creation_personalization import (  # noqa: PLC0415
        parse_personalization_picks,
    )
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        price_components_by_price,
    )
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    path = plan.draft.selected_path
    personal = {
        pick.technique_id: pick
        for pick in parse_personalization_picks(
            plan.draft.draft_data.get(TECHNIQUE_PERSONALIZATIONS_KEY),
            technique_ids=[t.pk for t in picks.techniques],
        )
    }
    prices = Restriction.objects.in_bulk([p.price_id for p in personal.values() if p.price_id])
    return _TechniquePicks(
        style=path.style.name if path is not None and path.style_id is not None else "",
        personal=personal,
        prices=prices,
        bonuses=SignatureMotifBonus.objects.in_bulk(
            [p.signature_bonus_id for p in personal.values() if p.signature_bonus_id]
        ),
        early_forms=TechniqueVariant.objects.in_bulk(
            [p.early_form_id for p in personal.values() if p.early_form_id]
        ),
        components=price_components_by_price(prices.keys()),
        resonance_ids=[pick.resonance.pk for pick in picks.ordered_resonances],
        lead=picks.lead_resonance,
    )


def _picked(rows: dict[int, Any], row_id: int | None) -> Any:
    """The row a pick names, or None when it names none."""
    return rows.get(row_id) if row_id else None


def _technique_entry(tech: Technique, context: _TechniquePicks) -> TechniqueEntry:
    """One technique as the new character's spellbook lists it: the hold its pick
    personalizes, the forms its gift thread reaches, and a flourish's signature."""
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.technique_forms import (  # noqa: PLC0415
        creation_next_signature,
        creation_technique_forms,
        technique_price_payload,
    )
    from world.magic.services.technique_personalization import hold_display_name  # noqa: PLC0415

    pick = context.personal.get(tech.pk)
    hold = CharacterTechnique(
        technique=tech,
        custom_name=pick.custom_name if pick else "",
        custom_description=pick.custom_description if pick else "",
        price=_picked(context.prices, pick.price_id) if pick else None,
    )
    lead = context.lead
    # A flourish weaves its TECHNIQUE thread in the lead resonance; without one, none.
    bonus = _picked(context.bonuses, pick.signature_bonus_id) if pick and lead else None
    early = _picked(context.early_forms, pick.early_form_id) if pick else None
    return TechniqueEntry(
        name=hold_display_name(hold, fallback=tech.name),
        catalog_name=tech.name,
        level=tech.level,
        style=context.style,
        description=hold.custom_description or tech.description,
        effect_summary=tech.cached_effect_summary,
        forms=creation_technique_forms(tech, context.resonance_ids, early_form=early),
        signature=_signature_payload(bonus),
        price=technique_price_payload(hold, components=context.components),
        # The next flourish is read off that thread, at the flourish's own level.
        next_signature=(
            creation_next_signature(lead.pk, bonus.min_crossing_level)
            if bonus is not None and lead is not None
            else None
        ),
    )


def _signature_payload(bonus: Any) -> TechniqueSignaturePayload | None:
    """A signed flourish as the spellbook shows it (``technique_signature_payload``)."""
    from world.magic.types.technique_effects import TechniqueSignaturePayload  # noqa: PLC0415

    if bonus is None:
        return None
    return TechniqueSignaturePayload(
        name=bonus.name,
        narrative_snippet=bonus.narrative_snippet,
        intensity_delta=bonus.flat_intensity_delta,
    )


def _gift_entry(gift: Gift, techniques: list[TechniqueEntry]) -> GiftEntry:
    """One gift as the spellbook lists it, with its authored resonances."""
    return GiftEntry(
        name=gift.name,
        description=gift.description,
        resonances=[r.name for r in gift.resonances.all()],
        techniques=techniques,
    )


def _motif(plan: _Plan, picks: MagicPicks) -> MotifSection | None:
    """Mirrors ``_build_magic_motif``: the Motif ``seed_motif_from_gift_resonance`` seeds
    with the lead resonance and the facets ``tie_creation_facets`` ties to it."""
    from world.magic.models import Facet  # noqa: PLC0415

    lead = picks.lead_resonance
    if lead is None:
        return None
    facet_ids = plan.draft.draft_data.get(GIFT_FACETS_KEY) or []
    facets = Facet.objects.in_bulk(facet_ids) if facet_ids else {}
    return MotifSection(
        description="",
        resonances=[
            MotifResonanceEntry(
                name=lead.name,
                facets=[facets[pk].name for pk in facet_ids if pk in facets],
                styles=[],
            )
        ],
    )


def _anima_ritual(plan: _Plan, picks: MagicPicks) -> AnimaRitualSection | None:
    """Mirrors ``_build_magic_anima_ritual``: the ritual ``provision_player_anima_ritual``
    creates from the Anima Check picks (Willpower, else the highest skill, as it falls
    back), the two resonance picks and its placeholder description."""
    from world.magic.services.anima import ANIMA_RITUAL_DESCRIPTION  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    stat = (
        picks.anima_stat
        or Trait.objects.filter(name="willpower", trait_type=TraitType.STAT).first()
    )
    skill = picks.anima_skill
    if skill is None:
        allocation = _skill_allocation(plan)
        if allocation:
            best = max(allocation, key=lambda pk: allocation[pk])
            skill = Skill.objects.filter(pk=best).first()
        if skill is None:
            skill = Skill.objects.filter(is_active=True).first()
    if stat is None or skill is None:
        return None
    primal = picks.primal_resonance
    outward = picks.outward_resonance
    return AnimaRitualSection(
        stat=stat.name,
        skill=skill.name,
        primal_resonance=primal.name if primal is not None else "",
        outward_resonance=outward.name if outward is not None else "",
        description=ANIMA_RITUAL_DESCRIPTION,
    )


def _natural_weapons(plan: _Plan) -> list[NaturalWeaponEntry]:
    """Mirrors ``_build_natural_weapons``: one per gift naming an active natural weapon
    (``provision_natural_weapon``, the major gift's first, then the species'), read off its
    template with no item made."""
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.species.services import species_gift_grants  # noqa: PLC0415

    picks = plan.picks
    gifts: list[tuple[Gift, bool]] = (
        [(picks.gift, False)] if picks is not None and picks.gift is not None else []
    )
    gifts.extend((grant.gift, True) for grant in species_gift_grants(plan.draft.selected_species))
    weapons: list[NaturalWeaponEntry] = []
    for gift, from_species in gifts:
        template = gift.natural_weapon_template
        if template is None or not template.is_active:
            continue
        weapon = ItemInstance(template=template, natural_weapon_gift=gift)
        damage_type = weapon.effective_weapon_damage_type
        # The facets ``stamp_inherent_facets`` puts on a new instance: the template's own,
        # none of them crafted, listed by name as ``_build_natural_weapons`` lists them.
        inherent = sorted(template.inherent_facets.all(), key=lambda facet: (facet.name, facet.pk))
        weapons.append(
            NaturalWeaponEntry(
                id=plan.next_id(),
                name=weapon.display_name,
                gift_name=gift.name,
                from_species=from_species,
                damage=weapon.effective_weapon_damage,
                damage_type=damage_type.name if damage_type else "",
                facets=[facet.name for facet in inherent],
                facets_used=0,
                facet_capacity=template.facet_capacity,
            )
        )
    return weapons


def _combat_style(plan: _Plan) -> CombatStyleSection | None:
    """Mirrors ``_build_combat_style`` for the style ``_finalize_combat_style`` sets."""
    from world.covenants.models import CombatStyleGear  # noqa: PLC0415
    from world.covenants.style_profile import armor_kinds, weapon_kinds  # noqa: PLC0415
    from world.magic.models import Tradition  # noqa: PLC0415

    style = plan.draft.selected_combat_style
    if style is None:
        return None
    held = list(
        CombatStyleGear.objects.filter(style=style).values_list("gear_archetype", flat=True)
    )
    skill = style.skill
    skill_value = _skill_allocation(plan).get(skill.pk, 0) if skill is not None else 0
    traditions = list(Tradition.objects.filter(combat_styles=style).order_by("sort_order", "name"))
    own = plan.draft.selected_tradition
    tradition = next(
        (t.name for t in traditions if own is not None and t.pk == own.pk),
        traditions[0].name if traditions else None,
    )
    return CombatStyleSection(
        id=style.pk,
        name=style.name,
        description=style.description,
        defense_style=style.defense_style,
        defense_style_display=style.get_defense_style_display(),
        armor_share_tenths=style.armor_share_tenths,
        hit_stat_name=style.hit_stat.name if style.hit_stat is not None else None,
        weapon_kinds=weapon_kinds(held),
        armor_kinds=armor_kinds(held),
        skill_name=skill.name if skill is not None else "",
        skill_value=skill_value,
        tradition_name=tradition,
        vows=list(style.compatible_roles.order_by("name").values_list("name", flat=True)),
    )
