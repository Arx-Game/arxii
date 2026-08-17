"""Factories for scheduled-downtime announcements (#3194)."""

from datetime import timedelta

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.downtime.models import DowntimeWindow


class DowntimeWindowFactory(DjangoModelFactory):
    class Meta:
        model = DowntimeWindow

    starts_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=6))
    expected_duration_minutes = 30
    message = factory.Sequence(lambda n: f"Planned maintenance window {n}")
