"""Mission-template visibility — the single eligibility gate (#870).

Visibility IS eligibility: one predicate drives both who *sees* a template
and who *may take* it (the ``visibility = eligibility`` design tenet — no
two-predicate split). Every surface that decides whether a character may be
offered a template routes through :func:`template_visible_to`:

- the NPC-offer path (``world.npc_services.services._mission_gates_pass``)
- trigger dispatch (``world.missions.services.trigger_dispatch``)

Semantics:

- ``OPEN`` — visible to everyone; ``availability_rule`` is not consulted.
- ``RESTRICTED`` — eligibility is the template's ``availability_rule``
  predicate. An empty rule admits no PC at all: that is the *emergent*
  staff-only ("in testing") state, not an error — there is deliberately no
  STAFF_ONLY tier.
- Staff (``is_staff_observer``) always bypass both modes.

Offer-specific gates (level band, cooldowns, ``requirements_override``,
``eligibility_rule``) are orthogonal and stay with their surfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core_management.permissions import is_staff_observer
from world.missions.constants import MissionVisibility
from world.predicates.predicates import CharacterPredicateContext, evaluate

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionTemplate
    from world.scenes.models import Persona


def template_visible_to(
    template: MissionTemplate,
    character: ObjectDB,
    *,
    persona: Persona | None = None,
) -> bool:
    """True if ``character`` may see / be offered ``template``.

    ``persona`` is the character's currently-presented persona (a mask),
    forwarded into the predicate context so persona-aware leaves
    (``is_member_of_org``, ``min_org_rank``, …) gate on the right identity.
    ``None`` means "no mask information" — persona-keyed leaves fail closed.
    """
    if template.visibility == MissionVisibility.OPEN:
        return True
    if is_staff_observer(character):
        return True
    rule = template.availability_rule or {}
    if not rule:
        # RESTRICTED with no gates admits no PC — the emergent staff-only
        # state. (evaluate({}) is vacuously True, so guard explicitly.)
        return False
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    return evaluate(rule, ctx)
