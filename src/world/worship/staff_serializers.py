"""Serializers for the Deity Editor (#3780): staff only."""

from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers

from world.magic.models import Facet, Resonance
from world.societies.models import Organization
from world.tarot.models import TarotCard
from world.worship.constants import (
    BeingRelationshipValence,
    BeingResonanceTier,
    BeingVisibility,
)
from world.worship.editor_services import (
    BeingPage,
    FeastDayLine,
    RelationshipLine,
    ResonanceLine,
    obscure_organization_of,
    visibility_of,
)
from world.worship.models import (
    BeingFacet,
    BeingRelationship,
    Prayer,
    Relic,
    Vision,
    WorshippedBeing,
    WorshipTradition,
)


class RefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


def _domain_chips(domains: str) -> list[str]:
    return [chip.strip() for chip in domains.replace(";", ",").split(",") if chip.strip()]


class StaffBeingListSerializer(serializers.ModelSerializer):
    """A tile on the god list."""

    tradition_name = serializers.CharField(source="tradition.name", read_only=True)
    nickname = serializers.SerializerMethodField()
    domain_chips = serializers.SerializerMethodField()
    visibility = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = WorshippedBeing
        fields = [
            "id",
            "name",
            "tradition_name",
            "nickname",
            "domain_chips",
            "resonance_pool",
            "lifetime_worship",
            "visibility",
            "organization_name",
            "is_active",
        ]
        read_only_fields = fields

    def get_nickname(self, obj: WorshippedBeing) -> str:
        # Annotated by StaffBeingViewSet.get_queryset; None when the being has none.
        return obj.first_nickname or ""

    def get_domain_chips(self, obj: WorshippedBeing) -> list[str]:
        return _domain_chips(obj.domains)

    def get_visibility(self, obj: WorshippedBeing) -> str:
        return visibility_of(obj)

    def get_organization_name(self, obj: WorshippedBeing) -> str:
        organization = obscure_organization_of(obj)
        return organization.name if organization is not None else ""


class ResonanceLineSerializer(serializers.Serializer):
    resonance = serializers.PrimaryKeyRelatedField(queryset=Resonance.objects.all())
    tier = serializers.ChoiceField(choices=BeingResonanceTier.choices)


class FeastDayLineSerializer(serializers.Serializer):
    ic_month = serializers.IntegerField(min_value=1, max_value=12)
    ic_day = serializers.IntegerField(min_value=1, max_value=31)
    name = serializers.CharField(max_length=100)
    lore = serializers.CharField(allow_blank=True, required=False, default="")


class RelationshipLineSerializer(serializers.Serializer):
    other_being = serializers.PrimaryKeyRelatedField(queryset=WorshippedBeing.objects.all())
    valence = serializers.ChoiceField(choices=BeingRelationshipValence.choices)
    public_story = serializers.CharField(allow_blank=True, required=False, default="")


class StaffBeingPageSerializer(serializers.Serializer):
    """The edit page, both directions: what staff read and what they save."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    domains = serializers.CharField(allow_blank=True, required=False, default="")
    tradition = serializers.PrimaryKeyRelatedField(queryset=WorshipTradition.objects.all())
    is_active = serializers.BooleanField(default=True)
    quote = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    nicknames = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )
    resonances = ResonanceLineSerializer(many=True, required=False, default=list)
    facets = serializers.PrimaryKeyRelatedField(
        queryset=Facet.objects.all(), many=True, required=False, default=list
    )
    feast_days = FeastDayLineSerializer(many=True, required=False, default=list)
    tarot_cards = serializers.PrimaryKeyRelatedField(
        queryset=TarotCard.objects.all(), many=True, required=False, default=list
    )
    relationships = RelationshipLineSerializer(many=True, required=False, default=list)
    visibility = serializers.ChoiceField(
        choices=BeingVisibility.choices, default=BeingVisibility.SECRET
    )
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True, default=None
    )
    gm_notes = serializers.CharField(allow_blank=True, required=False, default="")
    resonance_pool = serializers.IntegerField(read_only=True)
    codex_entry = serializers.IntegerField(read_only=True, allow_null=True)

    def validate(self, attrs):
        if attrs.get("visibility") == BeingVisibility.OBSCURE and attrs.get("organization") is None:
            raise serializers.ValidationError(
                {"organization": "An obscure being is known to one organization: pick it."}
            )
        return attrs

    def to_page(self) -> BeingPage:
        data = self.validated_data
        return BeingPage(
            name=data["name"],
            description=data.get("description", ""),
            domains=data.get("domains", ""),
            tradition_id=data["tradition"].pk,
            is_active=data.get("is_active", True),
            quote=data.get("quote", ""),
            nicknames=list(data.get("nicknames", [])),
            resonances=[
                ResonanceLine(resonance_id=line["resonance"].pk, tier=line["tier"])
                for line in data.get("resonances", [])
            ],
            facet_ids=[facet.pk for facet in data.get("facets", [])],
            feast_days=[
                FeastDayLine(
                    ic_month=line["ic_month"],
                    ic_day=line["ic_day"],
                    name=line["name"],
                    lore=line.get("lore", ""),
                )
                for line in data.get("feast_days", [])
            ],
            tarot_card_ids=[card.pk for card in data.get("tarot_cards", [])],
            relationships=[
                RelationshipLine(
                    other_being_id=line["other_being"].pk,
                    valence=line["valence"],
                    public_story=line.get("public_story", ""),
                )
                for line in data.get("relationships", [])
            ],
            visibility=data.get("visibility", BeingVisibility.SECRET),
            organization_id=data["organization"].pk if data.get("organization") else None,
            gm_notes=data.get("gm_notes", ""),
        )

    def to_representation(self, being: WorshippedBeing):  # type: ignore[override]
        entry = being.codex_entry
        organization = obscure_organization_of(being)
        relationships = []
        for row in BeingRelationship.objects.filter(
            Q(being_a=being) | Q(being_b=being)
        ).select_related("being_a", "being_b"):
            other = row.being_b if row.being_a_id == being.pk else row.being_a
            relationships.append(
                {
                    "other_being": other.pk,
                    "other_being_name": other.name,
                    "valence": row.valence,
                    "public_story": row.public_story,
                }
            )
        return {
            "id": being.pk,
            "name": being.name,
            "description": being.description,
            "domains": being.domains,
            "tradition": being.tradition_id,
            "is_active": being.is_active,
            "quote": entry.quote if entry is not None else "",
            "nicknames": list(being.nicknames.order_by("pk").values_list("name", flat=True)),
            "resonances": [
                {
                    "resonance": row.resonance_id,
                    "resonance_name": row.resonance.name,
                    "tier": row.tier,
                }
                for row in being.resonances.select_related("resonance").order_by("pk")
            ],
            "facets": list(
                BeingFacet.objects.filter(being=being)
                .order_by("pk")
                .values_list("facet_id", flat=True)
            ),
            "feast_days": [
                {"ic_month": row.ic_month, "ic_day": row.ic_day, "name": row.name, "lore": row.lore}
                for row in being.feast_days.order_by("ic_month", "ic_day")
            ],
            "tarot_cards": list(being.tarot_cards.order_by("pk").values_list("pk", flat=True)),
            "relationships": relationships,
            "visibility": visibility_of(being),
            "organization": organization.pk if organization is not None else None,
            "gm_notes": being.gm_notes,
            "resonance_pool": being.resonance_pool,
            "codex_entry": being.codex_entry_id,
        }


class EditorOptionsSerializer(serializers.Serializer):
    """Every picker's choices in one response: the catalogs are small."""

    traditions = RefSerializer(many=True)
    resonances = RefSerializer(many=True)
    facets = RefSerializer(many=True)
    tarot_cards = RefSerializer(many=True)
    organizations = RefSerializer(many=True)
    beings = RefSerializer(many=True)


