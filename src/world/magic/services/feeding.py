"""Feeding: the two-party anima transfer behind blood and essence appetites (#2853).

One service, two skins (`feed`/`drain` actions supply the flavor). The shape is
Soul Tether sineating inverted: deduct the victim's ``CharacterAnima``, credit
the feeder (overfill lands in decaying ``glut``), audit with a
``FeedingRecord``. The victim's anima loss converts to fatigue through the same
authored ratio machinery technique casts use, so a gorged-empty victim
collapses through the existing fatigue zones — no new knockout mechanic.

Restraint (ruled): SIP is non-fatal by construction; only a deliberate GORGE —
or a failed restraint check while Ravenous that escalates the feed — can kill,
and only NPCs can die of it (a PC victim bottoms out through fatigue collapse
and the consent layer; the peril death gate never lets a PC source kill). An
NPC gorged past empty dies through the real death pipeline and leaves a
crime-tagged deed with scene evidence — wide open at the consent layer, fully
priced at the justice layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from django.db import transaction

from world.magic.models.anima import CharacterAnima
from world.magic.models.appetites import FeedingRecord

logger = logging.getLogger(__name__)

# PLACEHOLDER magnitudes (#2853 author pass).
SIP_AMOUNT = 1
DRINK_AMOUNT = 3
# SIP never takes a victim below this reserve — non-fatal by construction.
SIP_SAFE_RESERVE = 1
RESTRAINT_CHECK_NAME = "fatigue_willpower"
RESTRAINT_DIFFICULTY = 0
FEEDING_KILL_CRIME_SLUG = "murder"
# 0 per #3463. This was a literal per-kill Legend award: draining a helpless
# victim minted a deed worth 10. Nothing was at stake for the feeder, so under
# the bard test it is worth no song. The deed row itself stays — it carries the
# murder's crime tag, its evidence and its witnesses, none of which read
# base_value. A feeding that genuinely could have killed the feeder settles
# through the stakes contract like anything else.
FEEDING_KILL_DEED_BASE_VALUE = 0

# #3001 blood-magic taints: extraction is affinity-neutral; the METHOD carries
# the taint. Authored CompromiseActType rows (content repo) resolved by name at
# fire time — absent rows log and skip, never invent (#2698).
MURDER_TAINT_ACT = "Murder by Anima Drain"
SEDUCTION_TAINT_ACTS = ("Seduction Feeding - Deception", "Seduction Feeding - Predation")


class FeedMode:
    SIP = "SIP"
    DRINK = "DRINK"
    GORGE = "GORGE"


@dataclass(frozen=True)
class FeedingResult:
    """Outcome of one feeding."""

    record: FeedingRecord | None
    taken: int
    glut_gained: int
    victim_fatigue: int
    lost_control: bool
    was_lethal: bool
    message: str
    death_harvest: int = 0
    """Total yield of a killing drain (#3001): death_harvest_multiplier x the
    victim's full maximum, replacing the drained remainder. 0 on any survivable
    feed."""


def feed_anima(
    feeder_sheet,
    victim_sheet,
    *,
    amount_mode: str = FeedMode.SIP,
    scene=None,
) -> FeedingResult:
    """Transfer anima from *victim_sheet* to *feeder_sheet* (#2853).

    Authorization (consent for PC victims, NPC openness) is the caller's
    concern — this is the commit seam. A Ravenous feeder attempting SIP/DRINK
    rolls restraint; failure escalates to GORGE (lost control). Lethality only
    triggers for NPC victims gorged at/past empty.
    """
    feeder_anima = _anima_or_none(feeder_sheet)
    victim_anima = _anima_or_none(victim_sheet)
    if feeder_anima is None or victim_anima is None:
        return FeedingResult(None, 0, 0, 0, False, False, "No anima to draw on.")

    mode = amount_mode
    lost_control = False
    if mode != FeedMode.GORGE and _is_ravenous(feeder_sheet) and not _restraint_holds(feeder_sheet):
        mode = FeedMode.GORGE
        lost_control = True

    available = victim_anima.current
    if mode == FeedMode.SIP:
        take = min(SIP_AMOUNT, max(0, available - SIP_SAFE_RESERVE))
    elif mode == FeedMode.DRINK:
        take = min(DRINK_AMOUNT, available)
    else:
        take = available

    with transaction.atomic():
        victim_anima.current -= take
        victim_anima.save(update_fields=["current"])

        victim_fatigue = _apply_victim_fatigue(victim_sheet, take)
        was_lethal = False
        if mode == FeedMode.GORGE and victim_anima.current <= 0:
            was_lethal = _maybe_kill_npc_victim(feeder_sheet, victim_sheet, scene)

        # #3001: a killing drain yields death_harvest_multiplier x the victim's
        # FULL maximum — the metaphysical reason vampires are tempted to finish
        # people off. The windfall replaces the drained remainder; overfill
        # lands in glut (the decaying high), so a kill is a rush, not a tank.
        harvest = take
        death_harvest = 0
        if was_lethal:
            from world.magic.models.anima import AnimaConfig  # noqa: PLC0415

            config = AnimaConfig.get_singleton()
            death_harvest = config.death_harvest_multiplier * victim_anima.maximum
            harvest = death_harvest

        room_for_current = feeder_anima.maximum - feeder_anima.current
        to_current = min(harvest, room_for_current)
        to_glut = harvest - to_current
        feeder_anima.current += to_current
        feeder_anima.glut += to_glut
        feeder_anima.save(update_fields=["current", "glut"])

        if was_lethal:
            grant_blood_taint(feeder_sheet, MURDER_TAINT_ACT)
        if take > 0 and _feeder_is_essence_kind(feeder_sheet):
            # The succubi lane: an essence feed IS the seduction (#3001 ruling —
            # +1 Insidia, +1 Praedari per feed).
            for act_name in SEDUCTION_TAINT_ACTS:
                grant_blood_taint(feeder_sheet, act_name)

        record = FeedingRecord.objects.create(
            feeder_sheet=feeder_sheet,
            victim_sheet=victim_sheet,
            scene=scene,
            amount_mode=mode,
            lost_control=lost_control,
            anima_taken=take,
            glut_gained=to_glut,
            victim_fatigue=victim_fatigue,
            was_lethal=was_lethal,
        )

    _reconcile_both(feeder_sheet, victim_sheet)
    message = _result_message(mode, take, lost_control, was_lethal)
    return FeedingResult(
        record,
        take,
        to_glut,
        victim_fatigue,
        lost_control,
        was_lethal,
        message,
        death_harvest,
    )


def _anima_or_none(sheet) -> CharacterAnima | None:
    if sheet is None:
        return None
    return sheet.anima_or_none


def grant_blood_taint(sheet, act_name: str) -> None:
    """Fire an authored blood-magic CompromiseActType at *sheet*, if authored.

    #3001: the extraction is neutral; the method (murder, seduction) grants the
    abyssal resonance. Rows are content-repo authored — an absent row logs and
    skips rather than being invented here (#2698). Shared by feeding kills and
    ritual sacrifice (services/ritual_pool.py).
    """
    from world.magic.models.fall_redemption import CompromiseActType  # noqa: PLC0415
    from world.magic.services.fall_redemption import grant_compromise_resonance  # noqa: PLC0415

    act = CompromiseActType.objects.filter(name=act_name).first()
    if act is None:
        logger.info("Compromise act %r not authored; blood taint skipped.", act_name)
        return
    grant_compromise_resonance(sheet, act)


def _feeder_is_essence_kind(feeder_sheet) -> bool:
    from world.species.appetites import AppetiteKind, appetite_for  # noqa: PLC0415

    return appetite_for(feeder_sheet) == AppetiteKind.ESSENCE


def _is_ravenous(sheet) -> bool:
    from world.magic.services.appetites import hunger_severity  # noqa: PLC0415

    anima = _anima_or_none(sheet)
    return anima is not None and hunger_severity(anima) > 0


def _restraint_holds(feeder_sheet) -> bool:
    """Roll the feeder's restraint. Fail-open when the check type isn't seeded.

    Reuses the fatigue willpower check type (the power-through-collapse roll) —
    a dedicated appetite-restraint check is a content follow-through on #2853.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=RESTRAINT_CHECK_NAME, is_active=True).first()
    character = feeder_sheet.character
    if check_type is None or character is None:
        logger.warning("Feeding restraint check unavailable; restraint holds by default.")
        return True
    result = perform_check(character, check_type, RESTRAINT_DIFFICULTY)
    return result.success_level > 0


def _apply_victim_fatigue(victim_sheet, taken: int) -> int:
    """Anima loss fatigues the victim through the authored cast ratios (ruled)."""
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.fatigue.services import apply_technique_fatigue  # noqa: PLC0415

    if taken <= 0:
        return 0
    return apply_technique_fatigue(victim_sheet, ActionCategory.PHYSICAL, taken, 0)


def _victim_is_npc(victim_sheet) -> bool:
    """A victim with no live player account is an NPC for feeding lethality."""
    character = victim_sheet.character
    return character is None or character.db_account is None


def _maybe_kill_npc_victim(feeder_sheet, victim_sheet, scene) -> bool:
    """Gorging an NPC past empty kills — through the real death machinery (ruled).

    PC victims never die of feeding (they bottom out through fatigue collapse;
    consent covers the rest). Story-protected NPCs survive. The kill mints a
    crime-tagged deed for the feeder, which generates scene evidence and
    witness knowledge through the existing justice seams — wide open at the
    consent layer, fully priced at the justice layer.
    """
    from world.stories.npc_protection import is_death_prevented_by_story  # noqa: PLC0415
    from world.vitals.services import mark_fed_to_death  # noqa: PLC0415

    if not _victim_is_npc(victim_sheet):
        return False
    feeder_character = feeder_sheet.character
    if is_death_prevented_by_story(victim_sheet, feeder_character):
        return False
    if not mark_fed_to_death(victim_sheet):
        return False
    _mint_feeding_kill_deed(feeder_sheet, victim_sheet, scene)
    return True


def _mint_feeding_kill_deed(feeder_sheet, victim_sheet, scene) -> None:
    """A feeding kill is a murder: deed + crime tag -> evidence + witnesses."""
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    persona = feeder_sheet.active_persona or feeder_sheet.primary_persona
    if persona is None:
        logger.warning("Feeding kill by sheet %s minted no deed (no persona).", feeder_sheet.pk)
        return
    source_type, _created = LegendSourceType.objects.get_or_create(
        name="Predation",
        defaults={"description": "PLACEHOLDER: deeds of feeding and predation (#2853)."},
    )
    crime = CrimeKind.objects.filter(slug=FEEDING_KILL_CRIME_SLUG).first()
    create_solo_deed(
        persona,
        f"Drained {victim_sheet} to death",
        source_type,
        FEEDING_KILL_DEED_BASE_VALUE,
        description="PLACEHOLDER: a body emptied of life, the marks unmistakable.",
        scene=scene,
        crime_kinds=[crime] if crime is not None else None,
        concealed=True,
    )


def _reconcile_both(feeder_sheet, victim_sheet) -> None:
    from world.magic.services.appetites import reconcile_ravenous  # noqa: PLC0415

    reconcile_ravenous(feeder_sheet)
    reconcile_ravenous(victim_sheet)


def _result_message(mode: str, take: int, lost_control: bool, was_lethal: bool) -> str:
    if take <= 0:
        return "There is nothing left to take."
    if was_lethal:
        return "You drain them utterly — and what you leave behind is a corpse."
    if lost_control:
        return "The hunger slips its leash — you take far more than you meant to."
    if mode == FeedMode.SIP:
        return "You take the barest taste."
    if mode == FeedMode.DRINK:
        return "You drink deep."
    return "You gorge yourself on stolen life."


# ---------------------------------------------------------------------------
# Consent-path resolvers (#2853): the transfer on an accepted feed/drain request.
# Registered at app-ready (world.magic.apps.ready) — the same seam boon/anima_ritual use;
# fires on both consent paths (NPC auto-accept and piloted accept).
# ---------------------------------------------------------------------------


def _resolve_feeding(request, result) -> None:
    """Perform the transfer after an accepted, successful feed/drain roll."""
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    success = (check_result.success_level > 0) if check_result is not None else False
    if not success:
        return
    feeder_sheet = request.initiator_persona.character_sheet
    victim_sheet = request.target_persona.character_sheet
    outcome = feed_anima(
        feeder_sheet, victim_sheet, amount_mode=FeedMode.DRINK, scene=request.scene
    )
    feeder = feeder_sheet.character
    victim = victim_sheet.character
    if feeder is not None:
        feeder.msg(outcome.message)
    if victim is not None and outcome.taken > 0:
        victim.msg("|rSomething vital drains out of you.|n")


def register_feeding_resolvers() -> None:
    """Register the feed/drain consent resolvers (called from world.magic.apps.ready)."""
    from world.scenes.action_resolvers import register_resolver  # noqa: PLC0415

    register_resolver("feed", _resolve_feeding)
    register_resolver("drain", _resolve_feeding)
