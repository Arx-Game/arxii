"""Issue-time refusal: PROJECT reward lines + unbound instance = hard refusal (#2045).

The no-silent-drop rule: a template carrying PROJECT reward lines must not issue
an instance with no bound project. The refusal is loud at the door (issuance),
not a silent no-op at payout.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.missions.services.run import staff_assign_mission


def _make_route_on_template(template):
    """Create a terminal route on a template (assumes entry node already exists)."""
    entry = template.nodes.get(is_entry=True)
    option = MissionOptionFactory(node=entry)
    return MissionOptionRouteFactory(option=option, target_node=None)


def _make_template_with_entry():
    """Create a template with an entry node (required by staff_assign_mission)."""
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class IssueTimeRefusalTests(TestCase):
    """PROJECT lines + unbound instance → hard refusal at issuance."""

    def test_staff_assign_refuses_project_lines_without_project(self) -> None:
        """A template with PROJECT reward lines can't be assigned without a project."""
        template = _make_template_with_entry()
        route = _make_route_on_template(template)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.PROJECT,
            amount=10,
        )
        character = CharacterFactory(db_key="RefusalChar")
        with self.assertRaises(ValueError):
            staff_assign_mission(template, character)

    def test_staff_assign_allows_project_lines_with_project(self) -> None:
        """A template with PROJECT reward lines is fine when a project is bound."""
        from world.projects.factories import ProjectFactory

        template = _make_template_with_entry()
        route = _make_route_on_template(template)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.PROJECT,
            amount=10,
        )
        character = CharacterFactory(db_key="BoundChar")
        project = ProjectFactory()
        instance = staff_assign_mission(template, character, project=project)
        self.assertEqual(instance.target_project_id, project.pk)

    def test_staff_assign_allows_no_project_lines_without_project(self) -> None:
        """A template without PROJECT reward lines is fine without a project."""
        template = _make_template_with_entry()
        character = CharacterFactory(db_key="NoProjectChar")
        instance = staff_assign_mission(template, character)
        self.assertIsNone(instance.target_project_id)
