"""The scene's cast list (#4418): who is in the scene to be played, and who plays each.

Derived, with no table of its own. Two kinds of row:

- ``npc``: a story NPC (``world.roster.services.activity.is_story_npc``) standing in
  the scene's room, minus the characters that are only a crowd's voice.
- ``crowd``: the opponents of the scene's encounters that are not COMPLETED, grouped
  by the voice they pose as (``CombatOpponent.voice_persona``), else by threat pool
  for mooks, else one row each (a swarm is one row with a body count).

"Played by" is a character name, never an account name: the borrower of the
entry's ACTIVE or OFFERED loan for this scene, else of any ACTIVE loan, else the
tenure holder. "Cast" alone means a technique cast (``cast_services``); this is the
cast list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from world.combat.constants import OpponentStatus, OpponentTier
from world.roster.constants import NPCLoanStatus
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatOpponent
    from world.roster.models import NPCLoan, RosterEntry
    from world.scenes.models import Persona, Scene

FALLBACK_PLAYER_NAME = "Staff"


@dataclass(frozen=True)
class CastListEntry:
    """One row of a scene's cast list: a named NPC or a crowd."""

    kind: Literal["npc", "crowd"]
    name: str
    roster_entry_id: int | None
    persona_id: int | None
    thumbnail_url: str
    played_by: str
    loan_id: int | None
    loan_status: str | None
    tier: str | None
    count: int | None
    description: str


@dataclass(frozen=True)
class _Player:
    """Who plays an entry: the name shown, and the loan that put them there, if any."""

    name: str
    loan: NPCLoan | None


def _character_names(account_ids: Iterable[int]) -> dict[int, str]:
    """Each account's character name, in one query.

    A GM or Staff OOC character first, else the account's own player character
    (never a story NPC it holds). An account with neither reads as staff.
    """
    from web.api.character_type import TYPECLASS_TO_CHARACTER_TYPE  # noqa: PLC0415
    from world.roster.models import RosterTenure  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    ids = set(account_ids)
    if not ids:
        return {}
    tenures = (
        RosterTenure.objects.filter(player_data__account_id__in=ids, end_date__isnull=True)
        .select_related("player_data", "roster_entry__roster", "roster_entry__character_sheet")
        .select_related("roster_entry__character_sheet__character")
        .order_by("pk")
    )
    gm_names: dict[int, str] = {}
    pc_names: dict[int, str] = {}
    for tenure in tenures:
        account_id = tenure.player_data.account_id
        character = tenure.roster_entry.character_sheet.character
        if character.db_typeclass_path in TYPECLASS_TO_CHARACTER_TYPE:
            gm_names.setdefault(account_id, character.db_key)
        elif tenure.roster_entry.roster.roster_type != RosterType.NPC:
            pc_names.setdefault(account_id, character.db_key)
    return {
        account_id: gm_names.get(account_id) or pc_names.get(account_id) or FALLBACK_PLAYER_NAME
        for account_id in ids
    }


def _loans_by_entry(scene: Scene, entry_ids: set[int]) -> dict[int, NPCLoan]:
    """The loan that decides who plays each entry: this scene's, else any ACTIVE one.

    ACTIVE wins over OFFERED; a loan for this scene wins over one made elsewhere.
    """
    from world.roster.models import NPCLoan  # noqa: PLC0415

    if not entry_ids:
        return {}
    loans = NPCLoan.objects.filter(roster_entry_id__in=entry_ids).filter(
        status__in=(NPCLoanStatus.ACTIVE, NPCLoanStatus.OFFERED)
    )
    best: dict[int, tuple[int, NPCLoan]] = {}
    for loan in loans.order_by("pk"):
        is_scene_loan = loan.scene_id == scene.pk
        if not is_scene_loan and loan.status != NPCLoanStatus.ACTIVE:
            continue
        rank = (2 if is_scene_loan else 0) + (1 if loan.status == NPCLoanStatus.ACTIVE else 0)
        current = best.get(loan.roster_entry_id)
        if current is None or rank >= current[0]:
            best[loan.roster_entry_id] = (rank, loan)
    return {entry_id: loan for entry_id, (_rank, loan) in best.items()}


def _players(scene: Scene, entries: list[RosterEntry]) -> dict[int, _Player]:
    """Who plays each of ``entries``, keyed by entry id."""
    from world.roster.models import RosterTenure  # noqa: PLC0415

    loans = _loans_by_entry(scene, {entry.pk for entry in entries})
    # Each entry's holder, read in one query (newest open tenure wins, as
    # ``current_tenure`` reads it).
    holder_ids: dict[int, int | None] = dict.fromkeys((entry.pk for entry in entries), None)
    open_tenures = (
        RosterTenure.objects.filter(roster_entry_id__in=list(holder_ids), end_date__isnull=True)
        .exclude(player_data__isnull=True)
        .values_list("roster_entry_id", "player_data__account_id")
        .order_by("pk")
    )
    holder_ids.update(open_tenures)
    account_ids = {loan.borrower_id for loan in loans.values()}
    account_ids |= {account_id for account_id in holder_ids.values() if account_id is not None}
    names = _character_names(account_ids)
    players: dict[int, _Player] = {}
    for entry in entries:
        loan = loans.get(entry.pk)
        if loan is not None:
            players[entry.pk] = _Player(name=names[loan.borrower_id], loan=loan)
            continue
        holder_id = holder_ids[entry.pk]
        name = names[holder_id] if holder_id is not None else ""
        players[entry.pk] = _Player(name=name, loan=None)
    return players


