"""E2E tests for social/mental combat verbs (#2015)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.models import CheckType
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
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.covenants.perks.evaluators import FAVORABLY_DISPOSED_MIN_AFFECTION
from world.magic.factories import ThreadFactory
from world.npc_services.factories import NPCStandingFactory
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


class ResolveSocialCheckSituationContextTests(TestCase):
    """#2536 Task 5 review fix: `_resolve_social_check` (the shared Rally/
    Demoralize/Taunt/Parley roll seam) must thread a SituationContext into
    perform_check so a future CHECK_BONUS perk scoped to one of these social
    CheckTypes can actually fire, mirroring CombatTechniqueResolver._roll_check.
    """

    def setUp(self) -> None:
        super().setUp()
        ensure_social_combat_content()
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_situation_ctx_threaded_with_live_round_context(self) -> None:
        from world.combat.round_context import CombatRoundContext
        from world.combat.services import _resolve_social_check
        from world.covenants.perks.context import SituationContext

        # _resolve_social_check re-imports `perform_check` locally from
        # world.checks.services (services.py:5600ish) rather than using the
        # module-level name — patch the source, not world.combat.services.
        with patch("world.checks.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=1)
            _resolve_social_check(self.participant, "Rally", 0)

        situation_ctx = mock_perform.call_args.kwargs["situation_ctx"]
        self.assertIsInstance(situation_ctx, SituationContext)
        self.assertEqual(situation_ctx.holder, self.participant.character_sheet)
        self.assertEqual(situation_ctx.subject, self.participant.character_sheet)
        self.assertIsNone(situation_ctx.target)
        self.assertIsInstance(situation_ctx.resolution, CombatRoundContext)
        self.assertEqual(situation_ctx.resolution.participant, self.participant)


class TargetSituationalPerkFiresThroughSocialCombatTests(TestCase):
    """#2536 Task 6 review fix (Important finding — untested fold-in): proves
    a TARGET_* situational perk genuinely fires through the shared
    ``_resolve_social_check`` CHECK_BONUS path for each verb that resolves
    against an opposing target (Demoralize/Taunt/Parley — Rally targets an
    ally, so no TARGET_* situation applies to it, see
    ``_resolve_social_check``'s docstring). ``ResolveSocialCheckSituationContextTests``
    above already proves a ``SituationContext`` object of the right SHAPE gets
    built; this proves a REAL perk actually fires through it end to end (via
    ``resolve_round``, the real production dispatch path — not a private
    resolver called directly), asserted the same way
    ``test_fired_perk_announced_exactly_once``
    (``world/checks/tests/test_situational_perk_check_bonus.py``) asserts
    CHECK_BONUS wiring: that ``announce_fired_perks`` receives the perk as a
    genuine firing.
    """

    def setUp(self) -> None:
        super().setUp()
        ensure_social_combat_content()
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        pool = ThreatPoolFactory()
        # A "story NPC" opponent (persona-linked) so _resolve_primary_target_sheet
        # can resolve a real CharacterSheet target — a bare MOOK opponent has no
        # CharacterSheet and TARGET_FAVORABLY_DISPOSED could never hold for it.
        self.target_sheet = CharacterSheetFactory()
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=pool,
            persona=self.target_sheet.primary_persona,
        )
        NPCStandingFactory(
            persona=self.participant.character_sheet.primary_persona,
            npc_persona=self.target_sheet.primary_persona,
            affection=FAVORABLY_DISPOSED_MIN_AFFECTION,
        )
        self.success = CheckOutcomeFactory(name="SocialTestSuccess", success_level=1)

    def _grant_target_favorably_disposed_perk(self, *, check_type_name: str):
        check_type = CheckType.objects.get(name=check_type_name)
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.participant.character_sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=30,
            check_type=check_type,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_FAVORABLY_DISPOSED)
        ThreadFactory(owner=self.participant.character_sheet, level=10)
        return perk

    def test_demoralize_fires_target_favorably_disposed_perk(self) -> None:
        perk = self._grant_target_favorably_disposed_perk(check_type_name="Demoralize")
        declare_demoralize(self.participant, self.opponent)

        with (
            force_check_outcome(self.success),
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
        ):
            resolve_round(self.encounter)

        assert mock_announce.call_count == 1
        (fired_arg,), _kwargs = mock_announce.call_args
        assert any(firing.perk == perk for firing in fired_arg)

    def test_taunt_fires_target_favorably_disposed_perk(self) -> None:
        perk = self._grant_target_favorably_disposed_perk(check_type_name="Taunt")
        declare_taunt(self.participant, self.opponent)

        with (
            force_check_outcome(self.success),
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
        ):
            resolve_round(self.encounter)

        assert mock_announce.call_count == 1
        (fired_arg,), _kwargs = mock_announce.call_args
        assert any(firing.perk == perk for firing in fired_arg)

    def test_parley_fires_target_favorably_disposed_perk(self) -> None:
        # Parley is gated: the opponent must be faltering (or the caller must
        # hold standing) before declare_parley will accept it (see
        # test_declare_parley_allows_faltering_opponent above).
        self.opponent.morale = FALTER_MORALE_THRESHOLD
        self.opponent.save()
        perk = self._grant_target_favorably_disposed_perk(check_type_name="Parley")
        declare_parley(self.participant, self.opponent)

        with (
            force_check_outcome(self.success),
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
        ):
            resolve_round(self.encounter)

        assert mock_announce.call_count == 1
        (fired_arg,), _kwargs = mock_announce.call_args
        assert any(firing.perk == perk for firing in fired_arg)
