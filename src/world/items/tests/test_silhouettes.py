"""Silhouette vocabulary + crafter form-pick validation (#2907)."""

from django.test import TestCase

from world.items.constants import WearFamily, silhouette_prose_noun
from world.items.crafting.services import _resolve_silhouette_choice
from world.items.exceptions import InvalidSilhouetteChoice
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import Silhouette


class SilhouetteModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boot = Silhouette.objects.create(name="Boot", wear_family=WearFamily.FOOTWEAR)
        cls.thigh_high = Silhouette.objects.create(
            name="Thigh-High Boot", wear_family=WearFamily.FOOTWEAR, parent=cls.boot
        )
        cls.circlet = Silhouette.objects.create(name="Circlet", wear_family=WearFamily.HEADWEAR)

    def test_umbrella_hierarchy(self):
        assert self.thigh_high.parent == self.boot
        assert list(self.boot.children.all()) == [self.thigh_high]

    def test_prose_noun_by_family(self):
        assert silhouette_prose_noun(WearFamily.FULL_GARMENT) == "cut"
        assert silhouette_prose_noun(WearFamily.JEWELRY) == "setting"
        assert silhouette_prose_noun(WearFamily.FOOTWEAR) == "silhouette"
        assert self.boot.prose_noun == "silhouette"

    def test_effective_silhouette_falls_back_to_template(self):
        template = ItemTemplateFactory(silhouette=self.boot)
        instance = ItemInstanceFactory(template=template)
        assert instance.effective_silhouette == self.boot
        instance.silhouette = self.thigh_high
        instance.save()
        assert instance.effective_silhouette == self.thigh_high


class SilhouetteChoiceValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boot = Silhouette.objects.create(name="Boot", wear_family=WearFamily.FOOTWEAR)
        cls.thigh_high = Silhouette.objects.create(
            name="Thigh-High Boot", wear_family=WearFamily.FOOTWEAR, parent=cls.boot
        )
        cls.circlet = Silhouette.objects.create(name="Circlet", wear_family=WearFamily.HEADWEAR)
        cls.template = ItemTemplateFactory(silhouette=cls.boot)
        cls.formless_template = ItemTemplateFactory(silhouette=None)

    def test_valid_pick_resolves_into_overrides(self):
        overrides = {"output_template": self.template, "silhouette_id": self.thigh_high.pk}
        _resolve_silhouette_choice(overrides)
        assert overrides["silhouette"] == self.thigh_high
        assert "silhouette_id" not in overrides

    def test_no_pick_is_a_no_op(self):
        overrides = {"output_template": self.template, "silhouette_id": None}
        _resolve_silhouette_choice(overrides)
        assert "silhouette" not in overrides

    def test_cross_family_pick_rejected(self):
        overrides = {"output_template": self.template, "silhouette_id": self.circlet.pk}
        with self.assertRaises(InvalidSilhouetteChoice):
            _resolve_silhouette_choice(overrides)

    def test_formless_template_accepts_no_pick(self):
        overrides = {
            "output_template": self.formless_template,
            "silhouette_id": self.thigh_high.pk,
        }
        with self.assertRaises(InvalidSilhouetteChoice):
            _resolve_silhouette_choice(overrides)

    def test_inactive_silhouette_rejected(self):
        retired = Silhouette.objects.create(
            name="Retired Form", wear_family=WearFamily.FOOTWEAR, is_active=False
        )
        overrides = {"output_template": self.template, "silhouette_id": retired.pk}
        with self.assertRaises(InvalidSilhouetteChoice):
            _resolve_silhouette_choice(overrides)


class FashionSeedTests(TestCase):
    def test_seed_is_idempotent_and_hierarchical(self):
        from world.items.models import Style
        from world.seeds.fashion import seed_fashion_vocabulary

        seed_fashion_vocabulary()
        first_count = Silhouette.objects.count()
        seed_fashion_vocabulary()
        assert Silhouette.objects.count() == first_count
        assert first_count >= 25
        thigh_high = Silhouette.objects.get(name="Thigh-High Boot")
        assert thigh_high.parent == Silhouette.objects.get(name="Boot")
        assert thigh_high.wear_family == WearFamily.FOOTWEAR
        # Styles are cultural registers with eras; ancient ones exist for
        # investigation-driven rediscovery.
        assert Style.objects.filter(era="ancient").count() >= 2
        assert Style.objects.filter(era="current").count() >= 5
