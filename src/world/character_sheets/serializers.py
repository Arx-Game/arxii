"""
Serializers for the character sheets API.
"""

from __future__ import annotations

from django.db.models import Model, QuerySet
from django.db.models.query import Prefetch
from rest_framework import serializers
from rest_framework.request import Request

from world.character_sheets.models import CharacterSheet, Guise
from world.character_sheets.services import can_edit_character_sheet
from world.character_sheets.types import (
    AnimaRitualSection,
    AppearanceSection,
    AuraData,
    AuraThemingData,
    DistinctionEntry,
    FormTraitEntry,
    GiftEntry,
    GoalEntry,
    GuiseEntry,
    IdentitySection,
    IdNameRef,
    MagicSection,
    MotifResonanceEntry,
    MotifSection,
    PathDetailSection,
    PathHistoryEntry,
    PronounsData,
    SkillEntry,
    SkillRef,
    SpecializationEntry,
    StorySection,
    TechniqueEntry,
    ThemingSection,
)
from world.classes.models import PathStage
from world.distinctions.models import CharacterDistinction
from world.forms.models import CharacterForm, CharacterFormValue, FormType
from world.goals.models import CharacterGoal
from world.magic.models import (
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterTechnique,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
)
from world.progression.models import CharacterPathHistory
from world.roster.models import RosterEntry, RosterTenure
from world.skills.models import CharacterSkillValue, CharacterSpecializationValue
from world.traits.models import CharacterTraitValue, TraitType

# --- Tiny helpers for nested {id, name} representations ---


def _id_name(obj: Model, name_field: str = "name") -> IdNameRef:
    """Return ``{id, name}`` for a model instance."""
    return IdNameRef(id=obj.pk, name=getattr(obj, name_field))


def _id_name_or_null(obj: Model | None, name_field: str = "name") -> IdNameRef | None:
    """Return ``{id, name}`` or ``None`` when the FK is nullable."""
    if obj is None:
        return None
    return _id_name(obj, name_field)


# --- Shared prefetch constants (used by multiple builders) ---

_SHARED_PATH_HISTORY_PREFETCH = Prefetch(
    "character__path_history",
    queryset=CharacterPathHistory.objects.select_related("path").order_by("-selected_at"),
    to_attr="cached_path_history",
)

# --- Per-section prefetch declarations + builder functions ---

_CAN_EDIT_SELECT_RELATED: tuple[str, ...] = ()
_CAN_EDIT_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "tenures",
        queryset=RosterTenure.objects.select_related("player_data__account"),
        to_attr="cached_tenures",
    ),
)

_IDENTITY_SELECT_RELATED: tuple[str, ...] = (
    "character__sheet_data__gender",
    "character__sheet_data__species",
    "character__sheet_data__heritage",
    "character__sheet_data__family",
    "character__sheet_data__tarot_card",
    "character__sheet_data__origin_realm",
)
_IDENTITY_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (_SHARED_PATH_HISTORY_PREFETCH,)


def _build_identity(roster_entry: RosterEntry, sheet: CharacterSheet) -> IdentitySection:
    """Build the identity section dict from a RosterEntry + CharacterSheet."""
    character = roster_entry.character
    family = sheet.family

    # Compose fullname: "FirstName FamilyName" or just the db_key.
    if family is not None:
        fullname = f"{character.db_key} {family.name}"
    else:
        fullname = character.db_key

    # Latest path from prefetched path_history (ordered by -selected_at).
    path_history: list = character.cached_path_history
    if path_history:
        latest_path = path_history[0].path
        path_value: IdNameRef | None = _id_name(latest_path)
    else:
        path_value = None

    return IdentitySection(
        name=character.db_key,
        fullname=fullname,
        concept=sheet.concept,
        quote=sheet.quote,
        age=sheet.age,
        gender=_id_name_or_null(sheet.gender, name_field="display_name"),
        pronouns=PronounsData(
            subject=sheet.pronoun_subject,
            object=sheet.pronoun_object,
            possessive=sheet.pronoun_possessive,
        ),
        species=_id_name_or_null(sheet.species),
        heritage=_id_name_or_null(sheet.heritage),
        family=_id_name_or_null(family),
        tarot_card=_id_name_or_null(sheet.tarot_card),
        origin=_id_name_or_null(sheet.origin_realm),
        path=path_value,
    )


