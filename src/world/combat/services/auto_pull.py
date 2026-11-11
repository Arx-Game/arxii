"""The automatic defensive pull (#5066 decision 12).

With ``CombatParticipant.auto_pull_defense`` on, the first time she is attacked in a round
with no pull of her own, her saved defensive pull (``defense_pull_resonance`` and
``defense_pull_tier``) is committed before her dodge rolls. It pulls only the threads that
relate to the dodge (a cast of her dodging technique) and are not already working for her on
the defence roll: a thread whose tier-0 passive already applies there (a vow, her stat or
skill threads) adds nothing by being pulled. When nothing is left it commits nothing and
charges nothing. Like any pull it lasts the round and boosts every use it relates to.

A pull is one row per participant per round (``CombatPull``), so a pull she declared herself
this round, with a cast or on its own, means there is nothing more to pull.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.combat.models import CombatParticipant
    from world.combat.services.reactions import Dodge
    from world.magic.models import Thread
    from world.magic.types.magic_skills import CastCheck
    from world.magic.types.pull import PullActionContext

PULLED_LINE = "You pull {count} thread{s} for defense."
NOTHING_LINE = "Your defensive pull finds no thread that is not already working for you."


def auto_pull_for_defense(
    participant: CombatParticipant,
    dodge: Dodge | None,
    defense_check_type: CheckType,
) -> bool:
    """Commit her saved defensive pull before this dodge, if she asked for one; True if pulled."""
    if not participant.auto_pull_defense:
        return False
    if participant.defense_pull_resonance_id is None or participant.defense_pull_tier is None:
        return False
    if dodge is None or dodge.source.technique_id is None:
        return False
    character = participant.character_sheet.character
    encounter = participant.encounter
    if character.combat_pulls.active_for_encounter(encounter):
        return False
    threads, context, cast_check = _pullable_threads(participant, dodge, defense_check_type)
    if not threads:
        _tell(character, NOTHING_LINE)
        return False
    return _commit(participant, threads, context, cast_check, dodge.source.technique_id)


def _pullable_threads(
    participant: CombatParticipant,
    dodge: Dodge,
    defense_check_type: CheckType,
) -> tuple[list[Thread], PullActionContext, CastCheck | None]:
    """Her threads in the saved resonance that relate to the dodge's cast and are not
    already working for her on the defence roll."""
    from world.combat.pull_helpers import _with_style_skill, pull_action_context  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415
    from world.magic.services.magic_skills import (  # noqa: PLC0415
        involved_trait_ids,
        resolve_cast_check,
    )
    from world.magic.services.resonance import (  # noqa: PLC0415
        _anchor_ambiently_active,
        _anchor_in_action,
    )
    from world.magic.types.pull import PullActionContext  # noqa: PLC0415

    sheet = participant.character_sheet
    character = sheet.character
    technique = Technique.objects.get(pk=dodge.source.technique_id)
    cast_check = resolve_cast_check(character, technique)
    use = pull_action_context(
        participant,
        encounter=participant.encounter,
        technique_id=technique.pk,
        cast_check=cast_check,
    )
    defense = PullActionContext(
        combat_encounter=participant.encounter,
        participant=participant,
        involved_traits=_with_style_skill(sheet, involved_trait_ids(defense_check_type, ())),
    )
    threads = [
        thread
        for thread in character.threads.all()
        if thread.resonance_id == participant.defense_pull_resonance_id
        and _anchor_in_action(thread, use)
        and not _anchor_ambiently_active(thread, defense, character=character)
    ]
    return threads, use, cast_check


def _commit(
    participant: CombatParticipant,
    threads: list[Thread],
    context: PullActionContext,
    cast_check: CastCheck | None,
    technique_id: int,
) -> bool:
    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from world.combat.pull_helpers import commit_combat_pull  # noqa: PLC0415
    from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

    declaration = CastPullDeclaration(
        resonance=participant.defense_pull_resonance,
        tier=participant.defense_pull_tier,
        threads=tuple(threads),
    )
    character = participant.character_sheet.character
    try:
        commit_combat_pull(
            declaration,
            participant,
            participant.encounter,
            technique_id,
            cast_check=cast_check,
            action_context=context,
        )
    except ActionDispatchError as refusal:
        _tell(character, refusal.user_message)
        return False
    _tell(character, PULLED_LINE.format(count=len(threads), s="" if len(threads) == 1 else "s"))
    return True


def _tell(character: object, line: str) -> None:
    from django.db import transaction  # noqa: PLC0415

    transaction.on_commit(lambda: character.msg(line))
