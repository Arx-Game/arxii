"""Service functions for proclamations and domain edicts (#2842)."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from django.db import transaction
from django.utils import timezone

from world.proclamations.models import (
    DomainEdict,
    EdictKind,
    Proclamation,
    StanceArchetype,
)

logger = logging.getLogger(__name__)

# Asymmetric scaling: aligned societies gain reputation scaled by tier,
# opposed societies lose reputation mitigated by success / full on failure.
# PLACEHOLDER tuning constants — to be adjusted by designer.
_ALIGNED_GAIN_PER_TIER = 10  # reputation per success_level
_OPPOSED_FULL_LOSS = 20  # full loss on complete failure (no mitigation)


@dataclass(frozen=True)
class ProclamationResult:
    """The outcome of issuing a proclamation."""

    proclamation: Proclamation
    society_deltas: dict[int, int]  # society_pk -> delta applied
    org_deltas: dict[int, int]  # org_pk -> delta applied


def _stance_dot_product(stance: StanceArchetype, society: object) -> int:
    """Compute the principle dot product between a stance vector + society.

    Same axis iteration as ``_archetype_dot_product`` in renown.py, but for a
    single stance object rather than a list of archetypes.
    """
    from world.societies.constants import PRINCIPLE_FIELD_NAMES  # noqa: PLC0415

    delta = 0
    for principle in PRINCIPLE_FIELD_NAMES:
        # Suppression justified: dynamic principle-axis field name; no default, loud.
        stance_value = getattr(stance, f"{principle}_delta")  # noqa: GETATTR_LITERAL
        # Suppression justified: dynamic principle-axis field name; no default, loud.
        society_value = getattr(society, principle)  # noqa: GETATTR_LITERAL
        delta += stance_value * society_value
    return delta


@transaction.atomic
def issue_proclamation(
    persona,
    stance: StanceArchetype,
    *,
    org=None,
    prose: str = "",
    character=None,
) -> ProclamationResult:
    """Issue a proclamation: roll a check, apply asymmetric reputation deltas.

    Rolls oratory/persuasion (the closest seeded CheckType), then for each
    society the persona has standing with:
    - **aligned** (dot > 0): reputation gain scaled by outcome tier — a failed
      roll wins nobody.
    - **opposed** (dot < 0): reputation loss mitigated by success, taken in
      full on failure, amplified on botch.

    If ``org`` is given, also applies reputation deltas to organizations with
    principle overrides the persona has standing with.

    Args:
        persona: The issuing Persona.
        stance: The StanceArchetype to proclaim.
        org: Optional Organization the persona speaks on behalf of.
        prose: Player-authored text, displayed verbatim, never parsed.
        character: The ObjectDB character for the check (resolved from
            persona if not given).

    Returns:
        ProclamationResult with the created Proclamation and applied deltas.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.societies.models import (  # noqa: PLC0415
        Society,
        SocietyReputation,
    )
    from world.societies.renown import (  # noqa: PLC0415
        bump_society_reputation,
    )

    # Resolve the character for the check
    if character is None:
        try:
            character = persona.character_sheet.character
        except AttributeError:
            character = None

    # Find the closest CheckType for oratory/persuasion
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = (
        CheckType.objects.filter(name__icontains="persuasion").first()
        or CheckType.objects.filter(name__icontains="oratory").first()
        or CheckType.objects.filter(name__icontains="diplomacy").first()
    )

    # Roll the check
    success_level = 0
    check_outcome_name = ""
    if check_type is not None and character is not None:
        result = perform_check(character, check_type, target_difficulty=0)
        check_outcome_name = result.outcome.name if result.outcome else ""
        success_level = result.success_level
    else:
        check_outcome_name = "NO_CHECK"

    # Create the Proclamation row
    proc = Proclamation.objects.create(
        issuer=persona,
        org=org,
        stance=stance,
        prose=prose,
        check_outcome=check_outcome_name,
    )

    # Gather societies: those the persona has reputation with, plus the
    # org's society if org is given
    society_ids = set(
        SocietyReputation.objects.filter(persona=persona).values_list("society_id", flat=True)
    )
    if org is not None and org.society_id is not None:
        society_ids.add(org.society_id)

    societies = Society.objects.filter(id__in=society_ids)

    # Apply reputation deltas to each society
    society_deltas: dict[int, int] = {}
    for society in societies:
        dot = _stance_dot_product(stance, society)
        if dot == 0:
            continue
        if dot > 0:
            # Aligned: gain scaled by success level; failed roll wins nothing
            delta = success_level * _ALIGNED_GAIN_PER_TIER
        # Opposed: loss mitigated by success, full on failure
        elif success_level > 0:
            # Mitigation: each success level reduces the loss
            delta = -max(0, _OPPOSED_FULL_LOSS - success_level * _ALIGNED_GAIN_PER_TIER)
        else:
            delta = -_OPPOSED_FULL_LOSS

        if delta != 0:
            bump_society_reputation(persona, society, delta)
            society_deltas[society.pk] = delta

    # Note: org-level principle overrides ({axis}_override) are a future
    # extension — v1 applies deltas through the society path (the org's
    # society is already in the society loop above). The org FK on the
    # Proclamation records who the issuer spoke on behalf of, for display.
    org_deltas: dict[int, int] = {}

    return ProclamationResult(
        proclamation=proc,
        society_deltas=society_deltas,
        org_deltas=org_deltas,
    )


@transaction.atomic
def enact_edict(domain, kind: EdictKind, proclamation: Proclamation) -> DomainEdict:
    """Enact an edict on a domain, replacing any active edict.

    Revokes the currently active edict (if any) and creates a new active one.
    The proclamation records the social bill that justified the edict.
    """
    DomainEdict.objects.filter(domain=domain, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    return DomainEdict.objects.create(
        domain=domain,
        kind=kind,
        proclamation=proclamation,
    )


@transaction.atomic
def revoke_edict(domain) -> DomainEdict | None:
    """Revoke the active edict on a domain, if any. Returns the revoked edict."""
    edict = DomainEdict.objects.filter(domain=domain, revoked_at__isnull=True).first()
    if edict is not None:
        edict.revoked_at = timezone.now()
        edict.save(update_fields=["revoked_at"])
    return edict
