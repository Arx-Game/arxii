"""Tests for magical alteration service functions."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    DamageTypeFactory,
)
from world.conditions.models import (
    ConditionInstance,
    ConditionResistanceModifier,
)
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    ResonanceFactory,
)
from world.magic.models import PendingAlteration
from world.magic.services import (
    create_pending_alteration,
    has_pending_alterations,
    resolve_pending_alteration,
    staff_clear_alteration,
)
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


class ResolvePendingAlterationTests(BaseEvenniaTest):
    """Test resolve_pending_alteration service function."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow",
            affinity=cls.affinity,
        )
        cls.damage_type = DamageTypeFactory(name="Holy")

    def test_resolve_creates_condition_and_event(self):
        """Resolving a pending creates ConditionInstance and MagicalAlterationEvent."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        pending = result.pending

        resolution = resolve_pending_alteration(
            pending=pending,
            name="Voice of Many",
            player_description="Your voice carries echoes of others when you speak.",
            observer_description="Their voice resonates with an eerie chorus.",
            weakness_damage_type=self.damage_type,
            weakness_magnitude=2,
            resonance_bonus_magnitude=1,
            social_reactivity_magnitude=1,
            is_visible_at_rest=False,
            resolved_by=None,
        )

        # Pending is now resolved
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED
        assert pending.resolved_alteration is not None
        assert pending.resolved_at is not None

        # Template was created
        assert resolution.template.tier == AlterationTier.MARKED
        assert resolution.template.origin_affinity == self.affinity

        # Condition was applied
        assert resolution.condition_instance is not None
        assert ConditionInstance.objects.filter(
            target=self.sheet.character,
        ).exists()

        # Event was created
        assert resolution.event is not None
        assert resolution.event.character == self.sheet

    def test_resolve_creates_resistance_modifier(self):
        """Resolving with weakness creates ConditionResistanceModifier."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        resolution = resolve_pending_alteration(
            pending=result.pending,
            name="Holy Sensitivity",
            player_description="A" * 40,
            observer_description="B" * 40,
            weakness_damage_type=self.damage_type,
            weakness_magnitude=2,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )
        ct = resolution.template.condition_template
        assert ConditionResistanceModifier.objects.filter(
            condition=ct,
            damage_type=self.damage_type,
        ).exists()


class HasPendingAlterationsTests(BaseEvenniaTest):
    """Test has_pending_alterations helper."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Primal")
        cls.resonance = ResonanceFactory(name="Storm", affinity=cls.affinity)

    def test_false_when_no_pendings(self):
        assert has_pending_alterations(self.sheet) is False

    def test_true_when_open_pending_exists(self):
        create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        assert has_pending_alterations(self.sheet) is True

    def test_false_after_resolution(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        resolve_pending_alteration(
            pending=result.pending,
            name="Resolved Scar",
            player_description="A" * 40,
            observer_description="B" * 40,
            weakness_magnitude=0,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_false_after_staff_clear(self):
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        staff_clear_alteration(
            pending=result.pending,
            staff_account=None,
            notes="Test clear",
        )
        assert has_pending_alterations(self.sheet) is False