_APPEARANCE_SELECT_RELATED: tuple[str, ...] = ("character__sheet_data__build",)
_APPEARANCE_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__forms",
        queryset=CharacterForm.objects.filter(form_type=FormType.TRUE).prefetch_related(
            Prefetch(
                "values",
                queryset=CharacterFormValue.objects.select_related("trait", "option"),
                to_attr="cached_values",
            )
        ),
        to_attr="cached_true_forms",
    ),
)


def _build_appearance(roster_entry: RosterEntry, sheet: CharacterSheet) -> AppearanceSection:
    """Build the appearance section dict from a RosterEntry + CharacterSheet."""
    character = roster_entry.character

    # Get form traits from the TRUE form (prefetched + filtered via to_attr).
    true_forms: list[CharacterForm] = character.cached_true_forms
    if true_forms:
        true_form = true_forms[0]
        form_traits: list[FormTraitEntry] = [
            FormTraitEntry(trait=fv.trait.display_name, value=fv.option.display_name)
            for fv in true_form.cached_values
        ]
    else:
        form_traits = []

    return AppearanceSection(
        height_inches=sheet.true_height_inches,
        build=_id_name_or_null(sheet.build, name_field="display_name"),
        description=sheet.additional_desc,
        form_traits=form_traits,
    )


_STATS_SELECT_RELATED: tuple[str, ...] = ()
_STATS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__trait_values",
        queryset=CharacterTraitValue.objects.filter(
            trait__trait_type=TraitType.STAT
        ).select_related("trait"),
        to_attr="cached_trait_values",
    ),
)


def _build_stats(roster_entry: RosterEntry) -> dict[str, int]:
    """Build the stats section: a flat dict mapping stat name to value.

    The queryset is pre-filtered to stat-type traits via Prefetch in the viewset.
    """
    character = roster_entry.character
    return {tv.trait.name: tv.value for tv in character.cached_trait_values}


_SKILLS_SELECT_RELATED: tuple[str, ...] = ()
_SKILLS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__skill_values",
        queryset=CharacterSkillValue.objects.select_related("skill__trait"),
        to_attr="cached_skill_values",
    ),
    Prefetch(
        "character__specialization_values",
        queryset=CharacterSpecializationValue.objects.select_related("specialization"),
        to_attr="cached_specialization_values",
    ),
)


def _build_skills(roster_entry: RosterEntry) -> list[SkillEntry]:
    """Build the skills section: a list of skill entries with nested specializations."""
    character = roster_entry.character

    # Build a lookup of specialization values keyed by parent_skill_id
    spec_by_skill: dict[int, list[SpecializationEntry]] = {}
    for sv in character.cached_specialization_values:
        skill_id = sv.specialization.parent_skill_id
        spec_by_skill.setdefault(skill_id, []).append(
            SpecializationEntry(
                id=sv.specialization.pk, name=sv.specialization.name, value=sv.value
            )
        )

    result: list[SkillEntry] = []
    for csv in character.cached_skill_values:
        skill = csv.skill
        result.append(
            SkillEntry(
                skill=SkillRef(id=skill.pk, name=skill.name, category=skill.category),
                value=csv.value,
                specializations=spec_by_skill.get(skill.pk, []),
            )
        )
    return result


_PATH_DETAIL_SELECT_RELATED: tuple[str, ...] = ()
_PATH_DETAIL_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (_SHARED_PATH_HISTORY_PREFETCH,)


def _build_path_detail(roster_entry: RosterEntry) -> PathDetailSection | None:
    """Build the detailed path section with step, tier, and history.

    Returns ``None`` when no path history exists for the character.  The
    ``path_history`` queryset is expected to be prefetched and ordered by
    ``-selected_at`` (newest first) so that index 0 is the current path.
    """
    character = roster_entry.character
    path_history: list = character.cached_path_history
    if not path_history:
        return None

    current = path_history[0]
    current_path = current.path

    history_list: list[PathHistoryEntry] = [
        PathHistoryEntry(
            path=entry.path.name,
            stage=entry.path.stage,
            tier=PathStage(entry.path.stage).label,
            date=entry.selected_at.date().isoformat(),
        )
        for entry in path_history
    ]

    return PathDetailSection(
        id=current_path.pk,
        name=current_path.name,
        stage=current_path.stage,
        tier=PathStage(current_path.stage).label,
        history=history_list,
    )


_DISTINCTIONS_SELECT_RELATED: tuple[str, ...] = ()
_DISTINCTIONS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__distinctions",
        queryset=CharacterDistinction.objects.select_related("distinction"),
        to_attr="cached_distinctions",
    ),
)


