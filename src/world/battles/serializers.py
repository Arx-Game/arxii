"""Serializers for the read-only battle aggregate API (#2009).

``BattleDetailSerializer`` is the single aggregate payload the strategic
battle-map page consumes: sides, places (with fortifications + any embedded
vehicle), units, and participants, all nested under one Battle. Persona
resolution follows ``world/combat/serializers.py``'s ``_primary_persona``
pattern — reads ``CharacterSheet.cached_payload_personas`` and exposes only
id/name/thumbnail_url/thumbnail_media_url (never account/username — see the
leak rule that motivated #1932).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from world.battles.models import (
    Battle,
    BattleMapBlueprint,
    BattleParticipant,
    BattlePlace,
    BattleSide,
    BattleUnit,
    BattleUnitTemplate,
    BattleUnitTemplateCapability,
    BattleVehicle,
    BlueprintBattlePlace,
    BlueprintFortification,
    Fortification,
)
from world.mechanics.models import Property
from world.scenes.constants import PersonaType
from world.societies.models import LegendEntry


class FortificationSerializer(serializers.ModelSerializer):
    """A defensible structure at a BattlePlace."""

    defending_side_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Fortification
        fields = [
            "id",
            "kind",
            "integrity",
            "max_integrity",
            "breached",
            "defending_side_id",
        ]


class BattleVehicleSummarySerializer(serializers.ModelSerializer):
    """Slim vehicle summary — read through BattleStateCache.vehicle_at_place, never a query."""

    unit_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = BattleVehicle
        fields = ["unit_id", "vehicle_kind", "is_structural"]


class BattlePlaceSerializer(serializers.ModelSerializer):
    """A named front/zone, with its battle-map position and embedded structures."""

    # DecimalField columns explicitly coerced to numbers — ModelSerializer's
    # default DecimalField renders as a string, which the battle-map page
    # (a numeric x/y plot) cannot consume.
    x = serializers.FloatField()
    y = serializers.FloatField()
    footprint_radius = serializers.FloatField()
    controlled_by_id = serializers.IntegerField(read_only=True, allow_null=True)
    encounter_scene_id = serializers.SerializerMethodField()
    encounter_roster = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    # Sourced from the "cached_fortifications" to_attr the view's Prefetch
    # populates (world/battles/views.py) — never the bare "fortifications"
    # manager, which would re-query.
    fortifications = FortificationSerializer(
        many=True, read_only=True, source="cached_fortifications"
    )

    class Meta:
        model = BattlePlace
        fields = [
            "id",
            "name",
            "terrain_type",
            "movement_cost",
            "x",
            "y",
            "footprint_radius",
            "controlled_by_id",
            "encounter_scene_id",
            "encounter_roster",
            "vehicle",
            "fortifications",
        ]

    def get_encounter_scene_id(self, obj: BattlePlace) -> int | None:
        """The scene backing this front's bridged CombatEncounter, if any (#1236)."""
        return obj.combat_encounter.scene_id if obj.combat_encounter_id else None

    def get_encounter_roster(self, obj: BattlePlace) -> dict | None:
        """Compact front-fight roster: status/outcome/participants/opponents (#2008).

        None when no CombatEncounter is bound. One query each for participants
        and opponents per bound place — battles carry a small, bounded number of
        fronts, so this is not an unbounded-loop N+1.
        """
        if not obj.combat_encounter_id:
            return None
        encounter = obj.combat_encounter
        return {
            "status": encounter.get_status_display(),
            "outcome": encounter.get_outcome_display() if encounter.outcome else None,
            "participants": [
                {
                    "character_name": p.character_sheet.character.db_key,
                    "status": p.get_status_display(),
                }
                for p in encounter.participants.select_related("character_sheet__character")
            ],
            "opponents": [
                {"name": o.name, "status": o.get_status_display()}
                for o in encounter.opponents.all()
            ],
        }

    def get_vehicle(self, obj: BattlePlace) -> dict | None:
        """Read the embedded vehicle, if any, through the battle's state cache.

        Never a fresh query — ``BattleStateCache.vehicle_at_place`` is the
        single source of truth for which vehicle occupies a place (#1714).
        """
        vehicle = obj.battle.state_cache.vehicle_at_place(obj.pk)
        if vehicle is None:
            return None
        return BattleVehicleSummarySerializer(vehicle).data


class BattleUnitSerializer(serializers.ModelSerializer):
    """An abstract typed force at a particular front (or embedded in a vehicle)."""

    side_id = serializers.IntegerField(read_only=True)
    place_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = BattleUnit
        fields = [
            "id",
            "name",
            "descriptor",
            "quality",
            "status",
            "strength",
            "morale",
            "individual_count",
            "side_id",
            "place_id",
        ]


