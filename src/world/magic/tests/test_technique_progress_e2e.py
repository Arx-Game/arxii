"""E2E journey test for technique learning meter (#2711).

Covers: create offer → accept → train over sessions → complete.
Also covers cross-path multiplier and grant_path_magic bypass.
"""

from decimal import Decimal

from django.test import TestCase

from actions.definitions.technique_training import TrainTechniqueAction
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
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
    TrainingOutcomeAward,
)
from world.magic.services.gift_acquisition import accept_technique_offer
from world.magic.services.path_magic import grant_path_magic
from world.magic.services.technique_progress import (
    contribute_to_technique_progress,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory
from world.traits.models import CheckOutcome

# Canonical outcome tiers (name -> success_level), matching seeds/checks.py.
_CANONICAL_OUTCOMES = [
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
]


def _ensure_outcome(name: str, success_level: int) -> CheckOutcome:
    outcome, _ = CheckOutcome.objects.get_or_create(
        name=name, defaults={"success_level": success_level}
    )
    return outcome


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
        result = contribute_to_technique_progress(self.learner, progress, dev_points=30)
        self.assertIsNone(result)

        # Train — complete
        progress.refresh_from_db()
        result = contribute_to_technique_progress(self.learner, progress, dev_points=20)
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


class TrainTechniqueActionJourneyE2ETest(TestCase):
    """Front door through the dispatch seam (#2739 final-review fold-in).

    Threads the production front door -- accepting a teaching offer via
    ``accept_technique_offer`` (#2711/#2726, the same acquisition seam
    ``TechniqueProgressE2ETest`` above exercises) -- through the
    player-facing session action ``TrainTechniqueAction.run()``
    (#2739) all the way to meter completion, rather than calling
    ``contribute_to_technique_progress``/``resolve_training_check`` directly
    as the action's own unit tests and ``ResolveTrainingCheckTest`` do (both
    start from an already-existing ``TechniqueProgress`` row). Setup mirrors
    ``TechniqueProgressE2ETest`` above; check-content seeding mirrors
    ``TrainTechniqueActionTestBase`` in
    ``actions/tests/test_technique_training_action.py``.
    """

    def setUp(self):
        self.learner = CharacterSheetFactory()
        self.learner_pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.learner_pool.current = 500
        self.learner_pool.save()

        self.teacher_tenure = RosterTenureFactory()
        self.teacher_pool = ActionPointPool.get_or_create_for_character(
            self.teacher_tenure.character
        )
        self.teacher_pool.current = 500
        self.teacher_pool.banked = 20
        self.teacher_pool.save()

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

        self.outcomes = {name: _ensure_outcome(name, sl) for name, sl in _CANONICAL_OUTCOMES}
        self._seed_award_rows()
        self._seed_check_content()

    def _seed_award_rows(self):
        multipliers = {
            "Critical Failure": Decimal("0.00"),
            "Failure": Decimal("0.00"),
            "Partial Success": Decimal("0.50"),
            "Success": Decimal("1.00"),
            "Critical Success": Decimal("1.50"),
        }
        for name, mult in multipliers.items():
            TrainingOutcomeAward.objects.update_or_create(
                outcome_tier=self.outcomes[name],
                defaults={"dev_point_multiplier": mult},
            )

    def _seed_check_content(self):
        """Minimal CheckType so resolve_training_check can resolve a check."""
        from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
        from world.skills.models import Skill
        from world.traits.models import Trait, TraitCategory, TraitType

        arcane_trait, _ = Trait.objects.get_or_create(
            name="Arcane Theory",
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.MAGIC,
                "is_public": True,
            },
        )
        Skill.objects.get_or_create(
            trait=arcane_trait,
            defaults={
                "tooltip": "Understanding the theoretical underpinnings of magical techniques.",
                "display_order": 0,
                "is_active": True,
            },
        )
        intellect_trait, _ = Trait.objects.get_or_create(
            name="intellect",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.MENTAL,
                "is_public": True,
            },
        )
        category, _ = CheckCategory.objects.get_or_create(
            name="Magic",
            defaults={"description": "Magic checks.", "display_order": 40},
        )
        check_type, _ = CheckType.objects.get_or_create(
            name="Technique Training",
            category=category,
            defaults={"is_active": True, "display_order": 10},
        )
        w = Decimal("1.0")
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=intellect_trait, defaults={"weight": w}
        )
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=arcane_trait, defaults={"weight": w}
        )

    def test_accept_offer_then_train_sessions_complete_meter(self):
        offer = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique,
            pitch="I will teach you",
            learn_ap_cost=20,
            banked_ap=20,
        )

        # Front door: accepting the offer mints the meter (no CharacterTechnique yet).
        progress = accept_technique_offer(self.learner, offer)
        self.assertIsInstance(progress, TechniqueProgress)
        self.assertEqual(progress.total_required, 20)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).exists()
        )

        # Dispatch seam: TrainTechniqueAction.run() drives the session to completion.
        with force_check_outcome(self.outcomes["Success"]):
            result = TrainTechniqueAction().run(
                self.learner.character,
                technique_id=self.technique.pk,
                ap_to_invest=20,
            )

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["technique_acquired"])
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).exists()
        )
        self.assertFalse(TechniqueProgress.objects.filter(pk=progress.pk).exists())
