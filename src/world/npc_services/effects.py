"""Per-kind effect handler registry for `NPCServiceOffer`.

When a player completes an interaction by selecting an offer's final action,
the offer's `kind` selects a handler from this registry. The handler is
responsible for producing the downstream object — issuing the permit item,
instantiating the mission, creating the loan obligation, etc.

Plan 2 ships only the `PERMIT` handler stub. Plan 3 (#668) fills in the real
`BuildingPermit` `ItemInstance` + `BuildingPermitDetails` row creation.
Future kinds (`MISSION`, `LOAN`, `TRAINING`, ...) register their own
handlers as they land. Mission migration onto this registry is tracked in
#686.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction

from world.npc_services.constants import OfferKind

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.currency.models import FavorTokenDetails
    from world.magic.models import Technique
    from world.npc_services.models import (
        NPCRole,
        NPCServiceOffer,
        SkillCourseEnrollment,
        SkillCourseOfferDetails,
    )
    from world.scenes.models import Persona
    from world.societies.models import Organization


@dataclass(frozen=True)
class EffectResult:
    """Structured result returned by an offer effect handler.

    Carries enough information for the interaction state machine to render
    a closing message to the player and (optionally) for the caller to
    reach the downstream object. ``kind`` echoes the offer kind so
    consumers don't have to redispatch; ``object_pk`` and ``object_label``
    identify the produced object when one is created (None when the
    effect is a one-shot side effect with no persistent object).
    """

    kind: str  # OfferKind value
    object_pk: int | None = None
    object_label: str = ""
    message: str = ""
    payload: dict = field(default_factory=dict)


# Effect handler signature:
#   handler(offer: NPCServiceOffer, persona: Persona) -> EffectResult
#
# The interaction state machine resolves the persona (PC's presented persona
# at the moment of grant) and passes both the offer row and the persona to
# the handler. Handlers are pure-Python service functions — no implicit
# globals; the offer + persona are everything the handler needs to produce
# its downstream object.
EffectHandler = Callable[["NPCServiceOffer", "Persona"], EffectResult]


def _stub_issue_permit(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """Plan 2 placeholder for permit issuance.

    Returns a structured result so the interaction state machine + tests
    can exercise the dispatch end-to-end without depending on Plan 3's
    `BuildingPermit` ItemTemplate + `BuildingPermitDetails` model. Plan 3
    (#668) replaces this body with real `ItemInstance` + details-row
    creation keyed on ``persona`` (the IC holder).
    """
    message = f"Permit '{offer.label}' would be issued to {persona} (Plan 3 wires real creation)."
    return EffectResult(
        kind=OfferKind.PERMIT.value,
        object_pk=None,
        object_label=offer.label,
        message=message,
        payload={"holder_persona_pk": persona.pk, "offer_pk": offer.pk},
    )


OFFER_EFFECT_HANDLERS: dict[str, EffectHandler] = {
    OfferKind.PERMIT.value: _stub_issue_permit,
    # LOAN (#930) is registered here rather than from a sub-package's ready():
    # the handler lives in this module (currency imported lazily) so there
    # is no consuming-app ready() to defer to.
}

# Lazy snapshot of the "production baseline" handler set. Populated on the
# first call to ``reset_offer_effect_handlers`` so the snapshot includes
# every handler registered by a sub-package's ready() hook, called from
# world/apps.py (notably the MISSION handler registered by
# ``world.missions.apps.ready``). If we snapshotted
# at module import time, ``reset_offer_effect_handlers`` would silently drop
# MISSION on every test reset — a foot-gun the #686 review surfaced.
_DEFAULT_HANDLERS: dict[str, EffectHandler] | None = None


def register_offer_effect_handler(kind: str, handler: EffectHandler) -> None:
    """Register/override a PER-KIND effect handler.

    Replaces Plan 2's stub for ``kind=PERMIT`` with Plan 3's real
    ``issue_permit`` at app-ready time. Tests can call this to wire a
    mock handler; pair with :func:`reset_offer_effect_handlers` in
    tearDown for isolation.
    """
    OFFER_EFFECT_HANDLERS[kind] = handler


def reset_offer_effect_handlers() -> None:
    """Restore the post-app-ready baseline handler set.

    Test-only escape hatch — production code should never call this. The
    baseline is snapshotted lazily on the first call to this function, so
    every handler registered by an ``AppConfig.ready()`` hook (PERMIT,
    MISSION, ...) is included in the snapshot. Use in tearDown when a test
    has registered a custom handler that must not leak.
    """
    global _DEFAULT_HANDLERS  # noqa: PLW0603
    if _DEFAULT_HANDLERS is None:
        _DEFAULT_HANDLERS = dict(OFFER_EFFECT_HANDLERS)
    OFFER_EFFECT_HANDLERS.clear()
    OFFER_EFFECT_HANDLERS.update(_DEFAULT_HANDLERS)


class UnregisteredOfferKindError(LookupError):
    """Raised when an offer is granted but its kind has no registered handler.

    Authoring error: every value in ``OfferKind`` should have a handler
    registered before any offer of that kind is saved. We fail loudly
    rather than silently no-op the grant.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"No effect handler registered for OfferKind={kind!r}")
        self.kind = kind


