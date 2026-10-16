"""Pledges (#4333 slice 2, design 2 and 3): serving a being to earn its favor.

A pledge type (``Pledge``) is a being's authored offer of service with a favor
target and a span. Taking one opens a ``Project`` of kind PLEDGE with a
``PledgeDetails`` sidecar; a character holds at most one open pledge.

* **Progress** is favor: ``bump_devotion`` calls :func:`record_pledge_credit`
  for every favor write, and while the character holds an open pledge to that
  being the credited amount is added to ``Project.current_progress`` and logged
  as a ``PledgeCredit`` with its calculation. There is no other counter.
* **Deeds** (:func:`credit_pledge_deed`, called by ``grant_resonance``): a
  resonance grant the being holds as FAVORED or ASSOCIATED earns a share of the
  amount granted, under a weekly cap on base deed favor.
* **Closing** (:func:`close_pledge`): reaching the target never resolves a
  pledge (PLEDGE is expiry-only). Its closing rite does, through
  ``perform_worship_rite(..., pay_award=False)``. A first Failure or Critical
  Failure leaves one retry (Ruling 17); any other result, or a second attempt,
  resolves it in one atomic block and the PLEDGE handler pays the CLOSING
  ``FavorOutcomeAward`` for the rite's outcome tier.
* **Lapse** (:func:`resolve_pledge_project` with no closing performance): at
  the span's end the tick resolves it. At least half the target earned pays the
  Partial Success closing award; less pays nothing (Ruling 18). Favor already
  earned is kept either way, and a lapse never delivers an answer.

* **Answers** (slice 3): a resolving closing rite releases one written-ahead
  answer for its tier, delivered as a vision by ``answer_services`` after the
  resolution commits; a lapse never does.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.worship.constants import (
    DAYS_PER_GAME_WEEK,
    FAVOR_EARNING_BASE_PERCENT,
    PLEDGE_MAX_CLOSE_ATTEMPTS,
    PRAYER_TEXT_MAX_LENGTH,
    BeingResonanceTier,
    FavorAwardKind,
    PledgeCreditSource,
    PledgeState,
)
from world.worship.exceptions import (
    NoOpenPledge,
    PledgeAlreadyOpen,
    PledgeError,
    PledgeNotReady,
    PledgeSpanEnded,
    PledgeUnavailable,
)
from world.worship.models import (
    BeingResonance,
    FavorOutcomeAward,
    Pledge,
    PledgeCredit,
    PledgeDetails,
)
from world.worship.types import (
    ClosingOutcome,
    EarningRateBreakdown,
    FavorSource,
    HolySite,
    PledgeCard,
    PledgeCreditLine,
    ServiceTermLine,
    ServiceTerms,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import ResonanceGrant
    from world.projects.models import Project
    from world.scenes.models import Persona, Scene
    from world.traits.models import CheckOutcome
    from world.worship.models import WorshippedBeing

#: Outcome tiers below this success level are a failed close (Failure, Critical Failure).
_FAILED_CLOSE_BELOW = 0
#: The success level of Partial Success, whose closing award a lapse at half pays.
_PARTIAL_SUCCESS_LEVEL = 0
#: Sources that are paid when a pledge resolves and never add to its progress.
_RESOLUTION_SOURCES = frozenset({PledgeCreditSource.CLOSING, PledgeCreditSource.LAPSE})


# ---------------------------------------------------------------------------
# Reading pledges
# ---------------------------------------------------------------------------


def open_pledge_for(sheet: CharacterSheet) -> PledgeDetails | None:
    """The character's open pledge (its project ACTIVE), or None."""
    return (
        PledgeDetails.objects.filter(character_sheet=sheet, project__status=ProjectStatus.ACTIVE)
        .select_related("project", "pledge__being", "pledge__closing_rite__kind")
        .first()
    )


