"""GM-owned scenario authoring permissions (#3565).

A GM's own StoryScenario graph is authored through the same missions Studio
API staff use, scoped to what they own. This module is the shared scoping
layer: ``scenario_scope_q`` filters a queryset down to "templates (or their
node/option/route/reward children) I own, plus anything OPEN and within my
GM level's risk ceiling"; ``IsStaffOrScenarioOwner`` is the permission class
every authoring viewset in ``world.missions.views`` uses in place of the
staff-only ``IsAdminUser``.

Lives in ``world.missions`` (not ``world.stories``) because it operates on
MissionTemplate/MissionNode/... querysets directly -- but it reads ownership
back through ``MissionTemplate.story_scenario`` (the reverse O2O `world.
stories.models.StoryScenario.template` declares), so it never needs to
import ``Story`` itself (ADR-0010: missions stays the general side).
"""

from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.missions.constants import MissionVisibility, risk_tier_to_renown_risk
from world.missions.models import MissionTemplate

_User = AbstractBaseUser | AnonymousUser | None


def has_gm_profile(user: _User) -> bool:
    """Whether ``user`` is authenticated and has a GMProfile."""
    if user is None or not user.is_authenticated:
        return False
    return user.gm_profile_or_none is not None


def max_risk_tier_for(user: _User) -> int:
    """Highest ``MissionTemplate.risk_tier`` (1..5) ``user`` may author writes at.

    Staff: 5 (no ceiling enforced by this predicate). No GMProfile: 0
    (nothing is theirs to author). Otherwise: the highest tier whose
    ``risk_tier_to_renown_risk`` sits at or under ``gm_max_risk(user)`` on
    the RenownRisk ladder.
    """
    from world.gm.services import gm_max_risk  # noqa: PLC0415
    from world.stories.services.stakes import risk_index  # noqa: PLC0415

    if user is None or not user.is_authenticated:
        return 0
    if user.is_staff:
        return 5
    if not has_gm_profile(user):
        return 0
    cap_idx = risk_index(gm_max_risk(user))
    tiers = [t for t in range(1, 6) if risk_index(risk_tier_to_renown_risk(t)) <= cap_idx]
    return max(tiers) if tiers else 0


def scenario_scope_q(user: _User, prefix: str = "") -> Q:
    """The read-scope filter for a non-staff author's authoring queryset.

    A row is in scope when either its MissionTemplate is a StoryScenario the
    user's own GM table leads, or it is OPEN and within the user's GM-level
    risk ceiling. ``prefix`` is the FK path from the queried model to its
    MissionTemplate (e.g. ``"node__template__"`` for MissionOptionViewSet) --
    empty for MissionTemplateViewSet itself, which queries the template
    directly.
    """
    return Q(**{f"{prefix}story_scenario__story__primary_table__gm__account": user}) | Q(
        **{
            f"{prefix}visibility": MissionVisibility.OPEN,
            f"{prefix}risk_tier__lte": max_risk_tier_for(user),
        }
    )


def user_leads_template(user: _User, template: MissionTemplate) -> bool:
    """Whether ``user`` is the Lead GM of the story owning ``template`` as a scenario.

    False for a catalog (non-scenario) template, an unauthenticated user, or
    a user with no GMProfile -- mirrors
    ``world.stories.permissions.account_may_route_beat``'s ownership walk,
    but starting from the template side.
    """
    if user is None or not user.is_authenticated:
        return False
    gm_profile = user.gm_profile_or_none
    if gm_profile is None:
        return False
    try:
        story = template.story_scenario.story
    except ObjectDoesNotExist:
        return False
    return bool(story.primary_table_id and story.primary_table.gm_id == gm_profile.pk)


class IsStaffOrScenarioOwner(BasePermission):
    """Staff, or a GM authoring within their own StoryScenario's scope (#3565).

    ``has_permission`` (list/create): staff always pass; a non-staff caller
    needs a GMProfile, and a POST (create) is allowed only when the view
    opts in via ``scenario_owner_can_create = True`` -- MissionTemplateViewSet
    leaves this False, so non-staff template creation is 403 outright
    (scenario templates are only ever created through
    ``POST /api/beats/{id}/scenario/``); the child viewsets
    (node/option/route/candidate/reward) set it True, and rely on
    ``ScenarioOwnedChildMixin.perform_create`` for the real ownership check
    (DRF never calls ``has_object_permission`` on create). Every viewset
    using this permission class must declare ``scenario_owner_can_create``
    (a plain bool) -- there is no ``getattr`` fallback (project convention:
    no literal-attribute-name ``getattr``).

    ``has_object_permission`` (retrieve/update/destroy): staff pass; a SAFE
    method is allowed when the resolved template is in the caller's
    ``scenario_scope_q`` (covers the OPEN+in-cap read case, not just
    ownership); an unsafe method requires ``user_leads_template``.
    """

    message = "Only staff or the Lead GM of this scenario's story may do that."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_staff:
            return True
        if not has_gm_profile(user):
            return False
        if request.method == "POST":
            return bool(view.scenario_owner_can_create)
        return True

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        user = request.user
        if user.is_staff:
            return True
        template = view.template_of(obj)
        if request.method in SAFE_METHODS:
            return (
                MissionTemplate.objects.filter(pk=template.pk)
                .filter(scenario_scope_q(user))
                .exists()
            )
        return user_leads_template(user, template)
