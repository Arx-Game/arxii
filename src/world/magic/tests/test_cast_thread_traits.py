"""A cast's thread pulls see the traits the cast rolls (#4450).

A TRAIT thread is in a cast's action when its trait is one the roll uses: the check type's stat
and skill, and the technique skill the cast adds. Both the passive tier-0 list and a declared
paid pull read the same trait ids.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.types import ExtraTraitTerm
from world.classes.factories import PathFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.pull_helpers import commit_combat_pull
from world.magic.constants import GiftKind, RitualExecutionKind, TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.magic.models.rituals import Ritual
from world.magic.services.cast_threads import (
    applicable_threads_for_cast,
    build_cast_applicable_threads,
)
from world.magic.services.magic_skills import resolve_cast_check
from world.magic.services.techniques import _charge_cast_pull
from world.magic.types.magic_skills import CastCheck
from world.magic.types.pull import CastPullDeclaration
from world.progression.factories import CharacterPathHistoryFactory
from world.skills.factories import SkillFactory
from world.traits.factories import StatTraitFactory


class CastThreadTraitsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.stat = StatTraitFactory()
        cls.technique_skill = SkillFactory()
        cls.path = PathFactory(technique_skill=cls.technique_skill)
        CharacterPathHistoryFactory(character=cls.sheet, path=cls.path)
        cls.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.stat, weight=1)
        cls.technique = TechniqueFactory(
            gift=GiftFactory(kind=GiftKind.MAJOR),
            action_template=ActionTemplateFactory(check_type=cls.check_type),
        )

    def trait_thread(self, trait):
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=trait,
        )


class ApplicableOnCastTests(CastThreadTraitsBase):
    def test_trait_thread_on_technique_skill_applicable_on_cast(self):
        thread = self.trait_thread(self.technique_skill.trait)
        cast_check = resolve_cast_check(self.sheet.character, self.technique)

        result = applicable_threads_for_cast(
            self.sheet.character, self.technique, cast_check=cast_check
        )

        self.assertEqual([(a.thread.pk, a.pull_tier) for a in result], [(thread.pk, 0)])

    def test_trait_thread_on_personal_stat_applicable_on_cast(self):
        account = AccountDB.objects.create(username="cast_thread_traits_personal")
        ritual = Ritual.objects.create(
            name="cast_thread_traits_personal_ritual",
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        personal_stat = StatTraitFactory()
        config = RitualCheckConfigFactory(ritual=ritual)
        CheckTypeTraitFactory(check_type=config.check_type, trait=personal_stat, weight=1)
        self.sheet.character.db_account = account
        self.sheet.character.save(update_fields=["db_account"])
        thread = self.trait_thread(personal_stat)
        cast_check = resolve_cast_check(self.sheet.character, self.technique)
        self.assertEqual(cast_check.check_type, config.check_type)

        result = applicable_threads_for_cast(
            self.sheet.character, self.technique, cast_check=cast_check
        )

        self.assertEqual([(a.thread.pk, a.pull_tier) for a in result], [(thread.pk, 0)])

    def test_trait_thread_on_a_trait_the_cast_does_not_roll_is_left_out(self):
        self.trait_thread(StatTraitFactory())
        cast_check = resolve_cast_check(self.sheet.character, self.technique)

        result = applicable_threads_for_cast(
            self.sheet.character, self.technique, cast_check=cast_check
        )

        self.assertEqual(result, [])

    def test_without_a_cast_check_trait_threads_stay_out_of_the_cast(self):
        self.trait_thread(self.technique_skill.trait)

        self.assertEqual(build_cast_applicable_threads(self.sheet, self.technique), [])

    def test_declared_pull_on_technique_skill_thread_keeps_its_tier(self):
        thread = self.trait_thread(self.technique_skill.trait)
        pull = CastPullDeclaration(resonance=self.resonance, tier=2, threads=(thread,))
        cast_check = CastCheck(
            check_type=self.check_type,
            extra_traits=(ExtraTraitTerm(self.technique_skill.trait, Decimal("1.00")),),
        )

        result = build_cast_applicable_threads(
            self.sheet, self.technique, cast_pull=pull, cast_check=cast_check
        )

        self.assertEqual([(a.thread.pk, a.pull_tier) for a in result], [(thread.pk, 2)])


class PaidPullContextTests(CastThreadTraitsBase):
    def test_paid_pull_context_has_involved_traits(self):
        thread = self.trait_thread(self.technique_skill.trait)
        pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(thread,))

        with patch("world.magic.services.resonance.spend_resonance_for_pull") as spend:
            spend.return_value.resolved_effects = []
            _charge_cast_pull(
                character=self.sheet.character,
                technique=self.technique,
                cast_pull=pull,
                effective_power=5,
            )

        context = spend.call_args.args[4]
        self.assertEqual(
            set(context.involved_traits), {self.stat.pk, self.technique_skill.trait.pk}
        )
        self.assertEqual(context.involved_techniques, (self.technique.pk,))

    def test_combat_pull_context_has_involved_traits(self):
        thread = self.trait_thread(self.technique_skill.trait)
        pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(thread,))
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )

        with patch("world.magic.services.resonance.spend_resonance_for_pull") as spend:
            commit_combat_pull(pull, participant, encounter, self.technique.pk)

        context = spend.call_args.kwargs["action_context"]
        self.assertEqual(
            set(context.involved_traits), {self.stat.pk, self.technique_skill.trait.pk}
        )
