from __future__ import annotations

from django.test import TestCase

from world.magic.types.power_ledger import PowerLedgerBuilder
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import InteractionPowerLedgerEntry
from world.scenes.power_ledger_services import persist_power_ledger


class SceneFinishPurgesLedgerTests(TestCase):
    def test_finish_scene_deletes_its_ledger_rows(self) -> None:
        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene, mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=interaction, ledger=PowerLedgerBuilder(base=5).build())
        assert InteractionPowerLedgerEntry.objects.filter(interaction__scene=scene).exists()

        scene.finish_scene()

        assert not InteractionPowerLedgerEntry.objects.filter(interaction__scene=scene).exists()

    def test_finish_scene_leaves_other_scenes_ledgers(self) -> None:
        scene_a = SceneFactory()
        scene_b = SceneFactory()
        ia = InteractionFactory(scene=scene_a, mode=InteractionMode.ACTION)
        ib = InteractionFactory(scene=scene_b, mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=ia, ledger=PowerLedgerBuilder(base=5).build())
        persist_power_ledger(interaction=ib, ledger=PowerLedgerBuilder(base=5).build())

        scene_a.finish_scene()

        assert not InteractionPowerLedgerEntry.objects.filter(interaction__scene=scene_a).exists()
        assert InteractionPowerLedgerEntry.objects.filter(interaction__scene=scene_b).exists()
