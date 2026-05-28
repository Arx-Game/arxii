from django.db import models
from django.test import TestCase

from world.magic.models.commitments import CommittingDeclaration


class CommittingDeclarationMixinTests(TestCase):
    def test_mixin_is_abstract(self) -> None:
        self.assertTrue(CommittingDeclaration._meta.abstract)

    def test_mixin_defines_strain_commitment_field(self) -> None:
        field = CommittingDeclaration._meta.get_field("strain_commitment")
        self.assertIsInstance(field, models.PositiveIntegerField)
        self.assertEqual(field.default, 0)
