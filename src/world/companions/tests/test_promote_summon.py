"""Tests for the summon → Companion promotion bridge (#2502)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory, ThreatPoolFactory
from world.companions.content import ensure_companion_content
from world.companions.factories import CompanionArchetypeFactory
from world.companions.services import PromoteSummonError, promote_summon_to_companion
from world.magic.specialization.services import grant_gift_to_character


class PromoteSummonTests(TestCase):
    """Summon-path and charmed-enemy-path promotion to persistent Companion."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Promote Test Room")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()

        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)

        # Seed charm content for the charmed-enemy-path tests.
        from world.conditions.charm_content import ensure_charm_content

        ensure_charm_content()

        # Give the GIFT thread enough level for Companion Capacity.
        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        self.thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        self.thread.level = 10
        self.thread.save(update_fields=["level"])

        self.archetype = CompanionArchetypeFactory(
            name="Promote Test Beast",
            bind_difficulty=20,
            capacity_cost=5,
            charm_difficulty_reduction=0,
        )

        self.encounter = CombatEncounterFactory()
        self.threat_pool = ThreatPoolFactory()

    def test_summon_path_promotion_creates_companion(self):
        """A summon with summoned_by=caster and allegiance=ALLY promotes to a Companion."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="Forced Promote Success", success_level=5)
        opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.threat_pool,
        )
        opponent.allegiance = CombatAllegiance.ALLY
        opponent.summoned_by = self.sheet
        opponent.status = OpponentStatus.ACTIVE
        opponent.save(update_fields=["allegiance", "summoned_by", "status"])

        with force_check_outcome(success):
            companion = promote_summon_to_companion(
                caster_sheet=self.sheet,
                combat_opponent=opponent,
                archetype=self.archetype,
                granting_gift=self.gift,
                name="Bound Summon",
            )

        self.assertEqual(companion.name, "Bound Summon")
        self.assertEqual(companion.owner, self.sheet)
        self.assertEqual(companion.granting_gift, self.gift)
        self.assertEqual(companion.archetype, self.archetype)

    def test_non_summon_non_charmed_rejected(self):
        """A CombatOpponent that is not an ALLY summon and not charmed is rejected."""
        opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.threat_pool,
        )
        # Default: summoned_by=None, allegiance=ENEMY, no charm condition.
        with self.assertRaises(PromoteSummonError) as ctx:
            promote_summon_to_companion(
                caster_sheet=self.sheet,
                combat_opponent=opponent,
                archetype=self.archetype,
                granting_gift=self.gift,
                name="Should Fail",
            )
        self.assertIn("cannot be promoted", ctx.exception.user_message)

    def test_over_capacity_rejected(self):
        """Promotion fails when Companion Capacity is exceeded."""

        # Fill capacity with an expensive companion.
        expensive_archetype = CompanionArchetypeFactory(
            name="Expensive Beast",
            bind_difficulty=20,
            capacity_cost=100,  # exceeds capacity (thread level 10 → low capacity)
        )
        # Use a summon to attempt promotion
        opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.threat_pool,
        )
        opponent.allegiance = CombatAllegiance.ALLY
        opponent.summoned_by = self.sheet
        opponent.status = OpponentStatus.ACTIVE
        opponent.save(update_fields=["allegiance", "summoned_by", "status"])

        with self.assertRaises(PromoteSummonError) as ctx:
            promote_summon_to_companion(
                caster_sheet=self.sheet,
                combat_opponent=opponent,
                archetype=expensive_archetype,
                granting_gift=self.gift,
                name="Should Fail",
            )
        self.assertIn("Capacity", ctx.exception.user_message)

    def test_charmed_enemy_path_creates_companion(self):
        """A charmed enemy (allegiance=ENEMY, Charmed) promotes with difficulty reduction."""
        from world.checks.test_helpers import force_check_outcome
        from world.conditions.constants import CHARM_CONDITION_NAME
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition
        from world.traits.factories import CheckOutcomeFactory

        # Create the charmed archetype with auto-success reduction.
        charmed_archetype = CompanionArchetypeFactory(
            name="Charmed Beast",
            bind_difficulty=20,
            capacity_cost=5,
            charm_difficulty_reduction=20,  # auto-success
        )

        opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.threat_pool,
        )
        # Enemy opponent (not a summon).
        opponent.allegiance = CombatAllegiance.ENEMY
        opponent.summoned_by = None
        opponent.status = OpponentStatus.ACTIVE
        opponent.save(update_fields=["allegiance", "summoned_by", "status"])

        # Apply Charmed condition with source_character = caster.
        charm_template = ConditionTemplate.get_by_name(CHARM_CONDITION_NAME)
        target_character = opponent.objectdb
        self.assertIsNotNone(target_character, "Opponent needs an objectdb for charm")
        apply_condition(target_character, charm_template, source_character=self.sheet.character)

        success = CheckOutcomeFactory(name="Forced Charm Bind Success", success_level=5)
        with force_check_outcome(success):
            companion = promote_summon_to_companion(
                caster_sheet=self.sheet,
                combat_opponent=opponent,
                archetype=charmed_archetype,
                granting_gift=self.gift,
                name="Charmed Foe",
            )

        self.assertEqual(companion.name, "Charmed Foe")

        # Verify charm was consumed.
        from world.conditions.services import get_active_conditions

        active = get_active_conditions(target_character, condition=charm_template)
        self.assertEqual(list(active), [], "Charm condition should be consumed after bind")

    def test_charmed_enemy_wrong_charmer_rejected(self):
        """A charmed enemy charmed by someone else is rejected (source_character check)."""
        from world.conditions.constants import CHARM_CONDITION_NAME
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition

        other_sheet = CharacterSheetFactory()
        other_sheet.character.location = self.room
        other_sheet.character.save()

        opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.threat_pool,
        )
        opponent.allegiance = CombatAllegiance.ENEMY
        opponent.status = OpponentStatus.ACTIVE
        opponent.save(update_fields=["allegiance", "status"])

        # Apply Charmed by the OTHER caster.
        charm_template = ConditionTemplate.get_by_name(CHARM_CONDITION_NAME)
        target_character = opponent.objectdb
        apply_condition(target_character, charm_template, source_character=other_sheet.character)

        with self.assertRaises(PromoteSummonError) as ctx:
            promote_summon_to_companion(
                caster_sheet=self.sheet,
                combat_opponent=opponent,
                archetype=self.archetype,
                granting_gift=self.gift,
                name="Should Fail",
            )
        self.assertIn("cannot be promoted", ctx.exception.user_message)
