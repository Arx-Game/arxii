"""Production social-action seed — templates, pools, and Flirt's attraction effects (#1697)."""

from django.test import TestCase, override_settings

from world.checks.constants import EffectType
from world.checks.models import ConsequenceEffect
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_actions import seed_social_action_content
from world.seeds.social_checks import seed_social_check_content
from world.seeds.social_relationships import (
    ATTRACTED_CONDITION_NAME,
    VERY_ATTRACTED_CONDITION_NAME,
    seed_social_relationship_content,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class SocialActionSeedTests(TestCase):
    """Gates on SEED_SAMPLE_CONTENT (#2698) — Seduce's Smitten wiring needs the
    real Smitten ConditionTemplate, which is content-repo-owned."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()

    def test_seeds_the_social_action_templates(self) -> None:
        from actions.models import ActionTemplate

        for name in ("Intimidate", "Persuade", "Deceive", "Flirt", "Perform"):
            template = ActionTemplate.objects.get(name=name)
            self.assertIsNotNone(template.consequence_pool_id, f"{name} has no pool")
        # Entrance is skipped — its "Presence" check is an unseeded placeholder (#1690).
        self.assertFalse(ActionTemplate.objects.filter(name="Entrance").exists())

    def test_flirt_success_sets_attracted_and_very_attracted(self) -> None:
        from actions.models import ActionTemplate

        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        effects = ConsequenceEffect.objects.filter(
            consequence=success, effect_type=EffectType.SET_RELATIONSHIP_CONDITION
        )
        names = set(effects.values_list("relationship_condition__name", flat=True))
        self.assertEqual(names, {ATTRACTED_CONDITION_NAME, VERY_ATTRACTED_CONDITION_NAME})
        # Attracted is permanent (no duration); Very Attracted is temporary.
        attracted = effects.get(relationship_condition__name=ATTRACTED_CONDITION_NAME)
        very = effects.get(relationship_condition__name=VERY_ATTRACTED_CONDITION_NAME)
        self.assertIsNone(attracted.relationship_condition_duration)
        self.assertIsNotNone(very.relationship_condition_duration)

    def test_flirt_does_not_apply_smitten(self) -> None:
        from actions.models import ActionTemplate

        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        self.assertFalse(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.APPLY_CONDITION
            ).exists()
        )

    def test_seduce_is_harder_and_sets_attraction_plus_smitten(self) -> None:
        from actions.models import ActionTemplate

        seduce = ActionTemplate.objects.get(name="Seduce")
        self.assertEqual(seduce.difficulty_tier_modifier, 1)  # one tier harder than Flirt
        success = seduce.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        rel_names = set(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.SET_RELATIONSHIP_CONDITION
            ).values_list("relationship_condition__name", flat=True)
        )
        self.assertEqual(rel_names, {ATTRACTED_CONDITION_NAME, VERY_ATTRACTED_CONDITION_NAME})
        # Seduce ALSO applies the Smitten condition (Flirt does not).
        self.assertTrue(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.APPLY_CONDITION
            ).exists()
        )

    def test_idempotent(self) -> None:
        seed_social_action_content()
        seed_social_action_content()
        from actions.models import ActionTemplate

        self.assertEqual(ActionTemplate.objects.filter(name="Flirt").count(), 1)
        flirt = ActionTemplate.objects.get(name="Flirt")
        success = flirt.consequence_pool.entries.get(
            consequence__outcome_tier__name="Success"
        ).consequence
        # No duplicate effects on re-seed.
        self.assertEqual(
            ConsequenceEffect.objects.filter(
                consequence=success, effect_type=EffectType.SET_RELATIONSHIP_CONDITION
            ).count(),
            2,
        )
        # #2540 slice 3: the ask flavors converge too — no duplicate templates/pools.
        for name in ("Con a Boon", "Charm a Boon", "Menace a Boon"):
            self.assertEqual(ActionTemplate.objects.filter(name=name).count(), 1, name)


@override_settings(SEED_SAMPLE_CONTENT=True)
class BoonAskFlavorSeedTests(TestCase):
    """#2540 slice 3 — the three ask-flavor sibling templates each roll their own check."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()

    def test_each_flavor_rolls_its_own_check_type(self) -> None:
        from actions.models import ActionTemplate

        expected = {
            "Con a Boon": "Con",
            "Charm a Boon": "Seduction",
            "Menace a Boon": "Intimidation",
        }
        for name, check_type_name in expected.items():
            template = ActionTemplate.objects.get(name=name)
            self.assertEqual(template.check_type.name, check_type_name, name)

    def test_menace_carries_the_intimidation_difficulty_bump(self) -> None:
        from actions.models import ActionTemplate

        menace = ActionTemplate.objects.get(name="Menace a Boon")
        self.assertEqual(menace.difficulty_tier_modifier, 1)
        con = ActionTemplate.objects.get(name="Con a Boon")
        charm = ActionTemplate.objects.get(name="Charm a Boon")
        self.assertEqual(con.difficulty_tier_modifier, 0)
        self.assertEqual(charm.difficulty_tier_modifier, 0)

    def test_flavors_reuse_the_boon_outcome_pool_labels(self) -> None:
        from actions.models import ActionTemplate

        boon_labels = {
            e.consequence.label
            for e in ActionTemplate.objects.get(name="Boon").consequence_pool.entries.all()
        }
        for name in ("Con a Boon", "Charm a Boon", "Menace a Boon"):
            template = ActionTemplate.objects.get(name=name)
            labels = {e.consequence.label for e in template.consequence_pool.entries.all()}
            self.assertEqual(labels, boon_labels, name)
