"""revoke_distinction unwind seam (#2607)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.services import grant_distinction, revoke_distinction
from world.distinctions.types import DistinctionOrigin


class RevokeDistinctionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.distinction = DistinctionFactory(slug="fidgety", cost_per_rank=-2)

    def test_revoke_deletes_the_row(self) -> None:
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)
        revoke_distinction(cd)
        assert not CharacterDistinction.objects.filter(pk=cd.pk).exists()

    def test_revoke_then_regrant_is_clean(self) -> None:
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)
        revoke_distinction(cd)
        again = grant_distinction(
            self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD
        )
        assert again.pk is not None
        assert again.rank == 1
