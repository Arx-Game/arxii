"""Round-trip coverage for the #3269 Phase B grid-bundle sections.

Places, ambient emits, travel hubs, functionaries, feature instances, and
``default_blueprint`` refs each ride the bundle now — this proves an authored
room's Phase B surfaces survive export -> wipe -> import, per the spec's
"a Linode-authored build is durable content" requirement.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.grid_export import export_grid_bundles
from core_management.grid_import import load_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from world.areas.positioning.models import PositionBlueprint
from world.narrative.models import AmbientEmit
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.functionaries import place_functionary
from world.npc_services.models import Functionary
from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureServiceStrategy,
)
from world.room_features.factories import RoomFeatureKindFactory
from world.room_features.models import RoomFeatureInstance
from world.scenes.place_models import Place
from world.travel.constants import TravelMode
from world.travel.models import TravelHub


class PhaseBSectionsRoundTripTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.grid = build_sample_grid()
        self.room = self.grid.taproom
        self.blueprint = PositionBlueprint.objects.create(name="Roundtrip Layout")
        self.room.default_blueprint = self.blueprint
        self.room.save(update_fields=["default_blueprint"])
        Place.objects.create(room=self.room, name="The Bar", description="Long oak bar.")
        AmbientEmit.objects.create(
            key="roundtrip-emit-001",
            text="A log settles in the hearth.",
            room_profile=self.room,
            gate_stat_key="crime",
            gate_min=40,
        )
        TravelHub.objects.create(
            room_profile=self.room,
            name="Taproom Coach Stop",
            travel_modes=[TravelMode.LAND.value],
        )
        self.role = NPCRoleFactory(name="Roundtrip Keeper")
        place_functionary(role=self.role, room=self.room)
        self.kind = RoomFeatureKindFactory(
            name="Roundtrip Board",
            service_strategy=RoomFeatureServiceStrategy.NOTICE_BOARD,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        RoomFeatureInstance.objects.create(room_profile=self.room, feature_kind=self.kind, level=2)

    def test_phase_b_surfaces_survive_export_wipe_import(self) -> None:
        result = export_grid_bundles(self.root)
        assert not result.errors, result.errors

        Place.objects.all().delete()
        AmbientEmit.objects.all().delete()
        TravelHub.objects.all().delete()
        Functionary.objects.all().update(is_active=False)
        RoomFeatureInstance.objects.all().delete()
        self.room.default_blueprint = None
        self.room.save(update_fields=["default_blueprint"])

        load_grid_bundles(self.root)

        self.room.refresh_from_db()
        assert self.room.default_blueprint_id == self.blueprint.pk
        assert Place.objects.filter(room=self.room, name="The Bar").exists()
        emit = AmbientEmit.objects.get(key="roundtrip-emit-001")
        assert emit.room_profile_id == self.room.pk
        assert emit.gate_min == 40
        hub = TravelHub.objects.get(room_profile=self.room)
        assert hub.travel_modes == [TravelMode.LAND.value]
        assert Functionary.objects.filter(room=self.room, role=self.role, is_active=True).exists()
        instance = RoomFeatureInstance.objects.filter(room_profile=self.room).active().get()
        assert instance.feature_kind_id == self.kind.pk
        assert instance.level == 2

    def test_credited_emit_is_frozen_not_overwritten(self) -> None:
        from world.contributors.models import ContentContributor

        writer = ContentContributor.objects.create(name="Apostate")
        emit = AmbientEmit.objects.get(key="roundtrip-emit-001")
        emit.written_by = writer
        emit.save(update_fields=["written_by"])
        result = export_grid_bundles(self.root)
        assert not result.errors

        emit.text = "A human rewrote this line by hand."
        emit.save(update_fields=["text"])
        import_result = load_grid_bundles(self.root)

        emit.refresh_from_db()
        assert emit.text == "A human rewrote this line by hand."
        assert any("frozen" in line for line in import_result.reports)
