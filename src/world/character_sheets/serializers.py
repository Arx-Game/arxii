"""
Serializers for the character sheets API.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework.request import Request

from world.character_sheets.models import CharacterSheet
from world.classes.models import PathStage
from world.forms.models import CharacterForm, FormType
from world.magic.models import CharacterAnimaRitual, CharacterAura, Motif
from world.roster.models import RosterEntry

# --- Tiny helpers for nested {id, name} representations ---


def _id_name(obj: Any, name_field: str = "name") -> dict[str, Any]:
    """Return ``{id, name}`` for a model instance."""
    return {"id": obj.pk, "name": getattr(obj, name_field)}


def _id_name_or_null(obj: Any | None, name_field: str = "name") -> dict[str, Any] | None:
    """Return ``{id, name}`` or ``None`` when the FK is nullable."""
    if obj is None:
        return None
    return _id_name(obj, name_field)


# --- Section builders ---


def _build_identity(roster_entry: RosterEntry, sheet: CharacterSheet) -> dict[str, Any]:
    """Build the identity section dict from a RosterEntry + CharacterSheet."""
    character = roster_entry.character
    family = sheet.family

    # Compose fullname: "FirstName FamilyName" or just the db_key.
    if family is not None:
        fullname = f"{character.db_key} {family.name}"
    else:
        fullname = character.db_key

    # Latest path from prefetched path_history (ordered by -selected_at).
    path_history = list(character.path_history.all())
    if path_history:
        latest_path = path_history[0].path
        path_value: dict[str, Any] | None = _id_name(latest_path)
    else:
        path_value = None

    return {
        "name": character.db_key,
        "fullname": fullname,
        "concept": sheet.concept,
        "quote": sheet.quote,
        "age": sheet.age,
        "gender": _id_name_or_null(sheet.gender, name_field="display_name"),
        "pronouns": {
            "subject": sheet.pronoun_subject,
            "object": sheet.pronoun_object,
            "possessive": sheet.pronoun_possessive,
        },
        "species": _id_name_or_null(sheet.species),
        "heritage": _id_name_or_null(sheet.heritage),
        "family": _id_name_or_null(family),
        "tarot_card": _id_name_or_null(sheet.tarot_card),
        "origin": _id_name_or_null(sheet.origin_realm),
        "path": path_value,
    }


def _build_appearance(roster_entry: RosterEntry, sheet: CharacterSheet) -> dict[str, Any]:
    """Build the appearance section dict from a RosterEntry + CharacterSheet."""
    character = roster_entry.character

    # Get form traits from the TRUE form (prefetched).
    true_forms = [f for f in character.forms.all() if f.form_type == FormType.TRUE]
    if true_forms:
        true_form: CharacterForm = true_forms[0]
        form_traits: list[dict[str, str]] = [
            {"trait": fv.trait.display_name, "value": fv.option.display_name}
            for fv in true_form.values.all()
        ]
    else:
        form_traits = []

    return {
        "height_inches": sheet.true_height_inches,
        "build": _id_name_or_null(sheet.build, name_field="display_name"),
        "description": sheet.additional_desc,
        "form_traits": form_traits,
    }


def _build_stats(roster_entry: RosterEntry) -> dict[str, int]:
    """Build the stats section: a flat dict mapping stat name to value.

    The queryset is pre-filtered to stat-type traits via Prefetch in the viewset.
    """
    character = roster_entry.character
    return {tv.trait.name: tv.value for tv in character.trait_values.all()}


def _build_skills(roster_entry: RosterEntry) -> list[dict[str, Any]]:
    """Build the skills section: a list of skill entries with nested specializations."""
    character = roster_entry.character

    # Build a lookup of specialization values keyed by parent_skill_id
    spec_by_skill: dict[int, list[dict[str, Any]]] = {}
    for sv in character.specialization_values.all():
        skill_id = sv.specialization.parent_skill_id
        spec_by_skill.setdefault(skill_id, []).append(
            {"id": sv.specialization.pk, "name": sv.specialization.name, "value": sv.value}
        )

    result: list[dict[str, Any]] = []
    for csv in character.skill_values.all():
        skill = csv.skill
        result.append(
            {
                "skill": {"id": skill.pk, "name": skill.name, "category": skill.category},
                "value": csv.value,
                "specializations": spec_by_skill.get(skill.pk, []),
            }
        )
    return result


def _build_path_detail(roster_entry: RosterEntry) -> dict[str, Any] | None:
    """Build the detailed path section with step, tier, and history.

    Returns ``None`` when no path history exists for the character.  The
    ``path_history`` queryset is expected to be prefetched and ordered by
    ``-selected_at`` (newest first) so that index 0 is the current path.
    """
    character = roster_entry.character
    path_history = list(character.path_history.all())
    if not path_history:
        return None

    current = path_history[0]
    current_path = current.path

    history_list: list[dict[str, Any]] = [
        {
            "path": entry.path.name,
            "stage": entry.path.stage,
            "tier": PathStage(entry.path.stage).label,
            "date": entry.selected_at.date().isoformat(),
        }
        for entry in path_history
    ]

    return {
        "id": current_path.pk,
        "name": current_path.name,
        "stage": current_path.stage,
        "tier": PathStage(current_path.stage).label,
        "history": history_list,
    }


def _build_distinctions(roster_entry: RosterEntry) -> list[dict[str, Any]]:
    """Build the distinctions section: a list of character distinction entries.

    Expects ``character.distinctions`` to be prefetched with
    ``select_related("distinction")``.
    """
    character = roster_entry.character
    return [
        {
            "id": cd.pk,
            "name": cd.distinction.name,
            "rank": cd.rank,
            "notes": cd.notes,
        }
        for cd in character.distinctions.all()
    ]


def _build_magic_gifts(sheet: CharacterSheet) -> list[dict[str, Any]]:
    """Build the gifts sub-section of magic from prefetched CharacterGift data.

    Groups character techniques by gift and includes gift resonances.
    """
    # Build a lookup of techniques by gift_id from prefetched character_techniques
    techniques_by_gift: dict[int, list[dict[str, Any]]] = {}
    for ct in sheet.character_techniques.all():
        tech = ct.technique
        techniques_by_gift.setdefault(tech.gift_id, []).append(
            {
                "name": tech.name,
                "level": tech.level,
                "style": tech.style.name,
                "description": tech.description,
            }
        )

    gifts: list[dict[str, Any]] = []
    for cg in sheet.character_gifts.all():
        gift = cg.gift
        resonance_names = [r.name for r in gift.resonances.all()]
        gifts.append(
            {
                "name": gift.name,
                "description": gift.description,
                "resonances": resonance_names,
                "techniques": techniques_by_gift.get(gift.pk, []),
            }
        )
    return gifts


def _build_magic_motif(sheet: CharacterSheet) -> dict[str, Any] | None:
    """Build the motif sub-section from the character's Motif (OneToOne).

    Returns ``None`` when the character has no motif.
    """
    try:
        motif = sheet.motif
    except Motif.DoesNotExist:
        return None

    resonances: list[dict[str, Any]] = []
    for mr in motif.resonances.all():
        facet_names = [fa.facet.name for fa in mr.facet_assignments.all()]
        resonances.append({"name": mr.resonance.name, "facets": facet_names})

    return {"description": motif.description, "resonances": resonances}


def _build_magic_anima_ritual(sheet: CharacterSheet) -> dict[str, Any] | None:
    """Build the anima ritual sub-section (OneToOne to CharacterSheet).

    Returns ``None`` when the character has no anima ritual.
    """
    try:
        ritual = sheet.anima_ritual
    except CharacterAnimaRitual.DoesNotExist:
        return None

    return {
        "stat": ritual.stat.name,
        "skill": ritual.skill.name,
        "resonance": ritual.resonance.name,
        "description": ritual.description,
    }


def _build_magic_aura(character: Any) -> dict[str, Any] | None:
    """Build the aura sub-section (OneToOne to ObjectDB, not CharacterSheet).

    Returns ``None`` when the character has no aura.
    """
    try:
        aura = character.aura
    except CharacterAura.DoesNotExist:
        return None

    return {
        "celestial": aura.celestial,
        "primal": aura.primal,
        "abyssal": aura.abyssal,
        "glimpse_story": aura.glimpse_story,
    }


def _build_magic(roster_entry: RosterEntry) -> dict[str, Any] | None:
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

    return {
        "gifts": gifts,
        "motif": motif_data,
        "anima_ritual": anima_ritual_data,
        "aura": aura_data,
    }


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
        ]

    def get_can_edit(self, obj: RosterEntry) -> bool:
        """
        True if the requesting user is the original account (first tenure) or staff.

        The original account is the player_data.account from the tenure with
        player_number=1. A current player who picked up a roster character
        (player_number > 1) does NOT get edit rights.

        Uses prefetched tenures from the viewset queryset to avoid extra queries.
        """
        request: Request | None = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        # Walk prefetched tenures to avoid an extra query
        original_tenure = next(
            (t for t in obj.tenures.all() if t.player_number == 1),
            None,
        )
        if original_tenure is None:
            return False

        return original_tenure.player_data.account == request.user

    def get_identity(self, obj: RosterEntry) -> dict[str, Any]:
        """Return the identity section of the character sheet."""
        sheet: CharacterSheet = obj.character.sheet_data
        return _build_identity(obj, sheet)

    def get_appearance(self, obj: RosterEntry) -> dict[str, Any]:
        """Return the appearance section of the character sheet."""
        sheet: CharacterSheet = obj.character.sheet_data
        return _build_appearance(obj, sheet)

    def get_stats(self, obj: RosterEntry) -> dict[str, int]:
        """Return the stats section of the character sheet."""
        return _build_stats(obj)

    def get_skills(self, obj: RosterEntry) -> list[dict[str, Any]]:
        """Return the skills section of the character sheet."""
        return _build_skills(obj)

    def get_path(self, obj: RosterEntry) -> dict[str, Any] | None:
        """Return the detailed path section of the character sheet."""
        return _build_path_detail(obj)

    def get_distinctions(self, obj: RosterEntry) -> list[dict[str, Any]]:
        """Return the distinctions section of the character sheet."""
        return _build_distinctions(obj)

    def get_magic(self, obj: RosterEntry) -> dict[str, Any] | None:
        """Return the magic section of the character sheet."""
        return _build_magic(obj)
