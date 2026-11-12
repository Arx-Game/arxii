"""Idempotent seed helpers for missives (#3289).

Rides The Big Button (``world.seeds.clusters``, cluster ``"messengers"``): the
universal messenger method, so a letter can be sent on a fresh clone/dev DB
without any manual authoring step. ``get_or_create`` never overwrites a row
staff have already tuned.
"""

from __future__ import annotations

from world.messengers.models import TransmissionMethod

MESSENGER_METHOD_NAME = "Messenger"


def ensure_messenger_method() -> TransmissionMethod:
    """Get-or-create the universal messenger method.

    The 30 game-minute delay is a PLACEHOLDER for staff to tune in the admin.
    """
    method, _ = TransmissionMethod.objects.get_or_create(
        name=MESSENGER_METHOD_NAME,
        defaults={
            "description": "A runner from the messenger guild carries your letter across the city.",
            "ic_delay_minutes": 30,
            "can_carry_items": True,
            "can_carry_coin": True,
            "is_universal": True,
        },
    )
    return method
