"""What the terms that end a standoff pay (#4323).

Only the act that ends a standoff pays, so a long press cannot be farmed: the terms whose
acceptance settles the last live group. Two things happen when they land, both graded by that
terms check's result tier and neither with an amount in code:

- the existing kindling path earns what the act feeds (``award_kindled_deeds``, a social act
  read in the standoff's own context, so a covenant resonance a Cynosure's parley kindles
  earns here as it would anywhere else);
- the result tier's ``StandoffEndingAward`` names the dramatic moment the ending counts as, so
  ``create_dramatic_moment_tag`` grants the character's own resonance and renown, and when the
  ending was witnessed by another player's character a deed is written into their legend.

Two characters one account plays pay nothing to each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.standoffs.constants import (
    EARNED_LEGEND,
    EARNED_RENOWN,
    LINE_ENDING_CREDIT,
    LINE_ENDING_EARNED,
)
from world.standoffs.models import StandoffEndingAward

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.magic.models import ResonanceGrant
    from world.scenes.models import Scene
    from world.standoffs.models import StandoffGroup, StandoffTerms
    from world.traits.models import CheckOutcome

LEGEND_SOURCE_NAME = "Standoff"


def ending_award(outcome: CheckOutcome) -> StandoffEndingAward | None:
    """The tier row for this roll result, or None when staff authored none (it pays nothing)."""
    return (
        StandoffEndingAward.objects.filter(outcome_tier=outcome)
        .select_related("moment_type")
        .first()
    )


def _stands_against_own_account(encounter: CombatEncounter, sheet: CharacterSheet) -> bool:
    """Whether a group of this standoff is a character the same account plays as ``sheet``."""
    from world.roster.services.npc_lending import played_by_one_account  # noqa: PLC0415

    return any(
        played_by_one_account(sheet, group.persona.character_sheet)
        for group in encounter.standoff_groups.filter(persona__isnull=False).select_related(
            "persona__character_sheet"
        )
    )


def _witnessed(scene: Scene, sheet: CharacterSheet) -> bool:
    """Whether another player's character was on the scene list when the standoff ended.

    The scene list is the one witness notion legend already uses
    (``scene_witness_personas``). A narrator, a story NPC nobody plays and a character played
    by the actor's own account are not witnesses.
    """
    from world.roster.services.npc_lending import current_player_of  # noqa: PLC0415
    from world.societies.knowledge_services import scene_witness_personas  # noqa: PLC0415

    actor_account = current_player_of(sheet)
    for persona in scene_witness_personas(scene):
        witness = persona.character_sheet
        if witness.pk == sheet.pk:
            continue
        account = current_player_of(witness)
        if account is not None and account != actor_account:
            return True
    return False


def _write_deed(
    *,
    sheet: CharacterSheet,
    scene: Scene,
    title: str,
    base_value: int,
    archetypes: list,
) -> bool:
    """Write the legend deed under the face the character presents; True when one was made."""
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_legend_event  # noqa: PLC0415

    source_type, _ = LegendSourceType.objects.get_or_create(
        name=LEGEND_SOURCE_NAME,
        defaults={"description": "A deed made by the terms that ended a standoff."},
    )
    _, entries = create_legend_event(
        title[:200],
        source_type,
        base_value,
        [active_persona_for_sheet(sheet)],
        scene=scene,
        archetypes=archetypes or None,
    )
    return bool(entries)


def _kindled(
    sheet: CharacterSheet, group: StandoffGroup, terms: StandoffTerms, outcome: CheckOutcome
) -> None:
    """Feed the existing kindling path with the ending as one social act.

    A standoff is a negotiation, not a combat round, so the act is read with no round
    context (``DURING_NEGOTIATION`` holds, exactly as it does for the standoff's own rolls)
    and the character's live mission, if any.
    """
    from world.magic.constants import KindlingActKind  # noqa: PLC0415
    from world.magic.services.kindling import (  # noqa: PLC0415
        KindlingContext,
        act_label,
        active_mission_for,
        award_kindled_deeds,
    )
    from world.magic.types.kindling import KindlingAct  # noqa: PLC0415

    target = group.persona.character_sheet if group.persona_id is not None else None
    award_kindled_deeds(
        sheet,
        act=KindlingAct(
            kind=KindlingActKind.SOCIAL,
            target=target,
            label=act_label(terms.name, group.name, ": "),
        ),
        outcome=outcome,
        context=KindlingContext(resolution=None, mission=active_mission_for(sheet)),
    )


def _credit_line(sheet: CharacterSheet, terms: StandoffTerms, *, deed: bool) -> str:
    """The room line crediting the ending, naming the face the actor presents.

    It says only what is public by nature, the name and the legend. The resonance that grew
    is the actor's own business and goes to the actor alone (``_tell_actor``).
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return LINE_ENDING_CREDIT.format(
        name=active_persona_for_sheet(sheet).name,
        terms=terms.name,
        earned=EARNED_LEGEND if deed else EARNED_RENOWN,
    )


def _tell_actor(sheet: CharacterSheet, grant: ResonanceGrant) -> None:
    """Tell the actor alone which resonance the ending grew and by how much, on commit."""
    from world.magic.services.resonance_checks import gain_bonus_clause  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    line = LINE_ENDING_EARNED.format(amount=grant.amount, resonance=grant.resonance.name)
    if clause := gain_bonus_clause(grant.resonance.affinity, grant.bonus_percent):
        line += f" {clause}"

    def _send() -> None:
        send_narrative_message(
            recipients=[sheet],
            body=line,
            category=NarrativeCategory.SYSTEM,
            ooc_note="Standoff ending",
            frame_tags={"earned_resonance": True},
        )

    transaction.on_commit(_send)


def pay_standoff_ending(
    *,
    encounter: CombatEncounter,
    group: StandoffGroup,
    terms: StandoffTerms,
    sheet: CharacterSheet,
    outcome: CheckOutcome,
) -> str:
    """Pay the terms that ended the standoff; returns the room's credit line, "" for none.

    Called once, by the terms whose acceptance settled the last group, inside that verb's
    transaction. The resonance the ending grew is told to the actor alone; the room's line
    carries only the name and the deed. Nothing is paid to a character no account plays, or
    when a group of the standoff is another character the actor's own account plays. When
    the moment type's per-scene cap is spent, the ending pays nothing, a deed included.
    """
    from world.magic.exceptions import DramaticMomentCapExceeded  # noqa: PLC0415
    from world.magic.models import ResonanceGrant  # noqa: PLC0415
    from world.magic.services.gain import create_dramatic_moment_tag  # noqa: PLC0415
    from world.roster.services.activity import is_player_character  # noqa: PLC0415
    from world.roster.services.npc_lending import current_player_of  # noqa: PLC0415

    account = current_player_of(sheet)
    if account is None or not is_player_character(sheet):
        return ""
    if _stands_against_own_account(encounter, sheet):
        return ""
    _kindled(sheet, group, terms, outcome)
    award = ending_award(outcome)
    if award is None:
        return ""
    archetypes = list(terms.archetypes.all())
    try:
        with transaction.atomic():
            tag = create_dramatic_moment_tag(
                character_sheet=sheet,
                moment_type=award.moment_type,
                tagged_by=account,
                scene=encounter.scene,
                archetypes=archetypes,
                # The game pays the ending, not a person's tag: no fatigue, and no refusal
                # for a character the account plays (#5327).
                by_system=True,
            )
    except DramaticMomentCapExceeded:
        # The moment type's per-scene cap is spent: this scene already paid it to her.
        return ""
    grant = (
        ResonanceGrant.objects.filter(source_dramatic_moment=tag)
        .select_related("resonance")
        .first()
    )
    deed = False
    if award.legend_value > 0 and _witnessed(encounter.scene, sheet):
        deed = _write_deed(
            sheet=sheet,
            scene=encounter.scene,
            title=f"{terms.name}: {group.name}",
            base_value=award.legend_value,
            archetypes=archetypes or list(award.moment_type.archetypes.all()),
        )
    if grant is not None:
        _tell_actor(sheet, grant)
    return _credit_line(sheet, terms, deed=deed)
