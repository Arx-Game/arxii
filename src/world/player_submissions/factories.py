"""Factories for player submission models."""

import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.player_submissions.constants import PetitionCategory, SubmissionStatus
from world.player_submissions.models import (
    BugReport,
    CheckProposal,
    Petition,
    PlayerFeedback,
    PlayerReport,
    SystemErrorReport,
)
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


class SystemErrorReportFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SystemErrorReport

    signature = factory.Sequence(lambda n: f"sig-{n}")
    label = "test.hook"
    exception_type = "ValueError"
    message = "boom"
    traceback = "Traceback (most recent call last): ..."


class CheckProposalFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CheckProposal

    submitted_by_account = factory.SubFactory(AccountFactory)
    submitted_by_persona = factory.SubFactory(PersonaFactory)
    proposed_name = factory.Sequence(lambda n: f"Proposed Check {n}")
    intent = factory.Faker("sentence")
    suggested_traits_text = "Perception + Survival"
    situation_text = factory.Faker("sentence")
    status = SubmissionStatus.OPEN


class PetitionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Petition

    account = factory.SubFactory(AccountFactory)
    category = PetitionCategory.OTHER_EMERGENCY
    description = factory.Faker("paragraph")
    status = SubmissionStatus.OPEN
