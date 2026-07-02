"""Tests for stakes activation at the combat encounter-creation seams (#1770 PR4).

Creating an encounter on a scene whose episodes carry staked UNSATISFIED
beats locks the stakes contract (StakeContractActivation) for the entering
party. Activation is idempotent while open, and the boundary seam is
consulted first (a blocked report skips activation).
"""

from unittest import mock

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.beat_wiring import (
    activate_stakes_for_scene,
    staked_unsatisfied_beats_for_scene,
)
from world.combat.duels import create_lethal_duel, create_pvp_duel
from world.combat.factories import ThreatPoolFactory
from world.scenes.place_services import ensure_scene_for_location
from world.societies.constants import RenownRisk
from world.stories.constants import BeatOutcome, StakeSeverity
from world.stories.factories import BeatFactory, EpisodeSceneFactory, StakeFactory
from world.stories.models import StakeContractActivation
from world.stories.types import StakeBoundaryReport


def _staked_beat_for_scene(scene, *, risk=RenownRisk.HIGH):
    """A staked UNSATISFIED beat whose episode is linked to *scene*."""
    beat = BeatFactory(risk=risk, target_level=4)
    EpisodeSceneFactory(episode=beat.episode, scene=scene)
    StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
    return beat


class StakedBeatsForSceneTests(TestCase):
    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Stakes Room", nohome=True)
        self.scene = ensure_scene_for_location(self.room)

    def test_finds_staked_unsatisfied_beats(self):
        beat = _staked_beat_for_scene(self.scene)
        self.assertEqual(staked_unsatisfied_beats_for_scene(self.scene), [beat])

    def test_ignores_unstaked_and_resolved_beats(self):
        unstaked = BeatFactory(risk=RenownRisk.NONE)
        EpisodeSceneFactory(episode=unstaked.episode, scene=self.scene)
        resolved = BeatFactory(risk=RenownRisk.HIGH, outcome=BeatOutcome.SUCCESS)
        EpisodeSceneFactory(episode=resolved.episode, scene=self.scene)
        self.assertEqual(staked_unsatisfied_beats_for_scene(self.scene), [])


class PvpDuelStakesActivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Duel Room", nohome=True)
        self.scene = ensure_scene_for_location(self.room)

    def test_pvp_duel_activates_staked_beat_contract(self):
        beat = _staked_beat_for_scene(self.scene)

        create_pvp_duel(self.a, self.b, self.room)

        activation = StakeContractActivation.objects.get(beat=beat)
        self.assertIsNone(activation.resolved_at)
        self.assertEqual(activation.declared_risk, RenownRisk.HIGH)
        # Incomplete contract (no WIN/LOSS columns) -> effective NONE (pillar 7).
        self.assertEqual(activation.effective_risk, RenownRisk.NONE)

    def test_second_encounter_on_same_scene_is_idempotent(self):
        beat = _staked_beat_for_scene(self.scene)

        create_pvp_duel(self.a, self.b, self.room)
        create_lethal_duel(
            self.a,
            {"name": "Master", "max_health": 200, "threat_pool": ThreatPoolFactory()},
            self.room,
        )

        self.assertEqual(StakeContractActivation.objects.filter(beat=beat).count(), 1)

    def test_no_staked_beat_activates_nothing(self):
        create_pvp_duel(self.a, self.b, self.room)
        self.assertFalse(StakeContractActivation.objects.exists())


class LethalDuelStakesActivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Lethal Room", nohome=True)
        self.scene = ensure_scene_for_location(self.room)

    def test_lethal_duel_activates_staked_beat_contract(self):
        beat = _staked_beat_for_scene(self.scene)

        create_lethal_duel(
            self.pc,
            {"name": "Master", "max_health": 200, "threat_pool": self.threat_pool},
            self.room,
        )

        self.assertTrue(
            StakeContractActivation.objects.filter(beat=beat, resolved_at__isnull=True).exists()
        )


class CastSeedStakesActivationTests(TestCase):
    """A hostile cast that seeds an encounter is a commit moment too."""

    def test_hostile_cast_seed_activates_staked_beat_contract(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.magic.factories import TechniqueFactory
        from world.scenes.factories import SceneFactory
        from world.vitals.models import CharacterVitals

        caster = CharacterSheetFactory()
        target = CharacterSheetFactory()
        for sheet in (caster, target):
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
        room = create_object("typeclasses.rooms.Room", key="Cast Room", nohome=True)
        scene = SceneFactory(location=room)
        beat = _staked_beat_for_scene(scene)

        seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=TechniqueFactory(),
            scene=scene,
            room=room,
        )

        self.assertTrue(
            StakeContractActivation.objects.filter(beat=beat, resolved_at__isnull=True).exists()
        )


class ActivateStakesForSceneBoundaryTests(TestCase):
    """The boundary seam gates activation (pillar 10); blocked -> skipped."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Boundary Room", nohome=True)
        self.scene = ensure_scene_for_location(self.room)

    def test_boundary_check_invoked_with_participant_sheets(self):
        _staked_beat_for_scene(self.scene)
        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries",
            return_value=StakeBoundaryReport(allowed=True),
        ) as mocked:
            activate_stakes_for_scene(self.scene, [self.sheet])
        mocked.assert_called_once()
        _stakes_arg, sheets_arg = mocked.call_args.args
        self.assertEqual(list(sheets_arg), [self.sheet])

    def test_blocked_report_skips_activation(self):
        beat = _staked_beat_for_scene(self.scene)
        blocked = StakeBoundaryReport(allowed=False, blocked_reason_private="private")
        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries",
            return_value=blocked,
        ):
            activate_stakes_for_scene(self.scene, [self.sheet])
        self.assertFalse(StakeContractActivation.objects.filter(beat=beat).exists())

    def test_none_scene_or_empty_party_is_a_noop(self):
        activate_stakes_for_scene(None, [self.sheet])
        activate_stakes_for_scene(self.scene, [])
        self.assertFalse(StakeContractActivation.objects.exists())
