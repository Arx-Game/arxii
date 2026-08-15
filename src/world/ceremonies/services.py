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

from world.ceremonies.constants import (
    CeremonyStatus,
    CeremonyTypeKey,
    ConversionOfferStatus,
    SeanceOfferStatus,
)
from world.ceremonies.models import (
    Ceremony,
    CeremonyHonoree,
    CeremonyOffering,
    CeremonySpeech,
    CeremonyType,
    get_ceremony_config,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.ceremonies.models import SeanceManifestationOffer, WorshipConversionOffer
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.societies.models import PhilosophicalArchetype
    from world.worship.models import WorshippedBeing

logger = logging.getLogger(__name__)

CEREMONY_CHECK_TYPE_NAME = "Ceremony Rites"
SPEECH_CHECK_TYPE_NAME = "Performance"
SPEECH_SPECIALIZATION_NAME = "Oratory"
CEREMONY_LEGEND_SOURCE = "Ceremony"
# PLACEHOLDER content mapping (#2361): reuses the existing Apostate-authored
# scandal vocabulary (#1464) for old→new conversion framing rather than
# minting new PhilosophicalArchetype rows — see ``_conversion_archetypes``.
_CONVERSION_BETRAYAL_ARCHETYPE = "Treacherous Scandal"


class CeremonyError(Exception):
    """Player-facing ceremony failure; ``user_message`` is safe to display."""

    def __init__(self, msg: str, *, user_message: str | None = None) -> None:
        super().__init__(msg)
        self.user_message = user_message or msg


class SeanceOfferError(Exception):
    """Player-facing seance-offer failure; ``user_message`` is safe to display."""

    def __init__(self, msg: str, *, user_message: str | None = None) -> None:
        super().__init__(msg)
        self.user_message = user_message or msg


class ConversionOfferError(Exception):
    """Player-facing conversion-offer failure; ``user_message`` is safe to display."""

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


def _validate_honorees_for_type(ceremony_type: CeremonyType, honoree_sheets: "list") -> None:
    """Decision 13/#2361 pre-open validation, per ceremony type."""
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
    if ceremony_type.key == CeremonyTypeKey.CONVERSION and len(honoree_sheets) != 1:
        msg = "A conversion rite has exactly one convert."
        raise CeremonyError(msg)


def _create_type_specific_offers(ceremony: Ceremony, officiant_sheet: "CharacterSheet") -> None:
    """SEANCE/CONVERSION consent-offer rows, minted alongside the honorees at open."""
    if ceremony.ceremony_type.key == CeremonyTypeKey.SEANCE:
        from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415

        SeanceManifestationOffer.objects.bulk_create(
            SeanceManifestationOffer(ceremony_honoree=honoree)
            for honoree in ceremony.honorees.all()
        )
    if ceremony.ceremony_type.key == CeremonyTypeKey.CONVERSION:
        from world.ceremonies.models import WorshipConversionOffer  # noqa: PLC0415

        convert_honoree = ceremony.honorees.get()
        if convert_honoree.honoree_sheet_id != officiant_sheet.pk:
            # PC-officiated route (Ratified amendment #1a): the convert is
            # someone other than the officiant — needs a consent offer. A
            # self-officiated solo rite (Ratified amendment #1b) needs none:
            # nobody consents to their own choice.
            WorshipConversionOffer.objects.create(ceremony_honoree=convert_honoree)


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
    A Conversion requires exactly one honoree — the convert (#2361). Only one OPEN
    ceremony may exist per location (DB constraint).
    """
    ceremony_type = CeremonyType.objects.filter(key=type_key).first()
    if ceremony_type is None:
        msg = "That kind of ceremony is not recognized."
        raise CeremonyError(msg)
    _validate_honorees_for_type(ceremony_type, honoree_sheets)

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
            _create_type_specific_offers(ceremony, officiant_sheet)
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
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=SPEECH_CHECK_TYPE_NAME).first()
    success_level = None
    if check_type is not None:
        oratory = Specialization.objects.filter(
            name=SPEECH_SPECIALIZATION_NAME,
            parent_skill__trait__name=SPEECH_CHECK_TYPE_NAME,
        ).first()
        result = perform_check_with_modifiers(
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


def finish_ceremony(*, ceremony: Ceremony, sincere: bool | None = None) -> Ceremony:
    """Close the rite: quality roll, renown tallies, worship, funeral effects.

    ``sincere`` is the heart-vs-lip-service choice (#2361 Ratified amendment #2)
    for a SELF-officiated CONVERSION honoree only (the officiant IS the convert,
    so there is no WorshipConversionOffer to read it from). Ignored for every
    other ceremony type, and ignored for a PC-officiated CONVERSION — there the
    choice was already recorded on the offer at accept time
    (``respond_to_conversion_offer``). Defaults True (sincere) when unspecified.
    """
    _require_open(ceremony)
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.worship.services import bump_devotion  # noqa: PLC0415

    config = get_ceremony_config()
    officiant_sheet = ceremony.officiant.character_sheet

    quality_level = 0
    check_type = CheckType.objects.filter(name=CEREMONY_CHECK_TYPE_NAME).first()
    if check_type is not None:
        # The rite follows the TRUE being's forms (Decision 10) — its tradition
        # specialization applies even when the presentation claims another god.
        result = perform_check_with_modifiers(
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
    honoree_base = (
        config.base_honoree_prestige
        + offering_value_total * config.offering_prestige_per_value
        + offering_legend_total
    )
    total_awarded = 0
    for honoree in honorees:
        amount = _award_honoree(
            honoree,
            ceremony=ceremony,
            speeches=speeches,
            base=honoree_base,
            multiplier=multiplier,
            speech_prestige_base=config.speech_prestige_base,
            sincere=sincere,
        )
        if amount is None:
            # CONVERSION honoree declined, or never answered — the rite
            # concludes but honors nothing for them (mirrors a declined
            # Seance offer): no deed, no worship repoint.
            continue
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

    if ceremony.ceremony_type.key == CeremonyTypeKey.WEDDING:
        _solemnize_wedding_honorees(honorees)

    ceremony.quality_level = quality_level
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.finished_at = timezone.now()
    ceremony.save(update_fields=["quality_level", "status", "finished_at"])
    revoke_seance_manifestations(ceremony)
    return ceremony


def abandon_ceremony(*, ceremony: Ceremony) -> Ceremony:
    """Decision 12: close the rite awarding nothing; frees the location + ghost window."""
    _require_open(ceremony)
    ceremony.status = CeremonyStatus.ABANDONED
    ceremony.finished_at = timezone.now()
    ceremony.save(update_fields=["status", "finished_at"])
    revoke_seance_manifestations(ceremony)
    return ceremony


def revoke_seance_manifestations(ceremony: Ceremony) -> None:
    """Force-unpuppet any manifested RETIRED honoree when a Seance closes (#2393).

    Dead-but-unretired honorees keep their ordinary puppet access after the
    seance closes (only their emit/pose window narrows back down) — only a
    retired honoree's temporary puppet grant is torn down here, mirroring
    ``vitals.services.retire_character``'s own unpuppet-on-retire loop. No-op
    for any non-Seance ceremony type.
    """
    if ceremony.ceremony_type.key != CeremonyTypeKey.SEANCE:
        return
    from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415
    from world.vitals.services import is_retired  # noqa: PLC0415

    offers = SeanceManifestationOffer.objects.filter(
        ceremony_honoree__ceremony=ceremony, status=SeanceOfferStatus.ACCEPTED
    ).select_related("ceremony_honoree__honoree_sheet")
    for offer in offers:
        sheet = offer.ceremony_honoree.honoree_sheet
        if not is_retired(sheet):
            continue
        character = sheet.character
        account = character.db_account
        if account is None:
            continue
        for session in list(character.sessions.all()):
            try:
                account.unpuppet_object(session)
            except Exception:
                logger.exception("unpuppet on seance close failed for sheet %s", sheet.pk)


def _solemnize_wedding_honorees(honorees) -> None:
    """WEDDING rite (#2999, #2358): find the honorees' active betrothal and land it.

    The two honorees' kinsperson nodes must share an active Betrothal; the
    rite then solemnizes in one stroke — union, marriage pact with the
    negotiated commitments, and the marrying-up prestige award. Honorees
    with no betrothal between them are honored (renown fired above) but
    nothing legal happens: the rite needs the promise first.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.societies.houses.models import Betrothal  # noqa: PLC0415
    from world.societies.houses.pact_services import solemnize_wedding  # noqa: PLC0415

    sheet_ids = [h.honoree_sheet_id for h in honorees]
    kin_ids = set(Kinsperson.objects.filter(sheet_id__in=sheet_ids).values_list("pk", flat=True))
    if len(kin_ids) < 2:  # noqa: PLR2004 — a wedding takes two
        return
    betrothal = (
        Betrothal.objects.filter(
            Q(kinsperson_a__in=kin_ids) & Q(kinsperson_b__in=kin_ids),
            broken_at__isnull=True,
            wed_at__isnull=True,
        )
        .order_by("created_at")
        .first()
    )
    if betrothal is None or not betrothal.is_active:
        return
    solemnize_wedding(betrothal)


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


def respond_to_seance_offer(
    offer: "SeanceManifestationOffer", *, account: object, accept: bool
) -> "SeanceManifestationOffer":
    """Accept or decline a pending seance manifestation offer (#2393).

    ``account`` must be the offer's honoree's own controlling account (verified
    via ``account_for_sheet``'s current-tenure walk — ``tenure.end_date IS
    NULL`` — not "currently available"; retiring a character does not end
    their tenure, so this still resolves correctly for a retired honoree,
    unlike ``get_available_characters()``, which additionally filters out
    anything ``is_retired``). Accepting physically moves the honoree's
    character object to the ceremony's location — this is what makes the
    location check in both ``GhostWindowPrerequisite`` and
    ``Account.can_puppet_for_seance`` satisfiable regardless of where the
    character was left (a ghost pinned to a death scene, or a retired
    character nobody has been able to move since).
    """
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415

    sheet = offer.ceremony_honoree.honoree_sheet
    if account_for_sheet(sheet) != account:
        msg = "That isn't your character to answer for."
        raise SeanceOfferError(msg)
    if offer.status != SeanceOfferStatus.PENDING:
        msg = "That offer has already been answered."
        raise SeanceOfferError(msg)
    if offer.ceremony_honoree.ceremony.status != CeremonyStatus.OPEN:
        msg = "That seance has already closed."
        raise SeanceOfferError(msg)

    offer.status = SeanceOfferStatus.ACCEPTED if accept else SeanceOfferStatus.DECLINED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at"])

    if accept:
        character = sheet.character
        destination = offer.ceremony_honoree.ceremony.location.objectdb
        if character.location != destination:
            character.move_to(destination, quiet=True)
    return offer


def pending_seance_offers_for_account(account: object) -> "QuerySet[SeanceManifestationOffer]":
    """PENDING seance offers addressed to any character this account has ever held (#2393).

    Reachable even for an account whose sole character is retired (and thus
    absent from get_available_characters) — the point of this surface.
    """
    from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415

    return (
        SeanceManifestationOffer.objects.filter(
            status=SeanceOfferStatus.PENDING,
            ceremony_honoree__honoree_sheet__roster_entry__tenures__player_data__account=account,
            ceremony_honoree__honoree_sheet__roster_entry__tenures__end_date__isnull=True,
        )
        .select_related("ceremony_honoree__honoree_sheet", "ceremony_honoree__ceremony")
        .distinct()
    )


def respond_to_conversion_offer(
    offer: "WorshipConversionOffer", *, account: object, accept: bool, sincere: bool = True
) -> "WorshipConversionOffer":
    """Accept or decline a pending public-conversion offer (#2361, Ratified amendment #1a).

    Mirrors ``respond_to_seance_offer``'s account-authorized shape — ``account``
    must be the offer's honoree's own controlling account. Accepting records the
    heart-vs-lip-service choice (Ratified amendment #2) right here on the offer;
    the actual ``WorshipDeclaration`` repoint happens later, at ceremony finish
    (``finish_ceremony``'s CONVERSION branch reads this row). Declining leaves the
    convert's worship completely untouched — the officiant's rite still concludes,
    it just honors nothing for them (mirrors a declined Seance offer). Unlike a
    Seance accept, nothing physically moves — a conversion has no manifestation
    window to open.
    """
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415

    sheet = offer.ceremony_honoree.honoree_sheet
    if account_for_sheet(sheet) != account:
        msg = "That isn't your character to answer for."
        raise ConversionOfferError(msg)
    if offer.status != ConversionOfferStatus.PENDING:
        msg = "That offer has already been answered."
        raise ConversionOfferError(msg)
    if offer.ceremony_honoree.ceremony.status != CeremonyStatus.OPEN:
        msg = "That conversion rite has already closed."
        raise ConversionOfferError(msg)

    offer.status = ConversionOfferStatus.ACCEPTED if accept else ConversionOfferStatus.DECLINED
    offer.is_sincere = bool(sincere) if accept else None
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "is_sincere", "responded_at"])
    return offer


def pending_conversion_offers_for_account(
    account: object,
) -> "QuerySet[WorshipConversionOffer]":
    """PENDING conversion offers addressed to any character this account has ever held.

    Mirrors ``pending_seance_offers_for_account`` (#2393).
    """
    from world.ceremonies.models import WorshipConversionOffer  # noqa: PLC0415

    return (
        WorshipConversionOffer.objects.filter(
            status=ConversionOfferStatus.PENDING,
            ceremony_honoree__honoree_sheet__roster_entry__tenures__player_data__account=account,
            ceremony_honoree__honoree_sheet__roster_entry__tenures__end_date__isnull=True,
        )
        .select_related("ceremony_honoree__honoree_sheet", "ceremony_honoree__ceremony")
        .distinct()
    )


def _require_open(ceremony: Ceremony) -> None:
    if ceremony.status != CeremonyStatus.OPEN:
        msg = "This ceremony has already concluded."
        raise CeremonyError(msg)


def _resolve_conversion_confirmation(
    honoree: CeremonyHonoree, sincere: bool | None
) -> tuple[bool, bool]:
    """Whether a CONVERSION honoree's rite is confirmed, and their heart-vs-lip choice.

    Self-officiated (the convert leading their own rite, Ratified amendment #1b)
    needs no consent offer — confirmed unconditionally; the ``sincere`` kwarg
    passed to ``finish_ceremony`` carries their choice (defaults True/sincere
    when unspecified). A PC-officiated conversion (amendment #1a) gates on the
    honoree's own ``WorshipConversionOffer``: confirmed only once ACCEPTED, and
    the choice recorded there at accept time governs — the officiant's
    ``sincere`` kwarg is never consulted for this route (only the convert's own
    account may set their inward truth).
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        offer = honoree.conversion_offer
    except ObjectDoesNotExist:
        return True, True if sincere is None else sincere
    if offer.status != ConversionOfferStatus.ACCEPTED:
        return False, False
    return True, bool(offer.is_sincere)


def _award_honoree(  # noqa: PLR0913 — keyword-only; each arg is a distinct tally input
    honoree: CeremonyHonoree,
    *,
    ceremony: Ceremony,
    speeches: list,
    base: int,
    multiplier: int,
    speech_prestige_base: int,
    sincere: bool | None,
) -> int | None:
    """Resolve one honoree's deed (title/archetypes/scene), mint it, tally prestige.

    Returns the awarded amount, or ``None`` for a CONVERSION honoree whose
    conversion wasn't confirmed (declined/still-pending offer) — the caller skips
    them entirely, no deed minted, no worship repoint.
    """
    title = f"Honored at a {ceremony.ceremony_type.name.lower()} PLACEHOLDER"
    archetypes = None
    deed_scene = None
    if ceremony.ceremony_type.key == CeremonyTypeKey.CONVERSION:
        outcome = _convert_honoree_if_confirmed(honoree, ceremony, sincere)
        if outcome is None:
            return None
        title, archetypes, deed_scene = outcome

    speech_levels = sum(
        max(s.success_level or 0, 0)
        for s in speeches
        if s.target_honoree_id is None or s.target_honoree_id == honoree.pk
    )
    amount = (base + speech_levels * speech_prestige_base) * multiplier // 100
    _mint_ceremony_deed(
        honoree.honoree_sheet, title, amount, archetypes=archetypes, scene=deed_scene
    )
    honoree.prestige_awarded = amount
    honoree.save(update_fields=["prestige_awarded"])
    return amount


def _convert_honoree_if_confirmed(
    honoree: CeremonyHonoree, ceremony: Ceremony, sincere: bool | None
) -> "tuple[str, list[PhilosophicalArchetype], object | None] | None":
    """Repoint a CONVERSION honoree's worship if their conversion is confirmed.

    Returns ``(deed_title, archetypes, scene)`` for ``finish_ceremony``'s per-honoree
    deed mint, or ``None`` when the honoree declined/never answered — the caller
    skips minting anything for them entirely. Side-effects (the actual
    ``convert_public_worship`` repoint) only happen on the confirmed path.
    """
    confirmed, honoree_is_sincere = _resolve_conversion_confirmation(honoree, sincere)
    if not confirmed:
        return None
    from world.worship.services import convert_public_worship  # noqa: PLC0415

    archetypes = _conversion_archetypes(honoree.honoree_sheet, ceremony.presented_being)
    convert_public_worship(
        honoree.honoree_sheet, ceremony.presented_being, is_sincere=honoree_is_sincere
    )
    title = f"Converted to {ceremony.presented_being.name} PLACEHOLDER"
    return title, archetypes, ceremony.scene


def _conversion_archetypes(
    sheet: "CharacterSheet", new_being: "WorshippedBeing"
) -> "list[PhilosophicalArchetype]":
    """PLACEHOLDER content mapping (#2361): archetype tags for the scandal fork.

    Reuses the existing Apostate-authored scandal vocabulary (#1464) — a
    conversion AWAY from an already-declared public faith reads as a broken vow
    ("Treacherous Scandal") regardless of which being it moves to or from;
    per-tradition/per-being framing (a specific "Heretical" vs "Pious" split)
    would mean minting new ``PhilosophicalArchetype`` rows into that closed,
    curated vocabulary, which this pass does not do — flagged for Apostate if a
    finer split is wanted later. A first public declaration (no prior public
    faith to betray) carries NO archetype tag, so ``route_deed_reach``'s
    archetype-required guard skips the scandal fork for it entirely — converting
    from nothing isn't a betrayal of anything.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.societies.models import PhilosophicalArchetype  # noqa: PLC0415

    try:
        declaration = sheet.worship_declaration
    except ObjectDoesNotExist:
        return []
    if declaration.public_being_id is None or declaration.public_being_id == new_being.pk:
        return []
    archetype = PhilosophicalArchetype.objects.filter(name=_CONVERSION_BETRAYAL_ARCHETYPE).first()
    return [archetype] if archetype is not None else []


def _mint_ceremony_deed(
    sheet: "CharacterSheet",
    title: str,
    value: int,
    *,
    archetypes: "list[PhilosophicalArchetype] | None" = None,
    scene=None,
) -> None:
    """Mint a solo deed through the legend engine (renown flows from there).

    ``archetypes``/``scene`` (#2361) pass straight through to
    ``create_solo_deed`` — untouched (None) for every ceremony type except
    CONVERSION, whose scandal framing needs the #1464 reach fork
    (``route_deed_reach``) to fire. ``create_solo_deed`` already no-ops the
    fork when ``scene`` is None or ``archetypes`` is empty, so this is a pure
    additive extension — every other caller's behavior is unchanged.
    """
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
        archetypes=archetypes,
        scene=scene,
    )
