"""Filters for scene action requests."""

from django.db.models import QuerySet
import django_filters

from world.scenes.action_models import SceneActionRequest, SceneActionTarget
from world.scenes.interaction_permissions import get_account_personas

# Direction values for SceneActionRequestFilter.role (#2166 — mirrors
# world.combat.filters.DuelChallengeFilter's role=incoming|outgoing).
_ROLE_INCOMING = "incoming"
_ROLE_OUTGOING = "outgoing"


class SceneActionRequestFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene_id")
    status = django_filters.CharFilter(field_name="status")
    initiator = django_filters.NumberFilter(field_name="initiator_persona_id")
    target = django_filters.NumberFilter(field_name="target_persona_id")
    # #2166 — ConsentAttentionNotifier's account-wide poll: narrow to requests
    # addressed to (role=incoming) or issued by (role=outgoing) ANY of the
    # requesting account's played characters, not just one persona.
    # SceneActionRequestViewSet.get_queryset already scopes the base queryset to
    # the account's own personas (never leaks another player's requests) — this
    # filter only narrows *which side* of that already-owned queryset to keep.
    role = django_filters.ChoiceFilter(
        choices=[(_ROLE_INCOMING, "Incoming"), (_ROLE_OUTGOING, "Outgoing")],
        method="filter_role",
        label="Request direction relative to the requesting account's played characters.",
    )

    class Meta:
        model = SceneActionRequest
        fields = ["scene", "status", "initiator", "target", "role"]

    def filter_role(
        self,
        queryset: QuerySet[SceneActionRequest],
        name: str,  # noqa: ARG002 — django-filter's method-filter signature requires it.
        value: str,
    ) -> QuerySet[SceneActionRequest]:
        request = self.request
        if request is None:
            return queryset.none()
        persona_ids = get_account_personas(request)
        if value == _ROLE_INCOMING:
            return queryset.filter(target_persona_id__in=persona_ids)
        if value == _ROLE_OUTGOING:
            return queryset.filter(initiator_persona_id__in=persona_ids)
        return queryset


class SceneActionTargetFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="action_request__scene_id")
    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = SceneActionTarget
        fields = ["scene", "status"]
