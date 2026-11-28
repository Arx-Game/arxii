"""Impulses: the pull of corruption a character carries (#5177).

A character carrying corruption in a resonance, whether their own or what a Sineater took on for a
Sinner (it is the same store), feels that resonance pull. From the Intrusive Thoughts stage the
condition reads "Intrusive Thoughts: <resonance>" and, when something the resonance cares about is
present in a scene, they are sent the words staff wrote for it, once per scene. From the Compulsion
stage it reads "Compulsion: <resonance>" and, while that is present, a scene-scoped condition
penalizes their rolls until they earn the resonance in the scene. Earning it adds a little
corruption (``CorruptionConfig.compulsion_indulge_corruption``) and lifts the penalty for the
scene.

"Something it cares about is present" is ``kindled_for(...).fed_tier``: an authored situation of
that resonance holds. The player always chooses what the character does; nothing here acts for them.

``impulses_now`` reads. ``refresh_impulses`` applies the consequences and is called explicitly after
a pose is posted, before a cast's modifiers are gathered, and when the kindled panel is shown.
``give_in_to_compulsion`` is called by ``grant_resonance`` when a deed grows a resonance.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from world.conditions.models import ConditionInstance
from world.magic.constants import COMPULSION_INDULGING_SOURCES, ImpulseKind
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.models.grant import ResonanceGrant
from world.magic.models.impulse import ImpulseShown
from world.magic.services.corruption import accrue_corruption, get_corruption_config
from world.magic.types.corruption import CorruptionSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionTemplate
    from world.magic.models.affinity import Resonance
    from world.magic.models.aura import CharacterResonance
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

_INTRUSIVE_PREFIX = "Intrusive Thoughts"
_COMPULSION_PREFIX = "Compulsion"


@dataclass(frozen=True)
class Impulse:
    """One resonance a character carries corruption in at an impulse stage.

    ``present`` says an authored situation of the resonance holds now, ``reasons`` are the
    player-word lines for it, and ``text`` is the words staff wrote for the resonance (blank
    when none). ``label`` is the name the condition shows.
    """

    resonance: Resonance
    stage_order: int
    is_compulsion: bool
    present: bool
    reasons: tuple[str, ...]
    text: str

    @property
    def label(self) -> str:
        prefix = _COMPULSION_PREFIX if self.is_compulsion else _INTRUSIVE_PREFIX
        return f"{prefix}: {self.resonance.name}"


@dataclass(frozen=True)
class ImpulseRefresh:
    """What ``refresh_impulses`` read and did.

    ``impulses`` is every impulse the character feels now, whatever happened to them.
    ``told`` are the lines sent to the character. ``compulsion_applied`` and
    ``compulsion_lifted`` say what happened to the Compulsion condition.
    """

    impulses: tuple[Impulse, ...] = ()
    told: tuple[str, ...] = ()
    compulsion_applied: bool = False
    compulsion_lifted: bool = False


# =============================================================================
# Display
# =============================================================================


def corruption_display_name(
    instance_or_template: ConditionInstance | ConditionTemplate,
    stage_order: int,
    resonance: Resonance | None = None,
) -> str:
    """The name a player is shown for a corruption condition at ``stage_order``.

    "Compulsion: <resonance>" from the Compulsion stage, "Intrusive Thoughts: <resonance>" from
    the Intrusive Thoughts stage, else the template's own name. A condition that is not a
    corruption condition keeps its own name. Display only: never a lookup key, and nothing in
    the database is renamed.

    ``instance_or_template`` is a ``ConditionInstance`` or a ``ConditionTemplate``;
    ``resonance`` defaults to the template's ``corruption_resonance``.
    """
    template = (
        instance_or_template.condition
        if isinstance(instance_or_template, ConditionInstance)
        else instance_or_template
    )
    if template.corruption_resonance_id is None:
        return template.name
    cfg = get_corruption_config()
    prefix = _prefix_for_stage(stage_order, cfg)
    if prefix is None:
        return template.name
    resonance = resonance if resonance is not None else template.corruption_resonance
    return f"{prefix}: {resonance.name}"


def _prefix_for_stage(stage_order: int, cfg: CorruptionConfig) -> str | None:
    if stage_order >= cfg.compulsion_stage:
        return _COMPULSION_PREFIX
    if stage_order >= cfg.intrusive_thoughts_stage:
        return _INTRUSIVE_PREFIX
    return None


# =============================================================================
# Reading
# =============================================================================


def _corruption_instances(
    sheet: CharacterSheet, cfg: CorruptionConfig
) -> tuple[list[ConditionInstance], ConditionInstance | None]:
    """The character's corruption conditions and their Compulsion condition, in one query."""
    character = sheet.character
    if character is None:
        return [], None
    match = Q(condition__corruption_resonance__isnull=False, current_stage__isnull=False)
    if cfg.compulsion_condition_id is not None:
        match |= Q(condition_id=cfg.compulsion_condition_id)
    rows = list(
        ConditionInstance.objects.filter(match, target=character).select_related(
            "current_stage", "condition__corruption_resonance__affinity"
        )
    )
    compulsion = next(
        (row for row in rows if row.condition_id == cfg.compulsion_condition_id), None
    )
    corruption = [
        row
        for row in rows
        if row.condition.corruption_resonance_id is not None and row.current_stage is not None
    ]
    return corruption, compulsion


