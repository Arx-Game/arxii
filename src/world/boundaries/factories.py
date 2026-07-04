"""Factory classes for boundaries models."""

import factory
from factory.django import DjangoModelFactory

from world.boundaries.constants import BoundaryKind, TreasuredSubjectKind
from world.boundaries.models import ContentTheme, PlayerBoundary, TreasuredSubject

_PLAYER_DATA_FACTORY = "world.roster.factories.PlayerDataFactory"
_ROSTER_TENURE_FACTORY = "world.roster.factories.RosterTenureFactory"


class ContentThemeFactory(DjangoModelFactory):
    class Meta:
        model = ContentTheme
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"theme-{n}")
    name = factory.Sequence(lambda n: f"Theme {n}")
    display_order = factory.Sequence(lambda n: n)


class PlayerBoundaryFactory(DjangoModelFactory):
    class Meta:
        model = PlayerBoundary

    owner = factory.SubFactory(_PLAYER_DATA_FACTORY)
    kind = BoundaryKind.ADVISORY
    theme = None


class TreasuredSubjectFactory(DjangoModelFactory):
    class Meta:
        model = TreasuredSubject

    owner = factory.SubFactory(_ROSTER_TENURE_FACTORY)
    subject_kind = TreasuredSubjectKind.CUSTOM
    subject_label = factory.Sequence(lambda n: f"Treasured Subject {n}")


# --- Seed themes (#1771 task 8) -------------------------------------------
#
# A SMALL starter ContentTheme catalog — mirrors world/consent/factories.py's
# make_default_categories() pattern exactly (plain get_or_create, not the
# ContentThemeFactory above, to sidestep the FactoryBoy django_get_or_create
# gotcha where a pre-existing row silently drops non-lookup kwargs). This is
# NOT a Shang-scale content-warning taxonomy; staff extend the catalog via
# admin as real needs surface. Safe to call multiple times (idempotent).


def make_child_endangerment_theme() -> ContentTheme:
    """Return the canonical Child Endangerment ContentTheme (get_or_create)."""
    theme, _ = ContentTheme.objects.get_or_create(
        key="child-endangerment",
        defaults={
            "name": "Child endangerment",
            "description": "Content involving harm, endangerment, or exploitation of children.",
            "display_order": 10,
        },
    )
    return theme


def make_suicide_self_harm_theme() -> ContentTheme:
    """Return the canonical Suicide & Self-Harm ContentTheme (get_or_create)."""
    theme, _ = ContentTheme.objects.get_or_create(
        key="suicide-self-harm",
        defaults={
            "name": "Suicide & self-harm",
            "description": "Content depicting or glorifying suicide or self-harm.",
            "display_order": 20,
        },
    )
    return theme


def make_sexual_violence_theme() -> ContentTheme:
    """Return the canonical Sexual Violence ContentTheme (get_or_create)."""
    theme, _ = ContentTheme.objects.get_or_create(
        key="sexual-violence",
        defaults={
            "name": "Sexual violence",
            "description": "Content depicting rape or other sexual violence.",
            "display_order": 30,
        },
    )
    return theme


def make_torture_theme() -> ContentTheme:
    """Return the canonical Torture ContentTheme (get_or_create)."""
    theme, _ = ContentTheme.objects.get_or_create(
        key="torture",
        defaults={
            "name": "Torture",
            "description": (
                "Content depicting graphic torture or prolonged physical/psychological abuse."
            ),
            "display_order": 40,
        },
    )
    return theme


def make_default_content_themes() -> dict[str, ContentTheme]:
    """Create (or retrieve) the small starter ContentTheme catalog.

    Returns a dict keyed by slug: ``child-endangerment``, ``suicide-self-harm``,
    ``sexual-violence``, ``torture``. Safe to call multiple times in the same
    transaction. NOT an exhaustive content-warning taxonomy — staff add more
    themes via admin as real hard lines surface; this is only the starter set.
    """
    return {
        "child-endangerment": make_child_endangerment_theme(),
        "suicide-self-harm": make_suicide_self_harm_theme(),
        "sexual-violence": make_sexual_violence_theme(),
        "torture": make_torture_theme(),
    }