def _build_distinctions(roster_entry: RosterEntry) -> list[DistinctionEntry]:
    """Build the distinctions section: a list of character distinction entries.

    Expects ``character.distinctions`` to be prefetched with
    ``select_related("distinction")``.
    """
    character = roster_entry.character
    return [
        DistinctionEntry(
            id=cd.pk,
            name=cd.distinction.name,
            rank=cd.rank,
            notes=cd.notes,
        )
        for cd in character.cached_distinctions
    ]


_MAGIC_SELECT_RELATED: tuple[str, ...] = (
    "character__aura",
    "character__sheet_data__anima_ritual__stat",
    "character__sheet_data__anima_ritual__skill__trait",
    "character__sheet_data__anima_ritual__resonance",
)
_MAGIC_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__sheet_data__character_gifts",
        queryset=CharacterGift.objects.select_related("gift").prefetch_related(
            Prefetch("gift__resonances", to_attr="cached_resonances")
        ),
        to_attr="cached_character_gifts",
    ),
    Prefetch(
        "character__sheet_data__character_techniques",
        queryset=CharacterTechnique.objects.select_related("technique__gift", "technique__style"),
        to_attr="cached_character_techniques",
    ),
    Prefetch(
        "character__sheet_data__motif__resonances",
        queryset=MotifResonance.objects.select_related("resonance").prefetch_related(
            Prefetch(
                "facet_assignments",
                queryset=MotifResonanceAssociation.objects.select_related("facet"),
                to_attr="cached_facet_assignments",
            )
        ),
        to_attr="cached_resonances",
    ),
)


def _build_magic_gifts(sheet: CharacterSheet) -> list[GiftEntry]:
    """Build the gifts sub-section of magic from prefetched CharacterGift data.

    Groups character techniques by gift and includes gift resonances.
    """
    # Build a lookup of techniques by gift_id from prefetched character_techniques
    techniques_by_gift: dict[int, list[TechniqueEntry]] = {}
    for ct in sheet.cached_character_techniques:
        tech = ct.technique
        techniques_by_gift.setdefault(tech.gift_id, []).append(
            TechniqueEntry(
                name=tech.name,
                level=tech.level,
                style=tech.style.name,
                description=tech.description,
            )
        )

    gifts: list[GiftEntry] = []
    for cg in sheet.cached_character_gifts:
        gift = cg.gift
        resonance_names = [r.name for r in gift.cached_resonances]
        gifts.append(
            GiftEntry(
                name=gift.name,
                description=gift.description,
                resonances=resonance_names,
                techniques=techniques_by_gift.get(gift.pk, []),
            )
        )
    return gifts


def _build_magic_motif(sheet: CharacterSheet) -> MotifSection | None:
    """Build the motif sub-section from the character's Motif (OneToOne).

    Returns ``None`` when the character has no motif.
    """
    try:
        motif = sheet.motif
    except Motif.DoesNotExist:
        return None

    resonances: list[MotifResonanceEntry] = []
    for mr in motif.cached_resonances:
        facet_names = [fa.facet.name for fa in mr.cached_facet_assignments]
        resonances.append(MotifResonanceEntry(name=mr.resonance.name, facets=facet_names))

    return MotifSection(description=motif.description, resonances=resonances)


def _build_magic_anima_ritual(sheet: CharacterSheet) -> AnimaRitualSection | None:
    """Build the anima ritual sub-section (OneToOne to CharacterSheet).

    Returns ``None`` when the character has no anima ritual.
    """
    try:
        ritual = sheet.anima_ritual
    except CharacterAnimaRitual.DoesNotExist:
        return None

    return AnimaRitualSection(
        stat=ritual.stat.name,
        skill=ritual.skill.name,
        resonance=ritual.resonance.name,
        description=ritual.description,
    )


def _build_magic_aura(character: Model) -> AuraData | None:
    """Build the aura sub-section (OneToOne to ObjectDB, not CharacterSheet).

    Returns ``None`` when the character has no aura.
    """
    try:
        aura = character.aura
    except CharacterAura.DoesNotExist:
        return None

    return AuraData(
        celestial=aura.celestial,
        primal=aura.primal,
        abyssal=aura.abyssal,
        glimpse_story=aura.glimpse_story,
    )


