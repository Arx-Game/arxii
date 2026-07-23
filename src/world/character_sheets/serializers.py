"""
Serializers for the character sheets API.

NOTE: This endpoint currently serves the full character sheet as a single
response.  The builder architecture (per-section prefetch declarations +
builder functions) naturally supports splitting into per-section endpoints
in the future when the frontend needs it.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model, QuerySet
from django.db.models.query import Prefetch
from evennia.objects.models import ObjectDB
from rest_framework import serializers
from rest_framework.request import Request

from world.character_creation.models import CharacterOriginSlot
from world.character_sheets.models import CharacterSheet, Profile, ProfileTextVersion
from world.character_sheets.services import can_edit_character_sheet
from world.character_sheets.types import (
    SHEET_VISIBILITY_RANK,
    AnimaRitualSection,
    AppearanceSection,
    AuraData,
    AuraThemingData,
    DistinctionEntry,
    FormTraitEntry,
    GiftEntry,
    GlimpseTagEntry,
    GoalEntry,
    IdentitySection,
    IdNameRef,
    MagicSection,
    MotifResonanceEntry,
    MotifSection,
    OriginSlotEntry,
    PathDetailSection,
    PathHistoryEntry,
    PersonaEntry,
    PronounsData,
    ResonanceBalanceEntry,
    SheetVisibility,
    SkillEntry,
    SkillRef,
    SpecializationEntry,
    StorySection,
    TechniqueEntry,
    ThemingSection,
)
from world.classes.models import PathStage
from world.conditions.models import ConditionInstance
from world.distinctions.models import CharacterDistinction
from world.forms.models import (
    CharacterForm,
    CharacterFormValue,
    FormType,
    PersonaTraitDescriptor,
)
from world.goals.models import CharacterGoal
from world.magic.constants import GlimpseState, RitualExecutionKind
from world.magic.models import (
    CharacterAura,
    CharacterGift,
    CharacterGlimpseTag,
    CharacterTechnique,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    MotifResonanceStyle,
    Ritual,
)
from world.progression.models import CharacterPathHistory
from world.roster.models import RosterTenure
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.skills.models import CharacterSkillValue, CharacterSpecializationValue
from world.skills.services import is_skill_at_xp_boundary
from world.traits.models import CharacterTraitValue, TraitType


class OriginSlotInputSerializer(serializers.Serializer):
    """Input for CharacterSheetViewSet.set-origin-slot (#2478)."""

    slot_id = serializers.IntegerField()
    value = serializers.CharField(allow_blank=True)


class OriginSlotClearSerializer(serializers.Serializer):
    """Input for CharacterSheetViewSet.clear-origin-slot (#2478)."""

    slot_id = serializers.IntegerField()


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
    "path_history",
    queryset=CharacterPathHistory.objects.select_related("path").order_by("-selected_at"),
    to_attr="cached_path_history",
)

# --- Per-section prefetch declarations + builder functions ---

_CAN_EDIT_SELECT_RELATED: tuple[str, ...] = ("roster_entry",)
_CAN_EDIT_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "roster_entry__tenures",
        queryset=RosterTenure.objects.select_related("player_data__account").order_by(
            "-start_date"
        ),
        to_attr="cached_tenures",
    ),
)

_IDENTITY_SELECT_RELATED: tuple[str, ...] = (
    "gender",
    "species",
    # #1270 — concept/quote + lineage (heritage/family/tarot/origin) now read through the
    # presented face's profile; the revealed case reads them off true_profile.
    "true_profile",
    "true_profile__heritage",
    "true_profile__family",
    "true_profile__tarot_card",
    "true_profile__origin_realm",
    # #2355 — public worship on the identity section (reverse OneToOne + its being).
    "worship_declaration__public_being",
)
_IDENTITY_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (_SHARED_PATH_HISTORY_PREFETCH,)


