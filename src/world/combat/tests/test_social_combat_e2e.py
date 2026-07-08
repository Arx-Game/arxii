"""E2E tests for social/mental combat verbs (#2015)."""

from django.test import TestCase

from world.combat.constants import (
    FALTER_MORALE_THRESHOLD,
    CombatManeuver,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
)
from world.combat.services import (
    declare_demoralize,
    declare_parley,
    declare_rally,
    declare_taunt,
)
from world.scenes.constants import RoundStatus


class DeclareSocialVerbTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        pool = ThreatPoolFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)

    def test_declare_rally_sets_maneuver(self) -> None:
        action = declare_rally(self.participant, self.ally)
        self.assertEqual(action.maneuver, CombatManeuver.RALLY)
        self.assertEqual(action.focused_ally_target, self.ally)
        self.assertTrue(action.is_ready)

    def test_declare_demoralize_sets_maneuver(self) -> None:
        action = declare_demoralize(self.participant, self.opponent)
        self.assertEqual(action.maneuver, CombatManeuver.DEMORALIZE)
        self.assertEqual(action.focused_opponent_target, self.opponent)

    def test_declare_taunt_sets_maneuver(self) -> None:
        action = declare_taunt(self.participant, self.opponent)
        self.assertEqual(action.maneuver, CombatManeuver.TAUNT)
        self.assertEqual(action.focused_opponent_target, self.opponent)

    def test_declare_parley_rejects_steady_opponent(self) -> None:
        # opponent morale is default (70, STEADY) with no standing -> gate fails
        with self.assertRaises(ValueError):
            declare_parley(self.participant, self.opponent)

    def test_declare_parley_allows_faltering_opponent(self) -> None:
        self.opponent.morale = FALTER_MORALE_THRESHOLD
        self.opponent.save()
        action = declare_parley(self.participant, self.opponent)
        self.assertEqual(action.maneuver, CombatManeuver.PARLEY)
        self.assertEqual(action.focused_opponent_target, self.opponent)


from world.checks.test_helpers import force_check_outcome  # noqa: E402
from world.combat.constants import (  # noqa: E402
    BREAK_MORALE_THRESHOLD,
    DEFAULT_OPPONENT_MORALE,
    DEMORALIZE_MORALE_PER_LEVEL,
    TAUNT_THREAT_PER_LEVEL,
)
from world.combat.models import ThreatRecord  # noqa: E402
from world.combat.services import resolve_round  # noqa: E402
from world.combat.social_combat_content import ensure_social_combat_content  # noqa: E402
from world.traits.factories import CheckOutcomeFactory  # noqa: E402


class ResolveSocialVerbTests(TestCase):
    """E2E resolve tests for the social verbs (#2015).

    Each declares the verb, forces a check outcome via force_check_outcome,
    runs resolve_round, and asserts the effect.
    """

    def setUp(self) -> None:
        super().setUp()
        ensure_social_combat_content()
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        pool = ThreatPoolFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)
        # The success outcome (success_level=1).
        self.success = CheckOutcomeFactory(name="SocialTestSuccess", success_level=1)

    def test_demoralize_depletes_morale(self) -> None:
        self.opponent.morale = DEFAULT_OPPONENT_MORALE
        self.opponent.save()
        declare_demoralize(self.participant, self.opponent)

        with force_check_outcome(self.success):
            resolve_round(self.encounter)

        self.opponent.refresh_from_db()
        self.assertEqual(
            self.opponent.morale,
            DEFAULT_OPPONENT_MORALE - DEMORALIZE_MORALE_PER_LEVEL,
        )

    def test_demoralize_at_break_threshold_flees(self) -> None:
        # Set morale so one demoralize (15 dmg) crosses the break threshold (25).
        self.opponent.morale = BREAK_MORALE_THRESHOLD + 5  # 30 -> 15 dmg -> 15 (break)
        self.opponent.save()
        declare_demoralize(self.participant, self.opponent)

        with force_check_outcome(self.success):
            resolve_round(self.encounter)

        self.opponent.refresh_from_db()
        # Morale crossed break; the opponent is now broken (will flee on next
        # select_npc_actions). Assert morale is at/below the threshold.
        self.assertLessEqual(self.opponent.morale, BREAK_MORALE_THRESHOLD)

    def test_taunt_increments_threat(self) -> None:
        declare_taunt(self.participant, self.opponent)

        with force_check_outcome(self.success):
            resolve_round(self.encounter)

        record = ThreatRecord.objects.filter(
            encounter=self.encounter,
            opponent=self.opponent,
            participant=self.participant,
        ).first()
        self.assertIsNotNone(record, "Taunt must create/increment a ThreatRecord")
        self.assertEqual(record.threat_value, TAUNT_THREAT_PER_LEVEL)
