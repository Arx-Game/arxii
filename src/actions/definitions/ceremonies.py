"""Ceremony actions (#2289): open, offering, speech, finish, abandon.

Thin wrappers over ``world.ceremonies.services`` — telnet (``ceremony``
command family) and web endpoints converge here via ``action.run()``. Also
includes the #2393 seance-offer response pair, account-authorized so a
retired honoree's player (who may have no puppeted character at all) can
answer.
"""

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.prerequisites import Prerequisite
from actions.types import ActionContext, TargetType


def _actor_sheet(actor: ObjectDB):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _actor_persona(actor: ObjectDB):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = _actor_sheet(actor)
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _room_profile(actor: ObjectDB):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    location = actor.location
    if location is None:
        return None
    try:
        return location.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return None


def _open_ceremony_here(actor: ObjectDB):
    from world.ceremonies.constants import CeremonyStatus  # noqa: PLC0415
    from world.ceremonies.models import Ceremony  # noqa: PLC0415

    profile = _room_profile(actor)
    if profile is None:
        return None
    return Ceremony.objects.filter(location=profile, status=CeremonyStatus.OPEN).first()


def _require_officiant(actor: ObjectDB):
    """The OPEN ceremony here, if the actor officiates it; else (None, error)."""
    ceremony = _open_ceremony_here(actor)
    if ceremony is None:
        return None, ActionResult(success=False, message="No ceremony is underway here.")
    persona = _actor_persona(actor)
    if persona is None or persona.pk != ceremony.officiant_id:
        return None, ActionResult(
            success=False, message="Only the officiant may direct the ceremony."
        )
    return ceremony, None


def _resolve_sheet_by_name(actor: ObjectDB, name: str):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    found = actor.search(name, global_search=True, quiet=True)
    target = found[0] if found else None
    if target is None:
        return None
    try:
        return target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _resolve_open_actor(actor: ObjectDB):
    """(persona, profile, error) — the officiant's persona + the room they stand in."""
    persona = _actor_persona(actor)
    if persona is None:
        return (
            None,
            None,
            ActionResult(success=False, message="You have no persona to officiate as."),
        )
    profile = _room_profile(actor)
    if profile is None:
        return None, None, ActionResult(success=False, message="This place cannot host a ceremony.")
    return persona, profile, None


def _resolve_open_honorees(actor: ObjectDB, honoree_names: list[str]):
    """(sheets, error) — resolves each honoree name or fails on the first miss."""
    honoree_sheets = []
    for name in honoree_names:
        sheet = _resolve_sheet_by_name(actor, name)
        if sheet is None:
            return None, ActionResult(success=False, message=f"No character '{name}' found.")
        honoree_sheets.append(sheet)
    return honoree_sheets, None


def _resolve_open_being(being_name: str | None):
    """(being, error) — a named being must resolve; no name means "use your worship"."""
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    if not being_name:
        return None, None
    being = WorshippedBeing.objects.filter(name__iexact=being_name, is_active=True).first()
    if being is None:
        return None, ActionResult(
            success=False, message=f"No worshipped being '{being_name}' is known."
        )
    return being, None


def _resolve_open_title(type_key: str, title_name: str | None):
    """(title, error) — CORONATION requires a resolvable title; other types ignore it."""
    from world.ceremonies.constants import CeremonyTypeKey  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415

    if type_key != CeremonyTypeKey.CORONATION:
        return None, None
    if not title_name:
        return None, ActionResult(
            success=False, message="Name the title being solemnized (=<title>)."
        )
    title = Title.objects.filter(name__iexact=title_name).first()
    if title is None:
        return None, ActionResult(success=False, message=f"No title '{title_name}' is known.")
    return title, None


