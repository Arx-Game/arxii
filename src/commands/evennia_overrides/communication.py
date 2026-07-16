"""Evennia command overrides for communication."""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist
from evennia import Command
from evennia.utils import search

from actions.definitions.communication import (
    EmitAction,
    MutterAction,
    PemitAction,
    PoseAction,
    SayAction,
    WhisperAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry
from world.scenes.place_models import Place


def _flag_page_contact(sender_char: object, target_char: object) -> None:
    """Fire BlockContactFlag for a page from a blocked player to the blocker (#1278/#2088).

    Page is OOC (no scene); ``BlockContactFlag.scene`` is nullable. The service
    no-ops when no active block exists, and dedupes per (blocker, blocked, scene=None).
    """
    if sender_char is None or target_char is None:
        return
    try:
        initiator_persona = sender_char.sheet_data.primary_persona
        target_persona = target_char.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist):
        return
    if initiator_persona is None or target_persona is None:
        return
    from world.scenes.block_services import flag_blocked_contact_attempt  # noqa: PLC0415

    flag_blocked_contact_attempt(
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        scene=None,
    )


def _ooc_muted_by(*, receiver_account: object, sender_char: object) -> bool:
    """True if the receiver has OOC-muted the sender's active persona (#2087).

    Page delivery check: if the receiver muted the sender's OOC, the page is
    silently dropped (the muter chose not to see this persona's OOC content).
    """
    try:
        sender_persona = sender_char.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist):
        return False
    if sender_persona is None:
        return False
    from world.scenes.mute_services import ooc_muted_persona_ids_for_viewer  # noqa: PLC0415

    muted_ids = ooc_muted_persona_ids_for_viewer(viewer_account=receiver_account)
    return sender_persona.pk in muted_ids


class CmdSay(ArxCommand):
    """Speak aloud to the room."""

    key = "say"
    locks = "cmd:all()"
    action = SayAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Say what?"
            raise CommandError(msg)
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result


class CmdWhisper(ArxCommand):
    """Whisper something to a target."""

    key = "whisper"
    locks = "cmd:all()"
    action = WhisperAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if "=" not in args:
            msg = "Usage: whisper <target>=<text>"
            raise CommandError(msg)
        target_name, text = args.split("=", 1)
        target_name = target_name.strip()
        text = text.strip()
        if not target_name or not text:
            msg = "Usage: whisper <target>=<text>"
            raise CommandError(msg)
        target = self.caller.search(target_name)
        if not target:
            msg = f"Could not find '{target_name}'."
            raise CommandError(msg)
        return {"target": target, "text": text}


