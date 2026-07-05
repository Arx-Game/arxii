"""Tests for the SituationTrapLink model."""

from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from world.checks.factories import CheckTypeFactory
from world.mechanics.factories import SituationTemplateFactory, SituationTrapLinkFactory
from world.mechanics.models import SituationTrapLink


class SituationTrapLinkModelTest(TestCase):
    def test_create_and_str(self) -> None:
        template = SituationTemplateFactory(name="The Sealed Passage")
        link = SituationTrapLink.objects.create(
            situation_template=template,
            name="Spike Pit",
            consequence_pool=ConsequencePoolFactory(),
            detect_check_type=CheckTypeFactory(name="Detect Traps"),
            disarm_check_type=CheckTypeFactory(name="Disarm Traps"),
            detect_difficulty=20,
            disarm_difficulty=25,
        )

        assert link.is_hidden is True
        assert template.trap_links.get() == link
        assert str(link) == "The Sealed Passage — trap: Spike Pit"


class SituationTrapLinkFactoryTest(TestCase):
    def test_factory_builds_valid_link(self) -> None:
        link = SituationTrapLinkFactory()

        assert link.pk is not None
        assert link.detect_difficulty == 20
        assert link.disarm_difficulty == 20
        assert link.is_hidden is True