def _description(sheet: CharacterSheet) -> str:
    return sheet.character.item_data.get_display_description() or ""


def _room_npc_entries(scene: Scene) -> list[RosterEntry]:
    """Story NPCs in the scene's room that are not a crowd's voice, by name."""
    from web.api.character_type import TYPECLASS_TO_CHARACTER_TYPE  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    room = scene.room
    if room is None:
        return []
    return list(
        RosterEntry.objects.filter(
            character_sheet__character__db_location=room,
            roster__roster_type=RosterType.NPC,
        )
        .exclude(
            character_sheet__character__db_typeclass_path__in=list(TYPECLASS_TO_CHARACTER_TYPE)
        )
        .exclude(story_npc_settings__is_template=True)
        .exclude(character_sheet__personas__voiced_opponents__isnull=False)
        .select_related("roster", "character_sheet__character")
        .order_by("character_sheet__character__db_key")
        .distinct()
    )


def _crowd_opponents(scene: Scene) -> list[CombatOpponent]:
    """Opponents still in the fight in the scene's unfinished encounters.

    Persona-backed opponents are notable NPCs, not crowd bodies, so they are left
    out: when standing in the room they are listed as NPCs.
    """
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    return list(
        CombatOpponent.objects.filter(
            encounter__scene=scene,
            persona__isnull=True,
            status=OpponentStatus.ACTIVE,
        )
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related(
            "threat_pool",
            "voice_persona__character_sheet__character",
            "voice_persona__character_sheet__roster_entry__roster",
        )
        .order_by("pk")
    )


def _group_key(opponent: CombatOpponent) -> tuple:
    if opponent.voice_persona_id is not None:
        return ("voice", opponent.voice_persona_id)
    if opponent.tier == OpponentTier.MOOK and opponent.threat_pool_id is not None:
        return ("pool", opponent.encounter_id, opponent.threat_pool_id)
    return ("row", opponent.pk)


def _bodies(opponent: CombatOpponent) -> int:
    if opponent.tier == OpponentTier.SWARM:
        return opponent.swarm_count or 0
    return 1


def _group_opponents(opponents: list[CombatOpponent]) -> list[list[CombatOpponent]]:
    """Opponents grouped into crowds, in the order each crowd's first row was made."""
    groups: dict[tuple, list[CombatOpponent]] = {}
    for opponent in opponents:
        groups.setdefault(_group_key(opponent), []).append(opponent)
    return list(groups.values())


def _unvoiced_crowd(rows: list[CombatOpponent]) -> CastListEntry:
    first = rows[0]
    pooled = first.tier == OpponentTier.MOOK and first.threat_pool_id is not None
    if pooled:
        name = first.threat_pool.name
        description = first.threat_pool.description or first.description
    else:
        name = first.name
        description = first.description
    return CastListEntry(
        kind="crowd",
        name=name,
        roster_entry_id=None,
        persona_id=None,
        thumbnail_url="",
        played_by="",
        loan_id=None,
        loan_status=None,
        tier=first.tier,
        count=sum(_bodies(row) for row in rows),
        description=description,
    )


def _voiced_crowd(rows: list[CombatOpponent], player: _Player | None) -> CastListEntry:
    first = rows[0]
    voice: Persona = first.voice_persona
    entry = voice.character_sheet.roster_entry
    loan = player.loan if player is not None else None
    return CastListEntry(
        kind="crowd",
        name=voice.name,
        roster_entry_id=entry.pk if entry is not None else None,
        persona_id=voice.pk,
        thumbnail_url=voice.thumbnail_url,
        played_by=player.name if player is not None else "",
        loan_id=loan.pk if loan is not None else None,
        loan_status=loan.status if loan is not None else None,
        tier=first.tier,
        count=sum(_bodies(row) for row in rows),
        description=_description(voice.character_sheet) or first.description,
    )


def scene_cast_list(scene: Scene) -> list[CastListEntry]:
    """The scene's named story NPCs (by name), then its crowds (in the order made)."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    npc_entries = _room_npc_entries(scene)
    crowds = _group_opponents(_crowd_opponents(scene))
    voice_entries = [
        rows[0].voice_persona.character_sheet.roster_entry
        for rows in crowds
        if rows[0].voice_persona_id is not None
    ]
    players = _players(scene, npc_entries + [entry for entry in voice_entries if entry])
    personas = {
        persona.character_sheet_id: persona
        for persona in Persona.objects.filter(
            character_sheet_id__in=[entry.character_sheet_id for entry in npc_entries],
            persona_type=PersonaType.PRIMARY,
        )
    }

    cast_list: list[CastListEntry] = []
    for entry in npc_entries:
        character = entry.character_sheet.character
        persona = personas.get(entry.character_sheet_id)
        player = players[entry.pk]
        cast_list.append(
            CastListEntry(
                kind="npc",
                name=character.db_key,
                roster_entry_id=entry.pk,
                persona_id=persona.pk if persona is not None else None,
                thumbnail_url=persona.thumbnail_url if persona is not None else "",
                played_by=player.name,
                loan_id=player.loan.pk if player.loan is not None else None,
                loan_status=player.loan.status if player.loan is not None else None,
                tier=None,
                count=None,
                description=_description(entry.character_sheet),
            )
        )
    for rows in crowds:
        voice = rows[0].voice_persona
        if voice is None:
            cast_list.append(_unvoiced_crowd(rows))
            continue
        entry = voice.character_sheet.roster_entry
        cast_list.append(_voiced_crowd(rows, players.get(entry.pk) if entry else None))
    return cast_list
