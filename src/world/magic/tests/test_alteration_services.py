"""Tests for magical alteration service functions."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    ResonanceFactory,
)
from world.magic.models import PendingAlteration
from world.magic.services import create_pending_alteration
from world.scenes.factories import SceneFactory


class CreatePendingAlterationTests(BaseEvenniaTest):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def test_creates_new_pending(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        assert result.created is True
        assert result.pending.status == PendingAlterationStatus.OPEN
        assert result.pending.tier == AlterationTier.MARKED

    def test_creates_with_snapshot_fields(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
            triggering_intensity=50,
            triggering_control=30,
            triggering_anima_deficit=20,
            audere_active=True,
        )
        assert result.pending.triggering_intensity == 50
        assert result.pending.triggering_control == 30
        assert result.pending.audere_active is True

    def test_same_scene_escalation_upgrades_tier(self):
        scene = SceneFactory()
        result1 = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        assert result1.created is True

        result2 = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED_PROFOUNDLY,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
            triggering_intensity=80,
        )
        assert result2.created is False
        assert result2.previous_tier == AlterationTier.MARKED
        assert result2.pending.tier == AlterationTier.MARKED_PROFOUNDLY
        assert result2.pending.triggering_intensity == 80
        assert PendingAlteration.objects.filter(character=self.sheet).count() == 1

    def test_same_scene_no_downgrade(self):
        scene = SceneFactory()
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene,
        )
        assert result.created is False
        assert result.previous_tier is None
        assert result.pending.tier == AlterationTier.TOUCHED

    def test_different_scenes_create_separate_pendings(self):
        scene1 = SceneFactory()
        scene2 = SceneFactory()
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene1,
        )
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=scene2,
        )
        assert (
            PendingAlteration.objects.filter(
                character=self.sheet,
                status=PendingAlterationStatus.OPEN,
            ).count()
            == 2
        )
