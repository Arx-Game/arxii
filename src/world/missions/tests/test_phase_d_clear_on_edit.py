"""Phase-D needs-rewrite lifecycle (#941): the editor clears the flag on rewrite.

The copy service flags cloned outcome text as needing a rewrite; the editor
serializer must clear that flag once an author actually rewrites the text
(else copied missions stay flagged forever). An explicit flag value wins.
"""

from django.test import TestCase

from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.serializers import (
    MissionOptionRouteCandidateSerializer,
    MissionOptionRouteSerializer,
)


class ClearOutcomeRewriteOnEditTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="phase-d-clear")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.dest = MissionNodeFactory(template=cls.template, key="dest")
        cls.option = MissionOptionFactory(node=cls.node, order=0)

    def _flagged_route(self):
        return MissionOptionRouteFactory(
            option=self.option,
            target_node=self.dest,
            outcome_text="copied prose",
            outcome_text_needs_rewrite=True,
        )

    def test_rewriting_outcome_text_clears_the_flag(self) -> None:
        route = self._flagged_route()

        serializer = MissionOptionRouteSerializer(
            route, data={"outcome_text": "an author's own words"}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        route.refresh_from_db()
        assert route.outcome_text == "an author's own words"
        assert route.outcome_text_needs_rewrite is False

    def test_explicit_flag_value_is_respected(self) -> None:
        route = self._flagged_route()

        serializer = MissionOptionRouteSerializer(
            route,
            data={"outcome_text": "reworded", "outcome_text_needs_rewrite": True},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        route.refresh_from_db()
        assert route.outcome_text_needs_rewrite is True

    def test_editing_other_fields_leaves_flag_set(self) -> None:
        route = self._flagged_route()

        serializer = MissionOptionRouteSerializer(route, data={"is_random_set": True}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        route.refresh_from_db()
        assert route.outcome_text_needs_rewrite is True  # untouched text → flag stays

    def test_candidate_serializer_clears_on_rewrite(self) -> None:
        route = MissionOptionRouteFactory(option=self.option, target_node=None, is_random_set=True)
        candidate = MissionOptionRouteCandidateFactory(
            route=route,
            target_node=self.dest,
            outcome_text="copied",
            outcome_text_needs_rewrite=True,
        )

        serializer = MissionOptionRouteCandidateSerializer(
            candidate, data={"outcome_text": "rewritten"}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        candidate.refresh_from_db()
        assert candidate.outcome_text_needs_rewrite is False
