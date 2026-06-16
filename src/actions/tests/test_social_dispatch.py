from django.test import TestCase

from actions.registry import get_action


class SocialActionRegistryTest(TestCase):
    def test_all_six_social_actions_are_registered(self):
        for key in ("entrance", "intimidate", "persuade", "deceive", "flirt", "perform"):
            action = get_action(key)
            self.assertIsNotNone(action, f"{key} not registered")

    def test_entrance_action_key(self):
        action = get_action("entrance")
        self.assertEqual(action.key, "entrance")

    def test_social_actions_have_persona_target_kind(self):
        from actions.constants import TargetKind

        for key in ("entrance", "intimidate", "persuade", "deceive", "flirt", "perform"):
            action = get_action(key)
            self.assertEqual(
                action.target_kind, TargetKind.PERSONA, f"{key}.target_kind != PERSONA"
            )

    def test_target_filters_has_excluded_persona_ids(self):
        from actions.types import TargetFilters

        filters = TargetFilters()
        self.assertTrue(hasattr(filters, "excluded_persona_ids"))
        self.assertIsInstance(filters.excluded_persona_ids, frozenset)