@dataclass
class OpenCeremonyAction(Action):
    """Open a ceremony recognizing honorees (``ceremony/<type> names[=<being>]``)."""

    key: str = "ceremony_open"
    name: str = "Open Ceremony"
    icon: str = "candle"
    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.ceremonies.services import CeremonyError, open_ceremony  # noqa: PLC0415

        persona, profile, error = _resolve_open_actor(actor)
        if error is not None:
            return error

        type_key = kwargs.get("type_key", "")
        honoree_sheets, error = _resolve_open_honorees(actor, kwargs.get("honoree_names") or [])
        if error is not None:
            return error
        being, error = _resolve_open_being(kwargs.get("being_name"))
        if error is not None:
            return error
        title, error = _resolve_open_title(type_key, kwargs.get("title_name"))
        if error is not None:
            return error

        try:
            ceremony = open_ceremony(
                officiant_persona=persona,
                type_key=type_key,
                honoree_sheets=honoree_sheets,
                location_profile=profile,
                being=being,
                title=title,
                is_staff_fiat=is_staff_observer(actor),
            )
        except CeremonyError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"You open a {ceremony.ceremony_type.name.lower()} in the name of "
                f"{ceremony.presented_being.name}."
            ),
        )


@dataclass
class CeremonyOfferingAction(Action):
    """Sacrifice items to the rite (``ceremony/offering <item>[,…]``)."""

    key: str = "ceremony_offering"
    name: str = "Make Offering"
    icon: str = "flame"
    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import CeremonyError, record_offering  # noqa: PLC0415
        from world.items.models import ItemInstance  # noqa: PLC0415

        ceremony, error = _require_officiant(actor)
        if error is not None:
            return error

        item_names: list[str] = kwargs.get("item_names") or []
        if not item_names:
            return ActionResult(success=False, message="Offer what?")
        instances = []
        for name in item_names:
            found = actor.search(name, quiet=True)  # ground or inventory
            obj = found[0] if found else None
            instance = (
                ItemInstance.objects.filter(game_object=obj).first() if obj is not None else None
            )
            if instance is None:
                return ActionResult(success=False, message=f"No offering '{name}' is within reach.")
            instances.append(instance)
        try:
            offerings = record_offering(ceremony=ceremony, item_instances=instances)
        except CeremonyError as exc:
            return ActionResult(success=False, message=exc.user_message)
        names = ", ".join(o.item_name for o in offerings)
        return ActionResult(success=True, message=f"The offering is consumed: {names}.")


