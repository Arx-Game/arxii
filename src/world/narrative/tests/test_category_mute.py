"""Category-level narrative mute (#1522) — the squelch behind the weather echo.

Mirrors UserStoryMute but at the category granularity: a player can silence the live push of a
whole category (e.g. WEATHER) while it stays readable in that category's tab. These pin the
service contract; the push-skip itself reuses the same ``muted_account_ids`` path the
story-mute already exercises.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import UserCategoryMute
from world.narrative.services import is_category_muted, set_category_mute


class CategoryMuteServiceTests(TestCase):
    def test_mute_creates_a_row(self) -> None:
        account = AccountFactory()
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=True)
        assert is_category_muted(account=account, category=NarrativeCategory.WEATHER)
        assert UserCategoryMute.objects.filter(account=account).count() == 1

    def test_mute_is_idempotent(self) -> None:
        account = AccountFactory()
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=True)
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=True)
        assert UserCategoryMute.objects.filter(account=account).count() == 1

    def test_unmute_removes_the_row(self) -> None:
        account = AccountFactory()
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=True)
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=False)
        assert not is_category_muted(account=account, category=NarrativeCategory.WEATHER)

    def test_mute_is_category_scoped(self) -> None:
        account = AccountFactory()
        set_category_mute(account=account, category=NarrativeCategory.WEATHER, muted=True)
        # Muting WEATHER doesn't touch other categories.
        assert not is_category_muted(account=account, category=NarrativeCategory.ATMOSPHERE)
