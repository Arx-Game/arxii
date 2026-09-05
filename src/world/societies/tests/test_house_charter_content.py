"""House charter models are authored content, not seeder invention (#2875).

SuccessionLaw, HoldingKind, HouseFeature and HouseTemplate carry the same
shape as HouseAspectDefinition (#2079/#2868): a natural key, CreditedContent,
and a CONTENT_MODELS registration, so the lore repo owns them going forward.
"""

from pathlib import Path
import tempfile

from django.test import TestCase, override_settings

from core.app_domains import credited_content_models
from core_management.content_export import CONTENT_MODELS, export_to_content_repo
from world.currency.constants import IncomeStreamKind
from world.societies.houses.constants import SuccessionDerivation, SuccessionOrdering
from world.societies.houses.models import (
    HoldingKind,
    HouseAspectDefinition,
    HouseFeature,
    HouseTemplate,
    SuccessionLaw,
)


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


class HouseTemplateRoundTripTests(TestCase):
    """A full charter recipe survives an export, wipe, and reload (#2875 Task 3).

    Proves the ordering claim behind
    ``config_prerequisites._house_charter_anchors``: a content-repo
    ``HouseTemplate`` FKs the Crown organization and its Society by name, so
    both must already exist in the database before the content load runs, or
    the FK cannot resolve. This test builds those two anchors with the exact
    helper the real load path calls (``_ensure_house_charter_anchors``) and
    leaves them standing through the wipe, then deletes every row that IS
    registered in ``CONTENT_MODELS`` (the charter itself, its succession law,
    its holdings, its features, its aspect definitions) and reloads from the
    export. The template comes back with every FK and M2M resolved against
    the anchors that were never touched, which is what "code prerequisites
    run before content load" means in practice.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_house_template_round_trips_with_all_relations(self) -> None:
        from core_management.content_fixtures import load_world_content
        from world.character_creation.factories import RealmFactory
        from world.roster.factories import FamilyKindFactory
        from world.seeds.houses import _ensure_house_charter_anchors

        realm = RealmFactory(name="Round Trip Realm")
        # The prerequisite anchors: plain seeder-owned config, not in
        # CONTENT_MODELS, so they are never wiped or reloaded below.
        society, _org_type, crown = _ensure_house_charter_anchors(realm)
        kind = FamilyKindFactory(name="Round Trip Family Kind")

        law = SuccessionLaw.objects.create(
            name="Round Trip Succession",
            derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
            ordering_rule=SuccessionOrdering.ELDEST,
        )
        holding_a = HoldingKind.objects.create(
            name="Round Trip Farmland",
            stream_kind=IncomeStreamKind.DOMAIN_TAX,
            base_gross=100,
        )
        holding_a.full_clean()
        holding_b = HoldingKind.objects.create(
            name="Round Trip Mine", stream_kind=IncomeStreamKind.CRIME_KICKUP, base_gross=200
        )
        feature_a = HouseFeature.objects.create(
            name="Round Trip Black Ledger",
            slug="rt-black-ledger",
            description="This house keeps a Black Ledger of every debt owed.",
        )
        feature_b = HouseFeature.objects.create(
            name="Round Trip Open Hearth",
            slug="rt-open-hearth",
            description="This house's hearth is open to any traveler.",
        )
        aspect_a = HouseAspectDefinition.objects.create(
            name="Round Trip Vice", prompt="Pick the house's founding vice."
        )
        aspect_b = HouseAspectDefinition.objects.create(
            name="Round Trip Totem", prompt="Pick the house's founding totem."
        )

        template = HouseTemplate.objects.create(
            name="Round Trip Charter",
            realm=realm,
            kind=kind,
            society=society,
            liege=crown,
            default_succession_law=law,
        )
        template.holdings.add(holding_a, holding_b)
        template.features.add(feature_a, feature_b)
        template.aspect_definitions.add(aspect_a, aspect_b)

        result = export_to_content_repo(self.root)
        self.assertEqual(result.errors, [])

        # Wipe only the CONTENT_MODELS rows, child-first: the template links
        # to all four, so it goes first, then the four catalogs it referenced.
        HouseTemplate.objects.filter(pk=template.pk).delete()
        HouseAspectDefinition.objects.filter(pk__in=[aspect_a.pk, aspect_b.pk]).delete()
        HouseFeature.objects.filter(pk__in=[feature_a.pk, feature_b.pk]).delete()
        HoldingKind.objects.filter(pk__in=[holding_a.pk, holding_b.pk]).delete()
        SuccessionLaw.objects.filter(pk=law.pk).delete()

        world_result = load_world_content(self.root)
        self.assertEqual(world_result.skipped, [])

        reloaded = HouseTemplate.objects.get(name="Round Trip Charter")
        self.assertEqual(reloaded.realm, realm)
        self.assertEqual(reloaded.kind, kind)
        self.assertEqual(reloaded.society, society)
        self.assertEqual(reloaded.liege, crown)
        self.assertEqual(reloaded.default_succession_law.name, "Round Trip Succession")
        self.assertEqual(
            {holding.name for holding in reloaded.holdings.all()},
            {"Round Trip Farmland", "Round Trip Mine"},
        )
        self.assertEqual(
            {feature.name for feature in reloaded.features.all()},
            {"Round Trip Black Ledger", "Round Trip Open Hearth"},
        )
        self.assertEqual(
            {aspect.name for aspect in reloaded.aspect_definitions.all()},
            {"Round Trip Vice", "Round Trip Totem"},
        )
