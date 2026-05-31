"""Test factories for the projects framework."""

from datetime import timedelta

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ContributionPrivacy,
    ProjectKind,
    ProjectStatus,
)
from world.projects.models import Contribution, Project
from world.scenes.factories import PersonaFactory


class ProjectFactory(DjangoModelFactory):
    class Meta:
        model = Project

    kind = ProjectKind.TEST_KIND
    completion_mode = CompletionMode.SINGLE_THRESHOLD
    status = ProjectStatus.PLANNING
    owner_persona = factory.SubFactory(PersonaFactory)
    started_at = factory.LazyFunction(timezone.now)
    time_limit = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    threshold_target = 100
    current_progress = 0
    description = ""


class ContributionFactory(DjangoModelFactory):
    class Meta:
        model = Contribution

    project = factory.SubFactory(ProjectFactory)
    contributor_persona = factory.SubFactory(PersonaFactory)
    kind = ContributionKind.AP
    ap_amount = 1
    money_amount = None
    item_instance = None
    check_outcome = None
    intent_text = ""
    privacy_setting = ContributionPrivacy.PRIVATE
