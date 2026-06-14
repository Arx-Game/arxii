"""Tests for ``CharacterThreadHandler.passive_capability_grants`` (#751 / Task B1).

Tier-0 CAPABILITY_GRANT ThreadPullEffect rows on COVENANT_ROLE threads are
applied only while the character holds an active, *engaged* CharacterCovenantRole
for that role. The handler returns the SET of granted CapabilityType PKs.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)


class PassiveCapabilityGrantsTests(TestCase):
    """Engagement-gated tier-0 CAPABILITY_GRANT application."""

    def _make_covenant_role_thread(self, *, sheet, role, resonance, level=10):
        """Build a COVENANT_ROLE thread for ``sheet`` anchored to ``role``/``resonance``."""
        return ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=role,
            level=level,
        )

    def _make_tier0_capability_effect(self, *, resonance, capability):
        """Author a tier-0 CAPABILITY_GRANT effect for a COVENANT_ROLE thread."""
        return ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=capability,
        )

    def test_engaged_role_grants_tier0_capability(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            left_at=None,
        )

        granted = character.threads.passive_capability_grants()
        self.assertIn(cap.pk, granted)

    def test_unengaged_role_does_not_grant(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=False,
            left_at=None,
        )

        granted = character.threads.passive_capability_grants()
        self.assertNotIn(cap.pk, granted)

    def test_two_resonances_grant_different_capabilities(self):
        """Two engaged roles, each with its own resonance/thread, grant both caps.

        The ``uniq_thread_covenant_role_active`` constraint forbids two active
        COVENANT_ROLE threads on the same (owner, role), and engaged-uniqueness
        is per covenant_type, so the individualization lever is exercised with
        two roles of different covenant types (DURANCE + BATTLE).
        """
        sheet = CharacterSheetFactory()
        character = sheet.character
        role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_b = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        res_a = ResonanceFactory()
        res_b = ResonanceFactory()
        cap_a = CapabilityTypeFactory()
        cap_b = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role_a, resonance=res_a)
        self._make_covenant_role_thread(sheet=sheet, role=role_b, resonance=res_b)
        self._make_tier0_capability_effect(resonance=res_a, capability=cap_a)
        self._make_tier0_capability_effect(resonance=res_b, capability=cap_b)

        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=role_a,
            engaged=True,
            left_at=None,
        )
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(
                covenant_type=CovenantType.BATTLE,
                battle_binding="standing",
            ),
            covenant_role=role_b,
            engaged=True,
            left_at=None,
        )

        granted = character.threads.passive_capability_grants()
        self.assertEqual(granted, {cap_a.pk, cap_b.pk})

    def test_same_resonance_two_roles_grants_when_any_engaged(self):
        """Two roles share one resonance + one tier-0 effect; engagement of any wins.

        The schema permits two active COVENANT_ROLE threads on the SAME resonance
        but DIFFERENT roles (the unique constraint is on (owner, role), not
        resonance). Both threads collapse into the single (COVENANT_ROLE,
        resonance) effect-lookup key, so the grant must be decided by an EXISTS
        over all threads sharing the key — not by whichever thread happens to win
        a dict slot. The pre-fix single-winner logic withheld the grant whenever
        the unengaged role's thread won the slot (nondeterministic — Thread has no
        Meta.ordering). The two roles are of different covenant types to satisfy
        both the per-(owner,role) thread constraint and the per-(character,
        covenant_type) engaged constraint.
        """
        sheet = CharacterSheetFactory()
        character = sheet.character
        role_durance = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_battle = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        # Two active COVENANT_ROLE threads on the SAME resonance, different roles.
        self._make_covenant_role_thread(sheet=sheet, role=role_durance, resonance=resonance)
        self._make_covenant_role_thread(sheet=sheet, role=role_battle, resonance=resonance)
        # Exactly ONE tier-0 effect for that (COVENANT_ROLE, resonance) key.
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        membership_durance = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=role_durance,
            engaged=False,
            left_at=None,
        )
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(
                covenant_type=CovenantType.BATTLE,
                battle_binding="standing",
            ),
            covenant_role=role_battle,
            engaged=False,
            left_at=None,
        )

        # Case B first: NEITHER role engaged → C is NOT granted.
        granted = character.threads.passive_capability_grants()
        self.assertNotIn(cap.pk, granted)

        # Case A: engage exactly one of the two roles → C IS granted (regardless
        # of which thread would have won any single-winner dict slot).
        membership_durance.engaged = True
        membership_durance.save(update_fields=["engaged"])
        character.threads.invalidate()

        granted = character.threads.passive_capability_grants()
        self.assertIn(cap.pk, granted)
