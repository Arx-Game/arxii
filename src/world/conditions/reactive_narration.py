"""Authored narration for the moments a reactive condition fires (#4587).

A condition can answer the fight in five ways that used to happen in silence: it strikes
back at a foe that hit its bearer, its source steps in for the bearer, it turns a foe on its
source, it holds the bearer up through a knockout, and a once-only condition is used up.
Staff write one line per moment on the ``ConditionTemplate`` (``<moment>_narration``), the
code supplies only the names and the delivery, and a moment with no line gets a plain one.

Three rules this module owns:

* A line is filled by :func:`fill_reactive_line`, which never raises: a stray brace, an
  unknown placeholder, a format spec or a name the moment cannot supply makes the line
  unusable and the caller falls back to the plain line. A combat round must not fail
  over a typo in staff text.
* Every name is the face the character presents (``persona_names_for_sheets``), never
  ``str(model)`` and never a real name behind a disguise.
* The line goes to the room through ``broadcast_action_outcome`` (one persisted OUTCOME
  row, pushed to web sessions and sent to telnet as text, so the live push and the
  scene log carry the same line) unless the moment is hidden by design: a template that
  is not ``is_visible_to_others``, or a bearer or source who is concealed, would be given
  away by a room line, so the bearer and the source are told privately instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import TYPE_CHECKING

from world.conditions.constants import DurationType, ReactiveMoment

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatOpponent
    from world.conditions.models import ConditionInstance, ConditionTemplate
    from world.scenes.models import Scene

BEARER = "bearer"
SOURCE = "source"
ATTACKER = "attacker"

#: The names each moment can supply to its line. Strike back and guard know the foe that
#: struck; the other three moments have no foe to name.
ALLOWED_PLACEHOLDERS: dict[ReactiveMoment, frozenset[str]] = {
    ReactiveMoment.RETALIATION: frozenset({BEARER, SOURCE, ATTACKER}),
    ReactiveMoment.GUARD: frozenset({BEARER, SOURCE, ATTACKER}),
    ReactiveMoment.PROVOKE: frozenset({BEARER, SOURCE}),
    ReactiveMoment.GRACE: frozenset({BEARER, SOURCE}),
    ReactiveMoment.SPENT: frozenset({BEARER, SOURCE}),
}

_FORMATTER = Formatter()


def line_field(moment: ReactiveMoment) -> str:
    """The ``ConditionTemplate`` field holding this moment's authored line."""
    return f"{moment.value}_narration"


def authored_line(template: ConditionTemplate, moment: ReactiveMoment) -> str:
    """The template's authored line for the moment, possibly blank."""
    match moment:
        case ReactiveMoment.RETALIATION:
            return template.retaliation_narration
        case ReactiveMoment.GUARD:
            return template.guard_narration
        case ReactiveMoment.PROVOKE:
            return template.provoke_narration
        case ReactiveMoment.GRACE:
            return template.grace_narration
        case ReactiveMoment.SPENT:
            return template.spent_narration
    return ""


def _has_effect(template: ConditionTemplate, moment: ReactiveMoment) -> bool:
    """True when the template carries the effect that makes this moment happen."""
    match moment:
        case ReactiveMoment.RETALIATION:
            return template.retaliation_damage > 0 or template.retaliation_condition_id is not None
        case ReactiveMoment.GUARD:
            return template.source_guards_bearer
        case ReactiveMoment.PROVOKE:
            return template.forces_attack_on_source
        case ReactiveMoment.GRACE:
            return template.prevents_knockout
        case ReactiveMoment.SPENT:
            return template.default_duration_type == DurationType.UNTIL_USED
    return False


_MISSING_EFFECT: dict[ReactiveMoment, str] = {
    ReactiveMoment.RETALIATION: "Give this condition strike-back damage or a strike-back "
    "condition first; this line is never told without one.",
    ReactiveMoment.GUARD: "Turn on 'source guards bearer' first; this line is never told "
    "without it.",
    ReactiveMoment.PROVOKE: "Turn on 'forces attack on source' first; this line is never "
    "told without it.",
    ReactiveMoment.GRACE: "Turn on 'prevents knockout' first; this line is never told without it.",
    ReactiveMoment.SPENT: "Set the duration to 'Until Used' first; only a once-only "
    "condition is ever used up.",
}