def dispatch_offer_effect(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """Look up the registered handler for ``offer.kind`` and invoke it.

    Raises ``UnregisteredOfferKindError`` if the kind has no handler —
    authoring should ensure every OfferKind value is wired before any
    offer of that kind ships.
    """
    # #2378 — dealing with an NPC while wanted risks recognition and alarm.
    from world.justice.constants import GuardTrigger  # noqa: PLC0415
    from world.justice.pipeline import maybe_guard_encounter  # noqa: PLC0415
    from world.justice.services import area_for_room  # noqa: PLC0415

    _sheet = persona.character_sheet
    _character = _sheet.character if _sheet is not None else None
    if _character is not None and _character.location is not None:
        maybe_guard_encounter(
            persona, area_for_room(_character.location), GuardTrigger.NPC_TRANSACTION
        )

    handler = OFFER_EFFECT_HANDLERS.get(offer.kind)
    if handler is None:
        raise UnregisteredOfferKindError(offer.kind)
    return handler(offer, persona)


class AmbiguousDebtorError(LookupError):
    """The persona's org standing doesn't resolve to exactly one authority org."""

    def __init__(self, count: int) -> None:
        super().__init__(f"Authority-org resolution matched {count} organizations")
        self.count = count
        self.user_message = (
            "The representative needs to know whose books this lands on — "
            "you keep the books for more than one house."
            if count
            else "You don't hold the spending authority for any house's books."
        )


class NoAvailableFavorTokenError(LookupError):
    """No unredeemed Golden Hare issued by ``academy``, held by the learner (#2440)."""

    def __init__(self, academy_name: str) -> None:
        super().__init__(f"No unredeemed Golden Hare issued by {academy_name!r} in learner's hand")
        self.user_message = f"You carry no Golden Hare for {academy_name} to call in."


class AcademyOfferApCostError(RuntimeError):
    """An Academy offer that charges its own AP was authored with a nonzero ``ap_cost``.

    TRAIN (#2440) charges AP through ``charge_and_learn``'s has-gift/major-gift
    multiplier logic (driven by ``TrainOfferDetails.learn_ap_cost``), and
    SKILL_COURSE (#4457) charges ``SkillCourseOfferDetails.session_ap_cost`` inside
    its handler, after every refusal. ``NPCServiceOffer.ap_cost`` must stay 0 for
    both: otherwise the generic pre-dispatch charge in ``services._charge_offer_ap``
    double-charges the learner's AP pool before the handler runs, and keeps it when
    the handler refuses. The details rows' ``clean()`` is the authoring-time guard;
    this is the runtime backstop, since no admin/serializer surface currently calls
    ``full_clean()`` on those rows.
    """

    def __init__(self, offer_pk: int, kind: str, ap_cost: int) -> None:
        super().__init__(
            f"{kind} offer pk={offer_pk} has ap_cost={ap_cost} (must be 0) - "
            "_charge_offer_ap would double-charge AP on top of the handler's own charge."
        )


def _resolve_unredeemed_hare(sheet: CharacterSheet, academy: Organization) -> FavorTokenDetails:
    """The learner's one unredeemed Golden Hare issued by ``academy`` (#2440).

    Exactly one Hare is charged per TRAIN acceptance — the first matching row
    (deterministic by pk) when several happen to be held. Raises
    ``NoAvailableFavorTokenError`` when the learner holds none.

    ``select_for_update()`` locks the matching rows for the lifetime of the
    caller's transaction, closing the TOCTOU where two concurrent TRAIN
    accepts both resolve the same unredeemed Hare before either redeems it
    (the row lock serializes the second caller behind the first's commit —
    it then re-queries and either finds a different Hare or raises
    ``NoAvailableFavorTokenError``). Must be called inside a
    ``transaction.atomic()`` block — see ``run_train_offer``.
    """
    from world.currency.models import FavorTokenDetails  # noqa: PLC0415

    token = (
        FavorTokenDetails.objects.select_for_update()
        .filter(
            issuing_organization=academy,
            redeemed_at__isnull=True,
            item_instance__holder_character_sheet=sheet,
            item_instance__destroyed_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if token is None:
        raise NoAvailableFavorTokenError(academy.name)
    return token


# What an Academy offer says when its role has no ``faction_affiliation`` to front it.
_ACADEMY_AUTHORING_ERRORS: dict[str, str] = {
    OfferKind.TRAIN.value: "This trainer has no house to teach for. (Authoring error.)",
    OfferKind.SKILL_COURSE.value: "This trainer has no house to teach for. (Authoring error.)",
    OfferKind.SETTLE_OBLIGATION.value: "This registrar keeps no house's books. (Authoring error.)",
}


def _academy_for(
    offer: NPCServiceOffer, sheet: CharacterSheet, kind: OfferKind
) -> Organization | EffectResult:
    """The Academy fronting ``offer``, or the refusal to return instead (#4457).

    The Academy is the role's ``faction_affiliation``: TRAIN, SKILL_COURSE and
    SETTLE_OBLIGATION offers are always fronted by an org, unlike LOAN's optional
    per-offer override. No affiliation is an authoring error. A learner who still
    owes the Academy her entrance Hare (``has_open_obligation``, #2428) is refused
    teaching; SETTLE_OBLIGATION skips that gate, since paying the debt is what it is for.
    """
    from world.societies.obligation_services import has_open_obligation  # noqa: PLC0415

    academy = offer.role.faction_affiliation
    if academy is None:
        return EffectResult(
            kind=kind.value,
            message=_ACADEMY_AUTHORING_ERRORS[kind.value],
            payload={"offer_pk": offer.pk},
        )
    if kind != OfferKind.SETTLE_OBLIGATION and has_open_obligation(sheet, academy):
        return EffectResult(
            kind=kind.value,
            message=f"{academy.name} won't take you on further until your debt is settled.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )
    return academy


def _resolve_authority_org(persona: Persona):
    """The one organization whose treasury this persona may commit (#930).

    Loans, collections, and improvements are all org-level acts; the handler
    contract only carries the persona, so the target is the single org where
    the persona holds treasury spend authority. Zero or several →
    ``AmbiguousDebtorError``.
    """
    from world.currency.services import (  # noqa: PLC0415
        can_spend_treasury,
        get_or_create_treasury,
    )

    orgs = [
        membership.organization
        for membership in persona.organization_memberships.select_related("organization")
        if can_spend_treasury(get_or_create_treasury(membership.organization), persona)
    ]
    if len(orgs) != 1:
        raise AmbiguousDebtorError(len(orgs))
    return orgs[0]


def grant_loan(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """LOAN effect handler (#930): extend a fiat loan on the offer's fixed terms.

    Creditor = the details row's org, falling back to the role's
    faction_affiliation. Debtor = the persona's one treasury-authority org.
    """
    from world.currency.services import extend_loan  # noqa: PLC0415

    details = offer.loan_offer_details
    creditor = details.creditor_organization or offer.role.faction_affiliation
    if creditor is None:
        return EffectResult(
            kind=OfferKind.LOAN.value,
            message="The representative has no house to lend from. (Authoring error.)",
            payload={"offer_pk": offer.pk},
        )
    try:
        debtor = _resolve_authority_org(persona)
    except AmbiguousDebtorError as exc:
        return EffectResult(
            kind=OfferKind.LOAN.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk, "debtor_candidates": exc.count},
        )
    instrument = extend_loan(
        creditor=creditor,
        debtor=debtor,
        principal=details.principal,
        interest_bps_monthly=details.interest_bps_monthly,
        fiat=True,
    )
    return EffectResult(
        kind=OfferKind.LOAN.value,
        object_pk=instrument.pk,
        object_label=f"Loan of {details.principal} from {creditor.name}",
        message=(
            f"{creditor.name} extends {details.principal} coppers to {debtor.name} "
            f"at {details.interest_bps_monthly} bps monthly."
        ),
        payload={"debt_instrument_pk": instrument.pk, "debtor_organization_pk": debtor.pk},
    )


OFFER_EFFECT_HANDLERS[OfferKind.LOAN.value] = grant_loan


def raise_court_grant(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """COURT_GRANT effect handler (#1718): petition the master for a permanent raise.

    Rolls offer.check_type/check_difficulty (eased by the master's affection
    toward the servant), and on success raises the servant's CourtPact.granted_pull_cap
    up to court_grant_ceiling(...). Every attempt (success or failure) records the
    petition outcome on the servant<->master NPCStanding row; crossing the
    consecutive-failure threshold fires the master's escalation ConsequencePool.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.covenants.court_grant import (  # noqa: PLC0415
        court_grant_ceiling,
        court_grant_petition_ease,
        raise_court_pact_grant,
        record_court_grant_petition_outcome,
    )
    from world.covenants.services import (  # noqa: PLC0415
        active_court_pact_for,
        get_court_grant_config,
    )
    from world.npc_services.models import NPCStanding  # noqa: PLC0415

    details = offer.court_grant_offer_details
    covenant = details.covenant
    servant_sheet = persona.character_sheet
    pact = active_court_pact_for(covenant=covenant, servant_sheet=servant_sheet)
    if pact is None:
        return EffectResult(
            kind=OfferKind.COURT_GRANT.value,
            message="You hold no sworn pact with this Court to petition on.",
            payload={"offer_pk": offer.pk},
        )

    config = get_court_grant_config()
    ceiling = court_grant_ceiling(covenant=covenant, servant_sheet=servant_sheet)
    master_persona = covenant.leader.primary_persona
    # Key off the servant's primary_persona, matching court_grant_ceiling's
    # internal master-standing lookup and _resolve_emergency_draw (#1718 final-
    # review Finding 3) — not the raw interaction-session `persona`, which may
    # be a non-primary persona and would silently decouple this write from the
    # ceiling read.
    standing, _ = NPCStanding.objects.get_or_create(
        persona=servant_sheet.primary_persona, npc_persona=master_persona
    )

    ease = court_grant_petition_ease(standing=standing, config=config)
    check_result = perform_check(
        persona.character_sheet.character,
        offer.check_type,
        target_difficulty=offer.check_difficulty,
        extra_modifiers=ease,
    )
    # CheckResult.success_level (world.checks.types) safely returns 0 when
    # outcome is None — no separate None-check needed.
    succeeded = check_result.success_level > 0
    record_court_grant_petition_outcome(
        standing,
        succeeded=succeeded,
        check_result=check_result,
        character=persona.character_sheet.character,
        config=config,
    )

    if not succeeded:
        return EffectResult(
            kind=OfferKind.COURT_GRANT.value,
            message="Your master is unmoved — this is not the time to ask for more.",
            payload={"offer_pk": offer.pk, "ceiling": ceiling},
        )

    raised = raise_court_pact_grant(pact=pact, new_cap=ceiling)
    message = (
        "Your master grants you greater strength — your cap now stands at "
        f"{raised.granted_pull_cap}."
    )
    return EffectResult(
        kind=OfferKind.COURT_GRANT.value,
        object_pk=raised.pk,
        object_label=f"Court grant raised to {raised.granted_pull_cap}",
        message=message,
        payload={"granted_pull_cap": raised.granted_pull_cap},
    )


OFFER_EFFECT_HANDLERS[OfferKind.COURT_GRANT.value] = raise_court_grant


def run_collection(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """COLLECTION effect handler (#930): dispatch a collector across the org's pools.

    The graded outcome (Tax Collection check + band table + graft) lives in
    ``currency.collect_org_income``; the debt-first + member-allowance +
    materials-allowance legs ride along via ``currency.collect_and_distribute``
    (#2540) so a collection also services the org's debt principal and pays its
    active members coin and (per category) raw materials before the remainders
    settle in the treasury / ``OrgMaterialStock``. This handler resolves the org,
    runs the dispatch, and phrases the toast. Copy approved by Apostate (2026-07-03).
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.currency.services import collect_and_distribute  # noqa: PLC0415

    try:
        organization = _resolve_authority_org(persona)
    except AmbiguousDebtorError as exc:
        return EffectResult(
            kind=OfferKind.COLLECTION.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk},
        )
    character = persona.character_sheet.character
    try:
        dispatch = collect_and_distribute(organization=organization, character=character)
    except ValidationError:
        return EffectResult(
            kind=OfferKind.COLLECTION.value,
            message="The strongboxes hold nothing worth a collector's boots.",
            payload={"offer_pk": offer.pk, "organization_pk": organization.pk},
        )
    result = dispatch.collection
    if result.catastrophe:
        # The collector-incident encounter is a combat-domain follow-up seam.
        message = (
            "Word comes back ugly: the collection run was set upon and "
            f"the take is gone. {format_coppers(result.gathered)} lost."
        )
    elif result.stolen > 0:
        message = (
            f"The collector returns light: {format_coppers(result.landed)} "
            f"banked of {format_coppers(result.gathered)} gathered; the rest went missing."
        )
    else:
        message = (
            f"The rounds went smoothly: {format_coppers(result.landed)} "
            "banked after the usual leakage."
        )
    if dispatch.debt_principal_paid > 0:
        message += (
            f" PLACEHOLDER: {format_coppers(dispatch.debt_principal_paid)} "
            "went to the house's creditors."
        )
    if dispatch.allowance.member_count > 0:
        message += (
            f" PLACEHOLDER: allowances went out to {dispatch.allowance.member_count} members."
        )
    if dispatch.material_allowance.total_by_category:
        message += (
            " PLACEHOLDER: raw materials were shared out to "
            f"{dispatch.material_allowance.member_count} members."
        )
    if dispatch.auto_sold > 0:
        message += (
            f" PLACEHOLDER: surplus stores were sold off for {format_coppers(dispatch.auto_sold)}."
        )
    return EffectResult(
        kind=OfferKind.COLLECTION.value,
        object_label=f"Collection for {organization.name}",
        message=message,
        payload={
            "organization_pk": organization.pk,
            "gathered": result.gathered,
            "landed": result.landed,
            "catastrophe": result.catastrophe,
            "debt_principal_paid": dispatch.debt_principal_paid,
            "allowance_member_count": dispatch.allowance.member_count,
            "material_allowance_member_count": dispatch.material_allowance.member_count,
            "auto_sold": dispatch.auto_sold,
        },
    )


def run_improvement(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """IMPROVEMENT effect handler (#930): invest in the domain's income lines.

    Scholarship/Economics against the ledgers (``currency.improve_org_domain``):
    success raises the streams and cracks down on graft; a partial only manages
    the crackdown. Copy approved by Apostate (2026-07-03).
    """
    from world.currency.services import improve_org_domain  # noqa: PLC0415

    try:
        organization = _resolve_authority_org(persona)
    except AmbiguousDebtorError as exc:
        return EffectResult(
            kind=OfferKind.IMPROVEMENT.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk},
        )
    character = persona.character_sheet.character
    result = improve_org_domain(organization=organization, character=character)
    if result.gross_raised:
        message = (
            "The investment takes; the income lines run richer, and the clerks mind their sums."
        )
    elif result.graft_cracked:
        message = (
            "No new coin found, but the crackdown bites; less leaks from the books this season."
        )
    else:
        message = "The ledgers resist; nothing comes of the effort this time."
    return EffectResult(
        kind=OfferKind.IMPROVEMENT.value,
        object_label=f"Domain investment for {organization.name}",
        message=message,
        payload={
            "organization_pk": organization.pk,
            "gross_raised": result.gross_raised,
            "graft_cracked": result.graft_cracked,
            "new_graft_pct": result.new_graft_pct,
        },
    )


OFFER_EFFECT_HANDLERS[OfferKind.COLLECTION.value] = run_collection
OFFER_EFFECT_HANDLERS[OfferKind.IMPROVEMENT.value] = run_improvement


def run_train_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """TRAIN effect handler (#2440): Academy trainer teaches a technique.

    One offer row per teachable technique (``TrainOfferDetails.technique`` —
    see that model's docstring for why). Flow: resolve the Academy (the
    role's ``faction_affiliation`` — TRAIN offers are always fronted by an
    org, unlike LOAN's optional per-offer override) -> obligation gate
    (``has_open_obligation``, #2428) -> availability gate (learner's own
    (Path × Gift) pool ∪ their Tradition's signature list, signatures
    members-only — ruling 3 on #2440) -> resolve exactly one unredeemed
    Golden Hare issued by the Academy and held by the learner -> charge AP +
    coin + the Hare -> acquire via the shared ``charge_and_learn`` seam
    (the same core ``accept_technique_offer`` uses).

    The Hare is redeemed to the ACADEMY regardless of the trainer's own
    ``teaches_tradition`` — Hares are Academy-specific venue tokens, not
    per-tradition (ruling 2026-07-17 on #2428; ``redeem_favor_token``'s
    issuer-match stands unchanged).

    Hare resolution + ``charge_and_learn`` + ``redeem_favor_token`` run
    inside one outer ``transaction.atomic()`` — all-or-nothing regardless
    of what the caller wraps this in. Without it, ``charge_and_learn``'s
    own ``@transaction.atomic`` commits independently before
    ``redeem_favor_token`` runs; a race between two concurrent TRAIN
    accepts resolving the same Hare would then leave the loser charged
    AP + coin + a technique with no Hare spent. ``_resolve_unredeemed_hare``
    additionally locks the Hare row (``select_for_update()``) so the race
    itself can't happen — the second caller serializes behind the first's
    commit and either finds a different Hare or gets a clean
    ``NoAvailableFavorTokenError`` refusal.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.currency.services import (  # noqa: PLC0415
        get_or_create_treasury,
        redeem_favor_token,
    )
    from world.magic.exceptions import MagicError  # noqa: PLC0415
    from world.magic.services.gift_acquisition import charge_and_learn  # noqa: PLC0415

    if offer.ap_cost != 0:
        raise AcademyOfferApCostError(offer.pk, OfferKind.TRAIN.value, offer.ap_cost)

    sheet = persona.character_sheet
    details = offer.train_offer_details
    technique = details.technique

    academy = _academy_for(offer, sheet, OfferKind.TRAIN)
    if isinstance(academy, EffectResult):
        return academy

    if not _technique_available_to_learner(sheet, offer.role, technique):
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message="This isn't yours to learn here.",
            payload={"offer_pk": offer.pk, "technique_pk": technique.pk},
        )

    try:
        with transaction.atomic():
            token = _resolve_unredeemed_hare(sheet, academy)
            progress = charge_and_learn(
                sheet,
                technique,
                base_ap_cost=details.learn_ap_cost,
                source=AccessChangeSource.ACADEMY_TRAINING,
                gold_cost=details.gold_cost,
                gold_treasury=get_or_create_treasury(academy),
            )
            redeem_favor_token(token, redeemer_org=academy)
    except NoAvailableFavorTokenError as exc:
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )
    except MagicError as exc:
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk},
        )
    except ValueError:
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message=f"You already know {technique.name}.",
            payload={"offer_pk": offer.pk, "technique_pk": technique.pk},
        )
    except ValidationError:
        # redeem_favor_token lost the race after charge_and_learn already
        # ran in this transaction's savepoint — the whole atomic block above
        # rolled back (AP, coin, and the TechniqueProgress are all undone).
        # A short purse never lands here: charge_and_learn refuses it first
        # with TrainingFundsInsufficient (a MagicError, handled above, #4523).
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message="Someone else called in that Hare before you finished.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )

    return EffectResult(
        kind=OfferKind.TRAIN.value,
        object_pk=progress.pk,
        object_label=technique.name,
        message=(
            f"{academy.name}'s trainer begins your training in {technique.name}. "
            f"Progress: {progress.points_accumulated}/{progress.total_required}."
        ),
        payload={
            "technique_progress_pk": progress.pk,
            "organization_pk": academy.pk,
            "favor_token_pk": token.pk,
        },
    )


def _technique_available_to_learner(
    sheet: CharacterSheet, role: NPCRole, technique: Technique
) -> bool:
    """Whether ``technique`` is in ``sheet``'s TRAIN availability via ``role`` (#2440).

    Availability is read from the learner's own Path's list for the gift, the same
    rule character creation offers by (``cg_catalog.get_technique_options``, #4555):
    a technique on no Path list of the learner's current Path is never available. Of
    the techniques on it, one no Tradition grant lists is tradition-agnostic (any
    Academy trainer can teach it); one a Tradition grant lists is members-only
    (ruling 3 on #2440) — offerable only when the trainer's own
    ``role.teaches_tradition`` is a listing Tradition and matches the learner's
    currently ACTIVE ``CharacterTradition`` membership
    (``left_at__isnull=True``). #2441 Task 8 gave ``CharacterTradition`` history
    (``left_at``) and an active-row constraint, so "current tradition" is now a
    real, singular concept — this seam was upgraded from the old
    membership-*set* read (any row ever held, matching
    ``world.magic.services.ritual_knowledge``'s "all traditions in history" walk,
    which is deliberately unchanged — ritual knowledge is learned-is-learned) to
    an active-only read: a former tradition's signature techniques stop being
    offerable the moment the learner switches or leaves, per ruling 3.
    """
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    path = current_path_for_character(sheet.character)
    if path is None:
        return False

    from world.magic.services.cg_catalog import get_technique_options  # noqa: PLC0415

    gift = technique.gift
    trainer_tradition = role.teaches_tradition
    # Both halves come from PathGiftGrant(path, gift). The pool half (listed by no
    # Tradition grant) never reads `tradition`, so trainer_tradition may be None;
    # only the members-only half is scoped by it.
    options = get_technique_options(path, gift, trainer_tradition, include_unready=True)
    if technique in options.pool:
        return True
    if trainer_tradition is None:
        # Generalist trainer: check for ghost tutelage (#2460).
        # The members-only list from get_technique_options(path, gift, None) is empty,
        # so re-query with each tutelage's tradition to get that tradition's techniques
        # on the learner's Path.
        for tutelage in sheet.ghost_tutelages.select_related("tradition"):
            tutelage_options = get_technique_options(
                path, gift, tutelage.tradition, include_unready=True
            )
            if technique in tutelage_options.tradition:
                return True
        return False
    if technique not in options.tradition:
        return False
    return sheet.character_traditions.filter(
        tradition=trainer_tradition, left_at__isnull=True
    ).exists()


OFFER_EFFECT_HANDLERS[OfferKind.TRAIN.value] = run_train_offer


def run_settle_obligation_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """SETTLE_OBLIGATION effect handler (#2428 whole-branch fix): the Academy Registrar
    clears a learner's OWED entrance obligation.

    ``settle_obligation`` (``world.societies.obligation_services``) was authored in an
    earlier task on this cluster but shipped with no live caller — an Unbound Prospect
    had no in-game way to ever pay off their Academy entrance debt. This handler is
    that caller: resolve the offer's org (the role's ``faction_affiliation``, same
    convention as ``run_train_offer``) -> fetch the learner's OWED
    ``OrganizationObligation`` against it (the row ``has_open_obligation`` only
    ``.exists()``-checks) -> no OWED row is a typed refusal, not an error -> resolve
    exactly one unredeemed Golden Hare issued by the org and held by the learner
    (reuses ``_resolve_unredeemed_hare``, same row-lock TOCTOU protection as TRAIN)
    -> ``settle_obligation`` redeems it and flips the row to SETTLED.

    Hare resolution + ``settle_obligation`` run inside one outer
    ``transaction.atomic()`` for the same reason ``run_train_offer`` wraps its own
    charge sequence: without it, a race between two concurrent settle attempts could
    resolve the same Hare before either redemption commits.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.societies.constants import ObligationState  # noqa: PLC0415
    from world.societies.exceptions import ObligationNotOwedError  # noqa: PLC0415
    from world.societies.models import OrganizationObligation  # noqa: PLC0415
    from world.societies.obligation_services import settle_obligation  # noqa: PLC0415

    sheet = persona.character_sheet
    academy = _academy_for(offer, sheet, OfferKind.SETTLE_OBLIGATION)
    if isinstance(academy, EffectResult):
        return academy

    obligation = OrganizationObligation.objects.filter(
        debtor=sheet, creditor=academy, state=ObligationState.OWED
    ).first()
    if obligation is None:
        return EffectResult(
            kind=OfferKind.SETTLE_OBLIGATION.value,
            message=f"You owe {academy.name} nothing.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )

    try:
        with transaction.atomic():
            token = _resolve_unredeemed_hare(sheet, academy)
            settle_obligation(obligation, token)
    except NoAvailableFavorTokenError as exc:
        return EffectResult(
            kind=OfferKind.SETTLE_OBLIGATION.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )
    except ObligationNotOwedError as exc:
        # Someone else settled this exact row (or it was settled by a sponsor)
        # between the query above and the lock inside settle_obligation.
        return EffectResult(
            kind=OfferKind.SETTLE_OBLIGATION.value,
            message=exc.user_message,
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )
    except ValidationError:
        # redeem_favor_token (inside settle_obligation) lost the race for this
        # Hare after _resolve_unredeemed_hare picked it — the whole atomic
        # block above rolled back, obligation still OWED.
        return EffectResult(
            kind=OfferKind.SETTLE_OBLIGATION.value,
            message="Someone else called in that Hare before you finished.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )

    return EffectResult(
        kind=OfferKind.SETTLE_OBLIGATION.value,
        object_pk=obligation.pk,
        object_label=f"Obligation to {academy.name} settled",
        message=f"The registrar marks your debt to {academy.name} paid in full.",
        payload={
            "obligation_pk": obligation.pk,
            "organization_pk": academy.pk,
            "favor_token_pk": token.pk,
        },
    )


OFFER_EFFECT_HANDLERS[OfferKind.SETTLE_OBLIGATION.value] = run_settle_obligation_offer


class _CourseRefusedError(Exception):
    """A skill course refusal, raised inside the handler's transaction (#4457).

    Every refusal is raised before the first charge (the handler locks the AP pool,
    purse and Hare rows before it checks them), so the rollback only undoes the
    skill-store reconciliation; it is never relied on to undo a charge, since
    identity-mapped rows would keep the charged values in memory. ``reason`` is the
    player-facing sentence; the handler adds "Nothing was charged." to it.
    """

    def __init__(self, reason: str, enrollment: SkillCourseEnrollment | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.enrollment = enrollment


def run_skill_course_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """SKILL_COURSE effect handler (#4457): an Academy course in one skill, a session at a time.

    The first acceptance enrolls the learner (coin to the Academy treasury and one
    Golden Hare, charged once per course) and runs the first session; each later
    acceptance of the same offer is one session. A session spends
    ``session_ap_cost`` AP, rolls the course's check, and develops the skill by
    ``session_development`` times the outcome's ``TrainingOutcomeAward`` multiplier
    (no row, or no outcome, teaches nothing), never more than the course has left.
    Development that would run past an XP boundary stays in the course
    (``train_skill(stop_at_boundary=True)``), because the course was paid for up front.

    Refusals, each before anything is charged: debt or no Academy (``_academy_for``),
    already trained in this course this game week, the skill parked at a boundary,
    short of AP, and when enrolling, short of coin or of a Hare. The week is recorded
    on the enrollment, not as an offer cooldown, because ``resolve_offer`` writes a
    cooldown even when the handler refuses. No surcharge applies to a learner without
    formal training (spec Decision 11).
    """
    if offer.ap_cost != 0:
        raise AcademyOfferApCostError(offer.pk, OfferKind.SKILL_COURSE.value, offer.ap_cost)

    sheet = persona.character_sheet
    course = offer.skill_course_offer_details
    academy = _academy_for(offer, sheet, OfferKind.SKILL_COURSE)
    if isinstance(academy, EffectResult):
        return academy

    try:
        with transaction.atomic():
            return _take_course_session(offer, course, sheet, academy)
    except _CourseRefusedError as exc:
        return EffectResult(
            kind=OfferKind.SKILL_COURSE.value,
            message=f"{exc.reason} Nothing was charged.",
            payload={
                "offer_pk": offer.pk,
                "skill_pk": course.skill_id,
                "enrollment_pk": exc.enrollment.pk if exc.enrollment else None,
            },
        )


def _take_course_session(
    offer: NPCServiceOffer,
    course: SkillCourseOfferDetails,
    sheet: CharacterSheet,
    academy: Organization,
) -> EffectResult:
    """Check every refusal, enroll when not yet enrolled, then run one session.

    Runs inside ``run_skill_course_offer``'s transaction; a refusal raises
    ``_CourseRefusedError``.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.npc_services.models import SkillCourseEnrollment  # noqa: PLC0415
    from world.skills.services import (  # noqa: PLC0415
        is_skill_at_xp_boundary,
        reconcile_skill_stores,
    )

    skill = course.skill
    # Lock the learner's AP pool first. It serializes her concurrent acceptances, so
    # the enrollment reads below see any course a racing acceptance already opened, and
    # the session's spend at the end cannot come up short after coin and a Hare were
    # charged (a rollback then would leave the identity-mapped purse and treasury
    # holding balances the database no longer has).
    pool = ActionPointPool.objects.select_for_update().get(
        pk=ActionPointPool.get_or_create_for_character(sheet.character).pk
    )
    enrollment = (
        SkillCourseEnrollment.objects.select_for_update()
        .filter(character_sheet=sheet, course=course, completed_at__isnull=True)
        .first()
    )
    week = get_current_game_week()
    # One session per course per game week, across enrollments: a course finished this
    # week and taken again is still refused until the week turns.
    latest_week_pk = (
        SkillCourseEnrollment.objects.filter(character_sheet=sheet, course=course)
        .order_by("-enrolled_at", "-pk")
        .values_list("last_session_week_id", flat=True)
        .first()
    )
    if latest_week_pk == week.pk:
        msg = "You have already trained in this course this week."
        raise _CourseRefusedError(msg, enrollment)

    rating = reconcile_skill_stores(sheet, skill)
    if is_skill_at_xp_boundary(rating):
        until = "a course can raise it" if enrollment is None else "the course can continue"
        msg = f"{skill.name} is at {rating} and needs a breakthrough before {until}."
        raise _CourseRefusedError(msg, enrollment)

    if not pool.can_afford(course.session_ap_cost):
        msg = f"A session costs {course.session_ap_cost} AP and you have {pool.current}."
        raise _CourseRefusedError(msg, enrollment)

    if enrollment is None:
        enrollment = _enroll_in_course(course, sheet, academy)

    if not pool.spend(course.session_ap_cost):
        # Unreachable: the pool row is locked and was checked in this transaction.
        msg = f"AP pool {pool.pk} came up short under its own row lock."
        raise RuntimeError(msg)
    return _run_course_session(offer, course, sheet, enrollment, rating=rating, week_pk=week.pk)


def _enroll_in_course(
    course: SkillCourseOfferDetails, sheet: CharacterSheet, academy: Organization
) -> SkillCourseEnrollment:
    """Charge one Hare and the coin (none for a free course), and open the enrollment (#4457).

    The coin and Hare checks both come before either charge; a short purse is named
    with its cost and balance, a missing Hare with the existing Hare refusal. Nothing
    after the first charge can refuse.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.currency.services import (  # noqa: PLC0415
        get_or_create_purse,
        get_or_create_treasury,
        redeem_favor_token,
        transfer,
    )
    from world.magic.exceptions import TrainingFundsInsufficient  # noqa: PLC0415
    from world.magic.services.gift_acquisition import enforce_can_afford_training  # noqa: PLC0415
    from world.npc_services.models import SkillCourseEnrollment  # noqa: PLC0415

    try:
        enforce_can_afford_training(sheet, course.coin_cost)
    except TrainingFundsInsufficient as exc:
        msg = (
            f"Enrolling costs {format_coppers(exc.cost)} "
            f"and you have {format_coppers(exc.balance)}."
        )
        raise _CourseRefusedError(msg) from exc
    try:
        token = _resolve_unredeemed_hare(sheet, academy)
    except NoAvailableFavorTokenError as exc:
        raise _CourseRefusedError(exc.user_message) from exc

    # The Hare first: redeem_favor_token refuses before it changes anything, and the
    # coin transfer after it cannot fail (the purse row is locked and was checked above).
    try:
        redeem_favor_token(token, redeemer_org=academy)
    except ValidationError as exc:
        # Another acceptance redeemed this Hare after we resolved it.
        msg = "Someone else called in that Hare before you finished."
        raise _CourseRefusedError(msg) from exc
    if course.coin_cost > 0:
        transfer(
            amount=course.coin_cost,
            reason=f"Academy course: {course.skill.name}",
            from_purse=get_or_create_purse(sheet),
            to_treasury=get_or_create_treasury(academy),
        )
    return SkillCourseEnrollment.objects.create(
        character_sheet=sheet,
        course=course,
        development_remaining=course.total_development,
    )


def _run_course_session(  # noqa: PLR0913 - one session's inputs, all already resolved
    offer: NPCServiceOffer,
    course: SkillCourseOfferDetails,
    sheet: CharacterSheet,
    enrollment: SkillCourseEnrollment,
    *,
    rating: int,
    week_pk: int,
) -> EffectResult:
    """Roll the session, develop the skill and count it off the enrollment (#4457).

    The AP is already spent. ``rating`` is the skill's rating before the session,
    reported when nothing is applied.
    """
    from decimal import Decimal  # noqa: PLC0415
    import math  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.models import TrainingOutcomeAward  # noqa: PLC0415
    from world.skills.services import is_skill_at_xp_boundary, train_skill  # noqa: PLC0415

    skill = course.skill
    check_result = perform_check_with_modifiers(
        sheet.character, course.check_type, target_difficulty=course.check_difficulty
    )
    award = (
        TrainingOutcomeAward.objects.filter(outcome_tier=check_result.outcome).first()
        if check_result.outcome is not None
        else None
    )
    multiplier = award.dev_point_multiplier if award is not None else Decimal(0)
    points = min(
        math.floor(Decimal(course.session_development) * multiplier),
        enrollment.development_remaining,
    )

    old_value = new_value = rating
    applied = 0
    if points > 0:
        trained = train_skill(
            sheet,
            skill,
            points,
            description=f"Academy course: {skill.name}",
            stop_at_boundary=True,
        )
        old_value, new_value, applied = trained.old_value, trained.new_value, trained.points_applied

    enrollment.development_remaining -= applied
    enrollment.last_session_week_id = week_pk
    if enrollment.development_remaining == 0:
        enrollment.completed_at = timezone.now()
    enrollment.save(update_fields=["development_remaining", "last_session_week", "completed_at"])

    outcome = check_result.outcome_name
    if applied == 0:
        said = f"{outcome}. You learn nothing this session; {course.session_ap_cost} AP spent."
    elif new_value > old_value:
        said = f"{outcome}. {skill.name} rises from {old_value} to {new_value}."
    else:
        said = f"{outcome}. {skill.name} stays at {new_value}, closer to {new_value + 1}."
    if enrollment.completed_at is not None:
        said += " The course is complete."
    else:
        said += (
            f" The course has {enrollment.development_remaining} of "
            f"{course.total_development} left."
        )
        if is_skill_at_xp_boundary(new_value):
            said += " Break through to continue the course."

    return EffectResult(
        kind=OfferKind.SKILL_COURSE.value,
        object_pk=enrollment.pk,
        object_label=skill.name,
        message=said,
        payload={
            "offer_pk": offer.pk,
            "skill_pk": skill.pk,
            "enrollment_pk": enrollment.pk,
            "outcome": outcome,
            "old_value": old_value,
            "new_value": new_value,
            "development_remaining": enrollment.development_remaining,
            "ap_spent": course.session_ap_cost,
        },
    )


OFFER_EFFECT_HANDLERS[OfferKind.SKILL_COURSE.value] = run_skill_course_offer


def run_styling_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """STYLING effect handler (#2632): an NPC stylist restyles one trait.

    Charges the PC's purse (sink — class-1 stylists front no treasury;
    PLACEHOLDER economics), then applies the offer's (trait, option) through
    the same ``change_appearance`` seam PC stylists and dyes use, with the
    note crediting the stylist. Insufficient funds is a business-rule
    refusal, not an exception — the offer stays available.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415
    from world.forms.services import NonCosmeticTraitError, change_appearance  # noqa: PLC0415
    from world.npc_services.functionaries import functionaries_in_location  # noqa: PLC0415

    details = offer.styling_offer_details
    sheet = persona.character_sheet

    # The placement actually serving the client: the co-located functionary of
    # this role, when one exists ("Alphonso the Stylist"); a global/roleless
    # interaction falls back to the role's name. Also anchors per-functionary
    # reaction lines (#2632).
    functionary = None
    character = sheet.character if sheet is not None else None
    if character is not None and character.location is not None:
        functionary = functionaries_in_location(character.location).filter(role=offer.role).first()
    stylist_label = functionary.display_name if functionary is not None else offer.role.name

    try:
        transfer(
            amount=details.price_coppers,
            reason=f"Styling: {offer.label}",
            from_purse=get_or_create_purse(sheet),
        )
    except DjangoValidationError:
        return EffectResult(
            kind=OfferKind.STYLING.value,
            message=f"You can't afford it — {details.price_coppers} coppers.",
            payload={"offer_pk": offer.pk},
        )

    try:
        change_appearance(
            sheet.character,
            details.trait,
            details.target_option,
            persona=persona,
            actor_persona=persona,
            # Clear any stale flavor text — the stylist's work replaces the
            # old look (#2632 replace-or-clear rule, same as item uses).
            descriptor="",
            note=f"{stylist_label}: {offer.label}",
        )
        # Learned by having it done (#2632): an exotic style from the stylist
        # teaches it — you can maintain the look with your own kit afterwards.
        from world.forms.services import learn_style  # noqa: PLC0415

        learn_style(sheet, details.target_option, taught_by_label=stylist_label)
    except NonCosmeticTraitError:
        return EffectResult(
            kind=OfferKind.STYLING.value,
            message="That trait can't be restyled. (Authoring error.)",
            payload={"offer_pk": offer.pk},
        )

    # Banded reaction line (#2632): an authored, allure-keyed reaction from
    # this placement (or the role's defaults) leads the message; the generic
    # craft line is the unauthored fallback.
    from world.npc_services.constants import ReactionMetric  # noqa: PLC0415
    from world.npc_services.reactions import reaction_line_for  # noqa: PLC0415

    reaction = reaction_line_for(
        role=offer.role,
        functionary=functionary,
        metric=ReactionMetric.ALLURE.value,
        sheet=sheet,
        name=persona.name,
    )
    outcome = f"{details.trait.display_name} is now {details.target_option.display_name}."
    message = (
        f"{reaction} {outcome}" if reaction else (f"{stylist_label} works their craft — {outcome}")
    )
    return EffectResult(
        kind=OfferKind.STYLING.value,
        object_label=offer.label,
        message=message,
        payload={"trait_pk": details.trait_id, "option_pk": details.target_option_id},
    )


def run_profile_recording_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """PROFILE_RECORDING effect handler (#2632): pay for an Archive sitting.

    Charges the purse and mints a COMMISSIONED ``RecordedProfile``; the
    player completes the write-up via
    ``world.npc_services.services.complete_recorded_profile``, which sets
    the character's description and archives the text forever.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415
    from world.npc_services.models import RecordedProfile  # noqa: PLC0415

    details = offer.profile_recording_offer_details
    sheet = persona.character_sheet

    try:
        transfer(
            amount=details.price_coppers,
            reason=f"Profile recording: {offer.label}",
            from_purse=get_or_create_purse(sheet),
        )
    except DjangoValidationError:
        return EffectResult(
            kind=OfferKind.PROFILE_RECORDING.value,
            message=f"You can't afford it — {details.price_coppers} coppers.",
            payload={"offer_pk": offer.pk},
        )

    profile = RecordedProfile.objects.create(
        persona=persona,
        recorded_by_label=offer.role.name,
        price_paid=details.price_coppers,
    )
    return EffectResult(
        kind=OfferKind.PROFILE_RECORDING.value,
        object_pk=profile.pk,
        object_label=f"Profile sitting with {offer.role.name}",
        message=(
            f"{offer.role.name} takes down your particulars. "
            "The finished profile awaits your review."
        ),
        payload={"recorded_profile_pk": profile.pk},
    )


OFFER_EFFECT_HANDLERS[OfferKind.STYLING.value] = run_styling_offer
OFFER_EFFECT_HANDLERS[OfferKind.PROFILE_RECORDING.value] = run_profile_recording_offer


def run_clue_reveal_offer(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """CLUE_REVEAL effect handler (#3428): an NPC reveals a pre-authored clue.

    CLUE_REVEAL offers are final (``is_final=True``), and the interaction state
    machine's final branch never rolls ``_apply_check`` — so, mirroring
    ``raise_court_grant``, **the handler rolls its own check** when
    ``offer.check_type`` is set. Success (or a null ``check_type``, which is
    auto-success) grants the clue's target through the same
    ``acquire_clue``/``grant_clue_target`` chokepoint room search and research
    use — ``acquire_clue`` also creates the ``CharacterClue`` row that
    ``services._clue_reveal_not_yet_held`` reads to stop offering an
    already-known clue. Failure just deflects — no grant, no held-clue row.
    Fails closed with a clear message when the finder has no roster tenure: a
    persona with no roster entry can't hold clues.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.clues.services import acquire_clue, grant_clue_target  # noqa: PLC0415
    from world.npc_services.functionaries import functionaries_in_location  # noqa: PLC0415

    details = offer.clue_reveal_offer_details
    clue = details.clue
    sheet = persona.character_sheet

    # Fail closed up front: a persona with no sheet (and so no character to
    # roll or roster entry to hold clues) gets nothing. Hoisting the guard
    # also makes every later sheet access None-safe.
    if sheet is None or sheet.character is None:
        return EffectResult(
            kind=OfferKind.CLUE_REVEAL.value,
            message="You have no roster tenure to hold what they'd tell you.",
            payload={"offer_pk": offer.pk, "clue_pk": clue.pk},
        )
    character = sheet.character

    # The placement actually serving the finder, mirroring run_styling_offer's
    # functionary resolution -- falls back to the role's name when no placed
    # Functionary is co-located (a global/roleless interaction).
    functionary = None
    if character.location is not None:
        functionary = functionaries_in_location(character.location).filter(role=offer.role).first()
    npc_label = functionary.display_name if functionary is not None else offer.role.name

    if offer.check_type is not None:
        check_result = perform_check(
            character,
            offer.check_type,
            target_difficulty=offer.check_difficulty,
        )
        succeeded = check_result.success_level > 0
    else:
        succeeded = True

    if not succeeded:
        return EffectResult(
            kind=OfferKind.CLUE_REVEAL.value,
            message=f"{npc_label} deflects. Whatever they know, they aren't telling you today.",
            payload={"offer_pk": offer.pk, "clue_pk": clue.pk},
        )

    roster_entry = sheet.roster_entry_or_none
    if roster_entry is None:
        return EffectResult(
            kind=OfferKind.CLUE_REVEAL.value,
            message="You have no roster tenure to hold what they'd tell you.",
            payload={"offer_pk": offer.pk, "clue_pk": clue.pk},
        )

    acquire_clue(roster_entry, clue)
    grant_clue_target(clue, roster_entry)

    message = f"{npc_label} tells you what they know. {clue.description}"
    return EffectResult(
        kind=OfferKind.CLUE_REVEAL.value,
        object_pk=clue.pk,
        object_label=clue.name,
        message=message,
        payload={"clue_pk": clue.pk},
    )


OFFER_EFFECT_HANDLERS[OfferKind.CLUE_REVEAL.value] = run_clue_reveal_offer