def _build_identity(
    sheet: CharacterSheet,
    *,
    display_name: str | None = None,
    reveal_identity: bool = True,
    bio_profile: Profile | None = None,
) -> IdentitySection:
    """Build the identity section (#1109/#1270-aware).

    ``display_name`` is the name resolved for the viewer (the presented persona / sdesc / reveal);
    defaults to the character's key. ``bio_profile`` is the **presented face's** bio (#1270): the
    real ``true_profile`` for a revealed identity, a cover persona's own (fabricated) profile when
    presenting an anonymous face that has authored one, or None (concept/quote blank). When
    ``reveal_identity`` is False — a non-privileged viewer of an anonymous face — the **real
    fullname** and **path** are withheld, but the presented face's own concept/quote AND lineage
    (#1270 slice 3: a cover persona's *fabricated* family/heritage/tarot/origin) DO show, so a
    cover identity reads as a real person. A non-revealed face with no cover profile shows none.
    """
    character = sheet.character
    name = display_name if display_name is not None else character.db_key
    concept = bio_profile.concept if bio_profile is not None else ""
    quote = bio_profile.quote if bio_profile is not None else ""

    # Lineage follows the presented bio profile (#1270 slice 3): a revealed viewer gets the real
    # lineage (bio_profile is true_profile); an outsider viewing a cover gets the cover's
    # fabricated lineage; an anonymous face with no cover profile gets none.
    family = bio_profile.family if bio_profile is not None else None
    heritage = _id_name_or_null(bio_profile.heritage) if bio_profile is not None else None
    tarot_card = _id_name_or_null(bio_profile.tarot_card) if bio_profile is not None else None
    origin = _id_name_or_null(bio_profile.origin_realm) if bio_profile is not None else None

    pronouns = PronounsData(
        subject=sheet.pronoun_subject,
        object=sheet.pronoun_object,
        possessive=sheet.pronoun_possessive,
    )

    if not reveal_identity:
        # The presented (mask/cover) name is already resolved; never compose the real db_key
        # with a family name here, and withhold the real progression path.
        fullname = name
        path_value: IdNameRef | None = None
    else:
        # Compose the real fullname: "FirstName FamilyName" or just the db_key.
        fullname = f"{character.db_key} {family.name}" if family is not None else character.db_key
        # Latest path from prefetched path_history (ordered by -selected_at).
        path_history: list = sheet.cached_path_history
        path_value = _id_name(path_history[0].path) if path_history else None

    # Public worship only (#2355) — the secret side never leaves owner surfaces.
    try:
        worship = _id_name_or_null(sheet.worship_declaration.public_being)
    except ObjectDoesNotExist:
        worship = None

    return IdentitySection(
        name=name,
        fullname=fullname,
        concept=concept,
        quote=quote,
        age=sheet.age,
        gender=_id_name_or_null(sheet.gender, name_field="display_name"),
        pronouns=pronouns,
        species=_id_name_or_null(sheet.species),
        heritage=heritage,
        family=_id_name_or_null(family),
        tarot_card=tarot_card,
        origin=origin,
        path=path_value,
        worship=worship,
    )


_APPEARANCE_SELECT_RELATED: tuple[str, ...] = ("build",)
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
    "character__form_state__active_fake_overlay",
)


def _resolve_active_persona(sheet: CharacterSheet) -> Persona | None:
    """The presented face, resolved from prefetched ``cached_personas`` (0 queries).

    Mirrors ``scenes.services.active_persona_for_sheet`` (the ``active_persona`` FK,
    else the PRIMARY persona) but reads the prefetch so the builder stays query-free.
    """
    personas: list[Persona] = sheet.cached_personas
    active_id = sheet.active_persona_id
    if active_id is not None:
        return next((p for p in personas if p.pk == active_id), None)
    return next((p for p in personas if p.persona_type == PersonaType.PRIMARY), None)


def _presented_bio_profile(
    sheet: CharacterSheet, active: Persona | None, *, reveal_identity: bool
) -> Profile | None:
    """The bio (concept/quote/story) source for the presented face (#1270).

    - **Revealed** (owner/staff/primary-public/discovered) → the real ``true_profile``.
    - **Anonymous face with its own authored cover profile** → that cover profile (a fabricated
      bio shown as if real, so the cover doesn't out itself with an empty one).
    - **Anonymous face with no cover profile** → None (concept/quote/story blank). Never the real
      ``true_profile`` for a non-revealed face — that would de-anonymize.
    """
    if reveal_identity:
        return sheet.true_profile
    if (
        active is not None
        and active.profile_id is not None
        and active.profile_id != sheet.true_profile_id
    ):
        return active.profile
    return None