def fill_reactive_line(text: str, names: Mapping[str, str]) -> str | None:
    """Fill an authored line with ``names``, or None when it cannot be used.

    None means: the line is blank, has a stray or unbalanced brace, names a placeholder
    that is not in ``names``, uses a conversion or format spec, or names a placeholder
    whose value is blank. Never raises. The text is parsed, never ``str.format``-ed, so
    attribute and index tricks (``{bearer.__class__}``) are refused rather than evaluated.
    """
    line = text.strip()
    if not line:
        return None
    parts: list[str] = []
    try:
        for literal, field, spec, conversion in _FORMATTER.parse(line):
            parts.append(literal)
            if field is None:
                continue
            if spec or conversion or not names.get(field, "").strip():
                return None
            parts.append(names[field])
    except ValueError:
        return None
    return "".join(parts)


def reactive_line_problem(template: ConditionTemplate, moment: ReactiveMoment) -> str:
    """Why staff's line for this moment cannot work as written, or '' when it can.

    Used by ``ConditionTemplate.clean``: it checks the line against the placeholders the
    moment supplies (using the same parse as :func:`fill_reactive_line`) and that the
    template has the effect the line narrates.
    """
    line = authored_line(template, moment).strip()
    if not line:
        return ""
    allowed = ALLOWED_PLACEHOLDERS[moment]
    try:
        for _literal, field, spec, conversion in _FORMATTER.parse(line):
            if field is None:
                continue
            if spec or conversion or field not in allowed:
                names = ", ".join("{" + name + "}" for name in sorted(allowed))
                return f"Use only these placeholders here, written plainly: {names}."
    except ValueError:
        return "A curly brace in this line is not closed. Write {{ or }} for a literal brace."
    if not _has_effect(template, moment):
        return _MISSING_EFFECT[moment]
    return ""


def presented_names(
    characters: list[ObjectDB],  # noqa: OBJECTDB_PARAM - a bearer or source may be any character
) -> dict[int, str]:
    """The name each character presents, keyed by object pk, in one batch.

    The active persona's name, else the primary persona's. A character with no sheet
    (an NPC object) is named by its key.
    """
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    by_sheet = persona_names_for_sheets([c.pk for c in characters])
    return {c.pk: by_sheet.get(c.pk) or c.db_key for c in characters}


def plain_reactive_line(moment: ReactiveMoment, *, ward: str, names: Mapping[str, str]) -> str:
    """The system line told when the template has no (usable) authored line."""
    bearer = names[BEARER]
    attacker = names.get(ATTACKER, "")
    source = names.get(SOURCE, "")
    match moment:
        case ReactiveMoment.RETALIATION:
            return f"{bearer}'s {ward} strikes {attacker or 'the attacker'} back."
        case ReactiveMoment.GUARD:
            between = f" and {attacker}" if attacker else ""
            return f"{source or 'A guardian'} steps between {bearer}{between}."
        case ReactiveMoment.PROVOKE:
            return f"{bearer} turns on {source or 'whoever provoked it'}."
        case ReactiveMoment.GRACE:
            return f"{bearer}'s {ward} keeps them on their feet."
        case ReactiveMoment.SPENT:
            return f"{bearer}'s {ward} is spent."
    msg = f"No plain line for reactive moment {moment!r}."
    raise ValueError(msg)


def attacker_name_of(ref: object) -> str:
    """The name of the foe a damage source names, or '' when it is not an opponent."""
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    return ref.name if isinstance(ref, CombatOpponent) else ""


