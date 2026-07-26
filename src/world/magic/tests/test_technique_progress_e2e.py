"""E2E journey test for technique learning meter (#2711).

Covers: create offer → accept → train over sessions → complete.
Also covers cross-path multiplier and grant_path_magic bypass.
"""

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    TechniqueProgress,
    TechniqueTeachingOffer,
    Thread,
)
from world.magic.services.gift_acquisition import accept_technique_offer
from world.magic.services.path_magic import grant_path_magic
from world.magic.services.technique_progress import (
    contribute_to_technique_progress,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory


class TechniqueProgressE2ETest(TestCase):
    def setUp(self):
        # Learner setup
        self.learner = CharacterSheetFactory()
        self.learner_pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.learner_pool.current = 500
        self.learner_pool.save()

        # Teacher setup
        self.teacher_tenure = RosterTenureFactory()
        self.teacher_pool = ActionPointPool.get_or_create_for_character(
            self.teacher_tenure.character
        )
        self.teacher_pool.current = 500
        self.teacher_pool.banked = 20
        self.teacher_pool.save()

        # Gift + technique
        self.gift = GiftFactory()
        self.technique = TechniqueFactory(gift=self.gift)
        CharacterGift.objects.create(character=self.learner, gift=self.gift)
        Thread.objects.create(
            owner=self.learner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )

    def test_full_journey_teaching(self):
        """Accept offer → train → complete."""
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="I will teach you",
            learn_ap_cost=50,
            banked_ap=20,
        )

        # Accept — creates meter, consumes teacher's banked AP
        progress = accept_technique_offer(self.learner, offer)
        self.assertIsInstance(progress, TechniqueProgress)
        self.assertEqual(progress.total_required, 50)

        # No CharacterTechnique yet
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).exists()
        )

        # Train — partial
        result = contribute_to_technique_progress(self.learner, progress, amount=30)
        self.assertIsNone(result)

        # Train — complete
        progress.refresh_from_db()
        result = contribute_to_technique_progress(self.learner, progress, amount=20)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, CharacterTechnique)

        # Meter is consumed
        self.assertFalse(TechniqueProgress.objects.filter(pk=progress.pk).exists())

    def test_cross_path_multiplier(self):
        """Cross-path learning has a higher meter total."""
        style_a = TechniqueStyleFactory()
        style_b = TechniqueStyleFactory()
        path_a = PathFactory(style=style_a)
        path_b = PathFactory(style=style_b)

        CharacterPathHistoryFactory(character=self.learner, path=path_a)
        CharacterPathHistoryFactory(
            character=self.teacher_tenure.roster_entry.character_sheet,
            path=path_b,
        )

        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="Cross-path teaching",
            learn_ap_cost=50,
            banked_ap=20,
        )

        progress = accept_technique_offer(self.learner, offer)
        self.assertTrue(progress.is_cross_path)
        self.assertEqual(progress.total_required, 100)  # 50 * 2.0

    def test_same_path_no_multiplier(self):
        """Same-path learning has no multiplier."""
        style = TechniqueStyleFactory()
        path = PathFactory(style=style)

        CharacterPathHistoryFactory(character=self.learner, path=path)
        CharacterPathHistoryFactory(
            character=self.teacher_tenure.roster_entry.character_sheet,
            path=path,
        )

        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="Same-path teaching",
            learn_ap_cost=50,
            banked_ap=20,
        )

        progress = accept_technique_offer(self.learner, offer)
        self.assertFalse(progress.is_cross_path)
        self.assertEqual(progress.total_required, 50)

    def test_grant_path_magic_bypasses_meter(self):
        """grant_path_magic mints CharacterTechnique directly, no meter."""
        from world.magic.models import PathGiftGrant

        path = PathFactory()
        PathGiftGrant.objects.create(path=path, gift=self.gift)
        grant = PathGiftGrant.objects.get(path=path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

        result = grant_path_magic(self.learner, path)
        self.assertIn(self.technique, result.granted_techniques)
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).exists()
        )
        self.assertFalse(
            TechniqueProgress.objects.filter(
                character_sheet=self.learner, technique=self.technique
            ).exists()
        )
