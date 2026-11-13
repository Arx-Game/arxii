"""Factories for missives tests (#3289)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
import factory
from factory import django as factory_django

from world.messengers.models import Missive, MissiveAttachment, TransmissionMethod
from world.scenes.factories import PersonaFactory


class TransmissionMethodFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = TransmissionMethod

    name = factory.Sequence(lambda n: f"Test Courier {n}")
    description = "A runner carries the letter across the city."
    ic_delay_minutes = 30
    can_carry_items = True
    can_carry_coin = True
    is_universal = True


class MissiveFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Missive

    sender_persona = factory.SubFactory(PersonaFactory)
    recipient_persona = factory.SubFactory(PersonaFactory)
    method = factory.SubFactory(TransmissionMethodFactory)
    body = "A short letter."
    available_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=30))


class MissiveAttachmentFactory(factory_django.DjangoModelFactory):
    """Defaults to a coin attachment; pass ``item=`` and ``coin_amount=None`` for an item."""

    class Meta:
        model = MissiveAttachment

    missive = factory.SubFactory(MissiveFactory)
    item = None
    coin_amount = 10
