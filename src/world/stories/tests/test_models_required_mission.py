"""Tests for the Phase-5b.3 ``Beat.required_mission`` FK.

The FK is the authoring-time side of the stories-missions seam: a
:class:`~world.stories.models.Beat` may name a
:class:`~world.missions.models.MissionTemplate` it requires. Default is
None (no mission link); on MissionTemplate deletion the FK is SET_NULL
(the beat itself is not also lost).

The product-level engine that walks ``required_mission`` to flip the Beat
when a launched instance terminates is deferred — see
:mod:`world.missions.services.beat` and
``docs/plans/2026-05-18-missions-design.md`` §13.x. 5b.3 lands the data
shape only.
"""

from django.test import TestCase

from world.missions.factories import MissionTemplateFactory
from world.stories.factories import BeatFactory
from world.stories.models import Beat


class BeatRequiredMissionTests(TestCase):
    """The ``required_mission`` FK is optional and SET_NULL on template delete."""

    def test_required_mission_field_exists_on_model(self) -> None:
        field_names = {f.name for f in Beat._meta.get_fields()}
        self.assertIn("required_mission", field_names)

    def test_required_mission_defaults_to_none(self) -> None:
        beat = BeatFactory()
        self.assertIsNone(beat.required_mission)
        self.assertIsNone(beat.required_mission_id)

    def test_required_mission_round_trips(self) -> None:
        template = MissionTemplateFactory(name="required-mission-tmpl")
        beat = BeatFactory(required_mission=template)
        beat.refresh_from_db()
        self.assertEqual(beat.required_mission, template)

    def test_mission_template_delete_set_nulls_required_mission(self) -> None:
        template = MissionTemplateFactory(name="required-mission-delete-tmpl")
        beat = BeatFactory(required_mission=template)
        beat_pk = beat.pk
        template.delete()
        # SET_NULL nulls the FK at the DB level; read the persisted value
        # directly (SharedMemoryModel's identity map would otherwise hand
        # back the cached in-memory FK).
        required_mission_id = (
            Beat.objects.filter(pk=beat_pk).values_list("required_mission_id", flat=True).first()
        )
        self.assertIsNone(required_mission_id)