@dataclass
class CeremonySpeechAction(Action):
    """Recognize a speaker (``ceremony/speech <name>[=<honoree>]``)."""

    key: str = "ceremony_speech"
    name: str = "Recognize Speaker"
    icon: str = "scroll"
    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    @staticmethod
    def _resolve_speech_parts(actor: ObjectDB, ceremony, kwargs: dict):
        """Resolve (speaker_persona, target_honoree, error) for the speech."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        speaker_name = kwargs.get("speaker_name", "")
        if not speaker_name:
            return None, None, ActionResult(success=False, message="Recognize whom?")
        speaker_sheet = _resolve_sheet_by_name(actor, speaker_name)
        if speaker_sheet is None:
            return (
                None,
                None,
                ActionResult(success=False, message=f"No character '{speaker_name}' found."),
            )
        try:
            speaker_persona = active_persona_for_sheet(speaker_sheet)
        except ObjectDoesNotExist:
            return (
                None,
                None,
                ActionResult(success=False, message="They have no persona to speak as."),
            )
        target_honoree = None
        honoree_name = kwargs.get("honoree_name")
        if honoree_name:
            honoree_sheet = _resolve_sheet_by_name(actor, honoree_name)
            if honoree_sheet is not None:
                target_honoree = ceremony.honorees.filter(honoree_sheet=honoree_sheet).first()
            if target_honoree is None:
                return (
                    None,
                    None,
                    ActionResult(
                        success=False,
                        message=f"'{honoree_name}' is not honored by this rite.",
                    ),
                )
        return speaker_persona, target_honoree, None

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import CeremonyError, record_speech  # noqa: PLC0415

        ceremony, error = _require_officiant(actor)
        if error is not None:
            return error

        speaker_persona, target_honoree, error = self._resolve_speech_parts(actor, ceremony, kwargs)
        if error is not None:
            return error
        try:
            speech = record_speech(
                ceremony=ceremony,
                speaker_persona=speaker_persona,
                target_honoree=target_honoree,
            )
        except CeremonyError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{speech.speaker} is recognized before the gathering.",
        )


@dataclass
class FinishCeremonyAction(Action):
    """Conclude the rite and tally its honors (``ceremony/finish``)."""

    key: str = "ceremony_finish"
    name: str = "Conclude Ceremony"
    icon: str = "bell"
    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import CeremonyError, finish_ceremony  # noqa: PLC0415

        ceremony, error = _require_officiant(actor)
        if error is not None:
            return error
        # #2361 — a self-officiated CONVERSION's heart-vs-lip-service choice
        # (Ratified amendment #2). Ignored for every other ceremony type, and
        # ignored for a PC-officiated conversion (the convert's own accept
        # already recorded it). Defaults to sincere when unspecified.
        sincere = kwargs.get("sincere")
        try:
            finish_ceremony(ceremony=ceremony, sincere=None if sincere is None else bool(sincere))
        except CeremonyError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message="The rite concludes; its honors are spoken and recorded."
        )


@dataclass
class AbandonCeremonyAction(Action):
    """Abandon the rite unfinished — awards nothing (``ceremony/abandon``)."""

    key: str = "ceremony_abandon"
    name: str = "Abandon Ceremony"
    icon: str = "candle-off"
    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.ceremonies.services import CeremonyError, abandon_ceremony  # noqa: PLC0415

        ceremony = _open_ceremony_here(actor)
        if ceremony is None:
            return ActionResult(success=False, message="No ceremony is underway here.")
        persona = _actor_persona(actor)
        is_officiant = persona is not None and persona.pk == ceremony.officiant_id
        if not is_officiant and not is_staff_observer(actor):
            return ActionResult(
                success=False, message="Only the officiant or staff may abandon the ceremony."
            )
        try:
            abandon_ceremony(ceremony=ceremony)
        except CeremonyError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="The rite is left unfinished.")


@dataclass
class _SeanceOfferActionBase(Action):
    """Shared account-authorized shape for seance-offer accept/decline (#2393).

    Mirrors ``actions/definitions/dramatic_moments.py``'s account-authorized
    pattern — the offer's own player may have no puppeted character at all (a
    retired honoree), so this takes an ``account`` kwarg and accepts
    ``actor=None`` through ``run()``.
    """

    category: str = "ceremonies"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list["Prerequisite"]:
        return []


def _seance_offer_or_none(offer_id: Any):
    from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415

    if offer_id is None:
        return None
    try:
        return SeanceManifestationOffer.objects.select_related(
            "ceremony_honoree__ceremony", "ceremony_honoree__honoree_sheet"
        ).get(pk=int(offer_id))
    except (SeanceManifestationOffer.DoesNotExist, ValueError, TypeError):
        return None


@dataclass
class RespondSeanceOfferAction(_SeanceOfferActionBase):
    """Accept or decline a pending seance manifestation offer (#2393).

    Expects kwargs: ``offer_id`` (int), ``account`` (AccountDB), ``accept`` (bool).
    """

    key: str = "seance_offer_respond"
    name: str = "Respond to Seance Offer"
    icon: str = "ghost"

    def execute(
        self, actor: ObjectDB | None, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import (  # noqa: PLC0415
            SeanceOfferError,
            respond_to_seance_offer,
        )

        offer = _seance_offer_or_none(kwargs.get("offer_id"))
        if offer is None:
            return ActionResult(success=False, message="Which offer? Provide an offer id.")
        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message="No account to answer for.")
        accept = bool(kwargs.get("accept"))
        try:
            respond_to_seance_offer(offer, account=account, accept=accept)
        except SeanceOfferError as exc:
            return ActionResult(success=False, message=exc.user_message)
        verb = "answer" if accept else "decline"
        return ActionResult(
            success=True,
            message=f"You {verb} the seance's call.",
            data={"offer_id": offer.pk, "status": offer.status},
        )


def _conversion_offer_or_none(offer_id: Any):
    from world.ceremonies.models import WorshipConversionOffer  # noqa: PLC0415

    if offer_id is None:
        return None
    try:
        return WorshipConversionOffer.objects.select_related(
            "ceremony_honoree__ceremony", "ceremony_honoree__honoree_sheet"
        ).get(pk=int(offer_id))
    except (WorshipConversionOffer.DoesNotExist, ValueError, TypeError):
        return None


@dataclass
class RespondConversionOfferAction(_SeanceOfferActionBase):
    """Accept or decline a pending public-conversion offer (#2361, Ratified amendment #1a).

    Expects kwargs: ``offer_id`` (int), ``account`` (AccountDB), ``accept`` (bool),
    and — only meaningful when ``accept`` is True — ``sincere`` (bool, the
    heart-vs-lip-service choice, Ratified amendment #2; defaults True).
    """

    key: str = "conversion_offer_respond"
    name: str = "Respond to Conversion Offer"
    icon: str = "candle"

    def execute(
        self, actor: ObjectDB | None, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import (  # noqa: PLC0415
            ConversionOfferError,
            respond_to_conversion_offer,
        )

        offer = _conversion_offer_or_none(kwargs.get("offer_id"))
        if offer is None:
            return ActionResult(success=False, message="Which offer? Provide an offer id.")
        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message="No account to answer for.")
        accept = bool(kwargs.get("accept"))
        sincere = kwargs.get("sincere")
        try:
            respond_to_conversion_offer(
                offer,
                account=account,
                accept=accept,
                sincere=True if sincere is None else bool(sincere),
            )
        except ConversionOfferError as exc:
            return ActionResult(success=False, message=exc.user_message)
        verb = "accept" if accept else "decline"
        return ActionResult(
            success=True,
            message=f"You {verb} the offered conversion.",
            data={"offer_id": offer.pk, "status": offer.status},
        )


def _wedding_consent_offer_or_none(offer_id: Any):
    from world.ceremonies.models import WeddingConsentOffer  # noqa: PLC0415

    if offer_id is None:
        return None
    try:
        return WeddingConsentOffer.objects.select_related(
            "ceremony_honoree__ceremony", "ceremony_honoree__honoree_sheet"
        ).get(pk=int(offer_id))
    except (WeddingConsentOffer.DoesNotExist, ValueError, TypeError):
        return None


@dataclass
class RespondWeddingConsentOfferAction(_SeanceOfferActionBase):
    """Accept or decline a pending wedding consent offer (#2358).

    Expects kwargs: ``offer_id`` (int), ``account`` (AccountDB), ``accept`` (bool).
    Mirrors ``RespondSeanceOfferAction`` — account-authorized, since the
    consenting spouse may not be the officiant nor even co-located.
    """

    key: str = "wedding_consent_respond"
    name: str = "Respond to Wedding Consent"
    icon: str = "rings"

    def execute(
        self, actor: ObjectDB | None, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import (  # noqa: PLC0415
            SeanceOfferError,
            respond_to_wedding_consent_offer,
        )

        offer = _wedding_consent_offer_or_none(kwargs.get("offer_id"))
        if offer is None:
            return ActionResult(success=False, message="Which offer? Provide an offer id.")
        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message="No account to answer for.")
        accept = bool(kwargs.get("accept"))
        try:
            respond_to_wedding_consent_offer(offer, account=account, accept=accept)
        except SeanceOfferError as exc:
            return ActionResult(success=False, message=exc.user_message)
        verb = "accept" if accept else "decline"
        return ActionResult(
            success=True,
            message=f"You {verb} the wedding.",
            data={"offer_id": offer.pk, "status": offer.status},
        )
