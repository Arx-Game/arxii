"""FilterSets for the NPC service framework."""

import django_filters

from world.npc_services.models import (
    MissionOfferDetails,
    NPCReactionLine,
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    PermitOfferDetails,
    RecordedProfile,
)


class NPCStandingFilterSet(django_filters.FilterSet):
    """Filter NPCStanding rows by persona / npc_persona / cooldown."""

    persona = django_filters.NumberFilter(field_name="persona_id")
    npc_persona = django_filters.NumberFilter(field_name="npc_persona_id")

    class Meta:
        model = NPCStanding
        fields: list[str] = []


class NPCRoleFilterSet(django_filters.FilterSet):
    faction_affiliation = django_filters.NumberFilter(field_name="faction_affiliation_id")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = NPCRole
        fields: list[str] = []


class NPCServiceOfferFilterSet(django_filters.FilterSet):
    role = django_filters.NumberFilter(field_name="role_id")
    kind = django_filters.CharFilter(field_name="kind")
    draw_mode = django_filters.CharFilter(field_name="draw_mode")

    class Meta:
        model = NPCServiceOffer
        fields: list[str] = []


class OfferCooldownFilterSet(django_filters.FilterSet):
    offer = django_filters.NumberFilter(field_name="offer_id")
    persona = django_filters.NumberFilter(field_name="persona_id")

    class Meta:
        model = OfferCooldown
        fields: list[str] = []


class MissionOfferDetailsFilterSet(django_filters.FilterSet):
    offer = django_filters.NumberFilter(field_name="offer_id")
    role = django_filters.NumberFilter(field_name="role_id")

    class Meta:
        model = MissionOfferDetails
        fields: list[str] = []


class PermitOfferDetailsFilterSet(django_filters.FilterSet):
    offer = django_filters.NumberFilter(field_name="offer_id")
    # No denormalized role on PermitOfferDetails (unlike mission details) — walk the
    # FK so the role editor can fetch a role's permit details in one call (#1684).
    role = django_filters.NumberFilter(field_name="offer__role_id")
    building_kind = django_filters.NumberFilter(field_name="building_kind_id")

    class Meta:
        model = PermitOfferDetails
        fields: list[str] = []


class RecordedProfileFilterSet(django_filters.FilterSet):
    persona = django_filters.NumberFilter(field_name="persona_id")
    status = django_filters.CharFilter()

    class Meta:
        model = RecordedProfile
        fields: list[str] = []


class NPCReactionLineFilterSet(django_filters.FilterSet):
    role = django_filters.NumberFilter(field_name="role_id")
    functionary = django_filters.NumberFilter(field_name="functionary_id")
    metric = django_filters.CharFilter()

    class Meta:
        model = NPCReactionLine
        fields: list[str] = []
