"""Journeys for magical skills (#4450): a technique's skill joins the roll its cast makes.

A caster on a Path whose staff-set technique skill is, say, Occult rolls her cast with that
skill added to the check the cast already used. These journeys cast the way the web client does
(``dispatch_player_action`` on ``cast_technique``, or a declared combat technique) and read back
the roll the cast made.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from actions.constants import ActionBackend, EnhancementSourceType
from actions.effects.registry import apply_effects
from actions.factories import ActionEnhancementFactory, ActionTemplateFactory
from actions.models import ActionEnhancement, RemoveConditionOnCheckConfig
from actions.player_interface import dispatch_player_action
from actions.registry import get_action
from actions.types import ActionContext, ActionRef
from flows.scene_data_manager import SceneDataManager
from integration_tests.harness import JourneyCase
from world.checks.factories import (
    CheckTypeFactory,
    CheckTypeTraitFactory,
    create_social_action_templates,
)
from world.checks.services import perform_check
from world.checks.test_helpers import CheckCapture, force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.classes.factories import PathFactory
from world.combat.constants import (
    ActionCategory,
    CombatAllegiance,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    ThreatPoolFactory,
)
from world.combat.services import resolve_round
from world.companions.content import BIND_ATTEMPT_CHECK_NAME, ensure_companion_content
from world.companions.factories import CompanionArchetypeFactory
from world.conditions.constants import BreakFreeMode
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition
from world.dreams.conditions import ensure_dream_conditions
from world.dreams.peril import get_dream_peril_config, resolve_dream_peril_collapse
from world.fatigue.constants import EffortLevel
from world.magic.constants import EffectKind, MagicActivity, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    EffectTypeFactory,
    GiftFactory,
    MagicActivitySkillFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import CharacterResonance
from world.magic.models.threads import Thread
from world.magic.services.threads import weave_thread
from world.magic.specialization.services import grant_gift_to_character
from world.magic.types.pull import CastPullDeclaration
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import WeeklySkillUsage
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import SkillFactory
from world.standoffs.factories import StandoffApproachFactory
from world.standoffs.services.state import open_standoff
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CharacterTraitValue, CheckOutcome, PointConversionRange, TraitType
from world.vitals.factories import create_dream_peril_pool
from world.vitals.models import CharacterVitals
from world.vitals.seeds import seed_survivability_content

SKILL_VALUE = 30


class CastingWithATechniqueSkill(JourneyCase):
    """Ysmay and Hobb walk the same Path; only Ysmay has trained its technique skill."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.skill = SkillFactory()
        self.path = PathFactory(technique_skill=self.skill)
        self.lantern = self.make_room("The Lantern")
        SceneFactory(room=self.lantern)

        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.template = ActionTemplateFactory(check_type=check_type)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.template,
        )
        self.ysmay = self.caster_on_the_path("Ysmay", skill_value=SKILL_VALUE)
        self.hobb = self.caster_on_the_path("Hobb", skill_value=0)

    def caster_on_the_path(self, name: str, *, skill_value: int):
        character = self.make_player(name, room=self.lantern)
        sheet = character.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        grant_technique(sheet.primary_persona, self.technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        if skill_value:
            CharacterTraitValue.objects.create(
                character=sheet, trait=self.skill.trait, value=skill_value
            )
        return character

    def cast_and_read_the_roll(
        self, character, **cast_kwargs
    ) -> tuple[tuple[ExtraTraitTerm, ...], CheckResult]:
        """Cast the technique on the web seam; return the terms the roll carried and its result.

        ``self.roll_modifiers`` is left holding the flat modifier the cast added to that roll.
        """
        rolled: list[CheckResult] = []

        def spy(*args, **kwargs) -> CheckResult:
            result = perform_check(*args, **kwargs)
            rolled.append(result)
            self.roll_modifiers = kwargs.get("extra_modifiers", 0)
            return result

        success = CheckOutcome.objects.get(name="Success")
        with (
            force_check_outcome(success) as capture,
            patch("actions.services.perform_check", side_effect=spy),
        ):
            outcome = self.web(
                character, "cast_technique", technique_id=self.technique.pk, **cast_kwargs
            )
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertEqual(len(rolled), 1)
        return capture.extra_traits, rolled[0]

    def test_scene_cast_adds_path_technique_skill(self) -> None:
        terms, result = self.cast_and_read_the_roll(self.ysmay)

        self.assertEqual(terms, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("1.00")),))
        _, untrained = self.cast_and_read_the_roll(self.hobb)
        self.assertEqual(result.trait_points - untrained.trait_points, SKILL_VALUE)

    def test_thread_on_technique_skill_pulls_on_web_cast(self) -> None:
        sheet = self.ysmay.sheet_data
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=10, lifetime_earned=10
        )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=1,
            flat_bonus_amount=3,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        CharacterThreadWeavingUnlockFactory(
            character=sheet,
            unlock=ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT, unlock_trait=self.skill.trait
            ),
        )
        thread = weave_thread(
            sheet, TargetKind.TRAIT, self.skill.trait, resonance, name="Occult Thread"
        )
        self.cast_and_read_the_roll(self.ysmay)
        unpulled = self.roll_modifiers

        self.cast_and_read_the_roll(
            self.ysmay,
            cast_pull=CastPullDeclaration(resonance=resonance, tier=1, threads=(thread,)),
        )

        self.assertEqual(self.roll_modifiers - unpulled, 3)
        balance = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(balance.balance, 9)