def _viewer_is_privileged(sheet: CharacterSheet, user: Any) -> bool:
    """Staff, or the viewer's account currently plays this character (#1109).

    Query-free: reads the prefetched ``cached_tenures`` (via ``current_tenure``).
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    roster_entry = sheet.roster_entry
    if roster_entry is None:
        return False
    current = roster_entry.current_tenure
    return current is not None and current.player_data.account_id == user.pk


def _viewer_access_level(sheet: CharacterSheet, user: Any, privileged: bool) -> int:
    """The viewer's section-visibility openness (#1271): 2=SELF, 1=FRIENDS, 0=PUBLIC.

    Privileged (owner/staff) see everything. The FRIENDS check (is the viewer's account on
    the sheet owner's ``PlayerAllowList``) runs at most once, and only when a section is
    actually gated to FRIENDS — so the common all-default (SELF) case adds no query.
    """
    if privileged:
        return 2
    if user is None or not user.is_authenticated:
        return 0
    gated = (
        sheet.stats_visibility,
        sheet.skills_visibility,
        sheet.magic_visibility,
        sheet.goals_visibility,
    )
    if SheetVisibility.FRIENDS not in gated:
        return 0  # nothing is FRIENDS-gated → no need to resolve the allow list
    roster_entry = sheet.roster_entry
    current = roster_entry.current_tenure if roster_entry is not None else None
    if current is None:
        return 0

    from evennia_extensions.models import PlayerAllowList  # noqa: PLC0415

    is_friend = PlayerAllowList.objects.filter(
        owner=current.player_data, allowed_player__account_id=user.pk
    ).exists()
    return 1 if is_friend else 0


def _section_visible(access: int, visibility: str) -> bool:
    """Whether a viewer at ``access`` openness may see a section with this tier (#1271)."""
    return access >= SHEET_VISIBILITY_RANK[visibility]


def _resolve_presented_identity(
    sheet: CharacterSheet, active: Persona | None, user: Any, privileged: bool
) -> tuple[str, bool]:
    """``(display_name, reveal_identity)`` for the presented face, per viewer (#1109).

    ``reveal_identity`` gates the character's real name / bio. It is shown to the owner / staff,
    for the PRIMARY public face, and to a viewer who has discovered an anonymous face's link. A
    named alt (hidden link) or an undiscovered mask keeps the character's primary identity hidden.
    The discovery lookup happens only in the anonymous-and-non-privileged branch (one query).
    """
    if active is None:
        return sheet.character.db_key, True
    if privileged:
        # The owner / staff always know who this is; when they're looking at a non-primary
        # face, append the real (primary) identity in parens so it's never ambiguous which
        # character a presented alt or mask belongs to — the same reason a GM needs it.
        if active.persona_type != PersonaType.PRIMARY:
            primary = next(
                (p for p in sheet.cached_personas if p.persona_type == PersonaType.PRIMARY), None
            )
            if primary is not None and primary.pk != active.pk:
                return f"{active.name} ({primary.name})", True
        return active.name, True
    if not active.is_fake_name:
        # Named face: render its own name; reveal the character bio only for the PRIMARY (the
        # main public identity). A named ESTABLISHED alt keeps its link to the primary hidden.
        return active.name, active.persona_type == PersonaType.PRIMARY

    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.persona_display import resolve_display_for_viewer  # noqa: PLC0415

    viewer_sheet_ids: set[int] = set()
    if user is not None and user.is_authenticated:
        viewer_sheet_ids = set(
            RosterEntry.objects.for_account(user).values_list("character_sheet_id", flat=True)
        )
    return resolve_display_for_viewer(
        active,
        viewer_persona_ids=set(),
        viewer_sheet_ids=viewer_sheet_ids,
        is_staff=bool(user and user.is_staff),
    )


def _build_appearance(
    sheet: CharacterSheet, *, reveal_identity: bool, privileged: bool
) -> AppearanceSection:
    """Build the appearance section: normalized TRUE-form traits overlaid with the
    active persona's descriptors (descriptor, else normalized) — mirroring the telnet
    ``item_data`` composition.

    Identity gating (#1325):

    - **Exact ``height_inches`` is owner/staff-only** (``privileged``). Every other
      observer — including a stranger viewing the real public face — sees ``None`` and
      reads only the coarse ``height_band`` (you can tell someone is tall by looking, but
      not their precise inches, and two faces of one character can't be matched on it).
    - **Free-text ``description`` shows only when ``reveal_identity``.** A mask must not
      leak prose that names height, scars, or hair ("a tall auburn-haired woman…").
    - ``form_traits`` already reduce to the generic option name unless the *presented*
      persona supplies a descriptor (a base mask shows "red", not "flowing crimson"); a
      richer disguise overlay supplying its own descriptors is the disguise system's job.

    Disguise concealment (#1272): when a non-privileged viewer sees a face wearing a
    disguise overlay, the overlay's ``concealment_level`` controls what shows:
    - ``NONE``: the overlay's traits + descriptors (the existing overlay behavior).
    - ``DESCRIPTOR``: the overlay's normalized values, descriptors hidden.
    - ``FULL``: no traits at all — an empty list.

    One query (the ``HeightBand`` range lookup); otherwise reads prefetched forms + personas.
    """
    from world.forms.models import ConcealmentLevel  # noqa: PLC0415
    from world.forms.services import get_height_band  # noqa: PLC0415

    character = sheet.character

    active = _resolve_active_persona(sheet)
    descriptors: dict[int, str] = (
        {d.trait_id: d.text for d in active.cached_trait_descriptors} if active is not None else {}
    )

    true_forms: list[CharacterForm] = character.cached_true_forms
    if true_forms:
        form_traits: list[FormTraitEntry] = [
            FormTraitEntry(
                trait=fv.trait.display_name,
                value=descriptors.get(fv.trait_id) or fv.option.display_name,
            )
            for fv in true_forms[0].cached_values
        ]
    else:
        form_traits = []

    # Disguise concealment (#1272): a non-privileged viewer of a disguised face sees
    # the overlay's traits (not the real form's), filtered by the overlay's level.
    # Gated on ``privileged`` only — a disguise overlay can be active even when the
    # presented face is the primary persona (reveal_identity=True for a public face).
    form_state = character.form_state_or_none
    if not privileged and form_state is not None and form_state.active_fake_overlay_id is not None:
        overlay = form_state.active_fake_overlay
        if overlay.concealment_level == ConcealmentLevel.FULL:
            form_traits = []
        else:
            # DESCRIPTOR and NONE both show the overlay's traits; DESCRIPTOR hides
            # the descriptor (shows only the normalized value).
            show_descriptors = overlay.concealment_level == ConcealmentLevel.NONE
            overlay_values = overlay.values.select_related("trait", "option").order_by(
                "trait__sort_order"
            )
            form_traits = [
                FormTraitEntry(
                    trait=v.trait.display_name,
                    value=(
                        descriptors.get(v.trait_id) or v.option.display_name
                        if show_descriptors
                        else v.option.display_name
                    ),
                )
                for v in overlay_values
            ]

    true_height = sheet.true_height_inches
    band = get_height_band(true_height) if true_height is not None else None

    return AppearanceSection(
        height_inches=true_height if privileged else None,
        height_band=band.display_name if band is not None else None,
        build=_id_name_or_null(sheet.build, name_field="display_name"),
        description=sheet.additional_desc if reveal_identity else "",
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


def _build_stats(sheet: CharacterSheet) -> dict[str, int]:
    """Build the stats section: a flat dict mapping stat name to value.

    The queryset is pre-filtered to stat-type traits via Prefetch in the viewset.
    """
    character = sheet.character
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


def _build_skills(sheet: CharacterSheet) -> list[SkillEntry]:
    """Build the skills section: a list of skill entries with nested specializations."""
    character = sheet.character

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
                at_boundary=is_skill_at_xp_boundary(csv.value),
                specializations=spec_by_skill.get(skill.pk, []),
            )
        )
    return result


_PATH_DETAIL_SELECT_RELATED: tuple[str, ...] = ()
_PATH_DETAIL_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (_SHARED_PATH_HISTORY_PREFETCH,)


def _build_path_detail(sheet: CharacterSheet) -> PathDetailSection | None:
    """Build the detailed path section with step, tier, and history.

    Returns ``None`` when no path history exists for the character.  The
    ``path_history`` queryset is expected to be prefetched and ordered by
    ``-selected_at`` (newest first) so that index 0 is the current path.
    """
    path_history: list = sheet.cached_path_history
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
        "distinctions",
        queryset=CharacterDistinction.objects.select_related("distinction"),
        to_attr="cached_distinctions",
    ),
)


