"""Ceremony lifecycle services (#2289).

The single write paths for ceremonies. Actions call these; commands and web
converge on the actions. Spec Decisions 10–13 (issue #2289) are implemented
here: being/presented mapping (10), belief-aligned devotion (11), bounded
abandonment (12), retired honorees (13).
"""

import logging
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from world.ceremonies.constants import CeremonyStatus, CeremonyTypeKey
from world.ceremonies.models import (
    Ceremony,
    CeremonyHonoree,
    CeremonyOffering,
    CeremonySpeech,
    CeremonyType,
    get_ceremony_config,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.worship.models import WorshippedBeing

logger = logging.getLogger(__name__)

CEREMONY_CHECK_TYPE_NAME = "Ceremony Rites"
SPEECH_CHECK_TYPE_NAME = "Performance"
SPEECH_SPECIALIZATION_NAME = "Oratory"
CEREMONY_LEGEND_SOURCE = "Ceremony"


class CeremonyError(Exception):
    """Player-facing ceremony failure; ``user_message`` is safe to display."""

    def __init__(self, msg: str, *, user_message: str | None = None) -> None:
        super().__init__(msg)
        self.user_message = user_message or msg


def _officiant_declaration(officiant_sheet: "CharacterSheet"):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return officiant_sheet.worship_declaration
    except ObjectDoesNotExist:
        return None


def _resolve_beings(
    officiant_sheet: "CharacterSheet", explicit: "WorshippedBeing | None"
) -> tuple["WorshippedBeing", "WorshippedBeing"]:
    """Decision 10: map the optional explicit being to (being, presented_being)."""
    declaration = _officiant_declaration(officiant_sheet)
    public = declaration.public_being if declaration else None
    secret = declaration.secret_being if declaration else None

    if explicit is None:
        if public is None:
            msg = "You must name the being this rite is for — you have no public worship."
            raise CeremonyError(msg)
        return public, public
    if secret is not None and explicit.pk == secret.pk and public is not None:
        # The twisted rite: secretly serves the hidden god behind the public front.
        return secret, public
    return explicit, explicit


def open_ceremony(  # noqa: PLR0913
    *,
    officiant_persona: "Persona",
    type_key: str,
    honoree_sheets: "list[CharacterSheet]",
    location_profile,
    being: "WorshippedBeing | None" = None,
    scene=None,
    event=None,
) -> Ceremony:
    """Open a ceremony at a location, recognizing zero or more honorees.

    Funerals and Seances require every honoree dead (retired stays valid, Decision 13).
    Only one OPEN ceremony may exist per location (DB constraint).
    """
    ceremony_type = CeremonyType.objects.filter(key=type_key).first()
    if ceremony_type is None:
        msg = "That kind of ceremony is not recognized."
        raise CeremonyError(msg)
    if ceremony_type.key in (CeremonyTypeKey.FUNERAL, CeremonyTypeKey.SEANCE):
        from world.vitals.services import is_dead  # noqa: PLC0415

        if not honoree_sheets:
            msg = "A funeral needs at least one deceased to honor."
            if ceremony_type.key == CeremonyTypeKey.SEANCE:
                msg = "A seance needs at least one dead soul to call."
            raise CeremonyError(msg)
        for sheet in honoree_sheets:
            if not is_dead(sheet):
                msg = f"{sheet} still lives; the rite of passing is not theirs."
                raise CeremonyError(msg)

    officiant_sheet = officiant_persona.character_sheet
    true_being, presented = _resolve_beings(officiant_sheet, being)

    try:
        with transaction.atomic():
            ceremony = Ceremony.objects.create(
                ceremony_type=ceremony_type,
                officiant=officiant_persona,
                being=true_being,
                presented_being=presented,
                location=location_profile,
                scene=scene,
                event=event,
            )
            CeremonyHonoree.objects.bulk_create(
                CeremonyHonoree(ceremony=ceremony, honoree_sheet=sheet) for sheet in honoree_sheets
            )
            if ceremony_type.key == CeremonyTypeKey.SEANCE:
                from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415

                SeanceManifestationOffer.objects.bulk_create(
                    SeanceManifestationOffer(ceremony_honoree=honoree)
                    for honoree in ceremony.honorees.all()
                )
    except IntegrityError as exc:
        msg = "A ceremony is already underway here."
        raise CeremonyError(msg) from exc

    if ceremony.is_twisted:
        from world.ceremonies.leak import run_twisted_rite_leak  # noqa: PLC0415

        run_twisted_rite_leak(ceremony=ceremony, officiant_sheet=officiant_sheet)
    return ceremony


def record_offering(
    *, ceremony: Ceremony, item_instances: "list[ItemInstance]"
) -> list[CeremonyOffering]:
    """Sacrifice items: destroy them, feed the being's pool, log offerings.

    Decision 11: the pool grant always goes to the TRUE being; the offerer's
    devotion follows the being they *believe* they served (presented when the
    rite is twisted — here the offerer is the officiant, who always knows the
    truth, so their devotion tracks the true being).
    """
    _require_open(ceremony)
    from world.items.services.usage import hard_delete_item_instance  # noqa: PLC0415
    from world.worship.services import bump_devotion, grant_worship  # noqa: PLC0415

    config = get_ceremony_config()
    officiant_sheet = ceremony.officiant.character_sheet
    offerings: list[CeremonyOffering] = []
    for instance in item_instances:
        value = instance.template.value
        legend_value = instance.legend_value
        name = str(instance)
        hard_delete_item_instance(instance)
        grant = None
        if value > 0:
            grant = grant_worship(
                ceremony.being,
                value * config.offering_resonance_per_value,
                granted_by=officiant_sheet,
                reason=f"ceremony:{ceremony.pk}",
            )
        offerings.append(
            CeremonyOffering.objects.create(
                ceremony=ceremony,
                item_name=name,
                item_value=value,
                item_legend_value=legend_value,
                worship_grant=grant,
                offered_by=ceremony.officiant,
            )
        )
        bump_devotion(officiant_sheet, ceremony.being, config.devotion_per_offering)
    return offerings


def record_speech(
    *,
    ceremony: Ceremony,
    speaker_persona: "Persona",
    target_honoree: CeremonyHonoree | None = None,
) -> CeremonySpeech:
    """Recognize a speaker; their Performance/Oratory roll shapes the tally."""
    _require_open(ceremony)
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=SPEECH_CHECK_TYPE_NAME).first()
    success_level = None
    if check_type is not None:
        oratory = Specialization.objects.filter(
            name=SPEECH_SPECIALIZATION_NAME,
            parent_skill__trait__name=SPEECH_CHECK_TYPE_NAME,
        ).first()
        result = perform_check(
            speaker_persona.character_sheet.character,
            check_type,
            specialization=oratory,
        )
        if result.outcome is not None:
            success_level = result.outcome.success_level
    return CeremonySpeech.objects.create(
        ceremony=ceremony,
        speaker=speaker_persona,
        success_level=success_level,
        target_honoree=target_honoree,
    )


