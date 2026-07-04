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

from world.npc_services.constants import OfferKind

if TYPE_CHECKING:
    from world.npc_services.models import NPCServiceOffer
    from world.scenes.models import Persona


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
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_pool_for_tier,
    )
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.covenants.court_grant import (  # noqa: PLC0415
        court_grant_ceiling,
        raise_court_pact_grant,
    )
    from world.covenants.services import (  # noqa: PLC0415
        active_court_pact_for,
        get_court_grant_config,
    )
    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.npc_services.services import record_petition_outcome  # noqa: PLC0415

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
    standing, _ = NPCStanding.objects.get_or_create(persona=persona, npc_persona=master_persona)

    ease = standing.affection // config.affection_divisor
    check_result = perform_check(
        persona.character_sheet.character,
        offer.check_type,
        target_difficulty=offer.check_difficulty,
        extra_modifiers=ease,
    )
    # CheckResult.success_level (world.checks.types) safely returns 0 when
    # outcome is None — no separate None-check needed.
    succeeded = check_result.success_level > 0
    crossed = record_petition_outcome(
        standing,
        succeeded=succeeded,
        escalation_threshold=config.petition_failure_escalation_threshold,
    )
    if crossed and config.escalation_consequence_pool_id is not None:
        apply_pool_for_tier(
            pool=config.escalation_consequence_pool,
            outcome_tier=check_result.outcome,
            context=ResolutionContext(
                character=persona.character_sheet.character,
                target=persona.character_sheet.character,
            ),
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
