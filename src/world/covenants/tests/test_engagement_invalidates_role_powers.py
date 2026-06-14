"""Service-layer regression for #751: engagement changes bust the role-power cache.

``CharacterThreadHandler.passive_capability_grants()`` caches the engaged-role-gated
CAPABILITY_GRANT set on the long-lived, idmapper-cached Character typeclass instance
(and its memoized ``.threads`` handler). Engaging/disengaging a covenant role changes
that set, so the engagement service functions MUST invalidate the thread handler or a
just-engaged role power would not apply (and a disengaged one would linger).

These tests prove the SERVICE invalidates — they never call ``invalidate()`` by hand;
they read the grant set through the same memoized ``character.threads`` handler the
service resolves via ``membership.character_sheet.character.threads``.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.services import clear_engaged_membership, set_engaged_membership
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)


class EngagementInvalidatesRolePowersTests(TestCase):
    """set_engaged_membership / clear_engaged_membership bust the cached grant set."""

    def _make_covenant_role_thread(self, *, sheet, role, resonance, level=10):
        return ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=role,
            level=level,
        )

    def _make_tier0_capability_effect(self, *, resonance, capability):
        return ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=capability,
        )

    def test_engage_then_disengage_invalidates_grant_cache(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=False,
            left_at=None,
        )

        # Populate the cache via the SAME memoized handler the service will invalidate.
        # Unengaged → cap absent (and now cached on character.threads).
        self.assertNotIn(cap.pk, character.threads.passive_capability_grants())

        # Engage via the service — it must invalidate the thread handler.
        set_engaged_membership(membership=membership)
        self.assertIn(cap.pk, character.threads.passive_capability_grants())

        # Disengage via the service — the cap must drop out again.
        clear_engaged_membership(membership=membership)
        self.assertNotIn(cap.pk, character.threads.passive_capability_grants())
