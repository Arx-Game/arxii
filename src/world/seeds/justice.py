"""Justice content seed (#1765) — the starter CrimeKind vocabulary.

PLACEHOLDER rows: two common kinds so the law/heat mechanism runs end-to-end.
The real vocabulary ("all the crimes you'd expect", plus regional flavor like
Luxen's capital Abyssal-magic statute) is Apostate's authoring pass — laws
themselves (AreaLaw rows) are world-building data, never seeded here.

CONTENT RULE (user-ratified, #1765): no sexual crimes of any nature, ever —
see the ``CrimeKind`` model docstring. Do not add such a row here or anywhere.
"""

from __future__ import annotations

# (slug, name, description) — PLACEHOLDER descriptions for Apostate's voice pass.
_CRIME_KINDS: list[tuple[str, str, str]] = [
    ("murder", "Murder", "PLACEHOLDER: the unlawful killing of a person."),
    ("theft", "Theft", "PLACEHOLDER: taking what is not yours."),
]


def seed_crime_kinds() -> None:
    """Idempotently ensure the starter crime kinds exist (never overwrites edits)."""
    from world.justice.models import CrimeKind  # noqa: PLC0415

    for slug, name, description in _CRIME_KINDS:
        CrimeKind.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": description}
        )
