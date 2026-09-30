"""Idempotent seed helpers for the societies system.

Per repo discipline (#683): seeds live in code, called via ``get_or_create`` /
``authored_or_sample``. NOT a committed fixture.
"""

from __future__ import annotations

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual
from world.seeds.sample_content import authored_or_sample
from world.societies.honors import HONORS_SERVICE_PATH

RITE_OF_HONORS_NAME = "Rite of Honors"


def ensure_rite_of_honors_ritual() -> Ritual | None:
    """Look up (or, under ``SEED_SAMPLE_CONTENT``, invent) the Rite of Honors row (#3466).

    Dispatches via ``HONORS_SERVICE_PATH``
    (``world.societies.honors.honor_deed``) at perform time. Single-actor and
    ``hedge_accessible=False`` (ruling) — this is a Gifted rite, deliberately:
    a Gifted voice's praise is what gives the telling its weight, and that is
    the entire point of channeling honoring through a ritual instead of a
    plain journal post. #3001's visibility-is-eligibility rule
    (``ritual_visible_to``, ``world/magic/services/ritual_pool.py``) closing
    it to a character with no magical profile is correct here, not a gap —
    the rite spending Golden Hares rather than anima doesn't change who may
    speak it, any more than a Gifted rite with material components would.

    ``magic.ritual`` is a ``CONTENT_MODELS`` entry (mixed ownership, split by
    ``author_account__isnull`` — see ``core_management/content_export.py``),
    so this follows ``world.seeds.game_content.magic.seed_canonical_rituals``'s
    own pattern for "Rite of Imbuing"/"Rite of Atonement"/"Ritual of the
    Durance": looked up first, invented only when ``SEED_SAMPLE_CONTENT`` is on
    or the content repo already authored it. Returns ``None`` otherwise
    (logged) rather than fabricating a row that would land in a content
    export.
    """
    return authored_or_sample(
        Ritual,
        {
            "description": (
                "Spend a Golden Hare to grow a witnessed deed's legend, or to "
                "establish a fresh deed for an extraordinary act an event "
                "never credited on its own."
            ),
            "narrative_prose": (
                "Shroudwatch trains every Prospect in this rite before they "
                "leave the Academy. Pay a Golden Hare, set down what you saw, "
                "and post it as a public journal entry. The telling adds "
                "weight to the deed itself, whether the one who did it is "
                "still standing or not."
            ),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": HONORS_SERVICE_PATH,
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
        name=RITE_OF_HONORS_NAME,
    )


#: The ruling of 2026-09-29 (#4061): a character votes from the highest seat they
#: personally hold. Retune in the admin (Crime Vote Weights); this only fills gaps.
CRIME_VOTE_WEIGHTS: tuple[tuple[str, int, int], ...] = (
    ("family", 1, 20),
    ("family", 2, 3),
    ("family", 3, 3),
    ("family", 4, 0),
    ("family", 5, 0),
    ("empire", 1, 20),
    ("empire", 2, 3),
    ("empire", 3, 3),
    ("empire", 4, 0),
    ("empire", 5, 0),
    ("gang", 1, 5),
    ("gang", 2, 2),
    ("gang", 3, 2),
    ("gang", 4, 2),
    ("gang", 5, 2),
    ("crew", 1, 2),
    ("crew", 2, 1),
    ("crew", 3, 1),
    ("crew", 4, 1),
    ("crew", 5, 1),
)


def seed_crime_vote_weights() -> int:
    """Idempotent: every (tier, rung) has a weight row; existing rows are never changed."""
    from world.societies.models import CrimeVoteWeight  # noqa: PLC0415

    created = 0
    for tier, rank_tier, weight in CRIME_VOTE_WEIGHTS:
        _row, was_created = CrimeVoteWeight.objects.get_or_create(
            tier=tier, rank_tier=rank_tier, defaults={"weight": weight}
        )
        created += int(was_created)
    return created