def _build_distinctions(sheet: CharacterSheet, *, privileged: bool) -> list[DistinctionEntry]:
    """Build the distinctions section: the character's *public* distinctions (#1334).

    Sensitive distinctions are *relocated* into Secrets (criminal / scandalous kinds, or a
    player-gated one): they drop off this public list and surface on the secret tab once learned.
    A non-privileged viewer sees only the non-secret entries; the owner / staff see all, with
    ``is_secret`` flagging which are gated. Expects ``sheet.distinctions`` prefetched with
    ``select_related("distinction")`` so the secret state resolves query-free.
    """
    return [
        DistinctionEntry(
            id=cd.pk,
            name=cd.distinction.name,
            rank=cd.rank,
            notes=cd.notes,
            is_secret=cd.is_secret,
            is_from_glimpse=cd.from_glimpse_id is not None,
        )
        for cd in sheet.cached_distinctions
        if privileged or not cd.is_secret
    ]


_MAGIC_SELECT_RELATED: tuple[str, ...] = ("character__aura",)
_MAGIC_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "character__db_account__authored_rituals",
        queryset=Ritual.objects.filter(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).select_related(
            "check_config__stat",
            "check_config__skill",
            "check_config__resonance",
        ),
        to_attr="cached_scene_action_rituals",
    ),
    Prefetch(
        "character_gifts",
        queryset=CharacterGift.objects.select_related("gift").prefetch_related(
            Prefetch("gift__resonances", to_attr="cached_resonances")
        ),
        to_attr="cached_character_gifts",
    ),
    Prefetch(
        "character_techniques",
        queryset=CharacterTechnique.objects.select_related("technique__gift", "technique__style"),
        to_attr="cached_character_techniques",
    ),
    Prefetch(
        "motif__resonances",
        queryset=MotifResonance.objects.select_related("resonance").prefetch_related(
            Prefetch(
                "facet_assignments",
                queryset=MotifResonanceAssociation.objects.select_related("facet"),
                to_attr="cached_facet_assignments",
            ),
            Prefetch(
                "style_assignments",
                queryset=MotifResonanceStyle.objects.select_related("style"),
                to_attr="cached_style_assignments",
            ),
        ),
        to_attr="cached_resonances",
    ),
    Prefetch(
        "character__aura__glimpse_tags",
        queryset=CharacterGlimpseTag.objects.select_related("tag"),
        to_attr="cached_glimpse_tags",
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
        style_names = [sa.style.name for sa in mr.cached_style_assignments]
        resonances.append(
            MotifResonanceEntry(name=mr.resonance.name, facets=facet_names, styles=style_names)
        )

    return MotifSection(description=motif.description, resonances=resonances)


def _build_magic_anima_ritual(sheet: CharacterSheet) -> AnimaRitualSection | None:
    """Build the anima ritual sub-section from the player's authored SCENE_ACTION Ritual.

    Reads from the prefetched ``cached_scene_action_rituals`` attribute on the
    account object, populated by the ``character__db_account__authored_rituals``
    Prefetch in ``_MAGIC_PREFETCH_RELATED``. Returns ``None`` when the character
    has no authored anima ritual or no account attached.
    """
    account = sheet.character.db_account
    if account is None:
        return None

    rituals: list[Ritual] = getattr(
        account,
        # Suppression justified: mutating prefetch on identity-mapped parent; context-over-cache
        # (#2401).
        "cached_scene_action_rituals",  # noqa: GETATTR_LITERAL
        None,
    )
    if not rituals:
        return None

    ritual = rituals[0]
    config = ritual.check_config_or_none
    if config is None:
        return None

    return AnimaRitualSection(
        stat=config.stat.name,
        skill=config.skill.name,
        resonance=config.resonance.name if config.resonance else "",
        description=ritual.description,
    )


def _build_magic_aura(character: ObjectDB, *, privileged: bool) -> AuraData | None:
    """Build the aura sub-section (OneToOne to ObjectDB, not CharacterSheet).

    Returns ``None`` when the character has no aura. Glimpse tags share the
    prose's visibility (the whole section is already tier-gated); only the
    ``can_finish_glimpse`` affordance is privileged-only (#2427).
    """
    try:
        aura = character.aura
    except CharacterAura.DoesNotExist:
        return None

    tag_rows: list[CharacterGlimpseTag] = getattr(
        aura,
        # Suppression justified: mutating prefetch on identity-mapped parent; context-over-cache
        # (#2401).
        "cached_glimpse_tags",  # noqa: GETATTR_LITERAL
        None,
    )
    if tag_rows is None:
        tag_rows = aura.glimpse_tags.select_related("tag")
    return AuraData(
        id=aura.pk,
        celestial=aura.celestial,
        primal=aura.primal,
        abyssal=aura.abyssal,
        glimpse_story=aura.glimpse_story,
        glimpse_state=aura.glimpse_state,
        glimpse_tags=[
            GlimpseTagEntry(
                id=row.tag.pk,
                axis=row.tag.axis,
                name=row.tag.name,
                description=row.tag.description,
            )
            for row in tag_rows
        ],
        can_finish_glimpse=privileged and aura.glimpse_state != GlimpseState.COMPLETE,
    )


def _build_magic_resonances(character: ObjectDB) -> list[ResonanceBalanceEntry]:
    """Build the claimed-resonance balances sub-section (#2032).

    Reads the character's cached ``resonances`` handler (``CharacterResonanceHandler``,
    ``typeclasses.characters.Character.resonances``) rather than issuing a fresh
    query — the same identity-mapped source every other resonance-balance reader
    (thread pulls, imbuing, sanctum) uses. Sorted by name for stable rendering.
    """
    entries = [
        ResonanceBalanceEntry(
            name=cr.resonance.name,
            balance=cr.balance,
            lifetime_earned=cr.lifetime_earned,
        )
        for cr in character.resonances.all()
    ]
    entries.sort(key=lambda entry: entry["name"])
    return entries


def _build_magic(sheet: CharacterSheet, *, privileged: bool = False) -> MagicSection | None:
    """Build the magic section with gifts, motif, anima ritual, aura, and resonances.

    Returns ``None`` when the character has no magic data at all (no gifts,
    no motif, no anima ritual, no aura, and no claimed resonances).
    """
    character = sheet.character

    gifts = _build_magic_gifts(sheet)
    motif_data = _build_magic_motif(sheet)
    anima_ritual_data = _build_magic_anima_ritual(sheet)
    aura_data = _build_magic_aura(character, privileged=privileged)
    resonances = _build_magic_resonances(character)

    # Return None if no magic data exists at all
    if (
        not gifts
        and motif_data is None
        and anima_ritual_data is None
        and aura_data is None
        and not resonances
    ):
        return None

    return MagicSection(
        gifts=gifts,
        motif=motif_data,
        anima_ritual=anima_ritual_data,
        aura=aura_data,
        resonances=resonances,
    )


_STORY_SELECT_RELATED: tuple[str, ...] = ("true_profile",)  # #1270 — background/personality
_STORY_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "origin_slots",
        queryset=CharacterOriginSlot.objects.select_related("slot"),
        to_attr="cached_origin_slots",
    ),
)


