"""Tests for the Phase-5b.3 ``MissionInstance.source_beat`` FK.

The FK is the runtime side of the stories-missions seam: a
:class:`~world.missions.models.MissionInstance` may have been launched as
the resolver of a specific :class:`~world.stories.models.Beat`. Default is
None (free mission); on Beat deletion the FK is SET_NULL (the run is not
also lost).

The product-level engine that flips the Beat when the instance terminates
is deferred — see :mod:`world.missions.services.beat` and
``docs/plans/2026-05-18-missions-design.md`` §13.x. 5b.3 lands the data
shape only.
"""

from django.test import TestCase

from world.missions.factories import MissionInstanceFactory, MissionTemplateFactory
from world.missions.models import MissionInstance
from world.stories.factories import BeatFactory


class MissionInstanceSourceBeatTests(TestCase):
    """The ``source_beat`` FK is optional and SET_NULL on Beat delete."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="source-beat-tmpl")

    def test_source_beat_field_exists_on_model(self) -> None:
        field_names = {f.name for f in MissionInstance._meta.get_fields()}
        self.assertIn("source_beat", field_names)

    def test_source_beat_defaults_to_none(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        self.assertIsNone(instance.source_beat)
        self.assertIsNone(instance.source_beat_id)

    def test_source_beat_round_trips(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        instance.refresh_from_db()
        self.assertEqual(instance.source_beat, beat)

    def test_beat_delete_set_nulls_source_beat(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        instance_pk = instance.pk
        beat.delete()
        # SET_NULL nulls the FK at the DB level; read the persisted value
        # directly (SharedMemoryModel's identity map would otherwise hand
        # back the cached in-memory FK).
        source_beat_id = (
            MissionInstance.objects.filter(pk=instance_pk)
            .values_list("source_beat_id", flat=True)
            .first()
        )
        self.assertIsNone(source_beat_id)
