"""The GM morale control: one morale state per use, with a reason (#4354)."""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.gm_standoff import GMStandoffMoraleAction
from evennia_extensions.factories import AccountFactory
from world.combat.constants import BREAK_MORALE_THRESHOLD, FALTER_MORALE_THRESHOLD, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    seed_scaling_defaults,
)
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.standoffs.constants import MoraleDirection
from world.standoffs.models import StandoffConfig, StandoffMoraleRuling
from world.standoffs.services.gm_morale import shift_group_morale
from world.standoffs.services.state import open_standoff
from world.standoffs.services.verbs import morale_terms_ease

REASON = "PLACEHOLDER ruling reason"
LEVEL = "world.standoffs.services.force.effective_combat_level"


class GMMoraleTests(TestCase):
    def setUp(self) -> None:
        # setUp, not setUpTestData: every test moves morale.
        seed_scaling_defaults()
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True)
        self.encounter = CombatEncounterFactory(scene=self.scene)
        CombatParticipantFactory(encounter=self.encounter)
        self.template = CreatureTemplateFactory(tier=OpponentTier.MOOK)
        self.members = [
            CombatOpponentFactory(
                encounter=self.encounter,
                creature_template=self.template,
                tier=OpponentTier.MOOK,
                morale=80,
                max_morale=100,
            )
            for _ in range(2)
        ]
        # get_or_create would drop has_morale on the seeded row: set it explicitly.
        self.tier = OpponentTierTemplateFactory(tier=OpponentTier.MOOK)
        self.tier.has_morale = True
        self.tier.save(update_fields=["has_morale"])
        level = patch(LEVEL, return_value=100)
        level.start()
        self.addCleanup(level.stop)
        self.group = open_standoff(self.encounter)[0]

    def states(self) -> list[str]:
        for member in self.members:
            member.refresh_from_db()
        return [morale_state_for(member) for member in self.members]

    def test_shake_moves_every_member_one_state_and_records_the_reason(self) -> None:
        outcome = shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        self.assertTrue(outcome.success)
        self.assertEqual(self.states(), [OpponentMoraleState.FALTER] * 2)
        self.assertEqual([m.morale for m in self.members], [FALTER_MORALE_THRESHOLD] * 2)
        self.assertEqual(outcome.room_line, f"{self.template.name} falters.")
        ruling = StandoffMoraleRuling.objects.get(group=self.group)
        self.assertEqual((ruling.direction, ruling.reason), (MoraleDirection.SHAKE, REASON))
        self.assertEqual(ruling.ruled_by, self.gm)

    def test_a_second_shake_breaks_them(self) -> None:
        shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        outcome = shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        self.assertEqual(self.states(), [OpponentMoraleState.BREAK] * 2)
        self.assertEqual([m.morale for m in self.members], [BREAK_MORALE_THRESHOLD] * 2)
        self.assertEqual(outcome.room_line, f"{self.template.name} breaks.")

    def test_steady_moves_back_one_state(self) -> None:
        shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        outcome = shift_group_morale(self.group, MoraleDirection.STEADY, REASON, ruled_by=self.gm)
        self.assertEqual(self.states(), [OpponentMoraleState.STEADY] * 2)
        self.assertEqual(outcome.room_line, f"{self.template.name} steadies.")

    def test_a_faltering_group_eases_terms(self) -> None:
        config = StandoffConfig.load()
        self.assertEqual(morale_terms_ease(self.members, config), 0)
        shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        self.states()
        self.assertEqual(morale_terms_ease(self.members, config), config.terms_ease_faltering)

    def test_a_reason_is_required(self) -> None:
        outcome = shift_group_morale(self.group, MoraleDirection.SHAKE, "  ", ruled_by=self.gm)
        self.assertFalse(outcome.success)
        self.assertEqual(self.states(), [OpponentMoraleState.STEADY] * 2)

    def test_refused_on_a_tier_without_morale(self) -> None:
        self.tier.has_morale = False
        self.tier.save(update_fields=["has_morale"])
        outcome = shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.message, "They have no morale to move.")

    def test_refused_outside_a_standoff(self) -> None:
        from world.standoffs.services.state import end_standoff_into_fight

        end_standoff_into_fight(self.encounter, initiated_by_pc_side=True)
        outcome = shift_group_morale(self.group, MoraleDirection.SHAKE, REASON, ruled_by=self.gm)
        self.assertFalse(outcome.success)

    def test_steady_on_a_steady_group_changes_nothing(self) -> None:
        outcome = shift_group_morale(self.group, MoraleDirection.STEADY, REASON, ruled_by=self.gm)
        self.assertFalse(outcome.success)
        self.assertFalse(StandoffMoraleRuling.objects.exists())

    def test_the_action_admits_the_scene_gm_only(self) -> None:
        stranger = AccountFactory()
        refused = GMStandoffMoraleAction().run(
            actor=None,
            account=stranger,
            group_id=self.group.pk,
            direction=MoraleDirection.SHAKE,
            reason=REASON,
        )
        self.assertFalse(refused.success)
        with patch("actions.definitions.gm_standoff._announce") as announce:
            done = GMStandoffMoraleAction().run(
                actor=None,
                account=self.gm,
                group_id=self.group.pk,
                direction=MoraleDirection.SHAKE,
                reason=REASON,
            )
        self.assertTrue(done.success)
        announce.assert_called_once_with(self.encounter, f"{self.template.name} falters.", "")