def _impulses_from(
    sheet: CharacterSheet, corruption: list[ConditionInstance], cfg: CorruptionConfig
) -> list[Impulse]:
    from world.magic.services.kindling import (  # noqa: PLC0415
        kindled_for_each,
        kindling_context_for,
    )

    stages = {
        row.condition.corruption_resonance: row.current_stage.stage_order for row in corruption
    }
    felt = sorted(
        (
            (resonance, stage)
            for resonance, stage in stages.items()
            if stage >= cfg.intrusive_thoughts_stage
        ),
        key=lambda item: item[0].name,
    )
    if not felt:
        return []
    context = kindling_context_for(sheet)
    answers = kindled_for_each(
        sheet,
        [resonance for resonance, _ in felt],
        resolution=context.resolution,
        mission=context.mission,
    )
    return [
        Impulse(
            resonance=resonance,
            stage_order=stage,
            is_compulsion=stage >= cfg.compulsion_stage,
            present=kindled.fed_tier is not None,
            reasons=tuple(kindled.fed_reasons),
            text=resonance.impulse_text,
        )
        for (resonance, stage), kindled in zip(felt, answers, strict=True)
    ]


def impulses_now(sheet: CharacterSheet) -> list[Impulse]:
    """Every resonance the character carries corruption in at the Intrusive Thoughts stage or
    above, with whether something it cares about is present now. Writes nothing.

    One query when the character carries none; the kindling context is built once.
    """
    cfg = get_corruption_config()
    corruption, _ = _corruption_instances(sheet, cfg)
    return _impulses_from(sheet, corruption, cfg)


def earned_in_scene(
    sheet: CharacterSheet,
    resonance: Resonance,
    scene: Scene,
    *,
    excluding: ResonanceGrant | None = None,
) -> bool:
    """Whether the character has earned ``resonance`` by a deed since ``scene`` began.

    Only a grant whose source is in ``COMPULSION_INDULGING_SOURCES`` counts: a deed the character
    did themselves, never a grant that landed from another player, a GM or a cron. Grants carry
    no scene of their own, so "in this scene" is a grant made since the scene started.
    ``excluding`` leaves out the grant a caller is in the middle of recording. A grant staff or
    the scene's GM undid (#5327) is no longer something she earned, so it does not count.
    """
    grants = ResonanceGrant.objects.filter(
        character_sheet=sheet,
        resonance=resonance,
        source__in=COMPULSION_INDULGING_SOURCES,
        granted_at__gte=scene.date_started,
        nullified_at__isnull=True,
    )
    if excluding is not None:
        grants = grants.exclude(pk=excluding.pk)
    return grants.exists()


# =============================================================================
# Applying
# =============================================================================


def _live(scene: Scene | None) -> Scene | None:
    if scene is None or not scene.is_active or scene.is_finished:
        return None
    return scene


def _tell_once(
    sheet: CharacterSheet, resonance: Resonance, scene: Scene, kind: str, line: str
) -> str | None:
    """Send ``line`` to the character once per (resonance, scene, kind); return it if sent.

    A character with no live session cannot hear it: nothing is recorded and nothing is sent,
    so the once-per-scene line is not spent on nobody.
    """
    # The same question the stored-message push asks: does a session hold this character now.
    if sheet.character is None or not sheet.character.sessions.all():
        return None
    _, created = ImpulseShown.objects.get_or_create(
        character_sheet=sheet, resonance=resonance, scene=scene, kind=kind
    )
    if not created:
        return None
    sheet.character.msg(line)
    return line


