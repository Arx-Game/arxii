"""The rite of settling, read for the sheet and the rite dialog (#5124).

``settling_rite_reading`` lists the character's waiting reflections as a player reads them
(what each is, the writing behind it, what the rite would do at a full share) with the
carried items that count as the offering and what the roll is. It writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.constants import ReflectionChoice, ReflectionTargetKind
from world.magic.models.drift import DriftConversionCap
from world.magic.models.reflection import Reflection
from world.magic.services.drift import get_drift_correction_config
from world.magic.services.drift_correction import (
    RITE_NOT_READY_MESSAGE,
    burden_holdings,
    disowns_unsettling,
    embraced_amount,
    fallback_conversion_target,
    main_affinity_rows,
    offerings_for,
    open_caps,
    reflected_resonance,
    rite_is_ready,
    waiting_reflections,
)
from world.magic.services.reflection import deed_in_sentence, deed_what
from world.magic.services.soul_tether import get_soul_tether_config, sineater_thread_resonance
from world.magic.types.drift import ReflectionReading, SettlingRiteReading

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models.affinity import Resonance

_EXCERPT_LENGTH = 160
_ONE_HUNDRED = Decimal(100)


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _EXCERPT_LENGTH:
        return text
    return text[: _EXCERPT_LENGTH - 1].rstrip() + "…"


def _writing(reflection: Reflection) -> tuple[str, str, str]:
    """(where, from_line, excerpt) for the writing that carries ``reflection``; blanks when
    it is gone."""
    entry = reflection.journal_entry
    if entry is not None:
        return (
            f'"{entry.title}" · journal',
            f'from your journal, "{entry.title}"',
            _excerpt(entry.body),
        )
    pose = reflection.interaction
    if pose is not None:
        scene = pose.scene
        where = f"Pose in {scene.name}" if scene is not None else "Pose"
        from_line = f"from your pose in {scene.name}" if scene is not None else "from your pose"
        return where, from_line, _excerpt(pose.content)
    return "", "", ""


def open_cap_line(sheet: CharacterSheet) -> str:
    """The sentence naming the character's open chance to atone, blank when none is open."""
    caps = DriftConversionCap.objects.filter(
        offer__character_sheet=sheet, cap__gt=0
    ).select_related("target_resonance")
    parts = [f"up to {cap.cap} toward {cap.target_resonance.name}" for cap in caps]
    if not parts:
        return ""
    return f"A chance to atone is open: {', '.join(parts)}."


def _effect_line(
    sheet: CharacterSheet,
    reflection: Reflection,
    target: Resonance | None,
    caps: dict[int, int],
    disown_percent: int,
) -> str:
    if reflection.tether_id is not None:
        return _burden_effect_line(reflection)
    resonance = reflected_resonance(reflection)
    embrace = reflection.choice == ReflectionChoice.EMBRACE
    if reflection.grant is not None:
        grant = reflection.grant
        if embrace:
            what = deed_in_sentence(grant) or f"your {resonance.name}"
            most = embraced_amount(sheet, grant, Decimal(1))
            return f"Your {resonance.name} from {what} grows, up to {most}."
        most = int(Decimal(grant.amount) * Decimal(disown_percent) / _ONE_HUNDRED)
        if most <= 0:
            return "Nothing will turn, because the deed earned too little."
        return f"{resonance.name} turns toward {_target_name(target)}, up to {most}."
    if embrace:
        return "Who you are moves toward who you have become."
    most = caps.get(target.pk, 0) if target is not None else 0
    if most <= 0:
        return "Nothing will turn, because no chance to atone is open."
    return f"{resonance.name} turns toward {_target_name(target)}, up to {most}."


def _burden_effect_line(reflection: Reflection) -> str:
    """What a full share would do to the Mire a Sineater carries for one Sinner. It says nothing
    of what the Sinner will be paid, or of the jackpot."""
    holdings = burden_holdings(reflection)
    if not holdings:
        return "Nothing will clear, because you carry none of it now."
    if reflection.choice == ReflectionChoice.SUCCUMB:
        parts = " and ".join(f"{h.amount} {h.resonance.name}" for h in holdings)
        becomes = "become" if len(holdings) > 1 else "becomes"
        return f"Up to {parts} {becomes} part of you."
    total = sum(h.amount for h in holdings)
    percent = get_soul_tether_config().purify_reward_percent
    reward = sum(h.amount * percent // 100 for h in holdings)
    own = sineater_thread_resonance(reflection.tether)
    if own is None or reward <= 0:
        return f"Up to {total} of it clears."
    return f"Up to {total} of it clears; your {own.name} grows by up to {reward}."


def _kind(reflection: Reflection) -> str:
    if reflection.tether_id is not None:
        return ReflectionTargetKind.BURDEN.value
    if reflection.grant is not None:
        return ReflectionTargetKind.DEED.value
    return ReflectionTargetKind.RESONANCE.value


def _target_name(target: Resonance | None) -> str:
    return target.name if target is not None else "your own affinity"


_BURDEN_VERBS = {
    ReflectionChoice.ABSOLVE: "Absolve",
    ReflectionChoice.CONDEMN: "Condemn",
    ReflectionChoice.SUCCUMB: "Succumb to",
}


def _title(reflection: Reflection) -> str:
    if reflection.tether_id is not None:
        verb = _BURDEN_VERBS[reflection.choice]
        return f"{verb} the Mire you carry for {reflection.tether.target.primary_persona.name}"
    verb = "Embrace" if reflection.choice == ReflectionChoice.EMBRACE else "Disown"
    if reflection.grant is not None:
        grant = reflection.grant
        return f"{verb} {deed_what(grant) or f'your {grant.resonance.name}'}"
    return f"{verb} your {reflection.resonance.name}"


def settling_rite_reading(
    sheet: CharacterSheet, items: Iterable[ItemInstance]
) -> SettlingRiteReading:
    """The waiting reflections, the offerings among ``items``, and whether the rite is ready."""
    config = get_drift_correction_config()
    reflections = waiting_reflections(sheet)
    main_rows = main_affinity_rows(sheet)
    # The rite turns toward the resonance its offering is tied to; before one is chosen the
    # sheet names the one the rite falls back to (the same function the rite uses).
    caps = open_caps(sheet)
    target = fallback_conversion_target(
        main_rows, caps if disowns_unsettling(reflections) else None
    )
    readings = []
    for reflection in reflections:
        where, from_line, excerpt = _writing(reflection)
        readings.append(
            ReflectionReading(
                id=reflection.pk,
                choice=reflection.choice,
                kind=_kind(reflection),
                title=_title(reflection),
                where=where,
                from_line=from_line,
                excerpt=excerpt,
                effect_line=_effect_line(
                    sheet, reflection, target, caps, config.disown_deed_percent
                ),
            )
        )
    ready = rite_is_ready(config)
    return SettlingRiteReading(
        reflections=tuple(readings),
        offerings=tuple(offerings_for(sheet, reflections, items)) if ready else (),
        rite_ready=ready,
        not_ready_message="" if ready else RITE_NOT_READY_MESSAGE,
        check_name=config.check_type.name if config.check_type_id is not None else "",
    )
