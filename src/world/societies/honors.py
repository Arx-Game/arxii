"""The Rite of Honors (#3466): `honor_deed`, the heart of the feature.

A character spends Golden Hares and writes a public journal to honor another
character's legendary deed from an event that already proved perilous.
Honoring raises that deed's ``base_value`` toward what the anchoring
``LegendEvent`` itself paid, and can *establish* a solo deed for an
extraordinary act that automatic settlement never credited.

The design rule that keeps this safe (ADR: "Honors size a deed within the
ceiling its event already proved"): honoring redistributes recognition inside
an envelope the event already proved and can never invent peril that did not
happen. That is the ``headroom`` clamp below — it is the whole point.

Posthumous is unrestricted by design (Decision 7): this module adds no
life-state or death check anywhere, and none should ever be added here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models, transaction

from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME
from world.currency.services import redeem_favor_token, resolve_unredeemed_favor_tokens
from world.journals.services import create_journal_entry
from world.npc_services.effects import NoAvailableFavorTokenError
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet
from world.societies.constants import DeedKnowledgeSource
from world.societies.knowledge_services import (
    grant_deed_knowledge,
    knows_deed,
    scene_witness_personas,
)
from world.societies.models import (
    LegendEntry,
    LegendEvent,
    LegendHonor,
    LegendLevelCalibration,
    LegendSourceType,
    Organization,
    refresh_legend_views,
)
from world.societies.services import create_solo_deed
from world.societies.spread_services import save_deed_story

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual


class HonorRefused(Exception):
    """Base for every refusal in the Rite of Honors. Carries a player-safe ``user_message``."""

    user_message: str = "The rite cannot be completed."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class NoAnchorEventError(HonorRefused):
    """The deed being amplified has no ``LegendEvent`` to bound it (#3466)."""

    def __init__(self) -> None:
        super().__init__(
            "This deed has no event to measure it against, so there is nothing to honor it within."
        )


class EventMintedNothingRefusal(HonorRefused):
    """The anchoring event never minted a single deed — it proved no peril (#3466 Decision 1)."""

    def __init__(self) -> None:
        super().__init__("That event never proved anyone's peril — there is nothing here to honor.")


class CannotHonorOwnDeedError(HonorRefused):
    """A character cannot honor a deed done by one of their own faces (#3466)."""

    def __init__(self) -> None:
        super().__init__("You cannot honor your own deed.")


class AlreadyHonoredError(HonorRefused):
    """This persona has already honored this deed (``unique_honor_per_honorer``)."""

    def __init__(self) -> None:
        super().__init__("You have already honored this deed.")


class NotPresentToEstablishError(HonorRefused):
    """Establishing a deed requires having been a witness (#3466 Decision 6)."""

    def __init__(self) -> None:
        super().__init__("You were not there to establish this deed.")


class UnknownDeedError(HonorRefused):
    """Amplifying a deed requires already knowing of it (#3466 Decision 6)."""

    def __init__(self) -> None:
        super().__init__("You do not know of this deed, so you cannot honor it.")


class HonoreeAlreadyAnchoredError(HonorRefused):
    """The honoree already has a LIVE deed anchored to this event (#3466 — one deed per act).

    Settled automatically or established by an earlier honor, it makes no difference:
    many voices are meant to grow ONE deed, never each mint their own for the same act.
    A struck (``is_active=False``) deed does not count — it is worth nothing everywhere
    else, so directing someone to "honor the existing deed instead" would send them to
    spend Hares on a record that can never be worth anything; the act may still deserve
    a fresh, genuine deed.
    """

    def __init__(self) -> None:
        super().__init__(
            "This event already has a deed recorded for that act — honor the existing "
            "deed instead of establishing a new one."
        )


class DeedAtCeilingError(HonorRefused):
    """The deed already carries as much legend as its event ever proved (Decision 2)."""

    def __init__(self) -> None:
        super().__init__("This deed's legend already matches everything its event proved.")


class InsufficientHaresError(HonorRefused):
    """The honorer does not hold enough unredeemed Golden Hares (#3466 Decision 3)."""

    def __init__(self, required: int) -> None:
        plural = "" if required == 1 else "s"
        super().__init__(
            f"You do not carry {required} unredeemed Golden Hare{plural} for this rite."
        )


def _honors_source_type() -> LegendSourceType:
    """Lazy ``LegendSourceType`` row for honor-established deeds (#3466).

    Mirrors ``_battle_source_type``'s lazy-row idiom (``world/battles/legend_wiring.py``)
    — ``LegendSourceType`` has no fixed enum of members, so rows are get-or-created on
    first use rather than fixture-seeded (fixtures aren't in version control).
    """
    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Honors",
        defaults={"description": "A deed established or amplified by the Rite of Honors."},
    )
    return source_type


