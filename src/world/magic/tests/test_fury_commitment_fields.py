from django.test import TestCase

from world.combat.models import ClashContributionDeclaration
from world.scenes.action_models import SceneActionRequest
from world.scenes.models import Interaction


class FuryFieldTests(TestCase):
    def test_mixin_exposes_fury_fields_on_both_concretes(self):
        for model in (SceneActionRequest, ClashContributionDeclaration):
            names = {f.name for f in model._meta.get_fields()}
            self.assertIn("fury_commitment", names)
            self.assertIn("fury_anchor", names)

    def test_interaction_has_fury_committed(self):
        self.assertIn("fury_committed", {f.name for f in Interaction._meta.get_fields()})