class FlirtingWithATechniqueSkill(JourneyCase):
    """Ysmay flirts with Hobb through a technique and pulls a thread on its skill (#4450).

    The technique-enhanced flirt rolls the flirt's own check plus the technique skill, so a
    thread on either is in the action. How much the pull adds to that roll is a separate
    matter (#4466); these journeys read the charge and the fizzle note over REST.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.seed_social_engagement()
        self.skill = SkillFactory()
        self.parlor = self.make_room("The Parlor")
        self.scene = SceneFactory(room=self.parlor)
        templates = create_social_action_templates()
        self.flirt = next(t for t in templates if t.name == "Flirt")
        self.ysmay = self.make_player("Ysmay", room=self.parlor)
        self.hobb = self.make_player("Hobb", room=self.parlor)
        sheet = self.ysmay.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=PathFactory(technique_skill=self.skill))
        CharacterTraitValue.objects.create(character=sheet, trait=self.skill.trait, value=30)
        self.technique = TechniqueFactory(
            name="Mesmerizing Gaze", intensity=3, control=8, anima_cost=2, gift=GiftFactory()
        )
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=self.technique,
        )
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=self.resonance, balance=10, lifetime_earned=10
        )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=3,
            effect_kind=EffectKind.FLAT_BONUS,
        )

    def thread_on(self, trait):
        sheet = self.ysmay.sheet_data
        CharacterThreadWeavingUnlockFactory(
            character=sheet,
            unlock=ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait),
        )
        return weave_thread(sheet, TargetKind.TRAIT, trait, self.resonance, name="Anchor")

    def balance(self) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.ysmay.sheet_data, resonance=self.resonance
        ).balance

    def flirt_with_a_pull_on(self, thread) -> dict:
        """Ysmay asks with the pull declared, Hobb accepts; return the accepted result."""
        created = self.api(self.account_of(self.ysmay)).post(
            reverse("sceneactionrequest-list"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.ysmay.sheet_data.primary_persona.pk,
                "target_persona": self.hobb.sheet_data.primary_persona.pk,
                "action_key": "flirt",
                "technique_id": self.technique.pk,
                "pull": {
                    "resonance_id": self.resonance.pk,
                    "tier": 1,
                    "thread_ids": [thread.pk],
                },
            },
            format="json",
            headers={"X-Character-ID": str(self.ysmay.pk)},
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        accepted = self.api(self.account_of(self.hobb)).post(
            reverse("sceneactionrequest-respond", args=[created.data["id"]]),
            {"decision": "accept"},
            format="json",
            headers={"X-Character-ID": str(self.hobb.pk)},
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        return accepted.data["result"]

    def test_thread_on_technique_skill_is_in_the_flirt(self) -> None:
        thread = self.thread_on(self.skill.trait)

        result = self.flirt_with_a_pull_on(thread)

        self.assertIsNone(result["fizzle_note"])
        self.assertEqual(self.balance(), 9)

    def test_thread_on_the_flirts_own_stat_is_still_in_the_flirt(self) -> None:
        stat = self.flirt.check_type.traits.first().trait
        thread = self.thread_on(stat)

        result = self.flirt_with_a_pull_on(thread)

        self.assertIsNone(result["fizzle_note"])
        self.assertEqual(self.balance(), 9)

    def test_thread_on_a_skill_the_flirt_does_not_roll_fizzles(self) -> None:
        thread = self.thread_on(SkillFactory().trait)

        result = self.flirt_with_a_pull_on(thread)

        self.assertEqual(result["fizzle_note"], "Thread anchor is not involved in this action.")
        self.assertEqual(self.balance(), 10)


class FightingWithATechniqueSkill(JourneyCase):
    """Ysmay declares a Path technique in a combat round; the round's roll carries the skill."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.skill = SkillFactory()
        self.path = PathFactory(technique_skill=self.skill)
        self.yard = self.make_room("The Yard")

        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        self.ysmay = self.make_player("Ysmay", room=self.yard)
        sheet = self.ysmay.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterTraitValue.objects.create(
            character=sheet, trait=self.skill.trait, value=SKILL_VALUE
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_combat_round_cast_adds_path_technique_skill(self) -> None:
        WeeklySkillUsage.flush_instance_cache()
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.ysmay,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.opponent.pk,
            },
        )
        self.assertTrue(declared.deferred)

        rolls: list[dict] = []

        def spy(character, check_type, *args, **kwargs) -> CheckResult:
            rolls.append({"character": character, "check_type": check_type, **kwargs})
            return perform_check(character, check_type, *args, **kwargs)

        with patch("world.combat.services.perform_check", side_effect=spy):
            resolve_round(self.encounter)

        term = ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("1.00"))
        casts = [
            roll
            for roll in rolls
            if roll["character"] == self.ysmay and roll.get("effort_level") == EffortLevel.MEDIUM
        ]
        self.assertEqual(len(casts), 1)
        self.assertEqual(casts[0]["check_type"], self.technique.action_template.check_type)
        self.assertEqual(tuple(casts[0]["extra_traits"]), (term,))
        usage = WeeklySkillUsage.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.skill.trait
        )
        self.assertEqual(usage.check_count, 1)


