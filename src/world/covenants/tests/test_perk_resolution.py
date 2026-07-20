"""Tests for the situational-perk resolution service (#2536, Task 3).

Built in ``setUp`` rather than ``setUpTestData`` throughout — factories here
create Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), which
would break ``setUpTestData``'s deepcopy (same rationale as
``test_perk_evaluators.py``).
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkRungFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.covenants.perks.services import FiredPerk, applicable_perks
from world.magic.constants import TargetKind, TechniqueFunction
from world.magic.factories import (
    ResonanceFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    ThreadFactory,
)
from world.npc_services.factories import NPCStandingFactory
from world.scenes.factories import SceneFactory


class SelfPerkTests(TestCase):
    """A SELF-beneficiary perk fires for the holder's own action."""

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )

    def test_self_perk_fires_on_own_action(self) -> None:
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=15,
        )
        fired = applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=None,
            target=None,
        )
        self.assertEqual(
            fired,
            [
                FiredPerk(
                    perk=perk, holder=self.subject_sheet, magnitude_tenths=15, rung_number=None
                )
            ],
        )

    def test_wrong_effect_kind_does_not_fire(self) -> None:
        VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
        )
        fired = applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=None,
            target=None,
        )
        self.assertEqual(fired, [])

    def test_unengaged_role_grants_no_perks(self) -> None:
        VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        other_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=other_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=False,
        )
        fired = applicable_perks(
            other_sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )
        self.assertEqual(fired, [])