class BattleParticipantSerializer(serializers.ModelSerializer):
    """A player character enlisted in the battle, with their public persona face."""

    side_id = serializers.IntegerField(read_only=True)
    place_id = serializers.IntegerField(read_only=True, allow_null=True)
    persona = serializers.SerializerMethodField()

    class Meta:
        model = BattleParticipant
        fields = ["id", "status", "side_id", "place_id", "persona"]

    def _primary_persona(self, obj: BattleParticipant):
        """Resolve the participant's PRIMARY persona through the cached accessor.

        Mirrors ``world/combat/serializers.py``'s ``_primary_persona`` — reads
        ``CharacterSheet.cached_payload_personas`` so serialization issues no
        per-row query when the view prefetches it.
        """
        try:
            character_sheet = obj.character_sheet
        except ObjectDoesNotExist:
            return None
        for persona in character_sheet.cached_payload_personas:
            if persona.persona_type == PersonaType.PRIMARY:
                return persona
        return None

    def get_persona(self, obj: BattleParticipant) -> dict | None:
        """Public persona identity only — id/name/thumbnail(s), never account/username.

        ``thumbnail_media_url`` mirrors ``world/combat/serializers.py``'s
        ``get_thumbnail_media_url`` — the uploaded-portrait ``Media`` FK,
        already ``select_related``'d by the view's Prefetch (world/battles/views.py),
        so this never issues a query. ``thumbnail_url`` is the legacy URLField,
        kept alongside for callers still on it.
        """
        persona = self._primary_persona(obj)
        if persona is None:
            return None
        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

        try:
            character = persona.character_sheet.character
        except AttributeError:
            character = None
        # #2196: use prefetched conditions if available (battles view prefetches
        # them on the character to avoid per-participant N+1).
        cached_conditions = (
            # Suppression justified: mutating condition set on identity-mapped ObjectDB; (#2401)
            # context-over-cache.
            getattr(character, "cached_active_conditions", None)  # noqa: GETATTR_LITERAL
            if character is not None
            else None
        )
        thumbnail_media_url = (
            resolve_thumbnail(
                character,
                persona=persona,
                cached_conditions=cached_conditions,
            )
            if character is not None
            else (persona.thumbnail.cloudinary_url if persona.thumbnail_id else None)
        )
        return {
            "id": persona.id,
            "name": persona.name,
            "thumbnail_url": persona.thumbnail_url or None,
            "thumbnail_media_url": thumbnail_media_url,
        }


class BattleDeedSerializer(serializers.ModelSerializer):
    """A legendary deed performed during the battle, scoped via the battle's scene (#1735).

    Reads from ``LegendEntry`` rows whose ``scene`` FK matches the battle's
    backing scene. Exposes the persona's public identity (id + name only) —
    never account/username (ADR-0033).
    """

    persona = serializers.SerializerMethodField()

    class Meta:
        model = LegendEntry
        fields = ["id", "title", "description", "base_value", "created_at", "persona"]

    def get_persona(self, obj: LegendEntry) -> dict | None:
        """Public persona identity only — id/name, never account/username."""
        persona = obj.persona
        if persona is None:
            return None
        return {"id": persona.id, "name": persona.name}


class BattleSideSerializer(serializers.ModelSerializer):
    """One side in the battle, with its victory tally and fielding covenant."""

    covenant_id = serializers.IntegerField(read_only=True, allow_null=True)
    covenant_name = serializers.SerializerMethodField()

    class Meta:
        model = BattleSide
        fields = [
            "id",
            "role",
            "victory_points",
            "victory_threshold",
            "posture",
            "covenant_id",
            "covenant_name",
        ]

    def get_covenant_name(self, obj: BattleSide) -> str | None:
        return obj.covenant.name if obj.covenant_id else None


class BattleListSerializer(serializers.ModelSerializer):
    """Slim row for the battle list endpoint."""

    scene_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Battle
        fields = ["id", "name", "scene_id", "outcome", "created_at"]


