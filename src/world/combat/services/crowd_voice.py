"""Giving a crowd a voice (#4418): a character the crowd poses as in the scene.

A crowd is a set of ``CombatOpponent`` rows (a threat pool's mooks, or a swarm). To
pose as one, a GM gives it a voice: a minted story NPC whose primary persona the
rows point at through ``CombatOpponent.voice_persona``. The voice has no combat
identity. ``CombatOpponent.persona`` is never set on crowd bodies: persona-backed
opponents are notable NPCs to surges, regard, technique targeting and parley, and
the ``persona_bearing_opponent_not_ephemeral`` constraint forbids it on ephemeral
bodies anyway.

Because the voice is an ordinary story NPC on the NPC shelf, held by the GM who
voiced it, lending it to a Guide is the same ``NPCLoan`` as for any named NPC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.combat.models import CombatOpponent
    from world.scenes.models import Persona


class CrowdVoiceError(Exception):
    """A crowd voice the rules refuse; ``user_message`` is safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _crowd_description(opponents: list[CombatOpponent]) -> str:
    first = opponents[0]
    if first.threat_pool is not None and first.threat_pool.description:
        return first.threat_pool.description
    return first.description


@transaction.atomic
def voice_crowd(*, opponents: list[CombatOpponent], name: str, by: AccountDB) -> Persona:
    """Mint a voice named ``name`` for ``opponents`` and return its persona.

    The voice is minted through ``mint_story_npc`` (so ``by`` needs GM trust and
    room under their story NPC cap, and owns and holds it), carries the crowd's
    description, and stands in the encounter's room. Every row's ``voice_persona``
    is set to its primary persona.

    Raises:
        CrowdVoiceError: no rows, rows from more than one encounter, a row that
            already has a voice, or a mint refusal (trust, cap, name taken).
    """
    from world.roster.services.staff_characters import (  # noqa: PLC0415
        StaffMintError,
        mint_story_npc,
    )

    if not opponents:
        msg = "Choose the crowd to give a voice."
        raise CrowdVoiceError(msg)
    encounter_ids = {opponent.encounter_id for opponent in opponents}
    if len(encounter_ids) > 1:
        msg = "A crowd's voice speaks for one fight."
        raise CrowdVoiceError(msg)
    if any(opponent.voice_persona_id is not None for opponent in opponents):
        msg = "That crowd already has a voice."
        raise CrowdVoiceError(msg)

    try:
        character = mint_story_npc(
            gm_account=by, name=name, description=_crowd_description(opponents)
        )
    except StaffMintError as exc:
        raise CrowdVoiceError(exc.user_message) from None

    encounter = opponents[0].encounter
    room = encounter.room or encounter.scene.room
    if room is not None:
        character.location = room
        character.save(update_fields=["db_location"])

    persona = character.sheet_data.primary_persona
    for opponent in opponents:
        opponent.voice_persona = persona
        opponent.save(update_fields=["voice_persona"])
    return persona
