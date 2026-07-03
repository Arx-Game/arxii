"""The founding scandal vocabulary (#1464/#1806) — authored by Apostate, 2026-07-03.

Nine "X Scandal" archetype rows: the player-legible *category* of a scandal
(rendered as its type on tidings/secrets) whose six-axis vectors do the
per-society judgment invisibly. Descriptions are drafted from Apostate's
dictation and remain his to tweak; **vectors are authoritative on reseed**
(update_or_create) so tuning lands without row churn.

Design rulings carried here:
- No edgelord societies: universal condemnation of crime rides the LAW channel
  (jurisdiction + the crime sting); these rows carry only the moral texture
  differential across societies.
- The victim decides the kind at the tagging seam — deed sources check who was
  harmed before choosing crime/scandal tags; the law model stays dumb.
- No sexual crimes are ever represented (the #1765 content rule); Debauched is
  about public excess and indignity, never whom or how someone loves.
- No seventh axis: comic society-specific scandals (the Nox vs dullness) are
  authored as targeted deed choices, not principles.
"""

from __future__ import annotations

# name -> (deltas dict, description). Vector scale: ±1 mild, ±2 clear, ±3
# strong, ±4 extreme (reserved). Axis poles: mercy Ruthless(-)/Compassion(+),
# method Cunning(-)/Honor(+), status Ambition(-)/Humility(+), change
# Tradition(-)/Progress(+), allegiance Loyalty(-)/Independence(+), power
# Hierarchy(-)/Equality(+).
_SCANDAL_ARCHETYPES: dict[str, tuple[dict[str, int], str]] = {
    "Violent Scandal": (
        {"mercy_delta": -1},
        "Blood spilled outside the forms — a beating over an insult, a killing "
        "that law or custom did not sanction. The hard societies read a certain "
        "respect into it; the gentle ones do not.",
    ),
    "Merciless Scandal": (
        {"mercy_delta": -4},
        "Mercy asked, and refused. The surrendered put to the sword, quarter "
        "denied to the yielding, prisoners never taken, wanton cruelty for its "
        "own sake. To most this is unforgivable; a barbaric society may simply "
        "not care about the rights of the surrendered.",
    ),
    "Treacherous Scandal": (
        {"method_delta": -3, "change_delta": 1, "allegiance_delta": 1},
        "The sworn word broken: vows taken before gods, oaths solemnly given, "
        "contracts sealed and abandoned. 'I promised, and I broke it.' Marriage "
        "vows live here, where a house held them.",
    ),
    "Deceitful Scandal": (
        {"method_delta": -2, "status_delta": -1},
        "The con revealed — a lie constructed and found out. Honorable societies "
        "call it disgrace; the cunning extend a professional's grudging respect.",
    ),
    "Unseemly Scandal": (
        {"power_delta": 1, "status_delta": -1},
        "Conduct beneath one's station: the lady caught filching trinkets, the "
        "lord in low company, expected courtesies abandoned. The indignity is "
        "the offense — hierarchical societies rage at it; egalitarian ones "
        "barely look up.",
    ),
    "Craven Scandal": (
        {"method_delta": -2, "mercy_delta": 1},
        "Cowardice before witnesses — the field fled, the second abandoned, the "
        "begging heard by all. The ruthless despise it more than anyone.",
    ),
    "Penurious Scandal": (
        {"status_delta": -2, "power_delta": 1},
        "A house that cannot pay. Creditors collecting at the source while the "
        "strongbox echoes; obligations met in excuses. Wealth is dignity, and "
        "this is its opposite.",
    ),
    "Debauched Scandal": (
        {"status_delta": -1, "change_delta": 1},
        "Public excess and indignity — the feast gone too far, what should have "
        "stayed private paraded in the open. The offense is the spectacle and "
        "the immodesty of it, never whom or how someone loves.",
    ),
    "Prodigal Scandal": (
        {"allegiance_delta": 2, "power_delta": 1},
        "A Gifted who does not serve. Talent owed to the house left idle or "
        "spent elsewhere — prodigal, wasteful, a duty of the Durance unmet. "
        "Noblesse oblige runs both ways, and this is its breach.",
    ),
}


def seed_scandal_archetypes() -> None:
    """Idempotent + authoritative on vectors/descriptions (tweaks land on reseed)."""
    from world.societies.models import PhilosophicalArchetype  # noqa: PLC0415

    for name, (deltas, description) in _SCANDAL_ARCHETYPES.items():
        PhilosophicalArchetype.objects.update_or_create(
            name=name,
            defaults={"description": description, **deltas},
        )
    # Retire the pre-authoring PLACEHOLDER rows (wrong-signed early drafts).
    PhilosophicalArchetype.objects.filter(
        name__in=["PLACEHOLDER Oathbreaking", "PLACEHOLDER Insolence"]
    ).delete()