def _build_story(*, sheet: CharacterSheet, bio_profile: Profile | None = None) -> StorySection:
    """Build the story section from the presented face's bio profile (#1270).

    ``bio_profile`` is the real ``true_profile`` for a revealed identity, a cover persona's own
    (fabricated) profile when presenting one, or None (empty story) — so a cover shows its own
    story and a bare anonymous figure shows nothing.
    """
    if bio_profile is None:
        return StorySection(
            background="",
            personality="",
            origin_story_state=sheet.origin_story_state,
            origin_slots=[],
        )
    # Origin-story slot answers are always the real sheet's (#2478) — a cover
    # identity doesn't get its own origin story. Uses the prefetched attr when
    # available (serializer path); falls back to a live query only when called
    # directly (e.g. unit tests without the prefetch set up).
    raw_slots = (
        sheet.cached_origin_slots
        if hasattr(sheet, "cached_origin_slots")
        else sheet.origin_slots.select_related("slot")
    )
    origin_slots = [
        OriginSlotEntry(
            slot_id=row.slot_id,
            slot_name=row.slot.name,
            slot_prompt=row.slot.prompt,
            value=row.value,
        )
        for row in raw_slots
    ]
    return StorySection(
        background=bio_profile.background,
        personality=bio_profile.personality,
        origin_story_state=sheet.origin_story_state,
        origin_slots=origin_slots,
    )


