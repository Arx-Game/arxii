"""Surrendering control to Fury (#4738 part B, slice of #4727 decision 5).

Brannoc fights a bandit on "The Ford" with Ilse, the one he would burn the world for (a tie of
tier 2 toward her). He casts and declares Fury: ``cast <technique> at <bandit> fury=<tier>
anchor=Ilse``. The tier is a preset amount of control he surrenders; his control roll's outcome
picks how much of the full trade he buys. The trade lands on his engagement for the rest of the
fight, and the cast he declared it with already channels it.

Hand-worked numbers. StrainConfig: 1.50 intensity per control surrendered. FuryConfig: 10%
more per point of provocation cap, one cap point per relationship tier, so Ilse's tier 2 gives
cap 2 and a x1.2 scale. Degree shares: Critical Failure 0%, Failure 25%, Partial Success 50%,
Success 75%, Critical Success 100%.
- Seething (depth 1) surrenders 6 control: full trade 6 x 1.5 x 1.2 = 10.8.
  Success buys floor(8.1) = 8; Partial Success floor(5.4) = 5.
- Unbound (depth 3) surrenders 12 control, but cap 2 clamps it to Seething.
Every roll in the round is forced (the control roll included), so each outcome is the test's
choice.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import resolve_round
from world.combat.services.encounter.config import get_strain_config
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic import services as magic_services
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    FuryConfigFactory,
    FuryDegreeShareFactory,
    FuryTierFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import CharacterEngagementFactory
from world.relationships.factories import CharacterRelationshipFactory
from world.scenes.constants import RoundStatus
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.services import ensure_canonical_check_outcome
from world.vitals.models import CharacterVitals

SHARES = {
    "Critical Failure": 0,
    "Failure": 25,
    "Partial Success": 50,
    "Success": 75,
    "Critical Success": 100,
}
TECHNIQUE_INTENSITY = 20
SEETHING_SURRENDERS = 6


class _AtTheFord(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        self.ford = self.make_room("The Ford")
        self.brannoc = self.make_player("Brannoc", room=self.ford)
        self.ilse = self.make_player("Ilse", room=self.ford)
        sheet = self.brannoc.sheet_data
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterRelationshipFactory(source=sheet, target=self.ilse.sheet_data, tier=2)

        cast_check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=cast_check, trait=StatTraitFactory(), weight=1)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            intensity=TECHNIQUE_INTENSITY,
            control=40,
            anima_cost=1,
            effect_type=EffectTypeFactory(name="Riverstrike", base_power=20),
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=cast_check),
        )
        CharacterTechniqueFactory(character=sheet, technique=self.technique)

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.ford
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter,
            name="Bandit",
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        self.engagement = CharacterEngagementFactory(character=sheet)

        FuryConfigFactory(provocation_cap_per_tier=1, bonus_scale_per_cap_point=10)
        config = get_strain_config()
        config.intensity_per_control_surrendered = Decimal("1.50")
        config.save()
        for name in CANONICAL_OUTCOME_LEVELS:
            FuryDegreeShareFactory(
                outcome_tier=ensure_canonical_check_outcome(name), intensity_percent=SHARES[name]
            )
        self.seething = FuryTierFactory(
            name="Seething", depth=1, control_surrendered=SEETHING_SURRENDERS
        )
        self.unbound = FuryTierFactory(name="Unbound", depth=3, control_surrendered=12)

    def declare_fury(self, tier) -> str:
        return self.telnet(
            self.brannoc,
            f"cast {self.technique.name} at {self.bandit.name} fury={tier.name} anchor=Ilse",
        )

    def resolve_with(self, outcome_name: str) -> list[int]:
        """Resolve the round with every roll at ``outcome_name``.

        Returns the runtime intensity each cast resolved with (a spy on the real
        ``use_technique``, so nothing about the cast is stubbed).
        """
        outcome = ensure_canonical_check_outcome(outcome_name)
        rolled = MagicMock(success_level=outcome.success_level, outcome=outcome)
        real_use_technique = magic_services.use_technique
        cast_intensities: list[int] = []

        def spy(**kwargs):
            result = real_use_technique(**kwargs)
            cast_intensities.append(result.runtime_intensity)
            return result

        with (
            patch("world.checks.services.perform_check", return_value=rolled),
            patch("world.magic.services.use_technique", side_effect=spy),
            self.captureOnCommitCallbacks(execute=True),
        ):
            resolve_round(self.encounter)
        return cast_intensities

    def engagement_now(self) -> CharacterEngagement:
        return CharacterEngagement.objects.get(pk=self.engagement.pk)


class SurrenderingControl(_AtTheFord):
    def test_a_success_buys_its_share_and_the_trade_stays_on_the_engagement(self) -> None:
        self.declare_fury(self.seething)

        casts = self.resolve_with("Success")

        engagement = self.engagement_now()
        self.assertEqual(engagement.intensity_modifier, 8)
        self.assertEqual(engagement.control_modifier, -SEETHING_SURRENDERS)
        self.assertEqual(engagement.fury_control_surrendered, SEETHING_SURRENDERS)
        # The cast Fury was declared with already channels what it bought.
        self.assertEqual(casts, [TECHNIQUE_INTENSITY + 8])

    def test_a_better_roll_buys_more(self) -> None:
        self.declare_fury(self.seething)
        self.resolve_with("Partial Success")
        partial = self.engagement_now().intensity_modifier

        self.assertEqual(partial, 5)
        self.assertGreater(8, partial)

    def test_the_anchor_cap_clamps_a_deeper_tier(self) -> None:
        self.declare_fury(self.unbound)

        self.resolve_with("Success")

        engagement = self.engagement_now()
        self.assertEqual(engagement.fury_control_surrendered, SEETHING_SURRENDERS)
        self.assertEqual(engagement.intensity_modifier, 8)

    def test_a_botched_roll_buys_nothing_but_still_surrenders(self) -> None:
        self.declare_fury(self.seething)

        self.resolve_with("Critical Failure")

        engagement = self.engagement_now()
        self.assertEqual(engagement.intensity_modifier, 0)
        self.assertEqual(engagement.control_modifier, -SEETHING_SURRENDERS)