def narrate_reactive_moment(  # noqa: PLR0913 - one moment's names and audience
    instance: ConditionInstance,
    moment: ReactiveMoment,
    *,
    attacker: str = "",
    bearer_name: str = "",
    encounter: CombatEncounter | None = None,
    plain_fallback: bool = True,
    hidden: bool | None = None,
) -> None:
    """Tell the audience that ``instance``'s reactive moment just happened.

    ``bearer_name`` overrides the presented name for a bearer that is an opponent (its
    ``CombatOpponent.name``, not its object's key); left out for an opponent, it is read
    from the opponent row. ``attacker`` is the foe's name for the moments that have one.
    ``encounter`` is the fight the moment happened in; without it the bearer's own fight is
    found (a player character's active participation, an opponent's own encounter), and with
    none the moment is told privately. ``plain_fallback=False`` says nothing when the template
    has no usable authored line (the caller has already narrated this event in its own words).
    ``hidden`` is :func:`reactive_moment_hidden` decided by a caller that is about to delete
    the instance (a spent concealing condition no longer conceals once it is gone); left out,
    it is decided here.
    """
    from world.conditions.serializers import condition_display_name  # noqa: PLC0415

    bearer = instance.target
    source = instance.source_character
    people = [bearer] if source is None or source.pk == bearer.pk else [bearer, source]
    opponent = _opponent_of(bearer)
    fight = encounter or _fight_of(bearer, opponent)
    names = _moment_names(people, source, opponent, bearer_name=bearer_name, attacker=attacker)

    line = fill_reactive_line(authored_line(instance.condition, moment), names)
    if line is None:
        if not plain_fallback:
            return
        line = plain_reactive_line(moment, ward=condition_display_name(instance), names=names)
    if hidden is None:
        hidden = reactive_moment_hidden(instance)
    _deliver_moment_line(line, people, fight, hidden=hidden)


def _moment_names(
    people: list[ObjectDB],
    source: ObjectDB | None,  # noqa: OBJECTDB_PARAM - a source may be any object, an NPC included
    opponent: CombatOpponent | None,
    *,
    bearer_name: str,
    attacker: str,
) -> dict[str, str]:
    """The presented names a moment's line fills in: the bearer, the source and the foe.

    ``people`` is the bearer, then the source when it is someone else; ``source`` is the
    condition's source, who may be the bearer. With no source the line has no ``{source}``
    name. A bearer or source who is a foe is named by its combat name, everyone else by the
    face they present.
    """
    bearer = people[0]
    presented = presented_names(people)
    names = {BEARER: bearer_name or (opponent.name if opponent else presented[bearer.pk])}
    if source is not None:
        source_opponent = _opponent_of(source)
        names[SOURCE] = source_opponent.name if source_opponent else presented[source.pk]
    if attacker:
        names[ATTACKER] = attacker
    return names


def _deliver_moment_line(
    line: str,
    people: list[ObjectDB],
    fight: CombatEncounter | None,
    *,
    hidden: bool,
) -> None:
    """Tell the room of ``fight`` the line, or tell ``people`` privately when hidden or unfought."""
    if fight is not None and not hidden:
        from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

        broadcast_action_outcome(encounter=fight, narration=line)
    else:
        _tell_privately(people, line, scene=fight.scene if fight is not None else None)


def _opponent_of(
    bearer: ObjectDB,  # noqa: OBJECTDB_PARAM - a bearer may be any object, an NPC included
) -> CombatOpponent | None:
    """The bearer's opponent row in a fight still going on, or None for anyone else."""
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    return (
        CombatOpponent.objects.filter(objectdb_id=bearer.pk)
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter")
        .order_by("-pk")
        .first()
    )


def _fight_of(
    bearer: ObjectDB,  # noqa: OBJECTDB_PARAM - a bearer may be any object, an NPC included
    opponent: CombatOpponent | None,
) -> CombatEncounter | None:
    """The fight the bearer is in: its opponent row's encounter, else its active participation."""
    if opponent is not None:
        return opponent.encounter
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415

    try:
        sheet = bearer.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    context = resolve_combat_round_context(sheet)
    return context.participant.encounter if context is not None else None


def reactive_moment_hidden(instance: ConditionInstance) -> bool:
    """True when a room line would give the moment away.

    Hidden by design: the template is not visible to others, or the bearer or the source
    carries a concealing condition (a room line naming them would give them away).
    """
    from world.conditions.services import is_concealed  # noqa: PLC0415

    bearer = instance.target
    source = instance.source_character
    if not instance.condition.is_visible_to_others or is_concealed(bearer):
        return True
    return source is not None and source.pk != bearer.pk and is_concealed(source)


def _tell_privately(
    people: list[ObjectDB],  # noqa: OBJECTDB_PARAM - the bearer and the source, any character
    line: str,
    *,
    scene: Scene | None,
) -> None:
    """Whisper the line, as the Narrator, to each person it names (web and telnet).

    ``scene`` is the fight's own scene when there is one, so the private row is kept in the
    scene the moment happened in and a refetch of that scene's log finds it.
    """
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    for person in people:
        narrate_privately(person, line, scene=scene)
