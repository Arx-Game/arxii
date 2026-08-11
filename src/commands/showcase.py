"""Showcase command (#2907) — the persistent fashion-modeling toggle.

Thin telnet shell over ``ShowcaseAction`` (the same seam the web will use).
While showcasing, every entrance the character makes auto-stakes cachet on
the statement; payouts settle at the weekly cron. No business logic here.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage: showcase - status; showcase <item name or #id> - highlight one "
    "piece; showcase outfit <name or #id> - highlight an ensemble; "
    "showcase off - stop."
)

_SUBVERB_OFF = "off"
_SUBVERB_OUTFIT = "outfit"
_SUBVERB_STATUS = "status"

# Lock string shared by every command in this module — extracted to satisfy
# the duplicated-literal SonarCloud smell (python:S1192).
LOCK_ALL = "cmd:all()"


class CmdShowcase(ArxCommand):
    """Choose what you are showcasing to the fashionable world.

    Usage:
        showcase                       - what you're currently showcasing + cachet
        showcase <item name or #id>    - highlight a single piece you hold
        showcase outfit <name or #id>  - highlight a saved outfit as an ensemble
        showcase off                   - stop showcasing

    While showcasing, making an entrance stakes cachet on your statement;
    the week's showings settle at the weekly cron; a good roll refunds the
    stake, and real engagement from other players pays more.
    """

    key = "showcase"
    locks = LOCK_ALL

    def func(self) -> None:
        from actions.definitions.fashion import ShowcaseAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        try:
            if not raw or raw.lower() == _SUBVERB_STATUS:
                self._show_status()
                return
            if raw.lower() == _SUBVERB_OFF:
                result = ShowcaseAction().run(actor=self.caller, mode="off")
            elif raw.lower().startswith(_SUBVERB_OUTFIT + " "):
                outfit_id = self._resolve_outfit_id(raw.split(maxsplit=1)[1].strip())
                result = ShowcaseAction().run(
                    actor=self.caller, mode="ensemble", outfit_id=outfit_id
                )
            else:
                item_id = self._resolve_item_id(raw)
                result = ShowcaseAction().run(actor=self.caller, mode="piece", item_id=item_id)
        except CommandError as err:
            self.msg(str(err))
            return
        if result.message:
            self.msg(result.message)

    def _show_status(self) -> None:
        from world.items.models import ShowcaseState  # noqa: PLC0415
        from world.items.services.fashion_showcase import get_or_create_wallet  # noqa: PLC0415

        sheet = self.caller.sheet_data
        wallet = get_or_create_wallet(sheet)
        state = ShowcaseState.objects.filter(character_sheet=sheet, is_active=True).first()
        if state is None:
            self.msg(f"You are not showcasing anything. Cachet: {wallet.balance}.\n{_USAGE}")
            return
        if state.item is not None:
            subject = f"the piece {state.item.display_name}"
        elif state.outfit is not None:
            subject = f"the {state.outfit.name} ensemble"
        else:
            subject = "nothing in particular"
        self.msg(f"You are showcasing {subject}. Cachet: {wallet.balance}.")

    def _resolve_outfit_id(self, token: str) -> int:
        from world.items.models import Outfit  # noqa: PLC0415

        sheet = self.caller.sheet_data
        if token.lstrip("#").isdigit():
            return int(token.lstrip("#"))
        outfit = Outfit.objects.filter(character_sheet=sheet, name__iexact=token).first()
        if outfit is None:
            msg = f"You have no outfit named '{token}'."
            raise CommandError(msg)
        return outfit.pk

    def _resolve_item_id(self, token: str) -> int:
        from world.items.models import ItemInstance  # noqa: PLC0415

        sheet = self.caller.sheet_data
        if token.lstrip("#").isdigit():
            return int(token.lstrip("#"))
        matches = list(
            ItemInstance.objects.filter(holder_character_sheet=sheet, custom_name__icontains=token)[
                :2
            ]
        ) or list(
            ItemInstance.objects.filter(
                holder_character_sheet=sheet, template__name__icontains=token
            )[:2]
        )
        if not matches:
            msg = f"You hold nothing matching '{token}'."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one piece matches '{token}' — use its #id."
            raise CommandError(msg)
        return matches[0].pk


class CmdReveal(ArxCommand):
    """Show a body part, worn piece, or marking (#2985).

    Usage:
        show <body part>        (show torso, show left arm)
        show <item name or #id>
        show <marking name>
        reveal ...              (same command)

    Declarative: name the goal and the layer walk parts whatever covers it.
    Showing a body part bares it down to skin — coat parts, doublet opens,
    the runes show. Showing a piece opens only the layers above it: the hot
    doublet shows, the skin stays covered. Dressing at the region closes
    everything back up; so does conceal.
    """

    key = "reveal"
    aliases = ["show"]
    locks = LOCK_ALL

    def func(self) -> None:
        from actions.definitions.fashion import RevealAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            self.msg("Show what? Usage: show <body part, item, or marking>")
            return
        kwargs = _resolve_show_target(self.caller, raw)
        if kwargs is None:
            return
        result = RevealAction().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)


class CmdCover(ArxCommand):
    """Conceal a body part, worn piece, or marking (#2985).

    Usage:
        conceal <body part>     (conceal torso, conceal left arm)
        conceal <item name or #id>
        conceal <marking name>
        cover ...               (same command)

    The inverse of show — close the worn-open layers back up. Honest when
    fabric cannot help: if nothing you wear covers it, it says so.
    """

    key = "cover"
    aliases = ["conceal"]
    locks = LOCK_ALL

    def func(self) -> None:
        from actions.definitions.fashion import CoverUpAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            self.msg("Conceal what? Usage: conceal <body part, item, or marking>")
            return
        kwargs = _resolve_show_target(self.caller, raw)
        if kwargs is None:
            return
        result = CoverUpAction().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)


def _resolve_show_target(caller: Any, token: str) -> dict | None:
    """Resolve a show/conceal target: body part first, then worn item, then marking.

    Returns action kwargs, or None after messaging the caller.
    """
    from world.items.constants import BodyRegion  # noqa: PLC0415

    lowered = token.lower().replace(" ", "_")
    if lowered in BodyRegion.values:
        return {"body_region": lowered}
    for region in BodyRegion:
        if region.label.lower() == token.lower():
            return {"body_region": region.value}
    try:
        return {"item_id": _resolve_worn_item_id(caller, token)}
    except CommandError as item_err:
        try:
            marking_id = _resolve_marking_id_or_none(caller, token)
        except CommandError as marking_err:
            caller.msg(str(marking_err))
            return None
        if marking_id is None:
            caller.msg(str(item_err))
            return None
        return {"marking_id": marking_id}


def _resolve_marking_id_or_none(caller: Any, token: str) -> int | None:
    """Resolve one of the caller's TRUE-form markings by name, or None.

    Returns None on no match; raises CommandError on an ambiguous match so
    the caller sees the disambiguation rather than the item-not-found text.
    """
    from world.forms.models import FormMarking, FormType  # noqa: PLC0415

    sheet = caller.sheet_data
    matches = list(
        FormMarking.objects.filter(
            form__character=sheet,
            form__form_type=FormType.TRUE,
            name__icontains=token,
        )[:2]
    )
    if not matches:
        return None
    if len(matches) > 1:
        msg = f"More than one marking matches '{token}' — be more specific."
        raise CommandError(msg)
    return matches[0].pk


def _resolve_worn_item_id(caller: Any, token: str) -> int:
    """Resolve a WORN item by #id or name (worn scope, unlike the held scope above)."""
    from world.items.models import EquippedItem  # noqa: PLC0415

    if token.lstrip("#").isdigit():
        return int(token.lstrip("#"))
    sheet = caller.sheet_data
    worn_ids = set(
        EquippedItem.objects.filter(character_id=sheet.character_id).values_list(
            "item_instance_id", flat=True
        )
    )
    from world.items.models import ItemInstance  # noqa: PLC0415

    matches = list(
        ItemInstance.objects.filter(pk__in=worn_ids, custom_name__icontains=token)[:2]
    ) or list(ItemInstance.objects.filter(pk__in=worn_ids, template__name__icontains=token)[:2])
    if not matches:
        msg = f"You wear nothing matching '{token}'."
        raise CommandError(msg)
    if len(matches) > 1:
        msg = f"More than one worn piece matches '{token}' — use its #id."
        raise CommandError(msg)
    return matches[0].pk