class ResistingLossOfSelf(JourneyCase):
    """Ysmay fights off a hold; staff mapped a skill to resisting loss of self (#4450).

    The skill joins her roll only when the hold's category is marked as a loss of self
    (corruption, atavism, possession). The same skill is mapped either way.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.skill = SkillFactory()
        MagicActivitySkillFactory(
            activity=MagicActivity.RESISTING_LOSS_OF_SELF, skill=self.skill, weight=Decimal("0.50")
        )
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)

    def hold_on_ysmay(self, *, loss_of_self: bool):
        category = ConditionCategoryFactory(
            name="Corruption" if loss_of_self else "Charm",
            alters_behavior=True,
            adds_loss_of_self_skills=loss_of_self,
        )
        template = ConditionTemplateFactory(
            category=category,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(),
            break_free_difficulty=10,
        )
        return ConditionInstanceFactory(target=self.ysmay, condition=template, is_aware=True)

    def roll_after(self, character, line: str) -> CheckCapture:
        """What the roll behind ``line`` was made with; fails when no roll happened."""
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as capture:
            self.telnet(character, line)
        self.assertIsNotNone(capture.check_type, f"{line!r} made no roll")
        return capture

    def test_breaking_free_of_corruption_adds_the_skill(self) -> None:
        self.hold_on_ysmay(loss_of_self=True)

        capture = self.roll_after(self.ysmay, "breakfree")

        self.assertEqual(
            capture.extra_traits, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("0.50")),)
        )

    def test_a_friends_rally_adds_nothing_of_his_own(self) -> None:
        """The rally roll is Hobb's persuasion; Ysmay's skill joins only her own break-free."""
        hold = self.hold_on_ysmay(loss_of_self=True)

        capture = self.roll_after(self.hobb, "rally Ysmay")

        self.assertEqual(capture.check_type, hold.condition.break_free_check_type)
        self.assertEqual(capture.extra_traits, ())

    def test_breaking_free_of_an_ordinary_hold_adds_nothing(self) -> None:
        hold = self.hold_on_ysmay(loss_of_self=False)

        capture = self.roll_after(self.ysmay, "breakfree")

        self.assertEqual(capture.check_type, hold.condition.break_free_check_type)
        self.assertEqual(capture.extra_traits, ())

    def test_resist_corruption_adds_loss_of_self_skill(self) -> None:
        """The roll made when a corrupting condition is applied carries the skill."""
        category = ConditionCategoryFactory(name="Atavism", adds_loss_of_self_skills=True)
        template = ConditionTemplateFactory(
            category=category, resist_check_type=CheckTypeFactory(), resist_difficulty=10
        )
        success = CheckOutcome.objects.get(name="Success")

        with force_check_outcome(success) as capture:
            apply_condition(self.ysmay, template)

        self.assertEqual(
            capture.extra_traits,
            (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("0.50")),),
        )


class SizingUpAStandoffWithTechniques(JourneyCase):
    """Ysmay faces road bandits in a standoff and knows two techniques (#4450).

    A casting approach is pressed with a technique, and each technique can carry its own
    skill, so ``standoff`` grades the approach once per technique she knows. A plain
    approach keeps its one line.
    """

    def setUp(self) -> None:
        super().setUp()
        road = self.make_room("The Old Road")
        self.ysmay = self.make_player("Ysmay", room=road)
        encounter = CombatEncounterFactory(room=road)
        CombatParticipantFactory(encounter=encounter, character_sheet=self.ysmay.sheet_data)
        CombatOpponentFactory(
            encounter=encounter, creature_template=CreatureTemplateFactory(name="Road Bandits")
        )
        open_standoff(encounter)
        StandoffApproachFactory(name="Hard Stare")
        StandoffApproachFactory(name="Show of Power", casts_technique=True)
        for name in ("Thunderclap", "Gale"):
            CharacterTechniqueFactory(
                character=self.ysmay.sheet_data, technique=TechniqueFactory(name=name)
            )

    def test_the_summary_grades_a_casting_approach_per_technique(self) -> None:
        told = self.telnet(self.ysmay, "standoff")

        self.assertIn("Road Bandits", told)
        self.assertRegex(told, r"press Show of Power with Thunderclap: \w+")
        self.assertRegex(told, r"press Show of Power with Gale: \w+")
        self.assertNotRegex(told, r"press Show of Power: ")
        self.assertRegex(told, r"press Hard Stare: \w+")


@override_settings(SEED_SAMPLE_CONTENT=True)
class BindingASummonedCompanion(JourneyCase):
    """Ysmay binds a creature she summoned; staff mapped a skill to companion binding (#4477).

    The web ``promote_summon`` action rolls the Bind Attempt check. The mapped skill joins
    that roll, and a binding with no mapped skill rolls without one.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.skill = SkillFactory()
        self.room = self.make_room("The Menagerie")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        sheet = self.ysmay.sheet_data
        self.gift = ensure_companion_content()
        grant_gift_to_character(sheet, self.gift, resonance=self.gift.resonances.first())
        thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift)
        thread.level = 10
        thread.save(update_fields=["level"])
        self.archetype = CompanionArchetypeFactory(bind_difficulty=20, capacity_cost=5)
        self.summon = CombatOpponentFactory(
            encounter=CombatEncounterFactory(room=self.room), threat_pool=ThreatPoolFactory()
        )
        self.summon.allegiance = CombatAllegiance.ALLY
        self.summon.summoned_by = sheet
        self.summon.status = OpponentStatus.ACTIVE
        self.summon.save(update_fields=["allegiance", "summoned_by", "status"])

    def bind(self):
        """Ysmay binds the summon through the web action; returns the roll and the result."""
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as capture:
            dispatched = self.web(
                self.ysmay,
                "promote_summon",
                combat_opponent_id=self.summon.pk,
                archetype_id=self.archetype.pk,
                gift_id=self.gift.pk,
                name="Pell",
            )
        return capture, dispatched.detail

    def test_the_mapped_skill_joins_the_bind_roll(self) -> None:
        MagicActivitySkillFactory(
            activity=MagicActivity.COMPANION_BINDING, skill=self.skill, weight=Decimal("0.50")
        )

        capture, result = self.bind()

        self.assertTrue(result.success, result.message)
        self.assertEqual(capture.check_type.name, BIND_ATTEMPT_CHECK_NAME)
        self.assertEqual(
            capture.extra_traits, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("0.50")),)
        )

    def test_an_unmapped_binding_rolls_without_a_skill(self) -> None:
        capture, result = self.bind()

        self.assertTrue(result.success, result.message)
        self.assertEqual(capture.extra_traits, ())


