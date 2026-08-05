"""Who could tell who worked that cast (#2710, reworked #2734).

Style is a property of the caster (#2700, ADR-0164), and so is how obvious their
casting is. This module answers one question — which characters in the room perceived
a cast, and how much of it they could pin on the caster — and answers it per observer,
at the instant of the cast.

**Concealment hides attribution, not the event.** A concealed working is a sniper
shot: the observers may not know where it came from, but nobody's head explodes in
secret. Failing the detection roll does not delete the cast from your feed — you still
see what happened, you just cannot say who did it or what they worked. The one
exception is a technique with ``has_perceptible_effect=False``, a working that leaves
nothing to perceive at all; for those there genuinely is no event to narrate, so a
failed roll shows nothing.

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
    from world.magic.models import Technique
    from world.scenes.models import Interaction, Persona

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CastAudience:
    """Who perceived a cast, split by how much of it they could attribute.

    ``concealed`` False means the cast is overt: every tier is empty and the caller
    must pose to the whole room exactly as it always has.

    The three tiers are a ladder of *attribution*, not of existence (#2734):

    ``full``
        Saw the caster and the technique — the ordinary attributed narration.
        Always includes the caster.
    ``vague``
        Registered that a working happened and what it did, but not by whom.
    ``effect_only``
        Saw what happened with no sense that it was worked at all. Empty when the
        technique has no perceptible effect, since then there is nothing to see.
    """

    concealed: bool
    full: list[Persona]
    vague: list[Persona]
    effect_only: list[Persona]


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
    technique: Technique,
) -> int:
    """The concealment rating for this cast; 0 when nothing imposes any.

    The gift's own style wins when set (#2905) — a gift the character didn't choose
    (a species gift) doesn't take its casting manner from whatever Path they did choose.
    Every technique has a gift (Technique.gift is required), so this check is always safe.
    Falls back to the caster's Path style exactly as before when the gift sets no style.

    The caller has already ruled out the free, no-query cases (an openly declared cast,
    a contact-range technique), so this only runs when concealment could still apply.
    """
    if technique.gift.style_id is not None:
        return technique.gift.style.cast_concealment

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
    technique: Technique,
    cast_openly: bool = False,
) -> CastAudience:
    """Who perceived this cast, and how much of it they could attribute.

    Returns an unconcealed audience — and runs no queries and no checks — whenever
    attribution cannot be hidden in the first place:

    * ``cast_openly``, the caster's deliberate waiver;
    * a ``SAME``-reach technique, where the act itself gives the actor away. You have
      to be standing on someone to stab or touch them, so a melee working is attributed
      no matter how subtly its caster works magic (#2734);
    * a caster whose style imposes no concealment — the overwhelmingly common path,
      byte-identical to pre-#2710 behaviour.

    Otherwise each co-located character rolls the detection check against
    ``cast_concealment`` plus the caster's level opposition (ADR-0166) and lands in
    ``full`` (``success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL``), ``vague``
    (exactly 1), or ``effect_only``. The caster is always in ``full``.
    """
    from world.magic.constants import TechniqueReach  # noqa: PLC0415

    if cast_openly or technique.reach == TechniqueReach.SAME:
        return _unconcealed()

    concealment = _concealment_for(caster, technique)
    if concealment <= 0:
        return _unconcealed()

    return _roll_cast_audience(caster, technique, concealment=concealment)


def _roll_cast_audience(
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — same caster the public entrypoint takes
    technique: Technique,
    *,
    concealment: int,
) -> CastAudience:
    """Roll every co-located observer against ``concealment`` and tier them.

    Split out of ``resolve_cast_audience`` so the cheap "can this even be concealed"
    gates stay readable at the entrypoint; this half only ever runs for a genuinely
    concealed cast.
    """
    full: list[Persona] = []
    vague: list[Persona] = []
    effect_only: list[Persona] = []
    # An imperceptible working leaves nothing for a non-detector to see, so the bottom
    # tier stays empty and the pre-#2734 hide-outright behaviour holds for it alone.
    perceptible = technique.has_perceptible_effect

    caster_persona = _persona_for(caster)
    if caster_persona is not None:
        full.append(caster_persona)

    check_type = _detection_check_type()
    if check_type is None:
        # Fail closed (ADR-0033) on ATTRIBUTION: with no way to roll, nobody gets to
        # name the caster. The effect is not the secret, though, so a perceptible
        # working is still narrated to the room — unauthored content must not silently
        # erase combat events from every participant's feed.
        logger.warning(
            "No active CheckType named %r — concealed casts are unattributable until "
            "content authors it (#2710).",
            DETECT_CAST_CHECK_NAME,
        )
        if perceptible:
            effect_only.extend(_observer_personas(caster))
        return CastAudience(concealed=True, full=full, vague=vague, effect_only=effect_only)

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
        elif perceptible:
            effect_only.append(persona)

    return CastAudience(concealed=True, full=full, vague=vague, effect_only=effect_only)


def _unconcealed() -> CastAudience:
    """An overt audience: the caller poses room-wide exactly as it always has.

    A fresh instance per call — never a shared module-level singleton, whose mutable
    tier lists a future caller could accidentally mutate in place.
    """
    return CastAudience(concealed=False, full=[], vague=[], effect_only=[])


def _observer_personas(
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — same caster the public entrypoint takes
) -> list[Persona]:
    """Every co-located character's presented persona, caster excluded."""
    personas = []
    for observer in _observers_in_room(caster):
        persona = _persona_for(observer)
        if persona is not None:
            personas.append(persona)
    return personas
