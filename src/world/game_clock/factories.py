"""FactoryBoy factories for game clock models."""

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from evennia_extensions.factories import AccountFactory
from world.game_clock.constants import DEFAULT_TIME_RATIO
from world.game_clock.models import GameClock, GameClockHistory


class GameClockFactory(DjangoModelFactory):
    class Meta:
        model = GameClock

    anchor_real_time = factory.LazyFunction(timezone.now)
    anchor_ic_time = factory.LazyFunction(
        lambda: timezone.now().replace(
            year=1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    )
    time_ratio = DEFAULT_TIME_RATIO
    paused = False


class GameClockHistoryFactory(DjangoModelFactory):
    class Meta:
        model = GameClockHistory

    changed_by = factory.SubFactory(AccountFactory)
    old_anchor_real_time = factory.LazyFunction(timezone.now)
    old_anchor_ic_time = factory.LazyFunction(timezone.now)
    old_time_ratio = DEFAULT_TIME_RATIO
    new_anchor_real_time = factory.LazyFunction(timezone.now)
    new_anchor_ic_time = factory.LazyFunction(timezone.now)
    new_time_ratio = DEFAULT_TIME_RATIO
    reason = ""
