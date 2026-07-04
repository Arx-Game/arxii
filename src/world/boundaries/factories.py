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
