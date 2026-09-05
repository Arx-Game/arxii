"""House charter models are authored content, not seeder invention (#2875).

SuccessionLaw, HoldingKind, HouseFeature and HouseTemplate carry the same
shape as HouseAspectDefinition (#2079/#2868): a natural key, CreditedContent,
and a CONTENT_MODELS registration, so the lore repo owns them going forward.
"""

from django.test import TestCase, override_settings

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


@override_settings(SEED_SAMPLE_CONTENT=True)
class HouseCharterSeederAuthoredOrSampleTests(TestCase):
    """``seed_houses_demo`` looks charter rows up; it no longer invents them (#2875).

    ``world.seeds.houses`` converted its ``SuccessionLaw``/``HoldingKind``/
    ``HouseTemplate``/``HouseFeature`` ``get_or_create`` calls to
    ``authored_or_sample`` (ADR-0171): a second press converges on the same
    row instead of duplicating it, and a row that is already there is looked
    up, never rewritten. ``authored_or_sample`` leaves ANY existing row alone
    regardless of credit, since its lookup is a plain filter with no
    ``written_by`` check, so the uncredited pre-existing row this test
    creates proves the same thing a credited (authored) one would (the
    ``authored_or_sample`` contract; ADR-0201 is the same "never clobber what
    is already there" rule applied to the content-fixture loader).
    """

    def test_seeding_twice_yields_one_charter_row_of_each_kind(self) -> None:
        from world.seeds.houses import TEMPLATE_NAME, seed_houses_demo

        seed_houses_demo()
        seed_houses_demo()

        self.assertEqual(
            SuccessionLaw.objects.filter(name="Veyrane Primogeniture PLACEHOLDER").count(), 1
        )
        self.assertEqual(HoldingKind.objects.filter(name="Farmland PLACEHOLDER").count(), 1)
        self.assertEqual(HouseTemplate.objects.filter(name=TEMPLATE_NAME).count(), 1)
        self.assertEqual(HouseFeature.objects.filter(name="Hearth Right PLACEHOLDER").count(), 1)

    def test_authored_charter_row_is_not_overwritten_by_the_seeder(self) -> None:
        from world.seeds.houses import seed_houses_demo

        authored = SuccessionLaw.objects.create(
            name="Veyrane Primogeniture PLACEHOLDER",
            derivation=SuccessionDerivation.TANISTRY_ELECTION,
            ordering_rule=SuccessionOrdering.MOST_POWERFUL_GIFTED,
            require_wedlock=False,
        )

        seed_houses_demo()

        authored.refresh_from_db()
        self.assertEqual(authored.derivation, SuccessionDerivation.TANISTRY_ELECTION)
        self.assertEqual(authored.ordering_rule, SuccessionOrdering.MOST_POWERFUL_GIFTED)
        self.assertFalse(authored.require_wedlock)
        self.assertEqual(
            SuccessionLaw.objects.filter(name="Veyrane Primogeniture PLACEHOLDER").count(), 1
        )