_GOALS_SELECT_RELATED: tuple[str, ...] = ()
_GOALS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "goals",
        queryset=CharacterGoal.objects.select_related("domain"),
        to_attr="cached_goals",
    ),
)


def _build_goals(sheet: CharacterSheet) -> list[GoalEntry]:
    """Build the goals section from prefetched CharacterGoal data."""
    return [
        GoalEntry(
            domain=goal.domain.name,
            points=goal.points,
            notes=goal.notes,
        )
        for goal in sheet.cached_goals
    ]


_PERSONAS_SELECT_RELATED: tuple[str, ...] = ()
_PERSONAS_PREFETCH_RELATED: tuple[str | Prefetch, ...] = (
    Prefetch(
        "personas",
        queryset=Persona.objects.select_related(
            "thumbnail",
            # #1270 — a cover persona presents its own profile's bio + lineage; pull the
            # lineage FKs so the identity builder reads them without extra queries.
            "profile",
            "profile__heritage",
            "profile__family",
            "profile__tarot_card",
            "profile__origin_realm",
        ).prefetch_related(
            # Each persona's per-trait descriptors, so the appearance builder can
            # overlay the active face's descriptors at zero extra queries.
            Prefetch(
                "trait_descriptors",
                queryset=PersonaTraitDescriptor.objects.select_related("trait"),
                to_attr="cached_trait_descriptors",
            )
        ),
        to_attr="cached_personas",
    ),
)


def _resolve_persona_thumbnail(
    persona,
    cached_conditions=None,
) -> str | None:
    """Resolve a persona's thumbnail dynamically (#2196).

    Uses ``resolve_thumbnail()`` to check condition/alt-self overrides.
    Falls back to the persona's own thumbnail when the character can't
    be resolved (edge case for detached personas).

    Args:
        persona: The persona to resolve a thumbnail for.
        cached_conditions: Prefetched active conditions for the character
            (avoids N+1 when iterating multiple personas). When None,
            ``resolve_thumbnail`` queries fresh.
    """
    from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

    try:
        character = persona.character_sheet.character
    except AttributeError:
        return persona.thumbnail.cloudinary_url if persona.thumbnail_id else None
    return resolve_thumbnail(
        character,
        persona=persona,
        cached_conditions=cached_conditions,
    )


