"""Estate settlement services (#1985).

``open_settlement`` is called from the single death writer
(``world.vitals.services._mark_dead``); ``execute_settlement`` is the ONE
idempotent execution path all three doors call (funeral finish, executor
will-reading, deadline sweeper). Spec: issue #1985 body.
"""

from datetime import timedelta
import logging

from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.estates.models import EstateSettlement, Will, WillExecutor, get_estate_config

logger = logging.getLogger(__name__)


def will_is_frozen(character_sheet: CharacterSheet) -> bool:
    """True once a settlement window exists — the will can no longer be edited."""
    return EstateSettlement.objects.filter(character_sheet=character_sheet).exists()


def open_settlement(character_sheet: CharacterSheet) -> EstateSettlement:
    """Open the settlement window at death; idempotent per sheet.

    Called from ``_mark_dead``. The deadline arms the sweeper door
    (``settlement_window_days`` real days, config PLACEHOLDER); the funeral
    and will-reading doors may execute any time before it.
    """
    config = get_estate_config()
    settlement, created = EstateSettlement.objects.get_or_create(
        character_sheet=character_sheet,
        defaults={"deadline": timezone.now() + timedelta(days=config.settlement_window_days)},
    )
    if created:
        _notify_executors(settlement)
    return settlement


def _notify_executors(settlement: EstateSettlement) -> None:
    """Tell each executor the window opened — best-effort, never blocks death."""
    will = Will.objects.filter(character_sheet=settlement.character_sheet).first()
    if will is None:
        return
    deceased_name = str(settlement.character_sheet)
    # PLACEHOLDER player-facing copy — Apostate rewrite pending (#1985).
    body = (
        f"You are named an executor of {deceased_name}'s will. Their estate may be "
        f"settled at a will-reading or funeral; if neither happens it settles on its own."
    )
    for executor in WillExecutor.objects.filter(will=will).select_related("persona"):
        character = executor.persona.character_sheet.character
        try:
            character.msg(body)
        except Exception:
            logger.exception("executor notify character.msg failed for %s", executor.pk)
        account = character.db_account
        if account is None:
            continue
        payload = {"deceased": deceased_name, "deadline": settlement.deadline.isoformat()}
        try:
            account.msg(estate_settlement_opened=((), payload))
        except Exception:
            logger.exception("estate_settlement_opened push failed for %s", account.pk)
