"""Filters for combat API endpoints."""

from django.db.models import Q, QuerySet
import django_filters

from world.combat.models import CombatEncounter, CreatureTemplate, DuelChallenge

# Duel-inbox direction filter values (relative to the requesting player).
_ROLE_INCOMING = "incoming"
_ROLE_OUTGOING = "outgoing"


class CombatEncounterFilter(django_filters.FilterSet):
    """Filter combat encounters by scene and status."""

    scene = django_filters.NumberFilter(field_name="scene_id")
    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = CombatEncounter
        fields = ["scene", "status"]


class DuelChallengeFilter(django_filters.FilterSet):
    """Narrow the duel-challenge inbox to one direction relative to the caller.

    ``role=incoming`` keeps challenges where the caller plays the challenged
    character; ``role=outgoing`` keeps challenges the caller issued. With no
    ``role`` the inbox returns both sides (#1180).
    """

    role = django_filters.ChoiceFilter(
        choices=[(_ROLE_INCOMING, "Incoming"), (_ROLE_OUTGOING, "Outgoing")],
        method="filter_role",
        label="Challenge direction relative to the requesting player.",
    )

    class Meta:
        model = DuelChallenge
        fields = ["role"]

    def filter_role(
        self, queryset: QuerySet[DuelChallenge], name: str, value: str
    ) -> QuerySet[DuelChallenge]:
        played_ids = self.request.user.played_character_sheet_ids
        if value == _ROLE_INCOMING:
            return queryset.filter(challenged_sheet_id__in=played_ids)
        if value == _ROLE_OUTGOING:
            return queryset.filter(challenger_sheet_id__in=played_ids)
        return queryset


class CreatureTemplateFilter(django_filters.FilterSet):
    """Filter for the bestiary catalog browse endpoint (#3424).

    ``search`` mirrors ``CheckTypeFilter``'s shape (name/description icontains)
    so the web picker and any future telnet browse verb stay consistent with
    the GM catalog conventions elsewhere.
    """

    search = django_filters.CharFilter(method="filter_search")
    tier = django_filters.CharFilter(field_name="tier", lookup_expr="iexact")

    def filter_search(
        self, queryset: QuerySet[CreatureTemplate], name: str, value: str
    ) -> QuerySet[CreatureTemplate]:
        del name
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))

    class Meta:
        model = CreatureTemplate
        fields = ["search", "tier"]