class BeneficiaryScopingTests(TestCase):
    """COVENANT_ALLIES/WHOLE_GROUP scoping across a co-present engaged group.

    Perks here carry NO attached situations (fire unconditionally once the
    beneficiary/role/group mechanics match) so these tests isolate the
    beneficiary-scoping logic from situation evaluation. Subject and mate
    hold DISTINCT roles (``subject_role`` vs ``role``) — subject needs SOME
    engaged role to establish the shared-covenant scope ``_ally_candidates``
    searches within, but must not incidentally hold the perk-bearing role
    itself, or it would legitimately show up as its OWN ally candidate too.
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        self.mate_sheet = CharacterSheetFactory()

        self.encounter = CombatEncounterFactory()
        self.subject_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        self.mate_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.mate_sheet
        )
        self.resolution = CombatRoundContext(self.subject_participant)

        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.subject_role,
            engaged=True,
        )

    def _mate_membership(self, *, engaged: bool) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.mate_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=engaged,
        )

    def _fire(self) -> list[FiredPerk]:
        return applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=self.resolution,
            target=None,
        )

    def test_covenant_allies_fires_on_mates_action_not_holders_own(self) -> None:
        self._mate_membership(engaged=True)
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        # Subject acting: mate's COVENANT_ALLIES perk fires (mate benefits subject).
        fired = self._fire()
        self.assertEqual([f.perk for f in fired], [perk])
        self.assertEqual(fired[0].holder, self.mate_sheet)

        # Mate acting on themselves: their own COVENANT_ALLIES perk does NOT fire.
        mate_resolution = CombatRoundContext(self.mate_participant)
        fired_for_mate = applicable_perks(
            self.mate_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=mate_resolution,
            target=None,
        )
        self.assertEqual(fired_for_mate, [])

    def test_whole_group_includes_the_holder(self) -> None:
        self._mate_membership(engaged=True)
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.WHOLE_GROUP,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        # Fires for the mate's own action (SELF/WHOLE_GROUP via the mate's own roles).
        mate_resolution = CombatRoundContext(self.mate_participant)
        fired_for_mate = applicable_perks(
            self.mate_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=mate_resolution,
            target=None,
        )
        self.assertEqual([f.perk for f in fired_for_mate], [perk])

        # Fires for the subject's action too (WHOLE_GROUP via the mate's role).
        fired_for_subject = self._fire()
        self.assertEqual([f.perk for f in fired_for_subject], [perk])
        self.assertEqual(fired_for_subject[0].holder, self.mate_sheet)

    def test_unengaged_mate_perk_does_not_fire(self) -> None:
        """The ruling: an unengaged covenant-mate is 'in civilian garb'."""
        self._mate_membership(engaged=False)
        VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        fired = self._fire()
        self.assertEqual(fired, [])


class SubRolePerkAddsTests(TestCase):
    """A resolved sub-role's perks ADD to the anchor role's perks."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory()
        self.parent_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.parent_role, resonance=self.resonance, unlock_thread_level=3
        )
        self.subject_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.parent_role,
            engaged=True,
        )

    def _qualify_subrole(self) -> None:
        character = self.subject_sheet.character
        ThreadFactory(
            owner=self.subject_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=3,
        )
        character.threads.invalidate()

    def test_subrole_perk_adds_to_anchor_perk(self) -> None:
        anchor_perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            name="Anchor Perk",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        subrole_perk = VowSituationalPerkFactory(
            covenant_role=self.sub_role,
            name="Subrole Perk",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        self._qualify_subrole()

        fired = applicable_perks(
            self.subject_sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )
        self.assertEqual({f.perk for f in fired}, {anchor_perk, subrole_perk})

    def test_without_qualifying_subrole_only_anchor_perk_fires(self) -> None:
        anchor_perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            name="Anchor Perk",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        VowSituationalPerkFactory(
            covenant_role=self.sub_role,
            name="Subrole Perk",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        fired = applicable_perks(
            self.subject_sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )
        self.assertEqual([f.perk for f in fired], [anchor_perk])


class AllySubRolePerkAddsTests(TestCase):
    """A covenant-mate's resolved sub-role perk ADDs to their anchor perk on
    the ally side too (#2536 review Critical fix) -- the flagship worked
    example: a Beguiler's level-3 Predari-resonance sub-role perk conveying
    COVENANT_ALLIES group bonuses. Mirrors ``SubRolePerkAddsTests`` (the SELF
    side) but resolves the SUB-ROLE on the MATE, not the subject.
    """

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory()
        self.parent_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.parent_role, resonance=self.resonance, unlock_thread_level=3
        )
        # Subject holds a DISTINCT role -- just enough to establish the
        # shared-covenant scope _ally_candidates searches within, without
        # incidentally holding the perk-bearing (parent/sub) role itself.
        self.subject_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        self.mate_sheet = CharacterSheetFactory()

        self.encounter = CombatEncounterFactory()
        self.subject_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        self.mate_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.mate_sheet
        )
        self.resolution = CombatRoundContext(self.subject_participant)

        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.subject_role,
            engaged=True,
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.mate_sheet,
            covenant=self.covenant,
            covenant_role=self.parent_role,
            engaged=True,
        )

    def _qualify_mate_subrole(self) -> None:
        ThreadFactory(
            owner=self.mate_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=3,
        )

    def _fire(self) -> list[FiredPerk]:
        return applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=self.resolution,
            target=None,
        )

    def test_ally_subrole_perk_adds_to_anchor_perk(self) -> None:
        anchor_perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            name="Anchor Ally Perk",
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        subrole_perk = VowSituationalPerkFactory(
            covenant_role=self.sub_role,
            name="Subrole Ally Perk",
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        self._qualify_mate_subrole()

        fired = self._fire()
        self.assertEqual({f.perk for f in fired}, {anchor_perk, subrole_perk})
        self.assertTrue(all(f.holder == self.mate_sheet for f in fired))

    def test_without_qualifying_mate_subrole_only_anchor_ally_perk_fires(self) -> None:
        anchor_perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            name="Anchor Ally Perk",
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        VowSituationalPerkFactory(
            covenant_role=self.sub_role,
            name="Subrole Ally Perk",
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        # No qualifying COVENANT_ROLE thread on the mate -- sub-role perk stays inert.
        fired = self._fire()
        self.assertEqual([f.perk for f in fired], [anchor_perk])


class AndCompositionAndRungLadderTests(TestCase):
    """AND-composed base situations + cumulative rung resolution (spec §2).

    Uses two independently-togglable DB-state situations for AND-composition
    (TARGET_FAVORABLY_DISPOSED, DURING_NEGOTIATION) and a third
    (TARGET_DISTRACTED) as the rung-2 extra, so every situation can be
    toggled without a combat setup.
    """

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="RungRoom", nohome=True)

        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        self.subject_sheet.character.location = self.room
        self.subject_sheet.character.save()
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )
        self.target_sheet = CharacterSheetFactory()

        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(
            technique=self.technique, function=TechniqueFunction.DISTRACTION
        )

        self.perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=10,
        )
        VowSituationalPerkSituationFactory(
            perk=self.perk, situation=Situation.TARGET_FAVORABLY_DISPOSED
        )
        self.rung1 = VowSituationalPerkRungFactory(
            perk=self.perk,
            rung_number=1,
            extra_situation=Situation.DURING_NEGOTIATION,
            magnitude_tenths=20,
        )
        self.rung2 = VowSituationalPerkRungFactory(
            perk=self.perk,
            rung_number=2,
            extra_situation=Situation.TARGET_DISTRACTED,
            magnitude_tenths=30,
        )

    def _favorable(self) -> None:
        NPCStandingFactory(
            persona=self.subject_sheet.primary_persona,
            npc_persona=self.target_sheet.primary_persona,
            affection=5,
        )

    def _negotiating(self) -> None:
        SceneFactory(location=self.room)

    def _distracted(self) -> None:
        ConditionInstanceFactory(
            target=self.target_sheet.character, source_technique=self.technique
        )

    def _fire(self) -> list[FiredPerk]:
        return applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=None,
            target=self.target_sheet,
        )

    def test_unmet_base_situation_does_not_fire(self) -> None:
        """AND-composition: base situation unmet -> no fire, even with rung extras met."""
        self._negotiating()
        self._distracted()
        # Deliberately NOT calling self._favorable() -- base situation unmet.
        self.assertEqual(self._fire(), [])

    def test_base_only(self) -> None:
        self._favorable()
        fired = self._fire()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].magnitude_tenths, 10)
        self.assertIsNone(fired[0].rung_number)

    def test_rung_one(self) -> None:
        self._favorable()
        self._negotiating()
        fired = self._fire()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].magnitude_tenths, 20)
        self.assertEqual(fired[0].rung_number, 1)

    def test_rung_two_requires_both_extras(self) -> None:
        self._favorable()
        self._negotiating()
        self._distracted()
        fired = self._fire()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].magnitude_tenths, 30)
        self.assertEqual(fired[0].rung_number, 2)

    def test_rung_two_extra_alone_falls_back_to_base(self) -> None:
        """Strictly cumulative: rung 2's extra alone (without rung 1's) -> base only."""
        self._favorable()
        self._distracted()
        # Deliberately NOT calling self._negotiating() -- rung 1's extra unmet.
        fired = self._fire()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].magnitude_tenths, 10)
        self.assertIsNone(fired[0].rung_number)


