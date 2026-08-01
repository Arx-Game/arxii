"""Who noticed that cast (#2710).

Style is a property of the caster (#2700, ADR-0164), and so is how obvious their
casting is. This module answers one question — which characters in the room perceived
a cast, and in how much detail — and answers it per observer, at the instant of the
cast.

Deliberately NOT built on ``world.conditions.services.can_perceive`` /
``register_detection``: those answer "can A perceive B right now" and persist detection
of a standing concealing condition. A cast is an *act*, not a state; there is nothing
durable to record, and reusing them would mean minting a throwaway condition per cast.

The audience this returns is materialised by the caller as ``InteractionReceiver`` rows,
so a scene log replays what each viewer perceived AT THE TIME rather than what they
could perceive today.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from world.checks.services import level_opposition, perform_check_with_modifiers
from world.magic.constants import CAST_DETECTION_ATTRIBUTION_LEVEL, DETECT_CAST_CHECK_NAME

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.scenes.models import Interaction, Persona

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CastAudience:
    """Who perceived a cast, split by how much they made out.

    ``concealed`` False means the cast is overt: ``full`` and ``vague`` are empty and
    the caller must pose to the whole room exactly as it always has.
    """

    concealed: bool
    full: list[Persona]
    vague: list[Persona]


def conceal_action_interaction(action_interaction: Interaction, audience: CastAudience) -> None:
    """Set a concealed cast's ACTION row to PERCEIVED_ONLY with the resolved receivers.

    #2710: this row's content is the technique name. Concealing only the OUTCOME pose
    would still show every bystander "Ilyra — Whisper of Binding" in the scene log via
    the ACTION row's ``technique_name``.

    Lives here rather than in ``world.scenes.cast_services`` (#2734) because the combat
    round-action pose seam needs the identical treatment, and combat must not import
    from the scene cast path to get it.
    """
    from world.scenes.constants import InteractionVisibility  # noqa: PLC0415
    from world.scenes.interaction_services import accounts_for_personas  # noqa: PLC0415
    from world.scenes.place_models import InteractionReceiver  # noqa: PLC0415

    action_interaction.visibility = InteractionVisibility.PERCEIVED_ONLY
    action_interaction.save(update_fields=["visibility"])
    receiver_accounts = accounts_for_personas(audience.full)
    # audience.full always includes the caster (resolve_cast_audience appends them),
    # and unlike create_interaction's place-scoped auto-populate path (which excludes
    # the writer via .exclude(pk=persona.pk)), we deliberately do NOT exclude them
    # here. create_action_interaction_core builds this row via Interaction.objects.
    # create(...) directly rather than through create_interaction, so it never pins
    # writer_account_id — receiver membership is the caster's only route back to
    # their own concealed ACTION row.
    InteractionReceiver.objects.bulk_create(
        [
            InteractionReceiver(
                interaction=action_interaction,
                timestamp=action_interaction.timestamp,
                persona=p,
                account_id=receiver_accounts.get(p.pk),
            )
            for p in audience.full
        ]
    )


def _concealment_for(
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — same caster the public entrypoint takes
    *,
    cast_openly: bool,
) -> int:
    """The caster's style concealment rating; 0 when overt, pathless, or cast openly."""
    if cast_openly:
        return 0
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    path = current_path_for_character(caster)
    if path is None or path.style_id is None:
        return 0
    return path.style.cast_concealment


def _detection_check_type() -> CheckType | None:
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.filter(name=DETECT_CAST_CHECK_NAME, is_active=True).first()


def _observers_in_room(
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — walks raw room contents (mixed object types)
) -> list[ObjectDB]:  # noqa: OBJECTDB_PARAM — returns raw room contents, same reasoning
    """Characters co-located with the caster, excluding the caster."""
    location = caster.location
    if location is None:
        return []
    return [obj for obj in location.contents if obj.pk != caster.pk]


def _persona_for(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — called for the caster and any observer
) -> Persona | None:
    """The face this character is currently presenting, or None if it has no sheet."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def resolve_cast_audience(
    *,
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — any co-located object may observe
    cast_openly: bool = False,
) -> CastAudience:
    """Who perceived this cast, and in how much detail.

    Returns an unconcealed audience — and runs no queries and no checks — whenever the
    caster's style imposes no concealment. That is the overwhelmingly common path and
    keeps every existing style byte-identical to its pre-#2710 behaviour.

    Otherwise each co-located character rolls the detection check against
    ``cast_concealment`` plus the caster's level opposition (ADR-0166), and lands in
    ``full`` (``success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL``), ``vague``
    (exactly 1), or neither. The caster is always in ``full``.
    """
    concealment = _concealment_for(caster, cast_openly=cast_openly)
    if concealment <= 0:
        # A fresh instance per call — never a shared module-level singleton, whose
        # mutable full/vague lists a future caller could accidentally mutate in place.
        return CastAudience(concealed=False, full=[], vague=[])

    full: list[Persona] = []
    vague: list[Persona] = []

    caster_persona = _persona_for(caster)
    if caster_persona is not None:
        full.append(caster_persona)

    check_type = _detection_check_type()
    if check_type is None:
        # Fail closed (ADR-0033): a missing detection CheckType must hide, not leak.
        logger.warning(
            "No active CheckType named %r — concealed casts are undetectable until "
            "content authors it (#2710).",
            DETECT_CAST_CHECK_NAME,
        )
        return CastAudience(concealed=True, full=full, vague=vague)

    from world.progression.services.skill_development import (  # noqa: PLC0415
        get_character_path_level,
    )

    difficulty = concealment + level_opposition(
        check_type,
        level=get_character_path_level(caster),
        character=caster,
    )

    # Per-observer query-in-a-loop, by the letter of the standing rule (django_notes.md)
    # -- but each observer needs their OWN independent roll, so this can't collapse into
    # a single batched query without breaking per-observer independence. Bounded by room
    # population; do not "optimize" this into one query.
    for observer in _observers_in_room(caster):
        persona = _persona_for(observer)
        if persona is None:
            continue
        result = perform_check_with_modifiers(observer, check_type, target_difficulty=difficulty)
        if result.success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL:
            full.append(persona)
        elif result.success_level >= 1:
            vague.append(persona)

    return CastAudience(concealed=True, full=full, vague=vague)
