"""Tests for the authored per-(role, resonance) role-powers catalog (#751 / Task B3).

``wire_covenant_role_powers_catalog`` seeds ONE Sword-archetype CovenantRole with a
per-(role, resonance) catalog: two authored resonances, each granting a distinct
tier-0 CAPABILITY_GRANT (the covenant's passive gift) plus a tier-1 active pull.
Individualization is ACROSS characters — two holders of the SAME role who anchor
DIFFERENT resonances unlock DIFFERENT capabilities. These tests prove idempotency
and that end-to-end individualization through the passive-application pipeline
(B1 handler -> B2 capability read).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.services import get_effective_capability_value
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    wire_covenant_role_powers_catalog,
)
from world.covenants.models import CovenantRole
from world.magic.constants import TargetKind
from world.magic.models import Thread, ThreadPullEffect


class RolePowersCatalogTests(TestCase):
    """Catalog seed: idempotent + individualized across holders of one role."""

    def test_catalog_is_idempotent_and_individualized(self):
        role_a, caps_a = wire_covenant_role_powers_catalog()
        role_b, caps_b = wire_covenant_role_powers_catalog()

        # Same role row returned; no duplicate CovenantRole created.
        self.assertEqual(role_a.pk, role_b.pk)

        # The two returned capabilities are distinct (per-resonance individualization).
        cap_a, cap_b = caps_a
        self.assertNotEqual(cap_a.pk, cap_b.pk)
        self.assertEqual({c.pk for c in caps_a}, {c.pk for c in caps_b})

        # At least two distinct resonances each carry a tier-0 CAPABILITY_GRANT.
        distinct_grant_resonances = (
            ThreadPullEffect.objects.filter(
                target_kind=TargetKind.COVENANT_ROLE,
                tier=0,
                effect_kind="CAPABILITY_GRANT",
            )
            .values("resonance")
            .distinct()
            .count()
        )
        self.assertGreaterEqual(distinct_grant_resonances, 2)

    def _weave_role_thread(self, *, sheet, role, resonance, level=20):
        """Weave an active COVENANT_ROLE thread for ``sheet`` on ``role``/``resonance``."""
        thread = Thread(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            level=level,
        )
        thread.full_clean()
        thread.save()
        return thread

    def _engage_holder(self, *, sheet, role):
        """Give ``sheet`` a covenant of the role's type + an engaged active membership."""
        covenant = CovenantFactory(covenant_type=role.covenant_type)
        return CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
            engaged=True,
            left_at=None,
        )

    def test_two_holders_same_role_different_resonance_get_different_capabilities(self):
        role, (cap_a, cap_b) = wire_covenant_role_powers_catalog()

        # The two resonances are the ones carrying the tier-0 grants for this role.
        grant_effects = list(
            ThreadPullEffect.objects.filter(
                target_kind=TargetKind.COVENANT_ROLE,
                tier=0,
                effect_kind="CAPABILITY_GRANT",
                capability_grant__in=[cap_a, cap_b],
            ).select_related("resonance")
        )
        res_for_cap = {e.capability_grant_id: e.resonance for e in grant_effects}
        res_a = res_for_cap[cap_a.pk]
        res_b = res_for_cap[cap_b.pk]

        # Two DIFFERENT characters (each its own CharacterSheet). sheet_data is the
        # canonical CharacterSheet accessor (ty resolves it; the bare factory return
        # is inferred as the factory class).
        sheet_a = CharacterSheetFactory().character.sheet_data
        sheet_b = CharacterSheetFactory().character.sheet_data

        # Each holder anchors the SAME role on a DIFFERENT resonance.
        self._weave_role_thread(sheet=sheet_a, role=role, resonance=res_a)
        self._weave_role_thread(sheet=sheet_b, role=role, resonance=res_b)
        self._engage_holder(sheet=sheet_a, role=role)
        self._engage_holder(sheet=sheet_b, role=role)

        # Holder A possesses cap_a, not cap_b.
        self.assertGreaterEqual(get_effective_capability_value(sheet_a, cap_a), 1)
        self.assertEqual(get_effective_capability_value(sheet_a, cap_b), 0)

        # Holder B possesses cap_b, not cap_a.
        self.assertGreaterEqual(get_effective_capability_value(sheet_b, cap_b), 1)
        self.assertEqual(get_effective_capability_value(sheet_b, cap_a), 0)

    def test_catalog_role_is_sword_primary(self):
        role, _caps = wire_covenant_role_powers_catalog()
        # Authored as a PRIMARY role (no parent, no resonance, level 0) per clean().
        self.assertIsNone(role.parent_role_id)
        self.assertIsNone(role.resonance_id)
        self.assertEqual(role.unlock_thread_level, 0)
        fetched = CovenantRole.objects.get(pk=role.pk)
        self.assertEqual(fetched.sword_weight, 1)
