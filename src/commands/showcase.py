"""Showcase command (#2907) — the persistent fashion-modeling toggle.

Thin telnet shell over ``ShowcaseAction`` (the same seam the web will use).
While showcasing, every entrance the character makes auto-stakes cachet on
the statement; payouts settle at the weekly cron. No business logic here.
"""

from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage: showcase — status; showcase <item name or #id> — highlight one "
    "piece; showcase outfit <name or #id> — highlight an ensemble; "
    "showcase off — stop."
)

_SUBVERB_OFF = "off"
_SUBVERB_OUTFIT = "outfit"
_SUBVERB_STATUS = "status"


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
    locks = "cmd:all()"

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
