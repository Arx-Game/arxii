"""Consent preference management actions (#1487)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


_MSG_NO_IDENTITY = "You have no character identity to manage consent for."
_MSG_NOT_YOUR_TENURE = "You can only manage consent for your own characters."
_MSG_NO_CATEGORY = "No consent category named '{}'"

_MODE_DEFAULT = "default"


def _resolve_owner_tenure(actor: ObjectDB, tenure_id: int | None):
    sheet = getattr(actor, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        return None, _MSG_NO_IDENTITY
    try:
        actor_player = actor.account.player_data
    except (AttributeError, ObjectDoesNotExist):
        return None, _MSG_NO_IDENTITY
    from world.roster.models import RosterTenure  # noqa: PLC0415

    try:
        tenure = RosterTenure.objects.select_related("player_data").get(pk=tenure_id)
    except RosterTenure.DoesNotExist:
        return None, _MSG_NOT_YOUR_TENURE
    if tenure.player_data_id != actor_player.pk:
        return None, _MSG_NOT_YOUR_TENURE
    return tenure, ""


def _resolve_category(key: str | None):
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415

    if key is None:
        return None, _MSG_NO_CATEGORY.format(key)
    try:
        return SocialConsentCategory.objects.get_by_natural_key(key), ""
    except SocialConsentCategory.DoesNotExist:
        return None, _MSG_NO_CATEGORY.format(key)


@dataclass
class SetSocialConsentPreferenceAction(Action):
    """Toggle the master social-consent opt-out switch for a tenure."""

    key: str = "set_social_consent_preference"
    name: str = "Set Social Consent Preference"
    icon: str = "shield"
    category: str = "consent"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.consent.services import set_social_consent_preference  # noqa: PLC0415

        tenure, err = _resolve_owner_tenure(actor, kwargs.get("tenure_id"))
        if tenure is None:
            return ActionResult(success=False, message=err)
        allow = kwargs.get("allow_social_actions")
        if not isinstance(allow, bool):
            return ActionResult(
                success=False,
                message="allow_social_actions must be a boolean.",
            )
        set_social_consent_preference(tenure, allow)
        state = "allowed" if allow else "blocked"
        return ActionResult(success=True, message=f"Social actions are now {state}.")


@dataclass
class SetSocialConsentCategoryRuleAction(Action):
    """Set or clear a per-category consent mode."""

    key: str = "set_social_consent_category_rule"
    name: str = "Set Consent Category Rule"
    icon: str = "shield"
    category: str = "consent"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.consent.services import (  # noqa: PLC0415
            remove_social_consent_category_rule,
            set_social_consent_category_rule,
        )

        tenure, err = _resolve_owner_tenure(actor, kwargs.get("tenure_id"))
        if tenure is None:
            return ActionResult(success=False, message=err)
        category, err = _resolve_category(kwargs.get("category_key"))
        if category is None:
            return ActionResult(success=False, message=err)
        mode = kwargs.get("mode")
        try:
            preference = tenure.social_consent_preference
        except ObjectDoesNotExist:
            from world.consent.services import set_social_consent_preference  # noqa: PLC0415

            preference = set_social_consent_preference(tenure, True)
        if mode == _MODE_DEFAULT or mode is None:
            remove_social_consent_category_rule(preference, category)
            return ActionResult(
                success=True,
                message=f"{category.name} reverted to default (everyone).",
            )
        try:
            set_social_consent_category_rule(preference, category, mode)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))
        return ActionResult(
            success=True,
            message=f"{category.name} set to {mode}.",
        )


@dataclass
class AddSocialConsentWhitelistAction(Action):
    """Allow a character to target the owner in a restricted category."""

    key: str = "add_social_consent_whitelist"
    name: str = "Add Consent Whitelist Entry"
    icon: str = "shield"
    category: str = "consent"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.consent.services import (  # noqa: PLC0415
            add_social_consent_whitelist,
            set_social_consent_preference,
        )
        from world.roster.models import RosterTenure  # noqa: PLC0415

        tenure, err = _resolve_owner_tenure(actor, kwargs.get("tenure_id"))
        if tenure is None:
            return ActionResult(success=False, message=err)
        category, err = _resolve_category(kwargs.get("category_key"))
        if category is None:
            return ActionResult(success=False, message=err)
        allowed_tenure_id = kwargs.get("allowed_tenure_id")
        try:
            allowed_tenure = RosterTenure.objects.get(pk=allowed_tenure_id)
        except RosterTenure.DoesNotExist:
            return ActionResult(
                success=False,
                message="That character cannot be whitelisted.",
            )
        if allowed_tenure.end_date is not None:
            return ActionResult(
                success=False,
                message="That character is not currently active.",
            )
        preference = getattr(tenure, "social_consent_preference", None)  # noqa: GETATTR_LITERAL
        if preference is None:
            set_social_consent_preference(tenure, True)
        add_social_consent_whitelist(tenure, allowed_tenure, category)
        return ActionResult(
            success=True,
            message=f"{allowed_tenure} may target you with {category.name} actions.",
        )


@dataclass
class RemoveSocialConsentWhitelistAction(Action):
    """Remove a character from a category whitelist."""

    key: str = "remove_social_consent_whitelist"
    name: str = "Remove Consent Whitelist Entry"
    icon: str = "shield"
    category: str = "consent"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.consent.services import remove_social_consent_whitelist  # noqa: PLC0415
        from world.roster.models import RosterTenure  # noqa: PLC0415

        tenure, err = _resolve_owner_tenure(actor, kwargs.get("tenure_id"))
        if tenure is None:
            return ActionResult(success=False, message=err)
        category, err = _resolve_category(kwargs.get("category_key"))
        if category is None:
            return ActionResult(success=False, message=err)
        allowed_tenure_id = kwargs.get("allowed_tenure_id")
        try:
            allowed_tenure = RosterTenure.objects.get(pk=allowed_tenure_id)
        except RosterTenure.DoesNotExist:
            return ActionResult(
                success=False,
                message="That character is not on the list.",
            )
        removed = remove_social_consent_whitelist(tenure, allowed_tenure, category)
        if not removed:
            return ActionResult(
                success=False,
                message="That character is not on the list.",
            )
        return ActionResult(
            success=True,
            message=f"{allowed_tenure} removed from {category.name} whitelist.",
        )
