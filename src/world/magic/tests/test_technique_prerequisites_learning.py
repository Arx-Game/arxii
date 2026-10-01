"""Technique-learning prerequisite gate (#4097, Task 4).

``charge_and_learn`` now checks ``check_requirements_for_technique`` (Task 3)
right after the "already knows this technique" gate, raising
``TechniqueRequirementsNotMet`` when an active requirement targeting the
technique isn't met. ``get_technique_options`` (CG catalog) excludes any
technique carrying an active requirement row outright — starter/special picks
have no prerequisites authored against them and a draft has no character to
evaluate a per-character check against.

Fixture setup for the ``charge_and_learn`` tests mirrors
``ChargeAndLearnGoldCostTest`` (``test_gift_acquisition_service.py``): the
learner already owns the gift + a level-10 GIFT thread, sidestepping the
XP-unlock gate and the technique cap so these tests stay focused on the
prerequisite gate.
"""

from __future__ import annotations

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import TechniqueRequirementsNotMet
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
)
from world.magic.models import Thread
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.cg_catalog import get_technique_options
from world.magic.services.gift_acquisition import charge_and_learn
from world.progression.models import TechniqueKnownRequirement


class ChargeAndLearnPrerequisitesTest(TestCase):
    """``charge_and_learn`` gates on ``check_requirements_for_technique``."""

    def setUp(self):
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.sheet = CharacterSheetFactory()
        # Already-owned gift + provisioned thread — sidesteps the XP-unlock
        # gate and the technique cap so these tests stay focused on
        # prerequisites (mirrors ChargeAndLearnGoldCostTest).
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.prerequisite = TechniqueFactory()
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def _learn(self):
        return charge_and_learn(
            self.sheet,
            self.technique,
            base_ap_cost=5,
            source=AccessChangeSource.ACADEMY_TRAINING,
        )

    def test_blocked_without_prerequisite(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )

        with self.assertRaises(TechniqueRequirementsNotMet) as ctx:
            self._learn()

        exc = ctx.exception
        self.assertEqual(exc.user_message, "You have not yet met what this technique requires.")
        self.assertEqual(len(exc.failed), 1)
        self.assertIn(self.prerequisite.name, exc.failed[0])

    def test_succeeds_after_learning_prerequisite(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.prerequisite)

        progress = self._learn()

        self.assertEqual(progress.technique, self.technique)

    def test_inactive_requirement_does_not_block(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=False,
        )

        progress = self._learn()

        self.assertEqual(progress.technique, self.technique)


class CgCatalogExcludesGatedTechniquesTest(TestCase):
    """``get_technique_options`` excludes any technique with an active requirement."""

    def setUp(self):
        self.path = PathFactory()
        self.gift = GiftFactory()
        self.tradition = TraditionFactory()
        cast_template = get_standalone_cast_template()

        self.ungated_technique = TechniqueFactory(gift=self.gift, action_template=cast_template)
        self.gated_technique = TechniqueFactory(gift=self.gift, action_template=cast_template)
        other_technique = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=self.gated_technique,
            required_technique=other_technique,
            is_active=True,
        )

        path_grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        path_grant.starter_techniques.set([self.ungated_technique, self.gated_technique])

    def test_gated_technique_excluded_from_pool(self):
        options = get_technique_options(self.path, self.gift, self.tradition)

        self.assertIn(self.ungated_technique, options.pool)
        self.assertNotIn(self.gated_technique, options.pool)

    def test_inactive_requirement_does_not_exclude(self):
        requirement = TechniqueKnownRequirement.objects.get(technique=self.gated_technique)
        requirement.is_active = False
        requirement.save()

        options = get_technique_options(self.path, self.gift, self.tradition)

        self.assertIn(self.gated_technique, options.pool)
