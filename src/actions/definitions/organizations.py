"""Generic organization membership lifecycle actions (#1511).

All seven actions are REGISTRY backend singletons and share the same seam
used by the web (`dispatch_player_action`) and telnet (`CmdOrg`).
"""

from __future__ import annotations

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
from world.societies.models import OrganizationMembershipOffer

_TARGET_FILTERS = TargetFilters(in_same_scene=True, exclude_self=True)


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
            return ActionResult(success=False, message="You have no character identity.")

        target_persona = _resolve_target_persona(kwargs)
        if target_persona is None:
            return ActionResult(success=False, message="Invite whom?")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

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
            return ActionResult(success=False, message="You have no character identity.")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

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
            return ActionResult(success=False, message="You have no character identity.")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

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
            return ActionResult(success=False, message="You have no character identity.")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

        membership = active_membership_for_persona(organization, actor_persona)
        if membership is None:
            return ActionResult(
                success=False,
                message="You are not a member of that organization.",
            )

        leave_organization(membership)
        return ActionResult(
            success=True,
            message=f"You leave {organization.name}.",
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

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message="You have no character identity.")

        target_persona = _resolve_target_persona(kwargs)
        if target_persona is None:
            return ActionResult(success=False, message="Promote whom?")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

        if not _same_room(actor, target_persona):
            return ActionResult(
                success=False,
                message="You must be in the same room to promote someone.",
            )

        actor_membership = active_membership_for_persona(organization, actor_persona)
        target_membership = active_membership_for_persona(organization, target_persona)
        if target_membership is None:
            return ActionResult(
                success=False,
                message="That person is not a member of the organization.",
            )
        if actor_membership is None:
            return ActionResult(
                success=False,
                message="You are not a member of that organization.",
            )

        try:
            promote_member(target_membership, actor_membership)
        except (
            NotOrganizationMemberError,
            NotAuthorizedToManageRanksError,
            CannotPromoteError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You promote {target_persona.name} in {organization.name}.",
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

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message="You have no character identity.")

        target_persona = _resolve_target_persona(kwargs)
        if target_persona is None:
            return ActionResult(success=False, message="Demote whom?")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

        if not _same_room(actor, target_persona):
            return ActionResult(
                success=False,
                message="You must be in the same room to demote someone.",
            )

        actor_membership = active_membership_for_persona(organization, actor_persona)
        target_membership = active_membership_for_persona(organization, target_persona)
        if target_membership is None:
            return ActionResult(
                success=False,
                message="That person is not a member of the organization.",
            )
        if actor_membership is None:
            return ActionResult(
                success=False,
                message="You are not a member of that organization.",
            )

        try:
            demote_member(target_membership, actor_membership)
        except (
            NotOrganizationMemberError,
            NotAuthorizedToManageRanksError,
            CannotDemoteError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You demote {target_persona.name} in {organization.name}.",
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

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        actor_persona = _actor_persona(actor)
        if actor_persona is None:
            return ActionResult(success=False, message="You have no character identity.")

        target_persona = _resolve_target_persona(kwargs)
        if target_persona is None:
            return ActionResult(success=False, message="Expel whom?")

        organization = _resolve_organization(kwargs.get("organization_id"))
        if organization is None:
            return ActionResult(success=False, message="Which organization?")

        if not _same_room(actor, target_persona):
            return ActionResult(
                success=False,
                message="You must be in the same room to expel someone.",
            )

        actor_membership = active_membership_for_persona(organization, actor_persona)
        target_membership = active_membership_for_persona(organization, target_persona)
        if target_membership is None:
            return ActionResult(
                success=False,
                message="That person is not a member of the organization.",
            )
        if actor_membership is None:
            return ActionResult(
                success=False,
                message="You are not a member of that organization.",
            )

        try:
            expel_member(target_membership, actor_membership)
        except (
            NotOrganizationMemberError,
            NotAuthorizedToKickError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You expel {target_persona.name} from {organization.name}.",
        )


# Module-level singletons registered in actions.registry.
org_invite_action = OrgInviteAction()
org_apply_action = OrgApplyAction()
org_join_action = OrgJoinAction()
org_leave_action = OrgLeaveAction()
org_promote_action = OrgPromoteAction()
org_demote_action = OrgDemoteAction()
org_expel_action = OrgExpelAction()