def _build_magic(roster_entry: RosterEntry) -> MagicSection | None:
    """Build the magic section with gifts, motif, anima ritual, and aura.

    Returns ``None`` when the character has no magic data at all (no gifts,
    no motif, no anima ritual, and no aura).
    """
    character = roster_entry.character
    sheet: CharacterSheet = character.sheet_data

    gifts = _build_magic_gifts(sheet)
    motif_data = _build_magic_motif(sheet)
    anima_ritual_data = _build_magic_anima_ritual(sheet)
    aura_data = _build_magic_aura(character)

    # Return None if no magic data exists at all
    if not gifts and motif_data is None and anima_ritual_data is None and aura_data is None:
        return None

    return MagicSection(
        gifts=gifts,
        motif=motif_data,
        anima_ritual=anima_ritual_data,
        aura=aura_data,
    )


_STORY_SELECT_RELATED: tuple[str, ...] = ()
_STORY_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()


def _build_story(sheet: CharacterSheet) -> StorySection:
    """Build the story section from CharacterSheet text fields."""
    return StorySection(
        background=sheet.background,
        personality=sheet.personality,
    )


_GOALS_SELECT_RELATED: tuple[str, ...] = ()
_GOALS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__goals",
        queryset=CharacterGoal.objects.select_related("domain"),
        to_attr="cached_goals",
    ),
)


def _build_goals(roster_entry: RosterEntry) -> list[GoalEntry]:
    """Build the goals section from prefetched CharacterGoal data."""
    character = roster_entry.character
    return [
        GoalEntry(
            domain=goal.domain.name,
            points=goal.points,
            notes=goal.notes,
        )
        for goal in character.cached_goals
    ]


_GUISES_SELECT_RELATED: tuple[str, ...] = ()
_GUISES_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__guises",
        queryset=Guise.objects.select_related("thumbnail"),
        to_attr="cached_guises",
    ),
)


def _build_guises(roster_entry: RosterEntry) -> list[GuiseEntry]:
    """Build the guises section from prefetched Guise data."""
    character = roster_entry.character
    return [
        GuiseEntry(
            id=guise.pk,
            name=guise.name,
            description=guise.description,
            thumbnail=guise.thumbnail.cloudinary_url if guise.thumbnail else None,
        )
        for guise in character.cached_guises
    ]


_THEMING_SELECT_RELATED: tuple[str, ...] = ("character__aura",)
_THEMING_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()


def _build_theming(roster_entry: RosterEntry) -> ThemingSection:
    """Build the theming section with aura percentages for frontend styling.

    Realm and species are already available in the identity section;
    the frontend can derive CSS classes from those IDs/names directly.
    """
    character = roster_entry.character

    aura_data: AuraThemingData | None = None
    try:
        aura = character.aura
        aura_data = AuraThemingData(
            celestial=aura.celestial,
            primal=aura.primal,
            abyssal=aura.abyssal,
        )
    except CharacterAura.DoesNotExist:
        pass

    return ThemingSection(aura=aura_data)


_PROFILE_PICTURE_SELECT_RELATED: tuple[str, ...] = ("profile_picture__media",)
_PROFILE_PICTURE_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()


def _build_profile_picture(roster_entry: RosterEntry) -> str | None:
    """Return the profile picture URL or ``None``.

    RosterEntry.profile_picture is a FK to TenureMedia, which in turn
    has a FK to PlayerMedia containing the ``cloudinary_url``.
    """
    profile_pic = roster_entry.profile_picture
    if profile_pic is None:
        return None
    return profile_pic.media.cloudinary_url


# --- Section registry for queryset aggregation ---

_ALL_SECTIONS: tuple[tuple[tuple[str, ...], tuple[str | Prefetch, ...]], ...] = (
    (_CAN_EDIT_SELECT_RELATED, _CAN_EDIT_PREFETCH_RELATED),
    (_IDENTITY_SELECT_RELATED, _IDENTITY_PREFETCH_RELATED),
    (_APPEARANCE_SELECT_RELATED, _APPEARANCE_PREFETCH_RELATED),
    (_STATS_SELECT_RELATED, _STATS_PREFETCH_RELATED),
    (_SKILLS_SELECT_RELATED, _SKILLS_PREFETCH_RELATED),
    (_PATH_DETAIL_SELECT_RELATED, _PATH_DETAIL_PREFETCH_RELATED),
    (_DISTINCTIONS_SELECT_RELATED, _DISTINCTIONS_PREFETCH_RELATED),
    (_MAGIC_SELECT_RELATED, _MAGIC_PREFETCH_RELATED),
    (_STORY_SELECT_RELATED, _STORY_PREFETCH_RELATED),
    (_GOALS_SELECT_RELATED, _GOALS_PREFETCH_RELATED),
    (_GUISES_SELECT_RELATED, _GUISES_PREFETCH_RELATED),
    (_THEMING_SELECT_RELATED, _THEMING_PREFETCH_RELATED),
    (_PROFILE_PICTURE_SELECT_RELATED, _PROFILE_PICTURE_PREFETCH_RELATED),
)


