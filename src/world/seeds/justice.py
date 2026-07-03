"""Justice content seed (#1765/#1806) — the crime vocabulary, authored by Apostate.

The normalized ``CrimeKind`` list (2026-07-03 authoring session). Laws
(``AreaLaw`` rows) are world data attached to authored areas and are NOT
seeded — the ratified postures live in ``docs/systems/justice.md`` for
transcription when the grid lands.

Rulings carried here:
- **The victim decides the kind at the tagging seam** — uneven societies are
  theme: assault is a crime *upon the gentle*; a khati's touch is a crime
  *against even the Simple* in Luxen; joy itself is contraband for the lower
  castes. Deed sources check who was harmed/who acted and pick the kind; the
  law model stays ``(area, kind, weight)``.
- Weak crowns, strong local control: the interesting law rows live at
  duchy/barony level; kingdom defaults are thin.
- Descriptions are drafted from Apostate's dictation and safe to edit in
  admin — this seed never overwrites an edited row (it only upgrades rows
  still carrying their original PLACEHOLDER text).

CONTENT RULE (user-ratified, #1765): no sexual crimes of any nature, ever —
see the ``CrimeKind`` model docstring. Do not add such a row here or anywhere.
"""

from __future__ import annotations

# (slug, name, description)
_CRIME_KINDS: list[tuple[str, str, str]] = [
    # --- violence & persons ------------------------------------------------
    ("murder", "Murder", "The unlawful killing of a person. Hot pursuit nearly everywhere."),
    (
        "assault-upon-the-gentle",
        "Assault upon the Gentle",
        "Laying hands on the noble-born. The crime is the station of the victim.",
    ),
    (
        "common-battery",
        "Common Battery",
        "Violence against common folk — prosecuted where and when anyone with "
        "power cares to notice, which is not often.",
    ),
    (
        "caste-transgression",
        "Caste Transgression",
        "Luxen's line crossed: a khati's touch upon even the Simple. "
        "The punishments are famous, and famously uneven.",
    ),
    ("abduction", "Abduction", "Taking a person against their will — captivity by crime."),
    # --- property ----------------------------------------------------------
    ("theft", "Theft", "Taking what is not yours, quietly."),
    ("robbery", "Robbery", "Taking what is not yours, by force or its threat."),
    ("burglary", "Burglary", "Breaking in to take — walls breached, locks defeated."),
    ("arson", "Arson", "Fire set upon what stands. Cities fear little more."),
    # --- trade & vice ------------------------------------------------------
    ("smuggling", "Smuggling", "Moving goods past the eyes that tax or forbid them."),
    (
        "contraband",
        "Contraband",
        "Holding or dealing what the law forbids — drugs and delights, mundane "
        "or lightly magical. In Luxen nearly anything that makes life "
        "enjoyable qualifies, for those low enough to be prosecuted for it.",
    ),
    # --- crown & coin ------------------------------------------------------
    ("treason", "Treason", "The realm betrayed to its enemies."),
    ("sedition", "Sedition", "Stirring subjects against their rightful lords."),
    ("forgery", "Forgery", "False instruments — coin, seal, or signature counterfeited."),
    ("bribery", "Bribery", "An official's judgment purchased."),
    (
        "tax-fraud",
        "Tax Fraud",
        "Declaring less than was taken. The ledgers remember what was actual "
        "and what was sworn.",
    ),
    # --- faith -------------------------------------------------------------
    (
        "sacrilege",
        "Sacrilege",
        "The divine profaned. Law in Luxen; elsewhere a local crime only where "
        "a domain is sworn to its god.",
    ),
    # --- the abyssal statutes (VERY hot wherever they are law) --------------
    (
        "abyssal-practice",
        "Abyssal Practice",
        "Any working of abyssal magic at all — Luxen's capital statute.",
    ),
    (
        "demon-summoning",
        "Demon Summoning",
        "Calling the abyss into the world. Illegal in Umbros, Ariwn, Inferna, "
        "and Aythirmok alike.",
    ),
    (
        "unbonded-great-work",
        "Unbonded Great Work",
        "Great abyssal magic performed without a soul-tether — power taken "
        "without the leash the law demands.",
    ),
    (
        "failure-to-announce",
        "Failure to Announce",
        "A puissant or greater abyssal mage entering a domain without declaring "
        "themselves and their soul-tether. A registration crime — quiet, "
        "bureaucratic, and taken very seriously.",
    ),
]


def seed_crime_kinds() -> None:
    """Idempotently ensure the authored crime kinds exist.

    Never overwrites an admin-edited row; rows still carrying their original
    PLACEHOLDER description are upgraded in place to the authored text.
    """
    from world.justice.models import CrimeKind  # noqa: PLC0415

    for slug, name, description in _CRIME_KINDS:
        kind, created = CrimeKind.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": description}
        )
        if not created and kind.description.startswith("PLACEHOLDER"):
            kind.name = name
            kind.description = description
            kind.save(update_fields=["name", "description"])
