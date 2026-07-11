"""CoerceAssetAction role gate (#1680 slice 3b).

The routing (played/piloted → agency; un-played NPC → auto) and the mint itself are
covered by world.assets.tests.test_coercion (the service) and the has_leverage/prereq
tests; this pins the role_context gate, which runs before any actor/target resolution.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from actions.definitions.coercion import CoerceAssetAction


class CoerceRoleGateTests(SimpleTestCase):
    def test_rejects_a_non_coercible_role_context(self) -> None:
        # 'fan' is a cultivation-only kind — not something you extort.
        result = CoerceAssetAction().execute(
            actor=MagicMock(), role_context="fan", target_persona_id=1
        )
        self.assertFalse(result.success)
        self.assertIn("informant", result.message)

    def test_rejects_a_missing_role_context(self) -> None:
        result = CoerceAssetAction().execute(actor=MagicMock(), target_persona_id=1)
        self.assertFalse(result.success)

    def test_accepts_the_three_coercible_kinds(self) -> None:
        from actions.definitions.coercion import _COERCIBLE_ROLE_CONTEXTS

        self.assertEqual(_COERCIBLE_ROLE_CONTEXTS, {"informant", "contact", "personal_favor"})