def finish_ceremony(*, ceremony: Ceremony) -> Ceremony:
    """Close the rite: quality roll, renown tallies, worship, funeral effects."""
    _require_open(ceremony)
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.worship.services import bump_devotion  # noqa: PLC0415

    config = get_ceremony_config()
    officiant_sheet = ceremony.officiant.character_sheet

    quality_level = 0
    check_type = CheckType.objects.filter(name=CEREMONY_CHECK_TYPE_NAME).first()
    if check_type is not None:
        # The rite follows the TRUE being's forms (Decision 10) — its tradition
        # specialization applies even when the presentation claims another god.
        result = perform_check(
            officiant_sheet.character,
            check_type,
            specialization=ceremony.being.tradition.rites_specialization,
        )
        if result.outcome is not None:
            quality_level = result.outcome.success_level

    multiplier = max(
        25, 100 + quality_level * config.quality_multiplier_percent_per_level
    )  # percent; floor keeps a botched rite from zeroing the honors (PLACEHOLDER)

    offering_value_total = sum(o.item_value for o in ceremony.offerings.all())
    offering_legend_total = sum(o.item_legend_value for o in ceremony.offerings.all())
    honorees = list(ceremony.honorees.select_related("honoree_sheet"))
    speeches = list(ceremony.speeches.all())
    total_awarded = 0
    for honoree in honorees:
        speech_levels = sum(
            max(s.success_level or 0, 0)
            for s in speeches
            if s.target_honoree_id is None or s.target_honoree_id == honoree.pk
        )
        base = (
            config.base_honoree_prestige
            + offering_value_total * config.offering_prestige_per_value
            + offering_legend_total
            + speech_levels * config.speech_prestige_base
        )
        amount = base * multiplier // 100
        _mint_ceremony_deed(
            honoree.honoree_sheet,
            f"Honored at a {ceremony.ceremony_type.name.lower()} PLACEHOLDER",
            amount,
        )
        honoree.prestige_awarded = amount
        honoree.save(update_fields=["prestige_awarded"])
        total_awarded += amount

    if total_awarded > 0:
        officiant_cut = total_awarded * config.officiant_cut_percent // 100
        if officiant_cut > 0:
            _mint_ceremony_deed(
                officiant_sheet,
                f"Officiated a {ceremony.ceremony_type.name.lower()} PLACEHOLDER",
                officiant_cut,
            )
    bump_devotion(officiant_sheet, ceremony.being, config.devotion_officiant)

    if ceremony.ceremony_type.key == CeremonyTypeKey.FUNERAL:
        for honoree in honorees:
            execute_will(honoree.honoree_sheet)

    ceremony.quality_level = quality_level
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.finished_at = timezone.now()
    ceremony.save(update_fields=["quality_level", "status", "finished_at"])
    return ceremony


