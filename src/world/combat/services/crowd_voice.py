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


NOT_A_CROWD_MESSAGE = "Those aren't a crowd still in the fight."
ALREADY_VOICED_MESSAGE = "That crowd already has a voice."


def _lock_and_check(opponents: list[CombatOpponent], *, voiced_ok: bool = False) -> None:
    """Lock the rows and refuse any that is no crowd body, or (unless ``voiced_ok``)
    is already voiced.

    Read as values, never instances: the identity map would hand back the cached
    rows as they were, and a voice another GM just gave them would be missed.
    """
    from world.combat.constants import OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    ids = {opponent.pk for opponent in opponents}
    rows = list(
        CombatOpponent.objects.select_for_update(of=("self",))
        .filter(pk__in=ids)
        .values_list("voice_persona_id", "persona_id", "status", "encounter__status")
    )
    if len(rows) != len(ids):
        raise CrowdVoiceError(NOT_A_CROWD_MESSAGE)
    for voice_id, persona_id, status, encounter_status in rows:
        if (
            persona_id is not None
            or status != OpponentStatus.ACTIVE
            or encounter_status == RoundStatus.COMPLETED
        ):
            raise CrowdVoiceError(NOT_A_CROWD_MESSAGE)
        if voice_id is not None and not voiced_ok:
            raise CrowdVoiceError(ALREADY_VOICED_MESSAGE)


@transaction.atomic
def voice_crowd(*, opponents: list[CombatOpponent], name: str, by: AccountDB) -> Persona:
    """Mint a voice named ``name`` for ``opponents`` and return its persona.

    The voice is minted through ``mint_story_npc`` (so ``by`` needs GM trust, and
    owns and holds it) without counting against the story NPC cap: a crowd's voice
    is not an NPC the GM keeps. It carries the crowd's description and stands in the
    encounter's room. Every row's ``voice_persona`` is set to its primary persona.

    The rows are locked and re-read first, so two GMs voicing the same crowd at
    once cannot both succeed. Which scene the rows belong to is the caller's check.

    Raises:
        CrowdVoiceError: no rows, rows from more than one encounter, a row that is
            not a persona-less ACTIVE body of an unfinished encounter, a row that
            already has a voice, or a mint refusal (trust, name taken).
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
    _lock_and_check(opponents)

    try:
        character = mint_story_npc(
            gm_account=by,
            name=name,
            description=_crowd_description(opponents),
            count_against_cap=False,
        )
    except StaffMintError as exc:
        raise CrowdVoiceError(exc.user_message) from None

    encounter = opponents[0].encounter
    room = encounter.room or encounter.scene.room
    if room is not None and not character.move_to(room, quiet=True):
        msg = "Something kept the crowd's voice from reaching the fight. Try again."
        raise CrowdVoiceError(msg)

    persona = character.sheet_data.primary_persona
    for opponent in opponents:
        opponent.voice_persona = persona
        opponent.save(update_fields=["voice_persona"])
    return persona


NAME_TAKEN_MESSAGE = "A character by that name already exists."
# The shortest column a crowd's name lands in: ``CombatOpponent.name`` (a voice's
# character key and persona name allow 255).
CROWD_NAME_MAX_LENGTH = 200
NAME_TOO_LONG_MESSAGE = f"A crowd's name can be at most {CROWD_NAME_MAX_LENGTH} characters."


@transaction.atomic
def describe_crowd(*, opponents: list[CombatOpponent], name: str, description: str) -> None:
    """Give every row of a crowd the same ``name`` and ``description`` (#4418).

    A blank ``name`` or ``description`` leaves that field as it is. The rows are
    locked and re-read like ``voice_crowd``'s, and must be persona-less ACTIVE bodies
    of one unfinished encounter. A crowd with a voice renames its voice character and
    persona too, so the name it poses under follows, and its voice takes the new
    description, which the voiced crowd's cast row shows. Everything is checked before
    anything is written.

    Raises:
        CrowdVoiceError: a name longer than ``CROWD_NAME_MAX_LENGTH``, no rows, rows
            from more than one encounter, a row that is no crowd body, or a voice name
            another character already has.
    """
    name = name.strip()
    description = description.strip()
    if len(name) > CROWD_NAME_MAX_LENGTH:
        raise CrowdVoiceError(NAME_TOO_LONG_MESSAGE)
    if not opponents:
        msg = "Choose the crowd to describe."
        raise CrowdVoiceError(msg)
    if len({opponent.encounter_id for opponent in opponents}) > 1:
        msg = "A crowd belongs to one fight."
        raise CrowdVoiceError(msg)
    _lock_and_check(opponents, voiced_ok=True)

    voices = {opponent.voice_persona for opponent in opponents if opponent.voice_persona_id}
    if name:
        _refuse_taken_voice_name(voices, name)

    fields = [field for field, value in (("name", name), ("description", description)) if value]
    for opponent in opponents:
        if name:
            opponent.name = name
        if description:
            opponent.description = description
        opponent.save(update_fields=fields)
    if name:
        _rename_voices(voices, name)
    if description:
        _describe_voices(voices, description)


def _describe_voices(voices: set[Persona], description: str) -> None:
    """The voice character takes the crowd's new description (#4418 bug 2).

    A voiced crowd's cast row reads its voice's description, so without this the
    GM's edit looked unsaved. Written through the sanctioned, versioned seam.
    """
    from world.character_sheets.services import set_physical_description  # noqa: PLC0415

    for voice in voices:
        set_physical_description(voice.character_sheet, description)


def _refuse_taken_voice_name(voices: set[Persona], name: str) -> None:
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    for voice in voices:
        character = voice.character_sheet.character
        if ObjectDB.objects.filter(db_key__iexact=name).exclude(pk=character.pk).exists():
            raise CrowdVoiceError(NAME_TAKEN_MESSAGE)


def _rename_voices(voices: set[Persona], name: str) -> None:
    """The voice character and its persona take the crowd's new name."""
    from world.character_sheets.services import StaffEditError, rename_character  # noqa: PLC0415

    for voice in voices:
        try:
            rename_character(voice.character_sheet, name)
        except StaffEditError as exc:
            raise CrowdVoiceError(exc.user_message) from None
