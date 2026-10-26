"""Tests for the reusable vow-holder pieces lifted out of perk resolution (#4581).

``vow_holder_candidates`` is the same holder set ``applicable_perks`` walks (the
subject's own engaged roles plus co-present covenant-mates' roles), now carrying
each candidate's anchor role. ``vow_holder_thread_levels`` reads every
candidate's COVENANT_ROLE thread level in one query. ``SituationCheck`` is the
cached situation evaluator ``_PerkResolver`` delegates to.

Built in ``setUp`` rather than ``setUpTestData``: the factories create Evennia
``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same reason every
neighboring covenants test file gives.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.round_context import CombatRoundContext
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    engage_vow_with_thread,
)
from world.covenants.perks.constants import PerkBeneficiary
from world.covenants.perks.context import NO_PARAMS
from world.covenants.perks.services import (
    SituationCheck,
    VowHolderCandidate,
    vow_holder_candidates,
    vow_holder_thread_levels,
)
from world.magic.factories import ResonanceFactory

_SELF = frozenset({PerkBeneficiary.SELF, PerkBeneficiary.WHOLE_GROUP})
_ALLY = frozenset({PerkBeneficiary.COVENANT_ALLIES, PerkBeneficiary.WHOLE_GROUP})


class OwnVowCandidateTests(TestCase):
    """The subject's own engaged vows: anchor plus resolved sub-role."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.anchor = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.anchor, resonance=self.resonance, unlock_thread_level=3
        )
        self.sheet = CharacterSheetFactory()

    def test_own_engaged_vow_yields_anchor_and_resolved_sub_role(self) -> None:
        engage_vow_with_thread(
            self.sheet,
            self.anchor,
            covenant=self.covenant,
            thread_level=3,
            resonance=self.resonance,
        )
        candidates = vow_holder_candidates(self.sheet, None)
        self.assertTrue(all(isinstance(c, VowHolderCandidate) for c in candidates))
        self.assertEqual({c.role_id for c in candidates}, {self.anchor.pk, self.sub_role.pk})
        self.assertEqual({c.anchor_role_id for c in candidates}, {self.anchor.pk})
        self.assertTrue(all(c.beneficiaries == _SELF for c in candidates))
        self.assertTrue(all(c.holder == self.sheet for c in candidates))
        self.assertFalse(any(c.is_secondary for c in candidates))

    def test_a_secondary_vow_adds_its_anchor_only(self) -> None:
        engage_vow_with_thread(
            self.sheet,
            CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=3,
        )
        # A secondary anchor with a qualifying sub-role: depth stays primary-only.
        engage_vow_with_thread(
            self.sheet,
            self.anchor,
            covenant=self.covenant,
            thread_level=3,
            resonance=self.resonance,
            is_secondary=True,
        )
        candidates = vow_holder_candidates(self.sheet, None)
        secondary = [c for c in candidates if c.is_secondary]
        self.assertEqual([c.role_id for c in secondary], [self.anchor.pk])
        self.assertEqual(secondary[0].anchor_role_id, self.anchor.pk)
        self.assertNotIn(self.sub_role.pk, {c.role_id for c in candidates})

    def test_a_disengaged_subject_has_no_candidates(self) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.anchor,
            engaged=False,
        )
        self.sheet.character.covenant_roles.invalidate()
        self.assertEqual(vow_holder_candidates(self.sheet, None), [])

    def test_thread_levels_are_one_query(self) -> None:
        engage_vow_with_thread(
            self.sheet,
            self.anchor,
            covenant=self.covenant,
            thread_level=3,
            resonance=self.resonance,
        )
        candidates = vow_holder_candidates(self.sheet, None)
        with self.assertNumQueries(1):
            levels = vow_holder_thread_levels(candidates)
        # Stored levels: shown 3 is stored 30 (#4585).
        self.assertEqual(levels, {(self.sheet.pk, self.anchor.pk): 30})

    def test_no_candidates_reads_no_thread_levels(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(vow_holder_thread_levels([]), {})


class AllyCandidateTests(TestCase):
    """A co-present covenant-mate's roles are ally candidates."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.subject_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.mate_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.mate_sub_role = SubroleCovenantRoleFactory(
            parent_role=self.mate_role, resonance=self.resonance, unlock_thread_level=3
        )
        self.sheet = CharacterSheetFactory()
        self.mate = CharacterSheetFactory()
        engage_vow_with_thread(
            self.sheet, self.subject_role, covenant=self.covenant, thread_level=1
        )
        engage_vow_with_thread(
            self.mate,
            self.mate_role,
            covenant=self.covenant,
            thread_level=3,
            resonance=self.resonance,
        )
        self.encounter = CombatEncounterFactory()
        self.resolution = CombatRoundContext(
            CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        )

    def test_a_co_present_mate_is_an_ally_candidate(self) -> None:
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.mate)
        candidates = vow_holder_candidates(self.sheet, self.resolution)
        mate_candidates = [c for c in candidates if c.holder == self.mate]
        self.assertEqual(
            {c.role_id for c in mate_candidates}, {self.mate_role.pk, self.mate_sub_role.pk}
        )
        self.assertEqual({c.anchor_role_id for c in mate_candidates}, {self.mate_role.pk})
        self.assertTrue(all(c.beneficiaries == _ALLY for c in mate_candidates))

    def test_a_mate_in_another_encounter_is_not(self) -> None:
        CombatParticipantFactory(encounter=CombatEncounterFactory(), character_sheet=self.mate)
        candidates = vow_holder_candidates(self.sheet, self.resolution)
        self.assertNotIn(self.mate, {c.holder for c in candidates})

    def test_thread_levels_cover_subject_and_mate_in_one_query(self) -> None:
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.mate)
        candidates = vow_holder_candidates(self.sheet, self.resolution)
        with self.assertNumQueries(1):
            levels = vow_holder_thread_levels(candidates)
        self.assertEqual(
            levels,
            # Stored levels: shown 1 and 3 are stored 10 and 30 (#4585).
            {(self.sheet.pk, self.subject_role.pk): 10, (self.mate.pk, self.mate_role.pk): 30},
        )


class SituationCheckTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_a_blank_situation_holds(self) -> None:
        check = SituationCheck(subject=self.sheet, target=None, resolution=None)
        with self.assertNumQueries(0):
            self.assertTrue(check.holds("", NO_PARAMS, self.sheet))