def _intrusive_line(impulse: Impulse) -> str:
    return impulse.text or f"Your {impulse.resonance.name} stirs at what is in front of you."


def _pull_line(impulse: Impulse) -> str:
    return (
        f"Your {impulse.resonance.name} pulls at you. "
        "Until you give in to it here, it clouds what you do."
    )


def _set_compulsion(
    sheet: CharacterSheet,
    cfg: CorruptionConfig,
    existing: ConditionInstance | None,
    compelling: list[Impulse],
) -> tuple[bool, bool]:
    """Lay, raise or lift the Compulsion condition; return (applied, lifted)."""
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        remove_condition,
    )

    character = sheet.character
    template = cfg.compulsion_condition
    if template is None or character is None:
        return False, False
    if not compelling:
        if existing is not None:
            return False, remove_condition(character, template)
        return False, False
    strongest = max(compelling, key=lambda impulse: impulse.stage_order)
    severity = strongest.stage_order - cfg.compulsion_stage + 1
    if existing is None:
        result = apply_condition(
            character,
            template,
            severity=severity,
            source_description=f"{_COMPULSION_PREFIX}: {strongest.resonance.name}",
        )
        return result.success, False
    if existing.severity < severity:
        advance_condition_severity(existing, severity - existing.severity)
        return True, False
    return False, False


def refresh_impulses(sheet: CharacterSheet, scene: Scene | None) -> ImpulseRefresh:
    """Read the character's impulses and apply what they call for in ``scene``.

    - Intrusive Thoughts stage with its situation present: send the resonance's impulse words
      once per scene.
    - Compulsion stage with its situation present and the resonance not yet earned in the
      scene: lay ``compulsion_condition`` (scene duration) at severity
      ``stage - compulsion_stage + 1``, keeping a higher severity already held, and tell the
      character once per scene.
    - When nothing compels the character any more (they settled below the stage, the situation
      passed, or they gave in), lift the condition.

    With no live ``scene`` it only reads. A character carrying no corruption at an impulse
    stage costs one query.
    """
    cfg = get_corruption_config()
    corruption, existing = _corruption_instances(sheet, cfg)
    impulses = _impulses_from(sheet, corruption, cfg)
    scene = _live(scene)
    if scene is None:
        return ImpulseRefresh(impulses=tuple(impulses))
    told: list[str] = []
    compelling: list[Impulse] = []
    for impulse in impulses:
        if not impulse.present:
            continue
        if not impulse.is_compulsion:
            line = _tell_once(
                sheet, impulse.resonance, scene, ImpulseKind.INTRUSIVE, _intrusive_line(impulse)
            )
        elif earned_in_scene(sheet, impulse.resonance, scene):
            continue
        else:
            compelling.append(impulse)
            line = _tell_once(
                sheet, impulse.resonance, scene, ImpulseKind.COMPULSION, _pull_line(impulse)
            )
        if line is not None:
            told.append(line)
    applied, lifted = _set_compulsion(sheet, cfg, existing, compelling)
    return ImpulseRefresh(
        impulses=tuple(impulses),
        told=tuple(told),
        compulsion_applied=applied,
        compulsion_lifted=lifted,
    )


