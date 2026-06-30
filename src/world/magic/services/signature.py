"""Signature-bonus selection service (#1582).

Player-facing interface for choosing, moving, or clearing a SignatureMotifBonus
on a TECHNIQUE-kind Thread.  Four public functions:

- ``available_signature_bonuses(character_sheet)`` — menu of qualifying bonuses.
- ``set_signature_bonus(thread, bonus)`` — choose / replace a bonus on a thread.
- ``clear_signature_bonus(thread)`` — remove the current bonus from a thread.
- ``signature_bonus_for(character, technique)`` — cast-wiring read (Tasks 5–6).

All reads go through the cached ``character.threads`` handler (never a fresh
``Thread.objects.filter``), mirroring the pattern in
``world/magic/specialization/services.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import TargetKind

if TYPE_CHECKING:
    from world.magic.models.signature import SignatureMotifBonus
    from world.magic.models.threads import Thread


def available_signature_bonuses(character_sheet) -> list[SignatureMotifBonus]:
    """Return every SignatureMotifBonus the character currently qualifies for.

    Iterates the full catalog and delegates gate evaluation to
    ``SignatureMotifBonus.qualifies_for(character_sheet)`` (Task 2).

    Args:
        character_sheet: The ``CharacterSheet`` whose Motif gates are evaluated.

    Returns:
        A list of qualifying ``SignatureMotifBonus`` catalog rows (may be empty).
    """
    from world.magic.models.signature import SignatureMotifBonus  # noqa: PLC0415

    return [
        bonus for bonus in SignatureMotifBonus.objects.all() if bonus.qualifies_for(character_sheet)
    ]


def set_signature_bonus(thread: Thread, bonus: SignatureMotifBonus) -> Thread:
    """Attach ``bonus`` to ``thread`` as its active signature bonus.

    Guards (in order):
    1. ``thread.target_kind == TECHNIQUE`` — else ``NotATechniqueThread``.
    2. ``bonus.qualifies_for(thread.owner)`` — else ``SignatureBonusNotAvailable``.
    3. The owner knows the technique (``CharacterTechnique`` row exists) — else
       ``TechniqueNotOwned``.

    After saving, invalidates ``character.threads`` so the change is immediately
    visible through the cached handler.

    Args:
        thread: The Thread that will carry the bonus (must be TECHNIQUE-kind).
        bonus: The SignatureMotifBonus to attach.

    Returns:
        The updated ``Thread`` instance.

    Raises:
        NotATechniqueThread: ``thread.target_kind != TECHNIQUE``.
        SignatureBonusNotAvailable: The bonus gate is not satisfied by the owner's Motif.
        TechniqueNotOwned: The owner has no CharacterTechnique for this thread's technique.
    """
    from world.magic.exceptions import (  # noqa: PLC0415
        NotATechniqueThread,
        SignatureBonusNotAvailable,
        TechniqueNotOwned,
    )
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    if thread.target_kind != TargetKind.TECHNIQUE:
        raise NotATechniqueThread

    if not bonus.qualifies_for(thread.owner):
        raise SignatureBonusNotAvailable

    if not CharacterTechnique.objects.filter(
        character=thread.owner, technique=thread.target_technique
    ).exists():
        raise TechniqueNotOwned

    with transaction.atomic():
        thread.signature_bonus = bonus
        thread.save(update_fields=["signature_bonus", "updated_at"])

    thread.owner.character.threads.invalidate()
    return thread


def clear_signature_bonus(thread: Thread) -> Thread:
    """Remove the current signature bonus from ``thread`` (set to None).

    Idempotent — safe to call when ``thread.signature_bonus`` is already None.

    After saving, invalidates ``character.threads`` so the change is visible
    through the cached handler.

    Args:
        thread: The Thread whose signature bonus should be cleared.

    Returns:
        The updated ``Thread`` instance.
    """
    with transaction.atomic():
        thread.signature_bonus = None
        thread.save(update_fields=["signature_bonus", "updated_at"])

    thread.owner.character.threads.invalidate()
    return thread


def signature_bonus_for(character, technique) -> SignatureMotifBonus | None:
    """Return the SignatureMotifBonus active on the character's technique thread, or None.

    Resolves the character's active (non-retired) TECHNIQUE-kind thread for
    ``technique`` via the cached ``character.threads`` handler (same read pattern
    as ``resolve_specialized_variant`` / ``gift_resonances_for`` in
    ``specialization/services.py``) — never a fresh ``Thread.objects.filter``.

    Returns ``None`` when:
    - The character has no active TECHNIQUE thread for ``technique``.
    - The thread has no signature bonus set.

    Consumed by the cast wiring in Tasks 5–6.

    Args:
        character: The game Character (not CharacterSheet) whose threads are read.
        technique: The Technique whose thread to look up.

    Returns:
        The active ``SignatureMotifBonus``, or ``None``.
    """
    thread = next(
        (
            t
            for t in character.threads.all()
            if (
                t.target_kind == TargetKind.TECHNIQUE
                and t.target_technique_id == technique.pk
                and t.retired_at is None
            )
        ),
        None,
    )
    if thread is None:
        return None
    return thread.signature_bonus