class BattleDetailSerializer(serializers.ModelSerializer):
    """Full battle aggregate — sides, places, units, and participants."""

    # Each nested list is sourced from the view's "cached_*" to_attr Prefetch
    # (world/battles/views.py._detail_prefetches) rather than the bare related
    # manager, so nesting costs zero extra queries.
    round = serializers.SerializerMethodField()
    sides = BattleSideSerializer(many=True, read_only=True, source="cached_sides")
    places = BattlePlaceSerializer(many=True, read_only=True, source="cached_places")
    units = BattleUnitSerializer(many=True, read_only=True, source="cached_units")
    participants = BattleParticipantSerializer(
        many=True, read_only=True, source="cached_participants"
    )
    # Writeup fields (#1735) — additive to the existing aggregate; the live
    # battle-map page ignores these, the writeup page consumes them.
    concluded_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    campaign_story_id = serializers.IntegerField(read_only=True, allow_null=True)
    scene_id = serializers.IntegerField(read_only=True)
    deeds = serializers.SerializerMethodField()

    class Meta:
        model = Battle
        fields = [
            "id",
            "name",
            "outcome",
            "risk_level",
            "is_paused",
            "round",
            "sides",
            "places",
            "units",
            "participants",
            "concluded_at",
            "created_at",
            "campaign_story_id",
            "scene_id",
            "deeds",
        ]

    def get_round(self, obj: Battle) -> dict | None:
        """The battle's current (latest non-completed) round, or None."""
        current = obj.current_round
        if current is None:
            return None
        return {"number": current.round_number, "status": current.status}

    def get_deeds(self, obj: Battle) -> list:
        """Legendary deeds scoped to this battle's backing scene (#1735).

        Reads from the ``cached_deeds`` to_attr the view's Prefetch populates
        on the battle's Scene (world/battles/views.py) — never a fresh query.
        """
        return BattleDeedSerializer(obj.scene.cached_deeds, many=True).data


class BlueprintFortificationSerializer(serializers.ModelSerializer):
    """Catalog-time counterpart to FortificationSerializer (#2010)."""

    class Meta:
        model = BlueprintFortification
        fields = ["id", "kind", "max_integrity", "defending_side_role"]


class BlueprintBattlePlaceSerializer(serializers.ModelSerializer):
    """A named front/zone within a BattleMapBlueprint, with its fortifications."""

    # DecimalField columns coerced to numbers -- mirrors BattlePlaceSerializer,
    # since the same battle-map page (a numeric x/y plot) consumes this shape.
    x = serializers.FloatField()
    y = serializers.FloatField()
    footprint_radius = serializers.FloatField()
    # Sourced from the "cached_fortifications" to_attr the view's Prefetch
    # populates (world/battles/views.py) -- never the bare "fortifications"
    # manager, which would re-query.
    fortifications = BlueprintFortificationSerializer(
        many=True, read_only=True, source="cached_fortifications"
    )

    class Meta:
        model = BlueprintBattlePlace
        fields = [
            "id",
            "name",
            "terrain_type",
            "movement_cost",
            "x",
            "y",
            "footprint_radius",
            "fortifications",
        ]


class BattleMapBlueprintSerializer(serializers.ModelSerializer):
    """Admin-authored, reusable battle-map layout a GM stages a Battle from (#2010)."""

    # Sourced from the "cached_places" to_attr the view's Prefetch populates.
    places = BlueprintBattlePlaceSerializer(many=True, read_only=True, source="cached_places")

    class Meta:
        model = BattleMapBlueprint
        fields = ["id", "name", "description", "is_active", "places"]


class BattleUnitTemplatePropertySerializer(serializers.ModelSerializer):
    """A Property tag on a BattleUnitTemplate, by name -- never a bare id (#2010)."""

    class Meta:
        model = Property
        fields = ["id", "name"]


class BattleUnitTemplateCapabilitySerializer(serializers.ModelSerializer):
    """An authored (template, capability) -> magnitude row, with the capability's name."""

    capability_id = serializers.IntegerField(read_only=True)
    capability_name = serializers.CharField(source="capability.name", read_only=True)

    class Meta:
        model = BattleUnitTemplateCapability
        fields = ["capability_id", "capability_name", "value"]


class BattleUnitTemplateSerializer(serializers.ModelSerializer):
    """Admin-authored, reusable unit stat block a GM stages a Battle from (#2010)."""

    # Sourced from the "cached_properties"/"cached_capability_values" to_attr
    # the view's Prefetch populates (world/battles/views.py).
    properties = BattleUnitTemplatePropertySerializer(
        many=True, read_only=True, source="cached_properties"
    )
    capability_values = BattleUnitTemplateCapabilitySerializer(
        many=True, read_only=True, source="cached_capability_values"
    )

    class Meta:
        model = BattleUnitTemplate
        fields = [
            "id",
            "name",
            "descriptor",
            "quality",
            "strength",
            "morale",
            "individual_count",
            "is_active",
            "properties",
            "capability_values",
        ]