def abandon_ceremony(*, ceremony: Ceremony) -> Ceremony:
    """Decision 12: close the rite awarding nothing; frees the location + ghost window."""
    _require_open(ceremony)
    ceremony.status = CeremonyStatus.ABANDONED
    ceremony.finished_at = timezone.now()
    ceremony.save(update_fields=["status", "finished_at"])
    return ceremony


def execute_will(character_sheet: "CharacterSheet") -> None:
    """Execute the deceased's estate — the funeral door of #1985.

    A funeral's finish calls this per honoree. Delegates to the single
    idempotent settlement path; an already-settled (or never-opened) estate
    is a quiet no-op, so honoring a long-dead character stays safe.
    """
    from world.estates.constants import SettlementDoor  # noqa: PLC0415
    from world.estates.services import execute_settlement  # noqa: PLC0415

    execute_settlement(character_sheet, via=SettlementDoor.FUNERAL)


def open_funeral_for(character_sheet: "CharacterSheet") -> Ceremony | None:
    """The OPEN funeral honoring this character, if any (the ghost container)."""
    return Ceremony.objects.filter(
        status=CeremonyStatus.OPEN,
        ceremony_type__key=CeremonyTypeKey.FUNERAL,
        honorees__honoree_sheet=character_sheet,
    ).first()


def _require_open(ceremony: Ceremony) -> None:
    if ceremony.status != CeremonyStatus.OPEN:
        msg = "This ceremony has already concluded."
        raise CeremonyError(msg)


def _mint_ceremony_deed(sheet: "CharacterSheet", title: str, value: int) -> None:
    """Mint a solo deed through the legend engine (renown flows from there)."""
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    persona = sheet.primary_persona
    if persona is None:
        return
    source_type, _ = LegendSourceType.objects.get_or_create(
        name=CEREMONY_LEGEND_SOURCE,
        defaults={"description": "Rites and ceremonies — honors spoken over the worthy."},
    )
    create_solo_deed(
        persona,
        title,
        source_type,
        value,
        description="PLACEHOLDER — ceremony deed prose pending Apostate rewrite.",
    )
