"""The partner's answer to an anima ritual that reached for them (#5280).

When a player character takes part in someone's anima ritual, the outward part of what it
earns the performer waits on the performance (``endorsement=PENDING``) until the partner says
whether the ritual took hold of them. Endorse grants the held part to the performer through the
resonance ledger; Withhold grants nothing; a scene that finishes with the question unanswered
lapses it. Each of the three is final: a row that is no longer pending takes no further answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import AnimaRitualEndorsement, GainSource
from world.magic.exceptions import AnimaRitualAnswerError
from world.magic.models import AnimaRitualPerformance, CharacterResonance, Resonance
from world.magic.services.resonance import grant_resonance

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene

NOT_WAITING = "That ritual is not waiting for your answer."


def pending_endorsements_for(sheet: CharacterSheet) -> QuerySet[AnimaRitualPerformance]:
    """The rituals waiting for ``sheet``'s answer, newest first."""
    return AnimaRitualPerformance.objects.filter(
        target_character=sheet, endorsement=AnimaRitualEndorsement.PENDING
    ).select_related("performer_persona", "outward_resonance__affinity", "ritual")


def _close(performance: AnimaRitualPerformance, answer: str) -> None:
    """Settle ``performance`` at ``answer``: the held part is spent, whatever the answer."""
    performance.endorsement = answer
    performance.outward_amount_pending = 0
    performance.save(update_fields=["endorsement", "outward_amount_pending"])


def _scene_is_over(scene_id: int | None) -> bool:
    """True when the ritual's scene is gone (``None``) or finished, read from the database."""
    from world.scenes.models import Scene  # noqa: PLC0415

    if scene_id is None:
        return True
    finished = Scene.objects.filter(pk=scene_id).values_list("date_finished", flat=True).first()
    return finished is not None


def _settle(
    partner_sheet: CharacterSheet,
    performance: AnimaRitualPerformance,
    held: dict,
    *,
    endorse: bool,
) -> str:
    """Settle a pending ritual the partner may answer, inside the row lock; ``held`` is the row
    as the lock read it. Returns the partner's read-back line."""
    from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    performer_sheet = performance.performer_persona.character_sheet
    partner_name = active_persona_for_sheet(partner_sheet).name
    performer_name = performance.performer_persona.name
    outward = (
        Resonance.objects.filter(pk=held["outward_resonance_id"]).first()
        if held["outward_resonance_id"] is not None
        else None
    )
    # The partner's own line reuses the endorsement wording of a scene entry
    # (``SceneEntryEndorseAction``) and names the resonance the ritual reached for.
    ritual_for = f"{performer_name}'s ritual"
    if outward is not None:
        ritual_for += f" for {outward.name}"
    if not endorse:
        _close(performance, AnimaRitualEndorsement.WITHHELD)
        send_stored_notice(
            performer_sheet, f"{partner_name} did not feel it.", ooc_note="Anima ritual"
        )
        return f"You do not endorse {ritual_for}."
    granted = 0
    pending = held["outward_amount_pending"]
    if (
        outward is not None
        and pending > 0
        and CharacterResonance.objects.filter(
            character_sheet=performer_sheet, resonance=outward
        ).exists()
    ):
        ledger: list = []
        grant_resonance(
            performer_sheet,
            outward,
            pending,
            source=GainSource.ANIMA_RITUAL,
            deed_label=performance.ritual.name,
            ledger_out=ledger,
        )
        granted = ledger[-1].amount
    _close(performance, AnimaRitualEndorsement.ENDORSED)
    line = f"{partner_name} felt it."
    if granted > 0 and outward is not None:
        line += f" Your {outward.name} grows by {granted}."
    send_stored_notice(performer_sheet, line, ooc_note="Anima ritual")
    return f"You endorse {ritual_for}."


def answer_anima_ritual(
    partner_sheet: CharacterSheet, performance: AnimaRitualPerformance, *, endorse: bool
) -> str:
    """Take the partner's answer to ``performance`` and return the line they read back.

    The row is locked and its answer read from the database, so a second answer (a double
    click, a telnet and a web answer together) finds it settled and grants nothing more. Only
    the character the ritual reached for may answer, and only while it is pending and its scene
    is still going: a ritual whose scene is finished or gone is lapsed here, whichever route
    ended the scene, and refused like any other that is not waiting.

    Endorse grants the held outward part to the performer, as an ``ANIMA_RITUAL`` grant, if she
    still holds the outward resonance (the ritual feeds the resonances she already has), and
    tells her "<partner> felt it. Your <outward> grows by N." Withhold grants nothing and tells
    her "<partner> did not feel it."

    Raises:
        AnimaRitualAnswerError: the ritual is not pending, is not the partner's to answer, or
            its scene is over.
    """
    with transaction.atomic():
        # Read the answer through the lock, never from the identity-mapped instance: another
        # process may have settled the row since this one cached it.
        held = (
            AnimaRitualPerformance.objects.select_for_update()
            .filter(pk=performance.pk)
            .values(
                "endorsement",
                "target_character_id",
                "outward_amount_pending",
                "outward_resonance_id",
                "scene_id",
            )
            .first()
        )
        if (
            held is None
            or held["endorsement"] != AnimaRitualEndorsement.PENDING
            or held["target_character_id"] != partner_sheet.pk
            or performance.performer_persona is None
        ):
            raise AnimaRitualAnswerError(NOT_WAITING)
        line = None
        if _scene_is_over(held["scene_id"]):
            _close(performance, AnimaRitualEndorsement.LAPSED)
        else:
            line = _settle(partner_sheet, performance, held, endorse=endorse)
    if line is None:
        # Raised after the block so the lapse above is committed, not rolled back with it.
        raise AnimaRitualAnswerError(NOT_WAITING)
    return line


def lapse_pending_endorsements(scene: Scene) -> int:
    """Lapse every answer still pending for ``scene``'s rituals and return how many.

    A ritual's question is asked inside its scene; once the scene finishes, the partner can no
    longer say whether it took hold, so the held part is never granted.
    """
    with transaction.atomic():
        rows = list(
            AnimaRitualPerformance.objects.select_for_update().filter(
                scene=scene, endorsement=AnimaRitualEndorsement.PENDING
            )
        )
        for row in rows:
            _close(row, AnimaRitualEndorsement.LAPSED)
    return len(rows)
