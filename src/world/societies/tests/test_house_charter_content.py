"""House charter models are authored content, not seeder invention (#2875).

SuccessionLaw, HoldingKind, HouseFeature and HouseTemplate carry the same
shape as HouseAspectDefinition (#2079/#2868): a natural key, CreditedContent,
and a CONTENT_MODELS registration, so the lore repo owns them going forward.
"""

from django.test import TestCase

from core.app_domains import credited_content_models
from core_management.content_export import CONTENT_MODELS
from world.societies.houses.constants import SuccessionDerivation, SuccessionOrdering
from world.societies.houses.models import HoldingKind, HouseFeature, HouseTemplate, SuccessionLaw


class HouseCharterContentRegistrationTests(TestCase):
    def test_charter_models_are_registered_content(self) -> None:
        for label in (
            "societies.successionlaw",
            "societies.holdingkind",
            "societies.housefeature",
            "societies.housetemplate",
        ):
            self.assertIn(label, CONTENT_MODELS)

    def test_charter_models_are_credited_for_the_workbench(self) -> None:
        credited = set(credited_content_models())
        for model in (SuccessionLaw, HoldingKind, HouseFeature, HouseTemplate):
            self.assertIn(model, credited)

    def test_natural_key_is_the_name(self) -> None:
        law = SuccessionLaw.objects.create(
            name="Agnatic primogeniture (test)",
            derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
            ordering_rule=SuccessionOrdering.ELDEST,
        )
        self.assertEqual(SuccessionLaw.objects.get_by_natural_key(*law.natural_key()), law)

    def test_holding_kind_natural_key_is_the_name(self) -> None:
        kind = HoldingKind.objects.create(
            name="Test Farmland (test)",
            stream_kind="farmland",
            base_gross=100,
        )
        self.assertEqual(HoldingKind.objects.get_by_natural_key(*kind.natural_key()), kind)

    def test_house_feature_natural_key_is_the_name(self) -> None:
        feature = HouseFeature.objects.create(
            name="Test Feature (test)",
            slug="test-feature-test",
            description="A test feature.",
        )
        self.assertEqual(HouseFeature.objects.get_by_natural_key(*feature.natural_key()), feature)