class PerkResolutionQueryBudgetTests(TestCase):
    """The candidate-perk fetch (perk + situations + rungs) never scales with
    perk count — regression coverage for #2536 Task 3's query-budget contract
    (mirrors ``test_perk_evaluators.AllyLowHealthQueryBudgetTests``).
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )

    def _add_perks(self, count: int) -> None:
        for i in range(count):
            perk = VowSituationalPerkFactory(
                covenant_role=self.role,
                name=f"Budget Perk {i}",
                beneficiary=PerkBeneficiary.SELF,
                effect_kind=PerkEffectKind.POWER_BONUS,
            )
            VowSituationalPerkSituationFactory(perk=perk, situation=Situation.DURING_NEGOTIATION)
            VowSituationalPerkRungFactory(
                perk=perk, rung_number=1, extra_situation=Situation.TARGET_DISTRACTED
            )

    def _count_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            applicable_perks(
                self.subject_sheet,
                effect_kind=PerkEffectKind.POWER_BONUS,
                resolution=None,
                target=None,
            )
        return len(ctx)

    #: Documented ceiling for the self-only candidate-perk fetch (module
    #: docstring's query-discipline section): 1 base query + 2 prefetches
    #: (situations, rungs), independent of perk count. No ally group is
    #: present in this shape (subject has no location/combat context), so
    #: ``_ally_candidates`` short-circuits before issuing any query.
    SELF_ONLY_QUERY_CEILING = 3

    def test_query_count_fixed_regardless_of_perk_count(self) -> None:
        # Warm caches first (covenant-roles handler, etc.) so both measurements
        # below start from the same warm state.
        applicable_perks(
            self.subject_sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )

        self._add_perks(2)
        count_with_two = self._count_queries()
        self.assertLessEqual(count_with_two, self.SELF_ONLY_QUERY_CEILING)

        self._add_perks(3)  # 5 perks total now, same role
        count_with_five = self._count_queries()

        self.assertEqual(count_with_two, count_with_five)
        self.assertLessEqual(count_with_five, self.SELF_ONLY_QUERY_CEILING)


class AllyMateCountQueryBudgetTests(TestCase):
    """The batched ally sub-role resolution (#2536 review Critical fix) never
    scales with MATE count -- only with role DIVERSITY among the group (see
    ``_ally_sub_role_candidates`` and the module docstring's query-discipline
    section). Every mate below shares the SAME anchor role, so the resolve
    cost stays at exactly one ``CovenantRole.matching_variant`` call
    regardless of how many mates hold it.
    """

    #: Documented ceiling for the full worst-case pipeline (module docstring):
    #: candidate-perk base query (1) + 2 prefetches since a matching perk
    #: exists (situations, rungs) + co-presence roster (1) + batched ally
    #: ``CharacterCovenantRole`` fetch (1) + batched ally ``Thread`` fetch
    #: (1) = 6. (Subject-side memberships/thread-resolve and the ally-side
    #: ``CovenantRole.matching_variant`` -> ``cached_sub_roles`` resolve are
    #: each warmed to 0 by the explicit warm-up call below -- see its
    #: docstring.)
    ALLY_QUERY_CEILING = 6

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory()
        self.parent_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        SubroleCovenantRoleFactory(
            parent_role=self.parent_role, resonance=self.resonance, unlock_thread_level=3
        )
        self.subject_role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.subject_sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.subject_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        self.resolution = CombatRoundContext(self.subject_participant)
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.subject_role,
            engaged=True,
        )
        # A matching perk so the candidate-perk fetch's 2 prefetch queries
        # (situations, rungs) are actually exercised -- the worst-case shape,
        # not the perkless floor.
        perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.DURING_NEGOTIATION)

    def _add_mates(self, count: int) -> None:
        for _ in range(count):
            mate_sheet = CharacterSheetFactory()
            CombatParticipantFactory(encounter=self.encounter, character_sheet=mate_sheet)
            CharacterCovenantRoleFactory(
                character_sheet=mate_sheet,
                covenant=self.covenant,
                covenant_role=self.parent_role,
                engaged=True,
            )
            ThreadFactory(
                owner=mate_sheet,
                resonance=self.resonance,
                target_kind=TargetKind.COVENANT_ROLE,
                target_covenant_role=self.parent_role,
                target_trait=None,
                level=3,
            )

    def _count_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            applicable_perks(
                self.subject_sheet,
                effect_kind=PerkEffectKind.POWER_BONUS,
                resolution=self.resolution,
                target=None,
            )
        return len(ctx)

    def test_query_count_fixed_regardless_of_mate_count(self) -> None:
        # Warm caches first, same rationale as PerkResolutionQueryBudgetTests
        # -- but INCLUDING one mate on the shared role/thread already present,
        # so the ally path itself runs once before either measurement below.
        # CovenantRole.matching_variant reads the role's cached_sub_roles
        # (a per-instance cached_property, not a per-call one); because
        # CovenantRole is a SharedMemoryModel, that ONE-TIME query is paid
        # against the SAME identity-mapped role instance regardless of which
        # mate triggers it first, so warming it here (rather than during
        # either measured call) keeps the two measurements comparable.
        self._add_mates(1)
        applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=self.resolution,
            target=None,
        )

        self._add_mates(1)  # 2 mates total
        count_with_two_mates = self._count_queries()
        self.assertLessEqual(count_with_two_mates, self.ALLY_QUERY_CEILING)

        self._add_mates(3)  # 5 mates total now, all on the SAME shared role
        count_with_five_mates = self._count_queries()

        self.assertEqual(count_with_two_mates, count_with_five_mates)
        self.assertLessEqual(count_with_five_mates, self.ALLY_QUERY_CEILING)