def _build_personas(
    sheet: CharacterSheet,
    *,
    privileged: bool = True,
    active: Persona | None = None,
    active_display_name: str | None = None,
    active_revealed: bool = True,
) -> list[PersonaEntry]:
    """Build the personas section (#1109-aware).

    The full list links every face of the character — a de-anonymization vector — so only the
    owner / staff get it. A non-privileged viewer sees only the *presented* (active) persona,
    rendered with the name already resolved for them; a not-revealed face (anonymous-undiscovered
    or a hidden-link alt) exposes just that name, with no description or thumbnail.
    """
    if privileged:
        # #2196: use prefetched conditions from the character (avoids N+1 per persona).
        # Suppression justified: mutating prefetch on identity-mapped parent; context-over-cache
        # (#2401).
        cached_conditions = getattr(sheet.character, "cached_active_conditions", None)  # noqa: GETATTR_LITERAL
        return [
            PersonaEntry(
                id=persona.pk,
                name=persona.name,
                thumbnail=_resolve_persona_thumbnail(persona, cached_conditions=cached_conditions),
            )
            for persona in sheet.cached_personas
        ]

    if active is None:
        return []
    return [
        PersonaEntry(
            id=active.pk,
            name=active_display_name if active_display_name is not None else active.name,
            thumbnail=(_resolve_persona_thumbnail(active) if active_revealed else None),
        )
    ]


_THEMING_SELECT_RELATED: tuple[str, ...] = ("character__aura",)
_THEMING_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()


def _build_theming(sheet: CharacterSheet) -> ThemingSection:
    """Build the theming section with aura percentages for frontend styling.

    Realm and species are already available in the identity section;
    the frontend can derive CSS classes from those IDs/names directly.
    """
    character = sheet.character

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


_PROFILE_PICTURE_SELECT_RELATED: tuple[str, ...] = ("roster_entry__profile_picture__media",)
_PROFILE_PICTURE_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()

_CURRENT_RESIDENCE_SELECT_RELATED: tuple[str, ...] = ("current_residence__objectdb",)
_CURRENT_RESIDENCE_PREFETCH_RELATED: tuple[str | Prefetch, ...] = ()


def _build_profile_picture(sheet: CharacterSheet) -> str | None:
    """Return the profile picture URL or ``None``.

    RosterEntry.profile_picture is a FK to TenureMedia, which in turn
    has a FK to Media containing the ``cloudinary_url``.
    """
    roster_entry = sheet.roster_entry
    profile_pic = roster_entry.profile_picture
    if profile_pic is None:
        return None
    return profile_pic.media.cloudinary_url


def _build_current_residence(sheet: CharacterSheet) -> IdNameRef | None:
    """Build the current_residence field: ``{id, name}`` or ``None``.

    Returns ``None`` when no residence is set. The room name is read from
    the linked ObjectDB (RoomProfile.objectdb.db_key).
    """
    rp = sheet.current_residence
    if rp is None:
        return None
    return IdNameRef(id=rp.pk, name=rp.objectdb.db_key)


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
    (_PERSONAS_SELECT_RELATED, _PERSONAS_PREFETCH_RELATED),
    (_THEMING_SELECT_RELATED, _THEMING_PREFETCH_RELATED),
    (_PROFILE_PICTURE_SELECT_RELATED, _PROFILE_PICTURE_PREFETCH_RELATED),
    (_CURRENT_RESIDENCE_SELECT_RELATED, _CURRENT_RESIDENCE_PREFETCH_RELATED),
)


def get_character_sheet_queryset() -> QuerySet[CharacterSheet]:
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

    return (
        CharacterSheet.objects.select_related(
            "character",
            *all_select,
            # #2196: prefetch the character's display data and active alternate
            # self so resolve_thumbnail() doesn't fire extra queries.
            "character__display_data",
            "active_alternate_self",
            "active_alternate_self__alternate_self",
        )
        .prefetch_related(*all_prefetch)
        .prefetch_related(
            # #2196: prefetch the character's active condition instances so
            # resolve_thumbnail() doesn't fire per-persona queries in _build_personas.
            Prefetch(
                "character__condition_instances",
                queryset=ConditionInstance.objects.select_related(
                    "condition", "current_stage"
                ).filter(
                    is_suppressed=False,
                ),
                to_attr="cached_active_conditions",
            )
        )
    )