def get_character_sheet_queryset() -> QuerySet[RosterEntry]:
    """Build the optimized queryset aggregating all section prefetch declarations.

    Each section declares its own ``select_related`` and ``prefetch_related``
    needs.  This function deduplicates them and returns a single queryset
    that satisfies every builder.
    """
    seen_select: set[str] = set()
    all_select: list[str] = []
    seen_prefetch: set[str] = set()
    all_prefetch: list[str | Prefetch] = []

    for select_related, prefetch_related in _ALL_SECTIONS:
        for sr in select_related:
            if sr not in seen_select:
                seen_select.add(sr)
                all_select.append(sr)
        for pr in prefetch_related:
            key = pr.prefetch_through if isinstance(pr, Prefetch) else pr
            if key not in seen_prefetch:
                seen_prefetch.add(key)
                all_prefetch.append(pr)

    return RosterEntry.objects.select_related(
        "character", "character__sheet_data", *all_select
    ).prefetch_related(*all_prefetch)


class CharacterSheetSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for character sheet data, looked up via RosterEntry.

    Returns a `can_edit` boolean indicating whether the requesting user
    is the original creator (player_number=1) or a staff member.
    """

    can_edit = serializers.SerializerMethodField()
    identity = serializers.SerializerMethodField()
    appearance = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    distinctions = serializers.SerializerMethodField()
    magic = serializers.SerializerMethodField()
    story = serializers.SerializerMethodField()
    goals = serializers.SerializerMethodField()
    guises = serializers.SerializerMethodField()
    theming = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = [
            "id",
            "can_edit",
            "identity",
            "appearance",
            "stats",
            "skills",
            "path",
            "distinctions",
            "magic",
            "story",
            "goals",
            "guises",
            "theming",
            "profile_picture",
        ]

    def get_can_edit(self, obj: RosterEntry) -> bool:
        """True if the requesting user is the original account or staff."""
        request: Request | None = self.context.get("request")
        if request is None:
            return False
        return can_edit_character_sheet(request.user, obj)

    def get_identity(self, obj: RosterEntry) -> IdentitySection:
        """Return the identity section of the character sheet."""
        sheet: CharacterSheet = obj.character.sheet_data
        return _build_identity(obj, sheet)

    def get_appearance(self, obj: RosterEntry) -> AppearanceSection:
        """Return the appearance section of the character sheet."""
        sheet: CharacterSheet = obj.character.sheet_data
        return _build_appearance(obj, sheet)

    def get_stats(self, obj: RosterEntry) -> dict[str, int]:
        """Return the stats section of the character sheet."""
        return _build_stats(obj)

    def get_skills(self, obj: RosterEntry) -> list[SkillEntry]:
        """Return the skills section of the character sheet."""
        return _build_skills(obj)

    def get_path(self, obj: RosterEntry) -> PathDetailSection | None:
        """Return the detailed path section of the character sheet."""
        return _build_path_detail(obj)

    def get_distinctions(self, obj: RosterEntry) -> list[DistinctionEntry]:
        """Return the distinctions section of the character sheet."""
        return _build_distinctions(obj)

    def get_magic(self, obj: RosterEntry) -> MagicSection | None:
        """Return the magic section of the character sheet."""
        return _build_magic(obj)

    def get_story(self, obj: RosterEntry) -> StorySection:
        """Return the story section of the character sheet."""
        sheet: CharacterSheet = obj.character.sheet_data
        return _build_story(sheet)

    def get_goals(self, obj: RosterEntry) -> list[GoalEntry]:
        """Return the goals section of the character sheet."""
        return _build_goals(obj)

    def get_guises(self, obj: RosterEntry) -> list[GuiseEntry]:
        """Return the guises section of the character sheet."""
        return _build_guises(obj)

    def get_theming(self, obj: RosterEntry) -> ThemingSection:
        """Return the theming section of the character sheet."""
        return _build_theming(obj)

    def get_profile_picture(self, obj: RosterEntry) -> str | None:
        """Return the profile picture URL or null."""
        return _build_profile_picture(obj)