def refresh_impulses_for_character(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a pose and a cast hold the character
) -> ImpulseRefresh | None:
    """``refresh_impulses`` for a character in the room's live scene; None when it has no sheet.

    The one call a pose and a cast make: it finds the sheet and the scene itself.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return None
    return refresh_impulses(sheet, get_active_scene(character.location))


def _isolated[T](
    call: Callable[[], T], failure: str, *, gate: Callable[[], bool] | None = None
) -> T | None:
    """Run ``call`` in its own savepoint; log ``failure`` and return None when it raises.

    Impulses are a side effect of a pose, a cast, a panel and a grant. A failure here forfeits
    only the impulse, never the act it rides on, and a database error does not poison an
    enclosing transaction. ``gate`` is asked first, outside the savepoint: when it answers
    False there is nothing to do and no savepoint is opened.
    """
    try:
        if gate is not None and not gate():
            return None
        with transaction.atomic():
            return call()
    except Exception:
        logger.exception(failure)
        return None


def safe_refresh_impulses(sheet: CharacterSheet, scene: Scene | None) -> ImpulseRefresh | None:
    """``refresh_impulses`` that can never fail its caller; None when it raised."""
    return _isolated(
        lambda: refresh_impulses(sheet, scene),
        f"Refreshing impulses failed for character sheet #{sheet.pk}",
    )


def safe_refresh_impulses_for_character(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a pose and a cast hold the character
) -> ImpulseRefresh | None:
    """``refresh_impulses_for_character`` that can never fail its caller; None when it raised.

    A character whose cached conditions hold no corruption and no Compulsion has nothing to
    refresh, so the common case of a pose or a cast costs no query and opens no savepoint.
    """

    def may_have_impulses() -> bool:
        # The handler caches the character's active conditions after its first use.
        compulsion_id = get_corruption_config().compulsion_condition_id
        return any(
            instance.condition.corruption_resonance_id is not None
            or (compulsion_id is not None and instance.condition_id == compulsion_id)
            for instance in character.conditions.active()
        )

    return _isolated(
        lambda: refresh_impulses_for_character(character),
        f"Refreshing impulses failed for character #{character.pk}",
        gate=may_have_impulses,
    )


# =============================================================================
# Giving in
# =============================================================================


def give_in_to_compulsion(grant: ResonanceGrant, row: CharacterResonance) -> None:
    """Give in to a Compulsion a deed grew a resonance under; never fails the grant.

    A failure in the work is logged and forfeits only the giving in, so ``grant_resonance``'s
    transaction is never rolled back by it.
    """
    _isolated(
        lambda: _give_in(grant, row),
        f"Giving in to a Compulsion failed for grant #{grant.pk}; the resonance grant stands",
    )


def _give_in(grant: ResonanceGrant, row: CharacterResonance) -> None:
    """A deed grew a resonance the character is compelled by: they give in to it.

    ``grant_resonance`` calls this once the grant is recorded, with the resonance row it holds.
    It does nothing, and costs nothing, for a row carrying no corruption. Otherwise, in a live
    scene, the first deed of the resonance there lifts the Compulsion for the rest of the scene
    (unless another resonance still compels the character), adds
    ``compulsion_indulge_corruption`` to the character's corruption in the resonance, and tells
    them. A Sineater carrying that resonance for a Sinner carries the addition for the Sinner
    with the largest holding. Only a source in ``COMPULSION_INDULGING_SOURCES`` counts: a grant
    from another player, a GM or a cron, and succumbing to the Mire, are not giving in.

    The line goes out after the surrounding transaction commits.
    """
    if row.corruption_current <= 0:
        return
    if grant.source not in COMPULSION_INDULGING_SOURCES:
        return
    sheet = grant.character_sheet
    character = sheet.character
    if character is None:
        return
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    scene = _live(get_active_scene(character.location))
    if scene is None:
        return
    cfg = get_corruption_config()
    corruption, existing = _corruption_instances(sheet, cfg)
    impulses = _impulses_from(sheet, corruption, cfg)
    compelled = next(
        (
            impulse
            for impulse in impulses
            if impulse.is_compulsion
            and impulse.present
            and impulse.resonance.pk == grant.resonance_id
        ),
        None,
    )
    if compelled is None or earned_in_scene(sheet, grant.resonance, scene, excluding=grant):
        return
    remaining = [
        impulse
        for impulse in impulses
        if impulse.is_compulsion
        and impulse.present
        and impulse.resonance.pk != grant.resonance_id
        and not earned_in_scene(sheet, impulse.resonance, scene)
    ]
    _set_compulsion(sheet, cfg, existing, remaining)
    added = 0
    if cfg.compulsion_indulge_corruption > 0:
        added = accrue_corruption(
            character_sheet=sheet,
            resonance=grant.resonance,
            amount=cfg.compulsion_indulge_corruption,
            source=CorruptionSource.INDULGED,
        ).amount_applied
    if added > 0:
        from world.magic.services.mire import add_to_largest_holding  # noqa: PLC0415

        add_to_largest_holding(sheet, grant.resonance, added)
    line = (
        f"You give in to your {grant.resonance.name}. It loosens its hold for now, "
        "and a little more of it stays with you."
    )
    transaction.on_commit(lambda: character.msg(line))
