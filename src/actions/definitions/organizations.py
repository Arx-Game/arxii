"""Generic organization membership lifecycle actions (#1511).

All seven actions are REGISTRY backend singletons and share the same seam
used by the web (`dispatch_player_action`) and telnet (`CmdOrg`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona
    from world.societies.models import Organization, OrganizationMembershipOffer

from world.societies.exceptions import (
    AlreadyOrganizationMemberError,
    CannotDemoteError,
    CannotPromoteError,
    InvalidOrganizationPersonaError,
    NotAGenericOrganizationError,
    NotAuthorizedToInviteError,
    NotAuthorizedToKickError,
    NotAuthorizedToManageRanksError,
    NotOrganizationMemberError,
    OrganizationMemberBlockError,
    OrganizationMembershipError,
    OrganizationOfferNotForYouError,
    OrganizationOfferPendingError,
    OrganizationOfferResolvedError,
)
from world.societies.membership_services import (
    accept_invitation,
    active_membership_for_persona,
    apply_to_organization,
    demote_member,
    expel_member,
    invite_to_organization,
    leave_organization,
    promote_member,
)
from world.societies.models import OrganizationMembership, OrganizationMembershipOffer

_TARGET_FILTERS = TargetFilters(in_same_scene=True, exclude_self=True)

_MSG_NO_CHARACTER_IDENTITY = "You have no character identity."
_MSG_WHICH_ORGANIZATION = "Which organization?"
_MSG_NOT_A_MEMBER = "You are not a member of that organization."
_MSG_TARGET_NOT_A_MEMBER = "That person is not a member of the organization."


def _actor_sheet(actor: ObjectDB) -> Any:
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _actor_persona(actor: ObjectDB) -> Persona | None:
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = _actor_sheet(actor)
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _resolve_target_value(value: Any) -> Persona | None:  # noqa: PLR0911
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, Persona):
        return value
    if isinstance(value, ObjectDB):
        try:
            sheet = value.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        if sheet is None:
            return None
        try:
            return active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None
    try:
        return Persona.objects.filter(pk=int(value)).select_related("character_sheet").first()
    except (TypeError, ValueError):
        return None


def _resolve_target_persona(kwargs: dict[str, Any]) -> Persona | None:
    target = kwargs.get("target")
    if target is None:
        target = kwargs.get("target_persona_id")
    return _resolve_target_value(target)


def _resolve_organization(value: Any) -> Organization | None:
    from world.societies.models import Organization  # noqa: PLC0415

    if value is None:
        return None
    if isinstance(value, Organization):
        return value
    try:
        return Organization.objects.filter(pk=int(value)).first()
    except (TypeError, ValueError):
        return None


def _same_room(actor: ObjectDB, target_persona: Persona) -> bool:
    try:
        actor_room = actor.db_location
    except (AttributeError, ObjectDoesNotExist):
        return False

    try:
        sheet = target_persona.character_sheet
        character = sheet.character
        target_room = character.db_location
    except (AttributeError, ObjectDoesNotExist):
        return False

    if actor_room is None or target_room is None:
        return False

    return actor_room.pk == target_room.pk


@dataclass
class OrgInviteAction(Action):
    key: str = "org_invite"
    name: str = "Invite to Organization"
    icon: str = "user-plus"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = field(default=_TARGET_FILTERS)
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        target_persona = _resolve_target_persona(kwargs)
        if target_persona is None:
            return ActionResult(success=False, message="Invite whom?")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        if not _same_room(actor, target_persona):
            return ActionResult(
                success=False,
                message="You must be in the same room to invite someone.",
            )

        try:
            invite_to_organization(organization, actor_persona, target_persona)
        except (
            NotAuthorizedToInviteError,
            AlreadyOrganizationMemberError,
            InvalidOrganizationPersonaError,
            OrganizationOfferPendingError,
            NotAGenericOrganizationError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You invite {target_persona.name} to join {organization.name}.",
        )


@dataclass
class OrgApplyAction(Action):
    key: str = "org_apply"
    name: str = "Apply to Organization"
    icon: str = "send"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        try:
            apply_to_organization(organization, actor_persona)
        except (
            AlreadyOrganizationMemberError,
            InvalidOrganizationPersonaError,
            OrganizationOfferPendingError,
            NotAGenericOrganizationError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You apply to join {organization.name}.",
        )


@dataclass
class OrgJoinAction(Action):
    key: str = "org_join"
    name: str = "Join Organization"
    icon: str = "log-in"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        offer = OrganizationMembershipOffer.objects.filter(
            organization=organization,
            to_persona=actor_persona,
            kind=OrganizationMembershipOffer.Kind.INVITE,
            status=OrganizationMembershipOffer.Status.PENDING,
        ).first()
        if offer is None:
            return ActionResult(
                success=False,
                message="You have no pending invitation to join that organization.",
            )

        try:
            accept_invitation(offer, actor_persona)
        except (
            OrganizationOfferResolvedError,
            OrganizationOfferNotForYouError,
            AlreadyOrganizationMemberError,
            OrganizationMemberBlockError,
            NotAGenericOrganizationError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You join {organization.name}.",
        )


@dataclass
class OrgLeaveAction(Action):
    key: str = "org_leave"
    name: str = "Leave Organization"
    icon: str = "log-out"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

        membership = active_membership_for_persona(organization, actor_persona)
        if membership is None:
            return ActionResult(
                success=False,
                message=_MSG_NOT_A_MEMBER,
            )

        leave_organization(membership)
        return ActionResult(
            success=True,
            message=f"You leave {organization.name}.",
        )


def _run_membership_management(  # noqa: PLR0911, PLR0913
    actor: ObjectDB,
    verb: str,
    preposition: str,
    service_fn: Callable[[OrganizationMembership, OrganizationMembership], Any],
    errors: tuple[type[OrganizationMembershipError], ...],
    kwargs: dict[str, Any],
) -> ActionResult:
    """Execute a promote/demote/expel action after shared validation."""
    actor_persona = _actor_persona(actor)
    if actor_persona is None:
        return ActionResult(success=False, message=_MSG_NO_CHARACTER_IDENTITY)

    target_persona = _resolve_target_persona(kwargs)
    if target_persona is None:
        return ActionResult(success=False, message=f"{verb.capitalize()} whom?")

    organization = _resolve_organization(kwargs.get("organization_id"))
    if organization is None:
        return ActionResult(success=False, message=_MSG_WHICH_ORGANIZATION)

    if not _same_room(actor, target_persona):
        return ActionResult(
            success=False,
            message=f"You must be in the same room to {verb} someone.",
        )

    actor_membership = active_membership_for_persona(organization, actor_persona)
    target_membership = active_membership_for_persona(organization, target_persona)
    if target_membership is None:
        return ActionResult(success=False, message=_MSG_TARGET_NOT_A_MEMBER)
    if actor_membership is None:
        return ActionResult(success=False, message=_MSG_NOT_A_MEMBER)

    try:
        service_fn(target_membership, actor_membership)
    except errors as exc:
        return ActionResult(success=False, message=exc.user_message)

    return ActionResult(
        success=True,
        message=f"You {verb} {target_persona.name} {preposition} {organization.name}.",
    )


@dataclass
class OrgPromoteAction(Action):
    key: str = "org_promote"
    name: str = "Promote Member"
    icon: str = "arrow-up"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = field(default=_TARGET_FILTERS)
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _run_membership_management(
            actor,
            verb="promote",
            preposition="in",
            service_fn=promote_member,
            errors=(
                NotOrganizationMemberError,
                NotAuthorizedToManageRanksError,
                CannotPromoteError,
            ),
            kwargs=kwargs,
        )


@dataclass
class OrgDemoteAction(Action):
    key: str = "org_demote"
    name: str = "Demote Member"
    icon: str = "arrow-down"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = field(default=_TARGET_FILTERS)
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _run_membership_management(
            actor,
            verb="demote",
            preposition="in",
            service_fn=demote_member,
            errors=(
                NotOrganizationMemberError,
                NotAuthorizedToManageRanksError,
                CannotDemoteError,
            ),
            kwargs=kwargs,
        )


@dataclass
class OrgExpelAction(Action):
    key: str = "org_expel"
    name: str = "Expel Member"
    icon: str = "user-minus"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = field(default=_TARGET_FILTERS)
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _run_membership_management(
            actor,
            verb="expel",
            preposition="from",
            service_fn=expel_member,
            errors=(
                NotOrganizationMemberError,
                NotAuthorizedToKickError,
            ),
            kwargs=kwargs,
        )


_MSG_NO_ACTIVE_PERSONA = "No active persona."
_MSG_NO_DOMAIN_OR_EDICT = "No such domain or edict."
_MSG_NO_STANCE = "No such stance."


@dataclass
class IssueProclamationAction(Action):
    """Issue a proclamation, optionally enacting a domain edict (#2842, #3412).

    Wraps the SAME ``world.societies.proclamations`` service calls
    ``ProclamationViewSet.proclaim`` used to call directly. Routing through
    ``action.run()`` activates the offscreen-act gate (#3412 slice 3): a
    captured, unconscious, or dead leader can no longer proclaim or enact an
    edict. This action does NOT duplicate the leadership/domain-authority
    checks — those still live in the service layer exactly as before
    (``issue_proclamation``'s ``_require_org_leadership``, ``enact_edict``'s
    ``can_administer_domain``); this action only adds the lifecycle gate in
    front of the same call. One key covers both branches (plain/org stance
    and domain-edict enactment) since they are the same "speak for the
    house" act with the same actor-lifecycle exposure — see
    ``ProclamationCreateSerializer.validate`` for the mutually-exclusive
    domain/edict_kind vs. stance shape this mirrors.
    """

    key: str = "issue_proclamation"
    name: str = "Issue Proclamation"
    icon: str = "megaphone"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.models import Domain, EdictKind  # noqa: PLC0415
        from world.societies.models import StanceArchetype  # noqa: PLC0415
        from world.societies.proclamations import (  # noqa: PLC0415
            ProclamationError,
            enact_edict,
            issue_proclamation,
        )

        persona = Persona.objects.filter(pk=kwargs.get("persona_id")).first()
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_PERSONA)

        try:
            if kwargs.get("domain_id"):
                domain = Domain.objects.filter(pk=kwargs["domain_id"]).first()
                kind = EdictKind.objects.filter(pk=kwargs.get("edict_kind_id")).first()
                if domain is None or kind is None:
                    return ActionResult(success=False, message=_MSG_NO_DOMAIN_OR_EDICT)
                edict = enact_edict(domain, kind, persona, prose=kwargs.get("prose", ""))
                row = edict.proclamation
            else:
                stance = StanceArchetype.objects.filter(pk=kwargs.get("stance_id")).first()
                if stance is None:
                    return ActionResult(success=False, message=_MSG_NO_STANCE)
                org = _resolve_organization(kwargs.get("org_id"))
                row = issue_proclamation(persona, stance, prose=kwargs.get("prose", ""), org=org)
        except ProclamationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, data={"proclamation": row})


# Module-level singletons registered in actions.registry.
org_invite_action = OrgInviteAction()
org_apply_action = OrgApplyAction()
org_join_action = OrgJoinAction()
org_leave_action = OrgLeaveAction()
org_promote_action = OrgPromoteAction()
org_demote_action = OrgDemoteAction()
org_expel_action = OrgExpelAction()
issue_proclamation_action = IssueProclamationAction()
