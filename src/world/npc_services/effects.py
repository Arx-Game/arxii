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
    from world.npc_services.models import NPCRole, NPCServiceOffer
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
    # LOAN (#930) is registered here rather than from an AppConfig.ready():
    # the handler lives in this module (currency imported lazily) so there
    # is no consuming-app ready() to defer to.
}

# Lazy snapshot of the "production baseline" handler set. Populated on the
# first call to ``reset_offer_effect_handlers`` so the snapshot includes
# every handler registered by an AppConfig.ready() hook (notably the
# MISSION handler registered by ``MissionsConfig.ready``). If we snapshotted
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


class TrainOfferMisconfiguredError(RuntimeError):
    """A TRAIN-kind ``NPCServiceOffer`` was authored with a nonzero ``ap_cost`` (#2440).

    TRAIN's AP charge flows entirely through ``charge_and_learn``'s has-gift/
    major-gift multiplier logic (driven by ``TrainOfferDetails.learn_ap_cost``).
    ``NPCServiceOffer.ap_cost`` must stay 0 for TRAIN offers — otherwise the
    generic pre-dispatch charge in ``services._charge_offer_ap`` silently
    double-charges the learner's AP pool before this handler even runs.
    ``TrainOfferDetails.clean()`` is the authoring-time guard; this is the
    runtime backstop, since no admin/serializer surface currently calls
    ``full_clean()`` on ``TrainOfferDetails`` rows.
    """

    def __init__(self, offer_pk: int, ap_cost: int) -> None:
        super().__init__(
            f"TRAIN offer pk={offer_pk} has ap_cost={ap_cost} (must be 0) — "
            "_charge_offer_ap would double-charge AP on top of charge_and_learn."
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
    ``currency.collect_org_income``; this handler resolves the org, runs the
    dispatch, and phrases the toast. Copy approved by Apostate (2026-07-03).
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.currency.services import collect_org_income  # noqa: PLC0415

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
        result = collect_org_income(organization=organization, character=character)
    except ValidationError:
        return EffectResult(
            kind=OfferKind.COLLECTION.value,
            message="The strongboxes hold nothing worth a collector's boots.",
            payload={"offer_pk": offer.pk, "organization_pk": organization.pk},
        )
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
    return EffectResult(
        kind=OfferKind.COLLECTION.value,
        object_label=f"Collection for {organization.name}",
        message=message,
        payload={
            "organization_pk": organization.pk,
            "gathered": result.gathered,
            "landed": result.landed,
            "catastrophe": result.catastrophe,
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


def run_train_offer(  # noqa: PLR0911 - one distinct business-rule return per gate
    offer: NPCServiceOffer, persona: Persona
) -> EffectResult:
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
    from world.societies.obligation_services import has_open_obligation  # noqa: PLC0415

    if offer.ap_cost != 0:
        raise TrainOfferMisconfiguredError(offer.pk, offer.ap_cost)

    sheet = persona.character_sheet
    details = offer.train_offer_details
    technique = details.technique

    academy = offer.role.faction_affiliation
    if academy is None:
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message="This trainer has no house to teach for. (Authoring error.)",
            payload={"offer_pk": offer.pk},
        )

    if has_open_obligation(sheet, academy):
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message=f"{academy.name} won't take you on further until your debt is settled.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )

    if not _technique_available_to_learner(sheet, offer.role, technique):
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message="This isn't yours to learn here.",
            payload={"offer_pk": offer.pk, "technique_pk": technique.pk},
        )

    try:
        with transaction.atomic():
            token = _resolve_unredeemed_hare(sheet, academy)
            character_technique = charge_and_learn(
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
        # rolled back (AP, coin, and the CharacterTechnique are all undone).
        return EffectResult(
            kind=OfferKind.TRAIN.value,
            message="Someone else called in that Hare before you finished.",
            payload={"offer_pk": offer.pk, "organization_pk": academy.pk},
        )

    return EffectResult(
        kind=OfferKind.TRAIN.value,
        object_pk=character_technique.pk,
        object_label=technique.name,
        message=f"{academy.name}'s trainer walks you through {technique.name}.",
        payload={
            "character_technique_pk": character_technique.pk,
            "organization_pk": academy.pk,
            "favor_token_pk": token.pk,
        },
    )


def _technique_available_to_learner(
    sheet: CharacterSheet, role: NPCRole, technique: Technique
) -> bool:
    """Whether ``technique`` is in ``sheet``'s TRAIN availability via ``role`` (#2440).

    Availability = the learner's own (Path × Gift) pool ∪ their Tradition's
    signature list (ruling 3 on #2440). The pool half is tradition-agnostic
    (any Academy trainer can teach it); the signature half is members-only —
    offerable only when the trainer's own ``role.teaches_tradition`` matches the
    learner's currently ACTIVE ``CharacterTradition`` membership
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
    # get_technique_options' pool half never reads `tradition` (it's sourced
    # from PathGiftGrant(path, gift) only) — safe to pass trainer_tradition
    # (even None) as the query arg; only the signature half is scoped by it.
    options = get_technique_options(path, gift, trainer_tradition)
    if technique in options.pool:
        return True
    if trainer_tradition is None:
        # Generalist trainer: check for ghost tutelage (#2460).
        # The signature list from get_technique_options(path, gift, None) is
        # empty (TraditionGiftGrant.tradition is non-nullable), so re-query
        # with each tutelage's tradition to get the real signature list.
        for tutelage in sheet.ghost_tutelages.select_related("tradition"):
            tutelage_options = get_technique_options(path, gift, tutelage.tradition)
            if technique in tutelage_options.signature:
                return True
        return False
    if technique not in options.signature:
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
    academy = offer.role.faction_affiliation
    if academy is None:
        return EffectResult(
            kind=OfferKind.SETTLE_OBLIGATION.value,
            message="This registrar keeps no house's books. (Authoring error.)",
            payload={"offer_pk": offer.pk},
        )

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

    details = offer.styling_offer_details
    sheet = persona.character_sheet
    stylist_label = offer.role.name

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
    except NonCosmeticTraitError:
        return EffectResult(
            kind=OfferKind.STYLING.value,
            message="That trait can't be restyled. (Authoring error.)",
            payload={"offer_pk": offer.pk},
        )

    return EffectResult(
        kind=OfferKind.STYLING.value,
        object_label=offer.label,
        message=(
            f"{stylist_label} works their craft — "
            f"{details.trait.display_name} is now {details.target_option.display_name}."
        ),
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
