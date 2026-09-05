"""Kinship serializers (#2062): Family + the viewer-aware tree payload.

The tree endpoint serializes ``family_tree_for``'s payload — nodes and typed
edges the requesting viewer is allowed to see (public record + truths they
know) — never raw graph rows.
"""

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.roster.constants import RelationshipType
from world.roster.models import Family, FamilyKind, KinSlotPool, Kinsperson


class FamilyKindSerializer(serializers.ModelSerializer):
    """Serializer for a family's authored kind (#3617)."""

    class Meta:
        model = FamilyKind
        fields = ["id", "name", "styles_as_house"]
        read_only_fields = fields


class FamilySerializer(serializers.ModelSerializer):
    """Serializer for family selection and display."""

    kind = FamilyKindSerializer(read_only=True)
    born_particle = serializers.SerializerMethodField(
        help_text="Nobiliary particle a born member wears (#3261); '' when none."
    )
    taken_in_particle = serializers.SerializerMethodField(
        help_text="Particle a married/adopted/legitimized member wears; '' when none."
    )
    inherited = serializers.SerializerMethodField(
        help_text="Aspects/features/liege a house materialized on this family carries (#3648)."
    )

    class Meta:
        model = Family
        fields = [
            "id",
            "name",
            "kind",
            "influence",
            "description",
            "is_playable",
            "origin_realm",
            "born_particle",
            "taken_in_particle",
            "inherited",
        ]
        read_only_fields = ["id"]

    def get_born_particle(self, obj: Family) -> str:
        from world.societies.houses.services import resolve_particle  # noqa: PLC0415

        return resolve_particle(obj)

    def get_taken_in_particle(self, obj: Family) -> str:
        from world.societies.houses.services import resolve_particle  # noqa: PLC0415

        return resolve_particle(obj, taken_in=True)

    @extend_schema_field(serializers.DictField())
    def get_inherited(self, obj: Family) -> dict:
        """Prefer the list view's batched grouping; fall back to a direct query.

        ``FamilyViewSet.list()`` passes ``inherited_by_family`` (four flat
        queries for the whole response) into context. Nested usage (e.g.
        ``FamilyTreeSerializer.family``) never provides that key, since it is
        one object, not a list - a direct lookup there is a bounded handful of
        queries, not a loop.
        """
        grouping = self.context.get("inherited_by_family")
        if grouping is not None:
            return grouping.get(obj.id, {"aspects": [], "features": [], "liege_name": ""})
        from world.societies.houses.services import house_for_family  # noqa: PLC0415

        org = house_for_family(obj)
        if org is None:
            return {"aspects": [], "features": [], "liege_name": ""}
        try:
            liege = org.fealty
        except ObjectDoesNotExist:
            liege = None
        return {
            "aspects": [
                {
                    "definition": facet.definition.name,
                    "option": facet.option.name,
                    "description": facet.option.description,
                }
                for facet in org.aspects.select_related("definition", "option")
            ],
            "features": [
                {
                    "name": s.feature.name,
                    "slug": s.feature.slug,
                    "description": s.feature.description,
                }
                for s in org.features.select_related("feature")
            ],
            "liege_name": liege.liege.name if liege is not None else "",
        }


class KinspersonNodeSerializer(serializers.Serializer):
    """One visible node in a family tree payload."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    tier = serializers.CharField()
    family_id = serializers.IntegerField(allow_null=True)
    is_deceased = serializers.BooleanField()
    is_appable = serializers.BooleanField()
    # CharacterSheet pk this node is bound to, or null for an unplayed NPC
    # (#3003 Task 8): the tree's own ``id`` is a Kinsperson pk, a different id
    # space from the relationship endpoint's ``a``/``b`` — a viewer needs this
    # to query relatedness for a node without conflating the two spaces.
    sheet_id = serializers.IntegerField(allow_null=True)
    gender = serializers.CharField(allow_blank=True)
    age = serializers.IntegerField(allow_null=True)
    description = serializers.CharField(allow_blank=True)


class ParentageEdgeSerializer(serializers.Serializer):
    """One visible parentage edge in a family tree payload."""

    child_id = serializers.IntegerField()
    parent_id = serializers.IntegerField()
    kind = serializers.CharField()
    is_true = serializers.BooleanField()
    via_secret = serializers.BooleanField()


class UnionEdgeSerializer(serializers.Serializer):
    """One visible union in a family tree payload."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    member_ids = serializers.ListField(child=serializers.IntegerField())
    ended = serializers.BooleanField()


class FamilyTreeSerializer(serializers.Serializer):
    """Viewer-aware graph payload for GET /api/roster/families/{id}/tree/.

    ``family`` is null for an ego-centric payload (``kin_tree_for_sheet``'s
    familyless branch) — a character with no house can still have kin.
    """

    family = FamilySerializer(allow_null=True)
    nodes = KinspersonNodeSerializer(many=True)
    parentage = ParentageEdgeSerializer(many=True)
    unions = UnionEdgeSerializer(many=True)


class KinRelationshipQuerySerializer(serializers.Serializer):
    """Query params for GET /api/roster/kin/relationship/ (#3003).

    ``a``/``b`` are character ids (``CharacterSheet`` pks) — validated here,
    never read off ``request.query_params`` directly in the view.
    """

    a = serializers.IntegerField(required=True)
    b = serializers.IntegerField(required=True)


class KinRelationshipSerializer(serializers.Serializer):
    """Response for GET /api/roster/kin/relationship/ (#3003).

    ``label`` is a viewer-derived ``RelationshipType`` value, or null when
    the two people have no visible relationship (including a hidden one the
    viewer has not learned).
    """

    label = serializers.ChoiceField(choices=RelationshipType.choices, allow_null=True)


class KinSlotSerializer(serializers.ModelSerializer):
    """An open appable position (CG slot browser)."""

    allowed_genders = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="display_name"
    )

    class Meta:
        model = Kinsperson
        fields = [
            "id",
            "name",
            "name_locked",
            "description",
            "age_min",
            "age_max",
            "allowed_genders",
            "family",
        ]
        read_only_fields = fields


class KinSlotPoolSerializer(serializers.ModelSerializer):
    """An open slot pool (CG slot browser)."""

    allowed_genders = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="display_name"
    )
    parent_names = serializers.SerializerMethodField()

    class Meta:
        model = KinSlotPool
        fields = [
            "id",
            "family",
            "description",
            "count_remaining",
            "age_min",
            "age_max",
            "allowed_genders",
            "parent_names",
        ]
        read_only_fields = fields

    def get_parent_names(self, obj: KinSlotPool) -> list[str]:
        return [p.display_name for p in obj.parents.all()]