class CharacterSheetSerializer(serializers.Serializer):
    """Read-only serializer for character sheet data, rooted on CharacterSheet.

    Uses to_representation to delegate to builder functions, eliminating
    SerializerMethodField boilerplate. Each builder returns a TypedDict
    that serves as the type contract for its section.
    """

    def to_representation(self, instance: Any) -> dict[str, Any]:
        sheet: CharacterSheet = instance
        request: Request | None = self.context.get("request")
        roster_entry = sheet.roster_entry
        user = request.user if request else None

        # Per-viewer identity gating (#1109): close the de-anonymization leaks. Only the owner /
        # staff see the full secret alt list (which would link every face); a non-privileged
        # viewer of a character presenting a NON-PRIMARY face (an anonymous mask, or a named
        # alt with a hidden link) never sees the character's real name / bio. "Privileged" =
        # staff, or the viewer's account currently plays this character (query-free, prefetched).
        privileged = _viewer_is_privileged(sheet, user)
        active = _resolve_active_persona(sheet)
        display_name, reveal_identity = _resolve_presented_identity(sheet, active, user, privileged)
        # #1271: player-controlled visibility tier per mechanical section. ``access`` is the
        # viewer's openness level (SELF=2 privileged, FRIENDS=1 allow-list, PUBLIC=0); a
        # section shows when access meets its tier. Defaults are SELF, so this preserves the
        # #1109 "private by default" behaviour until a player opens a section up.
        access = _viewer_access_level(sheet, user, privileged)
        show_stats = _section_visible(access, sheet.stats_visibility)
        show_skills = _section_visible(access, sheet.skills_visibility)
        show_magic = _section_visible(access, sheet.magic_visibility)
        show_goals = _section_visible(access, sheet.goals_visibility)
        # #1270 — bio (concept/quote/story) reads from the presented face's profile: the real
        # one when revealed, a cover persona's own when presenting one, else blank.
        bio_profile = _presented_bio_profile(sheet, active, reveal_identity=reveal_identity)

        return {
            "id": sheet.pk,
            "can_edit": can_edit_character_sheet(user, roster_entry) if user else False,
            "identity": _build_identity(
                sheet,
                display_name=display_name,
                reveal_identity=reveal_identity,
                bio_profile=bio_profile,
            ),
            "appearance": _build_appearance(
                sheet, reveal_identity=reveal_identity, privileged=privileged
            ),
            "stats": _build_stats(sheet) if show_stats else {},
            "skills": _build_skills(sheet) if show_skills else [],
            "path": _build_path_detail(sheet),
            "distinctions": _build_distinctions(sheet, privileged=privileged),
            "magic": _build_magic(sheet, privileged=privileged) if show_magic else None,
            # Story reads from the presented face's profile (cover identities show their own).
            "story": _build_story(sheet=sheet, bio_profile=bio_profile),
            "goals": _build_goals(sheet) if show_goals else [],
            "personas": _build_personas(
                sheet,
                privileged=privileged,
                active=active,
                active_display_name=display_name,
                active_revealed=reveal_identity,
            ),
            "theming": _build_theming(sheet),
            "profile_picture": _build_profile_picture(sheet),
            "current_residence": _build_current_residence(sheet),
        }


class ProfileTextVersionSerializer(serializers.ModelSerializer):
    """One entry of a sheet's prose-history timeline (#2631).

    ``reasoning`` is the player's Reason: from the table update request that
    applied this version — the timeline's narrative caption. Era renders as
    the player-facing "Season N".
    """

    era_season_number = serializers.IntegerField(
        source="era.season_number", read_only=True, allow_null=True
    )
    era_display_name = serializers.CharField(
        source="era.display_name", read_only=True, allow_null=True
    )
    reasoning = serializers.SerializerMethodField()
    staff_edited = serializers.SerializerMethodField()

    class Meta:
        model = ProfileTextVersion
        fields = [
            "id",
            "field",
            "text",
            "created_at",
            "ic_date",
            "era_season_number",
            "era_display_name",
            "reasoning",
            "staff_edited",
        ]
        read_only_fields = fields

    def get_reasoning(self, obj: ProfileTextVersion) -> str:
        """The applying request's player reasoning, via serializer context.

        The view builds ``reasoning_by_version`` in one query — never a
        prefetch onto the SharedMemoryModel instances (identity-map instances
        outlive the request; a stale prefetch cache would leak across views).
        """
        return self.context.get("reasoning_by_version", {}).get(obj.pk, "")

    def get_staff_edited(self, obj: ProfileTextVersion) -> bool:
        return obj.edited_by_id is not None