def latest_pledge_for(sheet: CharacterSheet) -> PledgeDetails | None:
    """The character's open pledge, else the one that resolved most recently."""
    return (
        PledgeDetails.objects.filter(character_sheet=sheet)
        .select_related("project", "pledge__being", "pledge__closing_rite__kind")
        .order_by("-created_at", "-pk")
        .first()
    )


def offered_pledges(being: WorshippedBeing) -> list[Pledge]:
    """The active pledge types ``being`` offers."""
    if not being.is_active:
        return []
    return list(
        Pledge.objects.filter(being=being, is_active=True).select_related("closing_rite__kind")
    )


def pledge_state(details: PledgeDetails) -> str:
    """OPEN, READY (at its target, awaiting the closing rite), CLOSED or LAPSED."""
    project = details.project
    if project.status in (ProjectStatus.ACTIVE, ProjectStatus.RESOLVING):
        target = project.threshold_target or 0
        return PledgeState.READY if project.current_progress >= target else PledgeState.OPEN
    if details.closing_performance_id is not None:
        return PledgeState.CLOSED
    return PledgeState.LAPSED


# ---------------------------------------------------------------------------
# Taking a pledge
# ---------------------------------------------------------------------------


def take_pledge(sheet: CharacterSheet, pledge: Pledge, *, prayer_text: str = "") -> PledgeDetails:
    """Open ``pledge`` for ``sheet``: a PLEDGE project and its sidecar.

    The favor target is the project's threshold and the span its time limit. A
    prayer, when given, is logged through ``pray`` after the pledge opens, so a
    holy-site prayer's devotion already counts toward it.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.prayer_services import pray  # noqa: PLC0415

    if not pledge.is_active or not pledge.being.is_active:
        raise PledgeUnavailable
    words = prayer_text.strip()
    if len(words) > PRAYER_TEXT_MAX_LENGTH:
        msg = f"A prayer is at most {PRAYER_TEXT_MAX_LENGTH} characters."
        raise PledgeError(msg)
    persona = active_persona_for_sheet(sheet)
    now = timezone.now()
    with transaction.atomic():
        # Locked so two requests cannot both open a pledge for one character.
        CharacterSheet.objects.select_for_update().filter(pk=sheet.pk).exists()
        if open_pledge_for(sheet) is not None:
            raise PledgeAlreadyOpen
        project = Project.objects.create(
            kind=ProjectKind.PLEDGE,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=pledge.span_weeks * DAYS_PER_GAME_WEEK),
            threshold_target=pledge.favor_target,
            description=f"Pledge to {pledge.being.name}: {pledge.name}",
        )
        details = PledgeDetails.objects.create(
            project=project, character_sheet=sheet, pledge=pledge
        )
    if words:
        details.prayer = pray(sheet, pledge.being, words).prayer
        details.save(update_fields=["prayer"])
    return details


# ---------------------------------------------------------------------------
# Progress: every favor write for the pledge's being
# ---------------------------------------------------------------------------


def record_pledge_credit(  # noqa: PLR0913 - the calculation's parts are keyword-only
    sheet: CharacterSheet,
    being: WorshippedBeing,
    *,
    base: int,
    rate: int,
    credited: int,
    source: FavorSource | None,
) -> PledgeCredit | None:
    """Credit ``credited`` favor to the character's pledge to ``being``, if any.

    Called by ``bump_devotion`` for every positive favor write. An open pledge
    to ``being`` gains the amount on ``Project.current_progress`` and a
    ``PledgeCredit`` row; a closing or lapse award names its pledge on
    ``source`` and is recorded without adding progress.
    """
    source = source or FavorSource()
    details = source.pledge_details or open_pledge_for(sheet)
    if details is None or details.pledge.being_id != being.pk:
        return None
    project = details.project
    if project.status == ProjectStatus.ACTIVE and source.kind not in _RESOLUTION_SOURCES:
        project.current_progress += credited
        project.save(update_fields=["current_progress", "updated_at"])
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    return PledgeCredit.objects.create(
        pledge_details=details,
        source=source.kind,
        base=max(base, 0),
        earning_rate_percent=rate,
        credited=credited,
        game_week=get_current_game_week(),
        resonance_grant=source.resonance_grant,
        offering=source.offering,
        rite_performance=source.rite_performance,
    )


def deed_favor_used_this_week(sheet: CharacterSheet) -> int:
    """Base favor ``sheet`` has earned from deeds in the current game week."""
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    total = PledgeCredit.objects.filter(
        pledge_details__character_sheet=sheet,
        source=PledgeCreditSource.DEED,
        game_week=get_current_game_week(),
    ).aggregate(total=Sum("base"))["total"]
    return total or 0


def credit_pledge_deed(grant: ResonanceGrant) -> PledgeCredit | None:
    """Turn a resonance grant into deed favor for an open pledge (design 2).

    Counts only while the character holds an open pledge, and only for a
    resonance the pledge's being holds as FAVORED or ASSOCIATED. Base favor is
    the grant's amount times the configured percentage for that tier, rounded
    down, at least 1, then held to what is left of the weekly deed cap (base
    favor, before the earning rate). A worship rite's own grant is skipped: the
    rite already pays favor.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415
    from world.worship.services import bump_devotion  # noqa: PLC0415

    if grant.source == GainSource.WORSHIP_RITE:
        return None
    sheet = grant.character_sheet
    details = open_pledge_for(sheet)
    if details is None:
        return None
    being = details.pledge.being
    tier = (
        BeingResonance.objects.filter(being=being, resonance_id=grant.resonance_id)
        .values_list("tier", flat=True)
        .first()
    )
    if tier is None:
        return None
    config = get_devotion_config()
    percent = (
        config.favored_deed_percent
        if tier == BeingResonanceTier.FAVORED
        else config.associated_deed_percent
    )
    base = max(grant.amount * percent // 100, 1)
    base = min(base, config.weekly_deed_favor_cap - deed_favor_used_this_week(sheet))
    if base <= 0:
        return None
    return bump_devotion(
        sheet,
        being,
        base,
        source=FavorSource(kind=PledgeCreditSource.DEED, resonance_grant=grant),
    ).pledge_credit


# ---------------------------------------------------------------------------
# Closing and resolution
# ---------------------------------------------------------------------------


def close_pledge(sheet: CharacterSheet, *, scene: Scene) -> ClosingOutcome:
    """Perform the open pledge's closing rite in ``scene`` (design 3).

    Requires the favor target met and the span not yet ended. The rite rolls
    and records its performance without paying its own award. A first Failure
    or Critical Failure leaves the pledge open for one retry (Ruling 17).
    Anything else, or a second attempt, resolves it in one atomic block: the
    project goes to RESOLVING, the performance is recorded on the sidecar and
    ``resolve_project`` runs the PLEDGE handler, which pays the closing award.
    Once that commits, the answer for the rite's tier is drawn and delivered as
    a vision, or held while the being's pool is short (slice 3, design 4).
    """
    from world.projects.services import resolve_project  # noqa: PLC0415
    from world.worship.answer_services import deliver_pledge_answer  # noqa: PLC0415
    from world.worship.rite_services import perform_worship_rite  # noqa: PLC0415

    details = open_pledge_for(sheet)
    if details is None:
        raise NoOpenPledge
    project = details.project
    if timezone.now() >= project.time_limit:
        raise PledgeSpanEnded
    if project.current_progress < (project.threshold_target or 0):
        raise PledgeNotReady
    rite = details.pledge.closing_rite
    rite_outcome = perform_worship_rite(sheet, rite, scene=scene, pay_award=False)
    performance = rite_outcome.performance
    outcome = performance.outcome_tier
    details.close_attempts += 1
    if (
        outcome.success_level < _FAILED_CLOSE_BELOW
        and details.close_attempts < PLEDGE_MAX_CLOSE_ATTEMPTS
    ):
        details.save(update_fields=["close_attempts"])
        return ClosingOutcome(
            details=details,
            rite=rite,
            outcome_name=outcome.name,
            resolved=False,
            award_base=0,
            award=0,
            earning_rate_percent=0,
        )
    resolved = False
    try:
        with transaction.atomic():
            project.status = ProjectStatus.RESOLVING
            project.save(update_fields=["status", "updated_at"])
            details.closing_performance = performance
            details.save(update_fields=["close_attempts", "closing_performance"])
            resolve_project(project, outcome_tier=outcome)
        resolved = True
    finally:
        if not resolved:
            # The rollback restored the rows; put the identity-mapped instances back
            # to match, or every later reader would see the refused resolution.
            project.status = ProjectStatus.ACTIVE
            details.closing_performance = None
            details.close_attempts -= 1
    award = details.credits.filter(source=PledgeCreditSource.CLOSING).order_by("-pk").first()
    # The answer goes out after the resolution commits: send_vision pushes the vision
    # to an online player the moment its own record commits, so a push from inside
    # the block above could show a vision a rolled-back resolution never kept.
    delivery = deliver_pledge_answer(details, outcome)
    return ClosingOutcome(
        details=details,
        rite=rite,
        outcome_name=outcome.name,
        resolved=True,
        award_base=award.base if award is not None else 0,
        award=award.credited if award is not None else 0,
        earning_rate_percent=award.earning_rate_percent if award is not None else 0,
        delivery=delivery,
    )


def closing_award_amount(
    *, outcome_tier: CheckOutcome | None = None, success_level: int | None = None
) -> int:
    """The CLOSING ``FavorOutcomeAward`` amount for a tier; 0 when none is authored."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    rows = FavorOutcomeAward.objects.filter(
        config=get_devotion_config(), kind=FavorAwardKind.CLOSING
    )
    if outcome_tier is not None:
        rows = rows.filter(outcome_tier=outcome_tier)
    else:
        rows = rows.filter(outcome_tier__success_level=success_level)
    award = rows.first()
    return award.amount if award is not None else 0


def lapse_pays_partial(project: Project) -> bool:
    """Ruling 18: a lapse pays the Partial Success award at half the target or more."""
    target = project.threshold_target or 0
    return project.current_progress * 2 >= target


def resolve_pledge_project(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """The PLEDGE kind handler, run by ``resolve_project`` (design 3).

    With a closing performance on the sidecar, the closing rite resolved it:
    pay the CLOSING award for ``outcome_tier``. Without one it lapsed at the end
    of its span, whatever tier the tick passed: pay the Partial Success closing
    award when at least half the target was earned, else nothing (Ruling 18).
    Awards go through ``bump_devotion`` at the earning rate. Favor already
    earned is never taken back. The closing answer is delivered by
    ``close_pledge`` once this resolution commits, never from inside it (a
    vision is pushed to the player as it is written); a lapse has none.
    """
    from world.worship.services import bump_devotion  # noqa: PLC0415

    details = project.pledge_details
    being = details.pledge.being
    if details.closing_performance_id is None:
        if not lapse_pays_partial(project):
            return
        amount = closing_award_amount(success_level=_PARTIAL_SUCCESS_LEVEL)
        kind = PledgeCreditSource.LAPSE
    else:
        amount = closing_award_amount(outcome_tier=outcome_tier)
        kind = PledgeCreditSource.CLOSING
    if amount <= 0:
        return
    bump_devotion(
        details.character_sheet,
        being,
        amount,
        source=FavorSource(
            kind=kind,
            pledge_details=details,
            rite_performance=details.closing_performance,
        ),
    )


# ---------------------------------------------------------------------------
# What earns favor, and the pledge card
# ---------------------------------------------------------------------------


def earning_rate_breakdown(sheet: CharacterSheet, being: WorshippedBeing) -> EarningRateBreakdown:
    """The earning rate's parts: the base, the Chosen bonus and favor earning modifiers."""
    from world.mechanics.constants import FAVOR_EARNING_CATEGORY_NAME  # noqa: PLC0415
    from world.worship.favor_services import (  # noqa: PLC0415
        active_patronage_of,
        favor_modifier_total,
    )
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    chosen = (
        get_chosen_favor_config().earn_bonus_percent
        if active_patronage_of(sheet, being) is not None
        else 0
    )
    return EarningRateBreakdown(
        base=FAVOR_EARNING_BASE_PERCENT,
        chosen_bonus=chosen,
        modifiers=favor_modifier_total(sheet, being, FAVOR_EARNING_CATEGORY_NAME),
    )


def multiplier_label(percent: int) -> str:
    """A percent multiplier as "x2" or "x1.5"."""
    return f"x{percent / 100:g}"


def service_terms(sheet: CharacterSheet, being: WorshippedBeing) -> ServiceTerms:
    """What earns favor with ``being`` for ``sheet``, system-generated from the
    being's resonances and facets and the devotion terms (design 9)."""
    from world.ceremonies.models import get_ceremony_config  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    config = get_devotion_config()
    lines: list[ServiceTermLine] = []
    resonances = BeingResonance.objects.filter(being=being).select_related("resonance")
    for row in sorted(resonances, key=lambda r: (r.tier != BeingResonanceTier.FAVORED, r.pk)):
        favored = row.tier == BeingResonanceTier.FAVORED
        percent = config.favored_deed_percent if favored else config.associated_deed_percent
        lines.append(
            ServiceTermLine(
                label=f"Deeds that grant {row.resonance.name} ({row.get_tier_display().lower()})",
                amount=f"{percent}% of amount",
            )
        )
    facets = sorted(being.being_facets.values_list("facet__name", flat=True))
    sacrifice = f"Sacrifices at a shrine or temple of {being.name}"
    if facets:
        multiplier = multiplier_label(
            get_ceremony_config().offering_favored_facet_multiplier_percent
        )
        sacrifice += f"; items with the {', '.join(facets)} facet count {multiplier}"
    lines.append(
        ServiceTermLine(label=sacrifice, amount=f"1 per {config.sacrifice_value_per_favor} value")
    )
    lines.append(
        ServiceTermLine(
            label=f"{being.name}'s rites, holy-site prayer, ceremony offerings",
            amount="keep earning, at your rate",
        )
    )
    return ServiceTerms(
        being=being,
        rate=earning_rate_breakdown(sheet, being),
        lines=lines,
        weekly_deed_cap=config.weekly_deed_favor_cap,
    )


def _sacrifice_calculation(credit: PledgeCredit) -> str:
    from world.ceremonies.models import get_ceremony_config  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    offering = credit.offering
    if offering is None:
        return f"{credit.base} base"
    raw = max(offering.item_value // get_devotion_config().sacrifice_value_per_favor, 1)
    text = f"value {offering.item_value}: {raw} base"
    if offering.facet_id is not None and credit.base != raw:
        percent = get_ceremony_config().offering_favored_facet_multiplier_percent
        text += f", {multiplier_label(percent)} {offering.facet.name} = {credit.base}"
    return text


def _credit_label(credit: PledgeCredit) -> tuple[str, str]:
    """(label, calculation before the rate) for one credit, in plain words."""
    source = credit.source
    if source == PledgeCreditSource.DEED and credit.resonance_grant is not None:
        grant = credit.resonance_grant
        label = f"{grant.get_source_display()} (granted {grant.amount} {grant.resonance.name})"
        return label, f"{credit.base} base"
    if source == PledgeCreditSource.SACRIFICE and credit.offering is not None:
        offering = credit.offering
        label = f"Sacrificed {offering.item_name}"
        if offering.facet_id is not None:
            label += f" ({offering.facet.name} facet, favored)"
        return label, _sacrifice_calculation(credit)
    if source == PledgeCreditSource.RITE and credit.rite_performance is not None:
        return (
            f"Performed {credit.rite_performance.rite.name}",
            f"rite award {credit.base} base",
        )
    if source in _RESOLUTION_SOURCES:
        performance = credit.rite_performance
        tier = performance.outcome_tier.name if performance is not None else "Partial Success"
        label = (
            f"Closing award for {tier}"
            if source == PledgeCreditSource.CLOSING
            else f"Lapse award (the {tier} closing award, half the target or more earned)"
        )
        return label, f"{credit.base} base"
    return credit.get_source_display(), f"{credit.base} base"


def credit_lines(details: PledgeDetails) -> list[PledgeCreditLine]:
    """Every credit to ``details``, oldest first, with its calculation."""
    lines: list[PledgeCreditLine] = []
    for credit in details.credits.select_related(
        "resonance_grant__resonance",
        "offering__facet",
        "rite_performance__rite",
        "rite_performance__outcome_tier",
    ):
        label, before_rate = _credit_label(credit)
        lines.append(
            PledgeCreditLine(
                id=credit.pk,
                source=credit.source,
                label=label,
                calculation=(
                    f"{before_rate}, at {credit.earning_rate_percent}% = +{credit.credited}"
                ),
                credited=credit.credited,
                counts_toward_progress=credit.source not in _RESOLUTION_SOURCES,
                created_at=credit.created_at,
            )
        )
    return lines


def pledge_card(details: PledgeDetails) -> PledgeCard:
    """The pledge card's data: state, progress, credits and the service terms."""
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    project = details.project
    being = details.pledge.being
    sheet = details.character_sheet
    favor = (
        DevotionStanding.objects.filter(character_sheet=sheet, being=being)
        .values_list("favor", flat=True)
        .first()
    ) or 0
    state = pledge_state(details)
    return PledgeCard(
        details=details,
        state=state,
        progress=project.current_progress,
        target=project.threshold_target or 0,
        time_limit=project.time_limit,
        close_attempts=details.close_attempts,
        retry_available=(
            state in (PledgeState.OPEN, PledgeState.READY) and details.close_attempts > 0
        ),
        favor=favor,
        credits=credit_lines(details),
        terms=service_terms(sheet, being),
    )


# ---------------------------------------------------------------------------
# Room lines
# ---------------------------------------------------------------------------


def broadcast_room_line(
    persona: Persona,
    text: str,
    *,
    location: ObjectDB | None,  # noqa: OBJECTDB_PARAM - the room the line is heard in
) -> None:
    """Write one OUTCOME room line (in the room's scene, if one runs) and deliver
    it on commit to the web and telnet, the way invocation lines go out."""
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_interaction,
        deliver_outcome_interaction,
        get_active_scene,
    )

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.OUTCOME,
        scene=get_active_scene(location),
    )
    deliver_outcome_interaction(interaction, location=location)


#: The two kinds of holy site, as the room line and the pledge dialog name them.
SITE_SHRINE = "shrine"
SITE_TEMPLE = "temple"


def holy_sites_here(sheet: CharacterSheet) -> list[HolySite]:
    """The beings holy where ``sheet`` stands: the room's shrine, then the temple
    over it. Empty anywhere else."""
    from world.worship.consecration_services import shrine_at, temple_over  # noqa: PLC0415

    location = sheet.character.location
    room = location.room_profile_or_none if location is not None else None
    sites: list[HolySite] = []
    shrine = shrine_at(room)
    if shrine is not None and shrine.being.is_active:
        sites.append(HolySite(being=shrine.being, site=SITE_SHRINE))
    temple = temple_over(room)
    if temple is not None and temple.being.is_active:
        sites.append(HolySite(being=temple.being, site=SITE_TEMPLE))
    return sites