class ActivityRowSerializer(serializers.Serializer):
    when = serializers.DateTimeField()
    text = serializers.CharField()
    note = serializers.CharField()


class OverviewSerializer(serializers.Serializer):
    resonance_pool = serializers.IntegerField()
    lifetime_worship = serializers.IntegerField()
    most_devoted_name = serializers.CharField(allow_null=True)
    most_devoted_favor = serializers.IntegerField(allow_null=True)
    site_count = serializers.IntegerField()
    recent_activity = ActivityRowSerializer(many=True)


class ContributorRowSerializer(serializers.Serializer):
    character_name = serializers.CharField()
    amount = serializers.IntegerField()
    reason = serializers.CharField()
    when = serializers.DateTimeField()


class OfferingRowSerializer(serializers.Serializer):
    item_name = serializers.CharField()
    offered_by = serializers.CharField()
    item_value = serializers.IntegerField()
    amount = serializers.IntegerField(allow_null=True)
    ceremony_id = serializers.IntegerField()
    when = serializers.DateTimeField(allow_null=True)


class DevoteeRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    character_name = serializers.CharField()
    favor = serializers.IntegerField()
    lifetime_favor = serializers.IntegerField()
    valence = serializers.CharField(allow_null=True)


class WorshipTabSerializer(serializers.Serializer):
    contributors = ContributorRowSerializer(many=True)
    offerings = OfferingRowSerializer(many=True)
    most_devoted = DevoteeRowSerializer(many=True)


class SiteRowSerializer(serializers.Serializer):
    kind = serializers.CharField()
    name = serializers.CharField()
    place = serializers.CharField()
    consecration_points = serializers.IntegerField()
    tier_name = serializers.CharField()
    bonus_percent = serializers.IntegerField()
    founder_name = serializers.CharField(allow_null=True)


class StaffPrayerSerializer(serializers.ModelSerializer):
    character_name = serializers.CharField(source="character_sheet.character.key", read_only=True)
    answered = serializers.SerializerMethodField()
    place = serializers.SerializerMethodField()

    class Meta:
        model = Prayer
        fields = [
            "id",
            "character_sheet",
            "character_name",
            "text",
            "devotion_granted",
            "dire_straits",
            "answered",
            "place",
            "prayed_at",
        ]
        read_only_fields = fields

    def get_answered(self, obj: Prayer) -> bool:
        return obj.intervention_id is not None or obj.visions.exists()

    def get_place(self, obj: Prayer) -> str:
        return obj.room_profile.objectdb.key if obj.room_profile_id is not None else ""


class StaffVisionSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.character.key", read_only=True)
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Vision
        fields = [
            "id",
            "recipient",
            "recipient_name",
            "body",
            "reveal_source",
            "prayer",
            "clue",
            "episode",
            "resonance_spent",
            "sent_by_name",
            "sent_at",
        ]
        read_only_fields = fields

    def get_sent_by_name(self, obj: Vision) -> str:
        return obj.sent_by.username if obj.sent_by_id is not None else ""


class RelicRowSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item_instance.display_name", read_only=True)

    class Meta:
        model = Relic
        fields = ["id", "item_instance", "item_name", "lore", "created_at"]
        read_only_fields = fields


class CodexRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    is_public = serializers.BooleanField()
    relation = serializers.CharField()
    organizations = serializers.ListField(child=serializers.CharField())
    clues = serializers.ListField(child=serializers.CharField())
