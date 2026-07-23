"""Tests for the missions leaf-resolver registry.

Each resolver tests one slice of the acting character's *own durable state*.
Tests build real factory objects (never mock the ORM) and exercise the
resolver both through the registry/``CharacterPredicateContext`` and through
the full ``evaluate`` rule tree, so the structural layer and the leaf layer
are verified together.

Phase C added persona-aware resolvers (``is_member_of_org``,
``min_org_reputation``, ``min_society_standing``) that consult
``ctx.presented_persona``. The earlier stub-seal on ``min_society_standing``
was removed in C8 — it's now a real resolver mirroring ``min_org_reputation``
against SocietyReputation. Persona-aware tests use ``sheet.primary_persona``
(auto-created by CharacterSheetFactory; the model has a partial unique
constraint enforcing one PRIMARY per sheet).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory, ThreadFactory
from world.missions.constants import MissionStatus
from world.missions.factories import MissionInstanceFactory, MissionTemplateFactory
from world.npc_services.factories import NPCStandingFactory
from world.predicates.predicates import CharacterPredicateContext, evaluate
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationFactory,
    SocietyFactory,
    SocietyReputationFactory,
)


class DistinctionAchievementResolverTests(TestCase):
    """has_distinction (ObjectDB-keyed) and has_achievement (sheet-keyed)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.distinction = DistinctionFactory(slug="brave")
        CharacterDistinctionFactory(character=cls.sheet, distinction=cls.distinction)
        cls.achievement = AchievementFactory(slug="first-blood")
        CharacterAchievementFactory(
            character_sheet=cls.sheet,
            achievement=cls.achievement,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_has_distinction_true_when_owned(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_distinction", slug="brave"))

    def test_has_distinction_false_when_not_owned(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_distinction", slug="craven"))

    def test_has_achievement_true_when_earned(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_achievement", slug="first-blood"))

    def test_has_achievement_false_when_not_earned(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_achievement", slug="last-stand"))

    def test_evaluate_composes_distinction_and_achievement(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "has_distinction", "params": {"slug": "brave"}},
                {"leaf": "has_achievement", "params": {"slug": "first-blood"}},
            ],
        }
        self.assertIs(evaluate(rule, self.ctx), True)

        missing = {
            "op": "AND",
            "of": [
                {"leaf": "has_distinction", "params": {"slug": "brave"}},
                {"leaf": "has_achievement", "params": {"slug": "nope"}},
            ],
        }
        self.assertIs(evaluate(missing, self.ctx), False)


class ConditionCapabilityResolverTests(TestCase):
    """has_condition (ObjectDB-keyed instance) and has_capability (>0 value)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.condition = ConditionTemplateFactory(name="Blessed")
        ConditionInstanceFactory(target=cls.character, condition=cls.condition)

        # A capability granted (positive value) by an active condition.
        cls.capability = CapabilityTypeFactory(name="nightvision")
        cls.cap_condition = ConditionTemplateFactory(name="Owl Sight")
        ConditionCapabilityEffectFactory(
            condition=cls.cap_condition,
            capability=cls.capability,
            value=10,
        )
        ConditionInstanceFactory(target=cls.character, condition=cls.cap_condition)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_has_condition_true_when_present(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_condition", key="Blessed"))

    def test_has_condition_false_when_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_condition", key="Cursed"))

    def test_has_condition_false_when_suppressed(self) -> None:
        """A suppressed ConditionInstance row exists but must not gate True."""
        from datetime import timedelta

        from django.utils import timezone

        suppressed_template = ConditionTemplateFactory(name="Hexed")
        ConditionInstanceFactory(
            target=self.character,
            condition=suppressed_template,
            is_suppressed=True,
            suppressed_until=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(self.ctx.has_leaf("has_condition", key="Hexed"))

    def test_has_capability_true_when_granted(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_capability", name="nightvision"))

    def test_has_capability_false_when_unknown(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_capability", name="flight"))

    def test_has_capability_true_from_non_condition_source(self) -> None:
        """#1010: a capability possessed via a non-condition source (here an
        innate baseline; also covers distinction/equipment/role-passive grants)
        satisfies has_capability via the effective read, not just conditions."""
        CapabilityTypeFactory(name="winged", innate_baseline=1)
        self.assertTrue(self.ctx.has_leaf("has_capability", name="winged"))


class ThreadResolverTests(TestCase):
    """has_thread / min_thread_level — owner is a CharacterSheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.thread = ThreadFactory(owner=cls.sheet, level=30)

        cls.other = CharacterFactory()
        cls.other_sheet = CharacterSheetFactory(character=cls.other)

    def test_has_thread_true_when_owner_has_one(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertTrue(ctx.has_leaf("has_thread"))

    def test_has_thread_false_when_none(self) -> None:
        ctx = CharacterPredicateContext(self.other)
        self.assertFalse(ctx.has_leaf("has_thread"))

    def test_min_thread_level_true_when_met(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertTrue(ctx.has_leaf("min_thread_level", level=30))
        self.assertTrue(ctx.has_leaf("min_thread_level", level=20))

    def test_min_thread_level_false_when_below(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("min_thread_level", level=40))


class TraitResolverTests(TestCase):
    """min_trait / has_skill — CharacterTraitValue keyed by ObjectDB."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.traits.factories import (
            CharacterTraitValueFactory,
            SkillTraitFactory,
            StatTraitFactory,
        )

        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.strength = StatTraitFactory(name="strength")
        CharacterTraitValueFactory(
            character=cls.character.sheet_data,
            trait=cls.strength,
            value=45,
        )
        cls.sewing = SkillTraitFactory(name="sewing")
        CharacterTraitValueFactory(
            character=cls.character.sheet_data,
            trait=cls.sewing,
            value=20,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_min_trait_true_when_met(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_trait", trait="strength", value=45))
        self.assertTrue(self.ctx.has_leaf("min_trait", trait="strength", value=10))

    def test_min_trait_false_when_below_or_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_trait", trait="strength", value=46))
        self.assertFalse(self.ctx.has_leaf("min_trait", trait="charm", value=1))

    def test_has_skill_true_when_present(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_skill", skill="sewing"))

    def test_has_skill_false_when_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_skill", skill="smithing"))


class CharacterLevelResolverTests(TestCase):
    """min_character_level: gates on CharacterSheet.current_level."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        # Two class assignments — current_level = max() = 7
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=cls.character.sheet_data, character_class=char_class, level=3
        )
        CharacterClassLevelFactory(
            character=cls.character.sheet_data,
            character_class=CharacterClassFactory(),
            level=7,
        )
        cls.sheet.invalidate_class_level_cache()

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_at_threshold(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_character_level", level=7))

    def test_true_when_above_threshold(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_character_level", level=3))

    def test_false_when_below_threshold(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_character_level", level=8))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "min_character_level", "params": {"level": 5}}
        self.assertTrue(evaluate(rule, self.ctx))
        rule_fail = {"leaf": "min_character_level", "params": {"level": 10}}
        self.assertFalse(evaluate(rule_fail, self.ctx))

    def test_zero_level_character_passes_zero_threshold(self) -> None:
        # Fresh character with no class assignments: current_level == 0.
        bare = CharacterFactory()
        CharacterSheetFactory(character=bare)
        ctx = CharacterPredicateContext(bare)
        self.assertTrue(ctx.has_leaf("min_character_level", level=0))
        self.assertFalse(ctx.has_leaf("min_character_level", level=1))


class CodexEntryResolverTests(TestCase):
    """has_codex_entry: gates on CharacterCodexKnowledge (KNOWN) for the entry.

    Authored params: ``subject`` (CodexSubject.name) + ``name`` (CodexEntry.name).
    CodexEntry uses ``unique_together = ["subject", "name"]`` so neither alone
    is a stable identifier.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.subject = CodexSubjectFactory(name="Test Subject")
        cls.known_entry = CodexEntryFactory(subject=cls.subject, name="Known Thing")
        cls.uncovered_entry = CodexEntryFactory(subject=cls.subject, name="Uncovered Thing")
        CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.known_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.uncovered_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_known(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Known Thing")
        )

    def test_false_when_uncovered(self) -> None:
        # UNCOVERED means seen-but-not-fully-learned; the predicate gates on
        # KNOWN — the character HAS the entry, not just has heard of it.
        self.assertFalse(
            self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Uncovered Thing")
        )

    def test_false_when_no_knowledge_row(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Nope"))

    def test_false_when_no_such_entry(self) -> None:
        self.assertFalse(
            self.ctx.has_leaf("has_codex_entry", subject="No Such Subject", name="Whatever")
        )

    def test_evaluate_dispatches(self) -> None:
        rule = {
            "leaf": "has_codex_entry",
            "params": {"subject": "Test Subject", "name": "Known Thing"},
        }
        self.assertTrue(evaluate(rule, self.ctx))


class ResonanceResolverTests(TestCase):
    """has_resonance: a CharacterResonance row for (sheet, resonance) exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.held = ResonanceFactory(name="Sylva")
        cls.unheld = ResonanceFactory(name="Praedari")
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.held)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_held(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_resonance", name="Sylva"))

    def test_false_when_not_held(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_resonance", name="Praedari"))

    def test_false_when_no_such_resonance(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_resonance", name="Nonexistent"))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "has_resonance", "params": {"name": "Sylva"}}
        self.assertTrue(evaluate(rule, self.ctx))


class NPCStandingResolverTests(TestCase):
    """min_npc_standing: gates on NPCStanding.affection for an NPC persona.

    The NPC is referenced by Persona PK (NPCStanding is keyed on personas
    after the unified-framework refactor). Comparison is affection >= ``min``.
    No standing row means affection is implicitly 0. The PC side uses
    ``ctx.presented_persona``; None presented persona fails closed
    (consistent with other persona-aware leaves).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.pc_persona = cls.sheet.primary_persona
        cls.liked_npc = PersonaFactory()
        cls.disliked_npc = PersonaFactory()
        cls.unknown_npc = PersonaFactory()
        NPCStandingFactory(persona=cls.pc_persona, npc_persona=cls.liked_npc, affection=50)
        NPCStandingFactory(persona=cls.pc_persona, npc_persona=cls.disliked_npc, affection=-20)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)

    def test_true_when_at_threshold(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.liked_npc.pk, min_affection=50
            )
        )

    def test_true_when_above_threshold(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.liked_npc.pk, min_affection=10
            )
        )

    def test_false_when_below_threshold(self) -> None:
        self.assertFalse(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.liked_npc.pk, min_affection=51
            )
        )

    def test_negative_affection_below_zero_threshold(self) -> None:
        # disliked: affection=-20; threshold 0 must FAIL.
        self.assertFalse(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.disliked_npc.pk, min_affection=0
            )
        )

    def test_no_standing_row_means_zero_affection(self) -> None:
        # No standing row exists for unknown_npc/pc_persona → affection=0.
        self.assertTrue(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.unknown_npc.pk, min_affection=0
            )
        )
        self.assertFalse(
            self.ctx.has_leaf(
                "min_npc_standing", npc_persona_id=self.unknown_npc.pk, min_affection=1
            )
        )

    def test_false_when_no_such_npc_persona(self) -> None:
        # Bogus PK — the predicate fails closed rather than raising.
        self.assertFalse(
            self.ctx.has_leaf("min_npc_standing", npc_persona_id=999999, min_affection=0)
        )

    def test_false_when_no_presented_persona(self) -> None:
        # PC has no presented persona — fail closed (TEMPORARY masks can't hold standing).
        ctx_no_persona = CharacterPredicateContext(self.character)
        self.assertFalse(
            ctx_no_persona.has_leaf(
                "min_npc_standing", npc_persona_id=self.liked_npc.pk, min_affection=0
            )
        )

    def test_evaluate_dispatches(self) -> None:
        rule = {
            "leaf": "min_npc_standing",
            "params": {"npc_persona_id": self.liked_npc.pk, "min_affection": 50},
        }
        self.assertTrue(evaluate(rule, self.ctx))


class OrgMembershipResolverTests(TestCase):
    """is_member_of_org: gates on the presented persona's membership in the org.

    Persona-aware — checks ``ctx.presented_persona``, not character's primary
    persona. Per societies CLAUDE.md, only PRIMARY/ESTABLISHED personas can
    hold memberships, so a TEMPORARY mask correctly fails (no membership row
    can exist for it). When ``presented_persona`` is None, the gate also
    fails (no persona to check).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        # CharacterSheetFactory auto-creates the PRIMARY persona (partial
        # unique constraint enforces one PRIMARY per sheet).
        cls.primary = cls.sheet.primary_persona
        cls.established = PersonaFactory(
            character_sheet=cls.sheet, persona_type=PersonaType.ESTABLISHED
        )
        cls.temporary = PersonaFactory(
            character_sheet=cls.sheet, persona_type=PersonaType.TEMPORARY
        )
        cls.guild = OrganizationFactory(name="Guild of Knives")
        # PRIMARY persona is a member of the guild.
        OrganizationMembershipFactory(persona=cls.primary, organization=cls.guild)

    def test_true_when_presented_primary_is_member(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertTrue(ctx.has_leaf("is_member_of_org", org="Guild of Knives"))

    def test_false_when_presented_established_is_not_member(self) -> None:
        # Different persona, same character, no membership row.
        ctx = CharacterPredicateContext(self.character, presented_persona=self.established)
        self.assertFalse(ctx.has_leaf("is_member_of_org", org="Guild of Knives"))

    def test_false_when_presented_temporary_mask(self) -> None:
        # TEMPORARY masks can't hold memberships at all → always fails.
        ctx = CharacterPredicateContext(self.character, presented_persona=self.temporary)
        self.assertFalse(ctx.has_leaf("is_member_of_org", org="Guild of Knives"))

    def test_false_when_no_presented_persona(self) -> None:
        # No persona context → fail closed.
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("is_member_of_org", org="Guild of Knives"))

    def test_false_when_no_such_org(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertFalse(ctx.has_leaf("is_member_of_org", org="Phantom Guild"))


class OrgReputationResolverTests(TestCase):
    """min_org_reputation: presented persona's reputation tier with the org meets threshold.

    Tier ordering (low → high): REVILED, DESPISED, DISLIKED, DISFAVORED,
    UNKNOWN, FAVORED, LIKED, HONORED, REVERED. The gate passes when the
    presented persona's current tier is >= the authored threshold.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.primary = cls.sheet.primary_persona
        cls.guild = OrganizationFactory(name="Honored Order")
        # Primary persona has reputation value 600 → HONORED tier.
        OrganizationReputationFactory(persona=cls.primary, organization=cls.guild, value=600)

    def test_true_when_tier_at_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        # HONORED (600) >= HONORED.
        self.assertTrue(ctx.has_leaf("min_org_reputation", org="Honored Order", tier="honored"))

    def test_true_when_tier_above_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        # HONORED >= FAVORED.
        self.assertTrue(ctx.has_leaf("min_org_reputation", org="Honored Order", tier="favored"))

    def test_false_when_tier_below_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        # HONORED < REVERED.
        self.assertFalse(ctx.has_leaf("min_org_reputation", org="Honored Order", tier="revered"))

    def test_false_when_no_reputation_row(self) -> None:
        other_org = OrganizationFactory(name="Unknown Order")
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        # No row → fail closed for any tier above UNKNOWN.
        self.assertFalse(ctx.has_leaf("min_org_reputation", org="Unknown Order", tier="favored"))
        # Even UNKNOWN tier — no row means we can't claim the standing.
        self.assertFalse(ctx.has_leaf("min_org_reputation", org="Unknown Order", tier="unknown"))
        _ = other_org  # silence unused

    def test_false_when_no_presented_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("min_org_reputation", org="Honored Order", tier="favored"))

    def test_false_when_no_such_org(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertFalse(ctx.has_leaf("min_org_reputation", org="Nonexistent", tier="favored"))

    def test_invalid_tier_raises(self) -> None:
        # Authoring error: unknown tier string → KeyError. Predicates fail
        # closed on data, but bad authoring should surface loudly.
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        with self.assertRaises(KeyError):
            ctx.has_leaf("min_org_reputation", org="Honored Order", tier="bogus")


class PresentedPersonaContextTests(TestCase):
    """C5 refactor: CharacterPredicateContext carries presented_persona.

    Verifies the ResolverContext plumbing — resolvers receive the persona
    the offering surface specified. Non-persona resolvers ignore it
    (covered by every C1-C4 test, which passes None implicitly).
    Persona-aware resolvers (C6-C8) consume it.
    """

    def test_default_persona_is_none(self) -> None:
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        ctx = CharacterPredicateContext(character)
        self.assertIsNone(ctx.presented_persona)

    def test_persona_passes_through_to_resolver(self) -> None:
        # Asserts the context attribute is settable + readable. The
        # ResolverContext dataclass freezes it at dispatch time.
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        # Use the auto-created PRIMARY (one-per-sheet constraint).
        persona = sheet.primary_persona
        ctx = CharacterPredicateContext(character, presented_persona=persona)
        self.assertIs(ctx.presented_persona, persona)


class SocietyStandingResolverTests(TestCase):
    """min_society_standing: presented persona's tier with the society is >= threshold.

    Mirror of OrgReputationResolverTests against SocietyReputation. Replaces
    the Phase-0 stub-seal (was raising NotImplementedError pending design).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.primary = cls.sheet.primary_persona
        cls.society = SocietyFactory(name="Glorious Society")
        SocietyReputationFactory(persona=cls.primary, society=cls.society, value=300)  # LIKED tier

    def test_true_when_at_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertTrue(
            ctx.has_leaf("min_society_standing", society="Glorious Society", tier="liked")
        )

    def test_true_when_above_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertTrue(
            ctx.has_leaf("min_society_standing", society="Glorious Society", tier="favored")
        )

    def test_false_when_below_threshold(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        # LIKED < HONORED.
        self.assertFalse(
            ctx.has_leaf("min_society_standing", society="Glorious Society", tier="honored")
        )

    def test_false_when_no_presented_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(
            ctx.has_leaf("min_society_standing", society="Glorious Society", tier="favored")
        )

    def test_false_when_no_reputation_row(self) -> None:
        other = SocietyFactory(name="Unknown Society")
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        self.assertFalse(
            ctx.has_leaf("min_society_standing", society="Unknown Society", tier="favored")
        )
        _ = other

    def test_invalid_tier_raises(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)
        with self.assertRaises(KeyError):
            ctx.has_leaf("min_society_standing", society="Glorious Society", tier="bogus")


class OrgRankResolverTests(TestCase):
    """min_org_rank (#870): presented persona holds at least ``rank`` in the org.

    ``OrganizationMembership.rank`` is 1=leader … 5=lowest, so "at least
    rank N" means ``membership.rank <= N``. Distinct from
    ``min_org_reputation`` (reputation tier, not membership rank).
    Persona-aware + fail-closed like the other membership leaves.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.primary = cls.sheet.primary_persona
        cls.guild = OrganizationFactory(name="Rank Guild")
        OrganizationMembershipFactory(persona=cls.primary, organization=cls.guild, rank=3)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)

    def test_true_at_exact_rank(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_org_rank", org="Rank Guild", rank=3))

    def test_true_when_threshold_is_lower_in_hierarchy(self) -> None:
        # Rank 3 satisfies "at least rank 5" (5 = lowest).
        self.assertTrue(self.ctx.has_leaf("min_org_rank", org="Rank Guild", rank=5))

    def test_false_when_threshold_is_higher_in_hierarchy(self) -> None:
        # Rank 3 does NOT satisfy "at least rank 2" (closer to leader).
        self.assertFalse(self.ctx.has_leaf("min_org_rank", org="Rank Guild", rank=2))

    def test_false_when_not_a_member(self) -> None:
        OrganizationFactory(name="Other Guild")
        self.assertFalse(self.ctx.has_leaf("min_org_rank", org="Other Guild", rank=5))

    def test_false_when_no_such_org(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_org_rank", org="Phantom Guild", rank=5))

    def test_false_when_no_presented_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("min_org_rank", org="Rank Guild", rank=5))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "min_org_rank", "params": {"org": "Rank Guild", "rank": 3}}
        self.assertTrue(evaluate(rule, self.ctx))


class ResonanceLevelResolverTests(TestCase):
    """min_resonance_level (#870): lifetime_earned for the named resonance >= amount.

    Gates on the monotonic ``lifetime_earned`` total, NOT the spendable
    ``balance`` — spending resonance currency must never revoke earned
    eligibility. Distinct from ``has_resonance`` (bare row existence).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.resonance = ResonanceFactory(name="Umbra")
        # Spent down to 2 spendable, but 10 earned over the lifetime.
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=2,
            lifetime_earned=10,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_at_exact_amount(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_resonance_level", resonance="Umbra", amount=10))

    def test_true_below_lifetime_even_though_balance_is_spent(self) -> None:
        # balance is 2, but the gate reads lifetime_earned (10) — spending
        # must not revoke eligibility.
        self.assertTrue(self.ctx.has_leaf("min_resonance_level", resonance="Umbra", amount=5))

    def test_false_above_lifetime(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_resonance_level", resonance="Umbra", amount=11))

    def test_false_when_no_row(self) -> None:
        ResonanceFactory(name="Lux")
        self.assertFalse(self.ctx.has_leaf("min_resonance_level", resonance="Lux", amount=1))

    def test_false_when_no_such_resonance(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_resonance_level", resonance="Nope", amount=1))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "min_resonance_level", "params": {"resonance": "Umbra", "amount": 10}}
        self.assertTrue(evaluate(rule, self.ctx))


class SocietyMembershipResolverTests(TestCase):
    """is_member_of_society (#870): presented persona belongs to ANY org in the society.

    First-class rather than an authored OR over ``is_member_of_org`` —
    org rosters change, and an enumerated rule silently rots when a new
    org joins the society. Persona-aware + fail-closed.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.primary = cls.sheet.primary_persona
        cls.society = SocietyFactory(name="Member Society")
        cls.org = OrganizationFactory(name="Society Org", society=cls.society)
        OrganizationMembershipFactory(persona=cls.primary, organization=cls.org)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character, presented_persona=self.primary)

    def test_true_when_member_of_an_org_in_society(self) -> None:
        self.assertTrue(self.ctx.has_leaf("is_member_of_society", society="Member Society"))

    def test_false_when_no_membership_in_society(self) -> None:
        other_society = SocietyFactory(name="Other Society")
        OrganizationFactory(name="Other Society Org", society=other_society)
        self.assertFalse(self.ctx.has_leaf("is_member_of_society", society="Other Society"))

    def test_false_when_no_such_society(self) -> None:
        self.assertFalse(self.ctx.has_leaf("is_member_of_society", society="Phantom Society"))

    def test_false_when_no_presented_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("is_member_of_society", society="Member Society"))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "is_member_of_society", "params": {"society": "Member Society"}}
        self.assertTrue(evaluate(rule, self.ctx))


class HasCompletedMissionResolverTests(TestCase):
    """has_completed_mission: gates on a COMPLETE MissionInstance of a template.

    Backs chained-mission unlocks (#726). Persona-scoped via
    ``MissionInstance.accepted_as_persona`` — an ESTABLISHED persona doesn't
    inherit a PRIMARY persona's history. Only ``MissionStatus.COMPLETE``
    satisfies (ACTIVE / ABANDONED don't). No presented persona fails closed;
    an unknown / not-yet-completed template fails closed naturally.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.pc_persona = cls.sheet.primary_persona
        cls.other_persona = PersonaFactory()
        cls.done_template = MissionTemplateFactory()
        cls.undone_template = MissionTemplateFactory()
        MissionInstanceFactory(
            template=cls.done_template,
            accepted_as_persona=cls.pc_persona,
            status=MissionStatus.COMPLETE,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character, presented_persona=self.pc_persona)

    def test_true_when_persona_completed_template(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf("has_completed_mission", template_id=self.done_template.pk)
        )

    def test_false_when_template_not_completed(self) -> None:
        self.assertFalse(
            self.ctx.has_leaf("has_completed_mission", template_id=self.undone_template.pk)
        )

    def test_false_when_completed_by_other_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character, presented_persona=self.other_persona)
        self.assertFalse(ctx.has_leaf("has_completed_mission", template_id=self.done_template.pk))

    def test_false_when_only_active(self) -> None:
        active_template = MissionTemplateFactory()
        MissionInstanceFactory(
            template=active_template,
            accepted_as_persona=self.pc_persona,
            status=MissionStatus.ACTIVE,
        )
        self.assertFalse(self.ctx.has_leaf("has_completed_mission", template_id=active_template.pk))

    def test_false_when_abandoned(self) -> None:
        abandoned_template = MissionTemplateFactory()
        MissionInstanceFactory(
            template=abandoned_template,
            accepted_as_persona=self.pc_persona,
            status=MissionStatus.ABANDONED,
        )
        self.assertFalse(
            self.ctx.has_leaf("has_completed_mission", template_id=abandoned_template.pk)
        )

    def test_false_when_no_presented_persona(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("has_completed_mission", template_id=self.done_template.pk))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "has_completed_mission", "params": {"template_id": self.done_template.pk}}
        self.assertTrue(evaluate(rule, self.ctx))
