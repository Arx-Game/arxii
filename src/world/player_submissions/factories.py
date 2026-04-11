"""Factories for player submission models."""

import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.scenes.factories import PersonaFactory


class PlayerFeedbackFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PlayerFeedback

    reporter_account = factory.SubFactory(AccountFactory)
    reporter_persona = factory.SubFactory(PersonaFactory)
    description = factory.Faker("paragraph")
    status = SubmissionStatus.OPEN


class BugReportFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BugReport

    reporter_account = factory.SubFactory(AccountFactory)
    reporter_persona = factory.SubFactory(PersonaFactory)
    description = factory.Faker("paragraph")
    status = SubmissionStatus.OPEN


class PlayerReportFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PlayerReport

    reporter_account = factory.SubFactory(AccountFactory)
    reported_account = factory.SubFactory(AccountFactory)
    reporter_persona = factory.SubFactory(PersonaFactory)
    reported_persona = factory.SubFactory(PersonaFactory)
    behavior_description = factory.Faker("paragraph")
    asked_to_stop = False
    blocked_or_muted = False
    status = SubmissionStatus.OPEN
