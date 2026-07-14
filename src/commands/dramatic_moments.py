"""Dramatic-moment suggestion telnet command — the ``moment`` namespace (#2183).

The telnet twin of the web ``DramaticMomentSuggestionViewSet``: both converge on the
account-authorized ``ConfirmDramaticMomentSuggestionAction`` /
``DismissDramaticMomentSuggestionAction`` (``actions/definitions/dramatic_moments.py``),
mirroring ``CmdEvent``'s host-lifecycle dispatch (``actor=None, account=self.caller.account``).

    moment suggestions   — list PENDING suggestions for the active scene here (GM/owner/staff only)
    moment confirm <id>  — confirm one (mints a DramaticMomentTag + resonance/renown)
    moment dismiss <id>  — dismiss one

No business logic lives here; the GM gate and resolution live entirely in the Actions
and service functions. ``moment suggestions`` reuses the same
``_account_can_gm_scene`` predicate the confirm/dismiss Actions gate on — a non-GM
player must never see pending suggestions about themselves (oracle leak, #2183 review).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.scenes.models import Scene

_SUBVERB_SUGGESTIONS = "suggestions"
_SUBVERB_CONFIRM = "confirm"
_SUBVERB_DISMISS = "dismiss"
_SUBVERB_TAG = "tag"
_TAG_LIST_ARG = "list"
_USAGE = "Usage: moment suggestions|confirm <id>|dismiss <id>|tag <character>=<type>|tag list"


class CmdMoment(ArxCommand):
    """List and resolve dramatic-moment suggestions; tag dramatic moments.

    Usage:
        moment suggestions   — list PENDING suggestions for the active scene here
        moment confirm <id>  — confirm a suggestion (mints the dramatic-moment tag)
        moment dismiss <id>  — dismiss a suggestion
        moment tag <char>=<type> — tag a character's dramatic moment (GM)
        moment tag list      — list available dramatic-moment types (GM)

    GM-gated: only the active scene's GM, owner, or staff may list, confirm,
    dismiss, or tag.
    """

    key = "moment"
    locks = "cmd:all()"
    action = None  # dispatches to multiple actions

    def func(self) -> None:
        """Route the leading subverb; bare ``moment`` shows usage."""
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_USAGE)
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if subverb == _SUBVERB_SUGGESTIONS:
            self._list_suggestions()
        elif subverb == _SUBVERB_CONFIRM:
            self._resolve(rest, confirm=True)
        elif subverb == _SUBVERB_DISMISS:
            self._resolve(rest, confirm=False)
        elif subverb == _SUBVERB_TAG:
            self._handle_tag(rest)
        else:
            raise CommandError(_USAGE)

    # -- resolution helpers ---------------------------------------------------

    def _active_scene(self) -> Scene:
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        scene = get_active_scene(getattr(self.caller, "location", None))  # noqa: GETATTR_LITERAL
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)
        return scene

    def _account(self) -> AccountDB:
        """The caller's account (confirm/dismiss are account-authorized)."""
        account = self.caller.account
        if account is None:
            msg = "You must be logged in to do that."
            raise CommandError(msg)
        return account

    # -- subverb handlers -------------------------------------------------------

    def _list_suggestions(self) -> None:
        from actions.definitions.dramatic_moments import (  # noqa: PLC0415
            _account_can_gm_scene,
        )
        from world.magic.constants import SuggestionStatus  # noqa: PLC0415
        from world.magic.models.dramatic_moment import DramaticMomentSuggestion  # noqa: PLC0415

        scene = self._active_scene()
        if not _account_can_gm_scene(self.caller.account, scene):
            msg = "Only the scene's GM, owner, or staff may view pending suggestions."
            raise CommandError(msg)
        suggestions = list(
            DramaticMomentSuggestion.objects.filter(scene=scene, status=SuggestionStatus.PENDING)
            .select_related("moment_type", "character_sheet", "character_sheet__character")
            .order_by("-created_at")
        )
        if not suggestions:
            self.msg("No pending dramatic-moment suggestions in this scene.")
            return
        lines = ["|wPending dramatic-moment suggestions:|n"]
        for suggestion in suggestions:
            sheet = suggestion.character_sheet
            char_name = sheet.character.db_key if sheet is not None else "?"
            lines.append(
                f"  #{suggestion.pk}: {suggestion.moment_type.label} — {char_name} "
                f"(success level {suggestion.success_level})"
            )
        lines.append("\nUse: moment confirm <id> / moment dismiss <id>")
        self.msg("\n".join(lines))

    def _resolve(self, rest: str, *, confirm: bool) -> None:
        from actions.definitions.dramatic_moments import (  # noqa: PLC0415
            ConfirmDramaticMomentSuggestionAction,
            DismissDramaticMomentSuggestionAction,
        )

        verb = _SUBVERB_CONFIRM if confirm else _SUBVERB_DISMISS
        if not rest or not rest.isdigit():
            msg = f"Usage: moment {verb} <id>"
            raise CommandError(msg)
        suggestion_id = int(rest)
        account = self._account()
        action_cls = (
            ConfirmDramaticMomentSuggestionAction
            if confirm
            else DismissDramaticMomentSuggestionAction
        )
        result = action_cls().run(actor=None, account=account, suggestion_id=suggestion_id)
        if result.message:
            self.msg(result.message)

    # -- tag subverb -----------------------------------------------------------

    def _handle_tag(self, rest: str) -> None:
        """``moment tag <character>=<type label>`` or ``moment tag list``."""
        if not rest:
            raise CommandError(_USAGE)
        if rest.lower() == _TAG_LIST_ARG:
            self._handle_tag_list()
            return
        if "=" not in rest:
            raise CommandError(_USAGE)
        name, type_label = (part.strip() for part in rest.split("=", 1))
        if not name or not type_label:
            raise CommandError(_USAGE)

        scene = self._active_scene()
        account = self._account()
        from actions.definitions.dramatic_moments import _account_can_gm_scene  # noqa: PLC0415

        if not _account_can_gm_scene(account, scene):
            msg = "Only the scene's GM, owner, or staff may tag dramatic moments."
            raise CommandError(msg)

        target = self.caller.search(name, global_search=True)
        if target is None:
            return

        sheet = target.character_sheet
        if sheet is None:
            self.msg("That is not a character.")
            return

        from world.magic.models.dramatic_moment import DramaticMomentType  # noqa: PLC0415
        from world.magic.services.gain import create_dramatic_moment_tag  # noqa: PLC0415

        moment_type = DramaticMomentType.objects.filter(label__iexact=type_label).first()
        if moment_type is None:
            available = ", ".join(
                str(m.label) for m in DramaticMomentType.objects.order_by("label")
            )
            self.msg(f"No dramatic-moment type named '{type_label}'. Available: {available}")
            return

        from world.magic.exceptions import (  # noqa: PLC0415
            DramaticMomentCapExceeded,
            EndorsementValidationError,
        )

        try:
            create_dramatic_moment_tag(
                character_sheet=sheet,
                moment_type=moment_type,
                tagged_by=account,
                scene=scene,
            )
        except (EndorsementValidationError, DramaticMomentCapExceeded) as exc:
            self.msg(exc.user_message)
            return

        self.msg(
            f"You tagged {target.db_key} with '{moment_type.label}'. Resonance and renown awarded."
        )

    def _handle_tag_list(self) -> None:
        """``moment tag list`` — show available DramaticMomentType rows."""
        scene = self._active_scene()
        account = self._account()
        from actions.definitions.dramatic_moments import _account_can_gm_scene  # noqa: PLC0415

        if not _account_can_gm_scene(account, scene):
            msg = "Only the scene's GM, owner, or staff may list dramatic-moment types."
            raise CommandError(msg)

        from world.magic.models.dramatic_moment import DramaticMomentType  # noqa: PLC0415

        types = list(DramaticMomentType.objects.select_related("resonance").order_by("label"))
        if not types:
            self.msg("No dramatic-moment types are defined.")
            return
        lines = ["|wAvailable dramatic-moment types:|n"]
        lines.extend(f"  {mt.label} — {mt.resonance.name} ({mt.resonance_amount})" for mt in types)
        lines.append("\nUse: moment tag <character>=<type>")
        self.msg("\n".join(lines))