def honor_deed(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    character_sheet: CharacterSheet,
    ritual: Ritual,  # noqa: ARG001 — forwarded per the SERVICE dispatch convention; unused here
    honoree_persona: Persona,
    deed: LegendEntry | None = None,
    event: LegendEvent | None = None,
    deed_title: str | None = None,
    journal_title: str,
    journal_body: str,
    **kwargs: object,  # noqa: ARG001 — absorbs extra dispatch-forwarded params this rite ignores
) -> LegendHonor:
    """Honor ``honoree_persona``'s deed, amplifying it or establishing it (#3466).

    Exactly one of ``deed`` (amplify an existing deed) or ``event`` (establish a new
    one under that event) must be given. All eligibility and affordability checks run
    before any write, inside one ``transaction.atomic()`` — a refusal (any
    ``HonorRefused`` subclass) leaves no Hare redeemed, no journal written, and no
    ``LegendHonor`` row.

    Never add a life-state or death check here — honoring the dead is unrestricted
    by design (Decision 7).
    """
    with transaction.atomic():
        # --- Step 1: resolve the anchor -----------------------------------
        if deed is not None:
            deed = LegendEntry.objects.select_for_update().select_related("persona").get(pk=deed.pk)
            anchor_event = deed.event
            if anchor_event is None:
                raise NoAnchorEventError
        else:
            if event is None:
                msg = "honor_deed requires either an existing deed or an event to establish under."
                raise ValueError(msg)
            anchor_event = event

        if not anchor_event.deeds.filter(is_active=True).exists():
            raise EventMintedNothingRefusal

        # --- Step 2: eligibility -------------------------------------------
        honorer_persona = active_persona_for_sheet(character_sheet)
        establishing = deed is None

        if establishing:
            if honoree_persona.character_sheet_id == character_sheet.pk:
                raise CannotHonorOwnDeedError
            if anchor_event.deeds.filter(persona=honoree_persona, is_active=True).exists():
                raise HonoreeAlreadyAnchoredError
            if not deed_title:
                msg = "honor_deed requires deed_title when establishing a new deed."
                raise ValueError(msg)
            witnesses = (
                scene_witness_personas(anchor_event.scene) if anchor_event.scene is not None else []
            )
            if honorer_persona not in witnesses:
                raise NotPresentToEstablishError
        else:
            if deed.persona.character_sheet_id == character_sheet.pk:
                raise CannotHonorOwnDeedError
            if not knows_deed(persona=honorer_persona, deed=deed):
                raise UnknownDeedError
            if LegendHonor.objects.filter(deed=deed, honorer=honorer_persona).exists():
                raise AlreadyHonoredError

        # --- Step 3: price (also serves step 4's calibration lookup) -------
        calibration = LegendLevelCalibration.objects.get(level=character_sheet.current_level)
        hares_required = calibration.honor_hares_required
        academy = Organization.objects.get(name=SHROUDWATCH_ACADEMY_NAME)
        try:
            tokens = resolve_unredeemed_favor_tokens(
                sheet=character_sheet, org=academy, count=hares_required
            )
        except NoAvailableFavorTokenError as exc:
            raise InsufficientHaresError(hares_required) from exc

        # --- Step 4: size it, clamped to the event's own ceiling ------------
        existing_base_value = deed.base_value if deed is not None else 0
        headroom = anchor_event.base_value - existing_base_value
        if headroom <= 0:
            raise DeedAtCeilingError
        value = min(calibration.honor_value_added, headroom)

        # --- Step 5: establish, or raise -------------------------------------
        if establishing:
            max_station = anchor_event.deeds.filter(is_active=True).aggregate(
                models.Max("earned_at_level")
            )["earned_at_level__max"]
            station = min(honoree_persona.character_sheet.current_level, max_station or 0)
            deed = create_solo_deed(
                honoree_persona,
                deed_title,
                _honors_source_type(),
                value,
                scene=anchor_event.scene,
                story=anchor_event.story,
                earned_at_level=station,
                event=anchor_event,
            )
        else:
            deed.base_value += value
            deed.save(update_fields=["base_value"])
            refresh_legend_views()

        # --- Step 6: write the public journal, mirrored onto the deed -------
        journal = create_journal_entry(
            author=character_sheet,
            title=journal_title,
            body=journal_body,
            is_public=True,
            award_weekly_xp=False,
        )
        deed_story = save_deed_story(author_persona=honorer_persona, deed=deed, text=journal_body)

        # --- Step 7: record -------------------------------------------------
        for token in tokens:
            redeem_favor_token(token, redeemer_org=academy)

        honor = LegendHonor.objects.create(
            deed=deed,
            honorer=honorer_persona,
            journal_entry=journal,
            deed_story=deed_story,
            hares_spent=hares_required,
            value_added=value,
            established_deed=establishing,
        )
        honor.hares.set(tokens)

        grant_deed_knowledge(
            deed=deed, personas=[honorer_persona], source=DeedKnowledgeSource.HEARD_TOLD
        )

        from world.magic.audere_majora import _post_declaration  # noqa: PLC0415

        _post_declaration(character_sheet.character, journal_body)

        # --- Step 8: title check ---------------------------------------------
        from world.achievements.services import maybe_grant_deed_title  # noqa: PLC0415

        maybe_grant_deed_title(deed)

    return honor
