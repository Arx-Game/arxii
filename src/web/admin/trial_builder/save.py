"""Writing a validated trial (#4513): routes, consequences and effects in one transaction.

``proposal.build`` already ran slice 1's rules over unsaved copies, so nothing here decides
whether a row is allowed. A saved row is credited to the operator's contributor, as on the
other builders.
"""

from __future__ import annotations

from django.db import transaction

from web.admin.authoring.credit import stamp_written
from web.admin.trial_builder.proposal import TierProposal
from web.admin.trial_builder.state import (
    FIRST_OTHER_ORDER,
    TierState,
    referencing_rows,
)
from world.checks.models import Consequence, ConsequenceEffect
from world.contributors.models import ContentContributor
from world.missions.models import MissionOption, MissionOptionRoute


def _save_consequence(
    proposal: TierProposal, contributor: ContentContributor
) -> Consequence | None:
    """The tier's consequence, created or updated; None when it has nothing to hold."""
    state, proposed = proposal.state, proposal.consequence
    assert proposed is not None  # noqa: S101 - only called for tiers the page owns
    consequence = state.consequence
    if consequence is None and not (proposal.effects or proposed.deliberately_free):
        return None
    if consequence is None:
        consequence = Consequence(outcome_tier=proposal.tier)
    consequence.label = proposed.label
    consequence.deliberately_free = proposed.deliberately_free
    consequence.free_reason = proposed.free_reason
    consequence.save()
    stamp_written(consequence, contributor)
    for effect in state.owned:
        effect.delete()
    for offset, effect in enumerate(state.others):
        effect.execution_order = FIRST_OTHER_ORDER + offset
        effect.save(update_fields=["execution_order"])
    for effect in proposal.effects:
        effect.consequence = consequence
        effect.save()
        stamp_written(effect, contributor)
    return consequence


def save(
    option: MissionOption, proposals: list[TierProposal], contributor: ContentContributor
) -> None:
    """Write every proposed tier: its consequence and effects, then its route."""
    with transaction.atomic():
        for proposal in proposals:
            state = proposal.state
            data = proposal.form.cleaned_data
            consequence = state.consequence
            if proposal.consequence is not None:
                consequence = _save_consequence(proposal, contributor)
            route = state.route or MissionOptionRoute(option=option, outcome_tier=proposal.tier)
            route.target_node = data.get("next_node")
            route.consequence = consequence
            if route.outcome_text != data.get("outcome_text", ""):
                route.outcome_text_needs_rewrite = False
            route.outcome_text = data.get("outcome_text", "")
            route.save()
            stamp_written(route, contributor)


def delete_trial_routes(states: list[TierState]) -> tuple[int, list[str]]:
    """Delete the option's tier routes: the whole trial this page edits.

    A route with rewards, candidates or renown hanging off it is left alone and named: deleting
    it would take those authored rows with it. A consequence nothing else uses goes with its
    routes. Returns how many routes were deleted and the refusals.
    """
    routed = [s for s in states if s.route is not None]
    held = referencing_rows([s.route for s in routed])
    refused = [
        f"{s.tier.name}: still has {', '.join(held[s.route.pk])}"
        for s in routed
        if held[s.route.pk]
    ]
    doomed = [s for s in routed if not held[s.route.pk]]
    consequences = [s.consequence for s in doomed if s.consequence is not None]
    with transaction.atomic():
        for state in doomed:
            state.route.delete()
        still_used = referencing_rows(consequences, skip=(ConsequenceEffect,))
        for consequence in consequences:
            if not still_used[consequence.pk]:
                consequence.delete()
    return len(doomed), refused
