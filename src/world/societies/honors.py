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

#: Dotted path ``Ritual.service_function_path`` dispatches to (#3466 Task 8).
#: The seeded row (``world.societies.seeds.ensure_rite_of_honors_ritual``) and
#: any test fixture must match this constant exactly — ``dispatch_ritual`` ->
#: ``_dispatch_service`` (``world/magic/services/ritual_dispatch.py``) resolves
#: it via ``importlib.import_module`` + ``getattr``; the string IS the binding.
HONORS_SERVICE_PATH = "world.societies.honors.honor_deed"


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
        super().__init__(
            "That event never proved anyone's peril, so there is nothing here to honor."
        )


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


class HonoreeNotPresentToEstablishError(HonorRefused):
    """The HONOREE must also have witnessed the anchoring event (whole-branch-review C2).

    Gating only the honorer's presence lets a witness mint a full-ceiling deed for
    someone who was never at the event — inventing peril the honoree never faced,
    which is the one thing this rite must never do. Presence is checked against the
    same ``scene_witness_personas`` list the honorer is checked against, never a
    sheet-wide "already has a deed here" scope (that would become a mask-identity
    oracle — see the module docstring / #3466 whole-branch-review C2).
    """

    def __init__(self) -> None:
        super().__init__(
            "The person you are honoring was not present at that event, so there is "
            "no peril of theirs to honor there."
        )


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
            "This event already has a deed recorded for that act. Honor the existing "
            "deed instead of establishing a new one."
        )


class DeedAtCeilingError(HonorRefused):
    """The deed already carries as much legend as its event ever proved (Decision 2)."""

    def __init__(self) -> None:
        super().__init__("This deed's legend already matches everything its event proved.")


class DeedNotActiveError(HonorRefused):
    """A struck (``is_active=False``) deed cannot be amplified (whole-branch-review I1).

    A struck deed is worth nothing everywhere its value is read (``get_total_value``,
    both materialized views) — spending Hares to raise a ``base_value`` no read path
    will ever surface would be a paid rite for nothing.
    """

    def __init__(self) -> None:
        super().__init__("This deed has been struck and can no longer be honored.")


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


def _resolve_anchor(
    deed: LegendEntry | None, event: LegendEvent | None
) -> tuple[LegendEntry | None, LegendEvent]:
    """Lock and return the deed being amplified (if any) and the event it hangs from.

    Raises when the anchor cannot be established at all: a deed with no event, a
    call with neither, or an event that minted nothing.
    """
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
        # Lock the event row so two concurrent establishes against the SAME
        # event serialize behind this transaction's commit (whole-branch-review
        # C3) — without this, two honorers can both read "no anchored deed yet"
        # and both create one. The amplify branch above gets equivalent
        # serialization for free via the deed's own select_for_update(); the
        # establish branch creates no row to lock ahead of time, so the event
        # itself is what has to be locked.
        anchor_event = LegendEvent.objects.select_for_update().get(pk=event.pk)

    if not anchor_event.deeds.filter(is_active=True).exists():
        raise EventMintedNothingRefusal

    return deed, anchor_event


def _check_establish_eligibility(
    *,
    character_sheet: CharacterSheet,
    honoree_persona: Persona,
    honorer_persona: Persona,
    anchor_event: LegendEvent,
    deed_title: str | None,
) -> None:
    """Refusals specific to minting a NEW deed under an event."""
    if honoree_persona.character_sheet_id == character_sheet.pk:
        raise CannotHonorOwnDeedError
    if anchor_event.deeds.filter(persona=honoree_persona, is_active=True).exists():
        raise HonoreeAlreadyAnchoredError
    if not deed_title:
        msg = "honor_deed requires deed_title when establishing a new deed."
        raise ValueError(msg)
    witnesses = scene_witness_personas(anchor_event.scene) if anchor_event.scene is not None else []
    if honorer_persona not in witnesses:
        raise NotPresentToEstablishError
    # The HONOREE must also have witnessed the event (whole-branch-review
    # C2) — gating only the honorer let a witness mint a full-ceiling deed
    # for someone who was never there, inventing peril they never faced.
    # Deliberately checked against the same witness list, never widened to
    # a sheet-wide "already has a deed here" scope (that would become a
    # mask-identity oracle — see `HonoreeAlreadyAnchoredError`'s docstring).
    if honoree_persona not in witnesses:
        raise HonoreeNotPresentToEstablishError


def _check_amplify_eligibility(
    *, character_sheet: CharacterSheet, honorer_persona: Persona, deed: LegendEntry
) -> None:
    """Refusals specific to adding to an EXISTING deed."""
    if deed.persona.character_sheet_id == character_sheet.pk:
        raise CannotHonorOwnDeedError
    if not deed.is_active:
        raise DeedNotActiveError
    if not knows_deed(persona=honorer_persona, deed=deed):
        raise UnknownDeedError
    if LegendHonor.objects.filter(deed=deed, honorer=honorer_persona).exists():
        raise AlreadyHonoredError


def _check_honor_eligibility(  # noqa: PLR0913 - mirrors honor_deed's inputs
    *,
    character_sheet: CharacterSheet,
    honoree_persona: Persona,
    honorer_persona: Persona,
    deed: LegendEntry | None,
    anchor_event: LegendEvent,
    deed_title: str | None,
    establishing: bool,
) -> None:
    """Every refusal that must land before a Hare is spent or a row is written."""
    # --- Step 2: eligibility -------------------------------------------
    if establishing:
        _check_establish_eligibility(
            character_sheet=character_sheet,
            honoree_persona=honoree_persona,
            honorer_persona=honorer_persona,
            anchor_event=anchor_event,
            deed_title=deed_title,
        )
        return
    _check_amplify_eligibility(
        character_sheet=character_sheet, honorer_persona=honorer_persona, deed=deed
    )


def honor_deed(  # noqa: PLR0913
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
        # --- Steps 1-2: resolve the anchor, then every eligibility refusal ---
        deed, anchor_event = _resolve_anchor(deed, event)
        # Always resolved as the PRIMARY persona (whole-branch-review C1) — never
        # the active/masked one. `_grant_title` (world.achievements.services) makes
        # the identical argument: an honor is a named public act (a public journal
        # + a scene pose already posted under the primary persona via
        # `_post_declaration`), so recording a mask as `LegendHonor.honorer` while
        # publishing under the real name is a deterministic mask-to-real link. The
        # rite is always performed as yourself.
        honorer_persona = character_sheet.primary_persona
        establishing = deed is None
        _check_honor_eligibility(
            character_sheet=character_sheet,
            honoree_persona=honoree_persona,
            honorer_persona=honorer_persona,
            deed=deed,
            anchor_event=anchor_event,
            deed_title=deed_title,
            establishing=establishing,
        )

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
