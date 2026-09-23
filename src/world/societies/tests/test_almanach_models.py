from django.db import IntegrityError, transaction
from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import TIER_TO_AREA_LEVEL, HouseState, TitleTier
from world.societies.houses.models import Domain, Title


class AlmanachSchemaTests(TestCase):
    def test_feudal_rungs_sit_between_city_and_continent(self) -> None:
        assert AreaLevel.CITY < AreaLevel.BARONY < AreaLevel.COUNTY < AreaLevel.DUCHY
        assert AreaLevel.DUCHY < AreaLevel.KINGDOM < AreaLevel.EMPIRE < AreaLevel.CONTINENT
        assert TIER_TO_AREA_LEVEL[TitleTier.MARCH] == AreaLevel.COUNTY

    def test_undefined_rungs_share_the_empty_name(self) -> None:
        realm = RealmFactory()
        Title.objects.create(name="", tier=TitleTier.BARONY, realm=realm)
        Title.objects.create(name="", tier=TitleTier.BARONY, realm=realm)
        assert Title.objects.filter(name="").count() == 2
        with transaction.atomic():
            Title.objects.create(name="Perdition", tier=TitleTier.BARONY, realm=realm)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Title.objects.create(name="Perdition", tier=TitleTier.BARONY, realm=realm)

    def test_domain_may_be_unowned_and_unnamed(self) -> None:
        a = AreaFactory(level=AreaLevel.BARONY)
        b = AreaFactory(level=AreaLevel.BARONY)
        Domain.objects.create(area=a, name="", owner_org=None)
        Domain.objects.create(area=b, name="", owner_org=None)
        assert Domain.objects.filter(owner_org__isnull=True).count() == 2

    def test_house_state_defaults_to_standing_and_unpublished(self) -> None:
        org = OrganizationFactory()
        assert org.house_state == HouseState.STANDING
        assert org.published_at is None