class CmdPage(FrontendMetadataMixin, Command):  # ty: ignore[invalid-base]
    """Send a private message to the player of a character."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "page character=message",
            "params_schema": {
                "character": {
                    "type": "string",
                    "widget": "character-search",
                    "options_endpoint": "/api/characters/online/",
                },
                "message": {"type": "string"},
            },
        },
    ]

    key = "page"
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:  # noqa: PLR0911 — sequential guard clauses for a dispatcher
        """Execute the page command."""
        if not self.args or "=" not in self.args:
            self.caller.msg("Usage: page <character>=<message>")
            return

        charname, text = [part.strip() for part in self.args.split("=", 1)]
        if not charname or not text:
            self.caller.msg("Usage: page <character>=<message>")
            return

        characters = search.object_search(charname, exact=True)
        if not characters:
            self.caller.msg(f"Could not find character '{charname}'.")
            return
        if len(characters) > 1:
            self.caller.msg(f"Multiple characters found matching '{charname}'.")
            return

        character = characters[0]
        try:
            _ = character.sheet_data.roster_entry
        except ObjectDoesNotExist:
            self.caller.msg(f"Character '{charname}' is not on the roster.")
            return

        account = character.active_account
        if not account:
            self.caller.msg(f"Character '{charname}' has no active player.")
            return

        # Quiet-mode (#1463) reach gating, both directions, keyed off the account↔account
        # allowlist. CmdPage is an AccountCmdSet command, so self.caller is the sender's
        # account; the per-character hidden flag is read on the sender's session puppet and
        # on the resolved target.
        from world.scenes.presence import (  # noqa: PLC0415
            account_on_allowlist,
            character_appears_offline,
        )

        # Suppression justified: Evennia cmdhandler sets .session at runtime.
        session = getattr(self, "session", None)  # noqa: GETATTR_LITERAL
        sender_char = session.puppet if session is not None else None
        # (a) A hidden character can only page people on their own allowlist — so they never
        #     strand a non-whitelisted friend who then can't reply (the friend would just see
        #     "offline"). Self-explaining refusal, since the sender may have forgotten.
        if (
            sender_char is not None
            and character_appears_offline(sender_char)
            and not account_on_allowlist(owner_account=self.caller, viewer_account=account)
        ):
            self.caller.msg(
                "You're hidden (appearing offline), so you can only page people on your "
                "allowlist. Use 'unhide' to come back online first."
            )
            return
        # (b) A hidden target is unreachable to anyone off their allowlist — the SAME message
        #     as if they were simply offline, so quiet mode never leaks.
        if character_appears_offline(character) and not account_on_allowlist(
            owner_account=account, viewer_account=self.caller
        ):
            self.caller.msg(f"Character '{charname}' is not online.")
            return

        # #2087 — OOC mute: if the receiving account has OOC-muted the sender's persona,
        # silently drop the page (the muter chose not to see this persona's OOC content).
        if sender_char is not None and _ooc_muted_by(
            receiver_account=account, sender_char=sender_char
        ):
            self.caller.msg(f"You page {character.key}: {text}")
            return

        character.msg(f"{self.caller.key} pages: {text}")
        self.caller.msg(f"You page {character.key}: {text}")

        # #1278/#2088 — flag circumvention: a blocked player paging the blocker via
        # another identity. OOC (no scene); the service no-ops when no active block
        # exists, and dedupes per (blocker, blocked, scene=None).
        _flag_page_contact(sender_char, character)


class CmdTabletalk(ArxCommand):
    """Send a message to everyone at your current place (table, corner, etc.)."""

    key = "tt"
    aliases: ClassVar[list[str]] = ["tabletalk"]
    locks = "cmd:all()"
    action = PoseAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Tabletalk what?"
            raise CommandError(msg)
        place = self._get_current_place()
        if place is None:
            msg = "You are not at a place. Join one first."
            raise CommandError(msg)
        return {"text": text, "place": place}

    def _get_current_place(self) -> Place | None:
        """Get the place the character is currently at."""
        from world.scenes.place_models import PlacePresence  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
            persona = sheet.primary_persona
        except (AttributeError, ObjectDoesNotExist):
            return None
        presence = PlacePresence.objects.filter(persona=persona).first()
        return presence.place if presence else None


class CmdPose(ArxCommand):
    """Pose an action to the room (prepends character name).

    Traditional MUSH convention: ``emote`` is an alias for pose (name-prefixed).
    Use ``emit`` for raw text with no automatic name prefix.
    """

    key = "pose"
    aliases: ClassVar[list[str]] = ["emote"]
    locks = "cmd:all()"
    action = PoseAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Pose what?"
            raise CommandError(msg)
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result


class CmdMutter(ArxCommand):
    """Mutter to specific listeners; the room catches a fragment (#905).

    Usage: mutter <name>[,<name>...]=<text>
    """

    key = "mutter"
    locks = "cmd:all()"
    action = MutterAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if "=" not in args:
            msg = "Usage: mutter <name>[,<name>...]=<text>"
            raise CommandError(msg)
        names_part, text = args.split("=", 1)
        text = text.strip()
        names = [n.strip() for n in names_part.split(",") if n.strip()]
        if not names or not text:
            msg = "Usage: mutter <name>[,<name>...]=<text>"
            raise CommandError(msg)
        receivers = []
        for name in names:
            target = self.caller.search(name)
            if not target:
                msg = f"Could not find '{name}'."
                raise CommandError(msg)
            receivers.append(target)
        return {"receivers": receivers, "text": text}


class CmdPemit(ArxCommand):
    """GM private narrative emit to specific characters (#906).

    Usage: pemit <name>[,<name>...]=<text>

    Delivers GM narration only to the listed characters; the persisted
    interaction is receiver-scoped, so nobody else (or the log) sees more
    than the receivers heard. Works in and out of scenes.

    Requires STARTING-tier GM trust or higher (or staff) -- gated by
    ``PemitAction``'s ``MinimumGMLevelPrerequisite`` (#2117). The command
    lock is ``cmd:all()``; real authorization lives entirely in the Action.
    """

    key = "pemit"
    locks = "cmd:all()"
    action = PemitAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if "=" not in args:
            msg = "Usage: pemit <name>[,<name>...]=<text>"
            raise CommandError(msg)
        names_part, text = args.split("=", 1)
        text = text.strip()
        names = [n.strip() for n in names_part.split(",") if n.strip()]
        if not names or not text:
            msg = "Usage: pemit <name>[,<name>...]=<text>"
            raise CommandError(msg)
        receivers = []
        for name in names:
            target = self.caller.search(name)
            if not target:
                msg = f"Could not find '{name}'."
                raise CommandError(msg)
            receivers.append(target)
        return {"receivers": receivers, "text": text}


class CmdEmit(ArxCommand):
    """Emit raw text to the room (no character name prepended).

    Classic MUSH emit: the text appears as-is. The interaction metadata
    still records who wrote it, but the content has no automatic prefix.
    """

    key = "emit"
    locks = "cmd:all()"
    action = EmitAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Emit what?"
            raise CommandError(msg)
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result