@override_settings(SEED_SAMPLE_CONTENT=True)
class SurvivingADreamsPeril(JourneyCase):
    """A dreamer collapses and resists the dream's peril; staff mapped a skill to it (#4477).

    ``resolve_dream_peril_collapse`` runs with the check engine unpatched; the forced outcome
    only fixes the die, and the capture reads back what the roll was made with.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.skill = SkillFactory()
        seed_survivability_content()
        ensure_dream_conditions()
        create_dream_peril_pool()
        config = get_dream_peril_config()
        config.resist_check_type = CheckTypeFactory()
        config.save(update_fields=["resist_check_type"])
        self.dreamer = self.make_player("Ysmay", room=self.make_room("The Dreamside"))

    def collapse(self) -> CheckCapture:
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as capture:
            resolve_dream_peril_collapse(self.dreamer.sheet_data)
        self.assertIsNotNone(capture.check_type, "the collapse made no resist roll")
        return capture

    def test_the_mapped_skill_joins_the_resist_roll(self) -> None:
        MagicActivitySkillFactory(
            activity=MagicActivity.DREAM_PERIL, skill=self.skill, weight=Decimal("0.50")
        )

        capture = self.collapse()

        self.assertEqual(
            capture.extra_traits, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("0.50")),)
        )

    def test_an_unmapped_peril_rolls_without_a_skill(self) -> None:
        self.assertEqual(self.collapse().extra_traits, ())


class AnEnhancedActionsConditionEffect(JourneyCase):
    """An action enhanced by a technique fires a remove-condition effect; its roll is read back.

    The effects registry dispatches the enhancement's config (the path ``restore_sense``
    takes) with the check engine unpatched; the forced outcome only fixes the die.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.skill = SkillFactory()
        room = self.make_room("The Quiet Room")
        self.ysmay = self.make_player("Ysmay", room=room)
        self.hobb = self.make_player("Hobb", room=room)

    def fire(self, enhancement: ActionEnhancement) -> CheckCapture:
        RemoveConditionOnCheckConfig.objects.create(
            enhancement=enhancement,
            check_type=CheckTypeFactory(),
            condition=ConditionTemplateFactory(),
            target_difficulty=10,
        )
        context = ActionContext(
            action=get_action("restore_sense"),
            actor=self.ysmay,
            target=self.hobb,
            kwargs={},
            scene_data=SceneDataManager(),
        )
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as capture:
            apply_effects(enhancement, context)
        self.assertIsNotNone(capture.check_type, "the effect made no roll")
        return capture

    def test_a_technique_source_adds_its_skill(self) -> None:
        enhancement = ActionEnhancementFactory(technique=TechniqueFactory(skill=self.skill))

        capture = self.fire(enhancement)

        self.assertEqual(
            capture.extra_traits, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("1.00")),)
        )

    def test_a_condition_source_adds_nothing(self) -> None:
        enhancement = ActionEnhancementFactory(
            source_type=EnhancementSourceType.CONDITION,
            technique=None,
            condition=ConditionTemplateFactory(),
        )

        self.assertEqual(self.fire(enhancement).extra_traits, ())
