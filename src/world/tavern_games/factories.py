"""Factories for tavern games tests (#3292)."""

from __future__ import annotations

import factory
from factory import django as factory_django

from world.scenes.factories import PersonaFactory, PlaceFactory
from world.tavern_games.constants import GameResolutionKind
from world.tavern_games.models import GameSeat, GameSession, TavernGame


class TavernGameFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = TavernGame
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Test Dice Game {n}")
    rules_blurb = "Highest roll takes the pot; ties re-roll."
    min_ante = 1
    max_ante = 1000
    resolution_kind = GameResolutionKind.HIGHEST_ROLL
    is_active = True


class GameSessionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GameSession

    place = factory.SubFactory(PlaceFactory)
    game = factory.SubFactory(TavernGameFactory)
    opened_by = factory.SubFactory(PersonaFactory)
    ante = 10


class GameSeatFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GameSeat

    session = factory.SubFactory(GameSessionFactory)
    persona = factory.SubFactory(PersonaFactory)
    ante_paid = 10
