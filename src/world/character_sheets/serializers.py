"""
Serializers for the character sheets API.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework.request import Request

from world.character_sheets.models import CharacterSheet
from world.forms.models import CharacterForm, FormType
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

    class Meta:
        model = RosterEntry
        fields = ["id", "can_edit", "identity", "appearance", "stats", "skills"]

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
