"""Tests for core.deletion: a delete's SET_NULL updates reach cached referrers (#4086)."""

from django.test import TestCase

from world.character_creation.factories import CharacterDraftFactory, RealmFactory
from world.character_creation.models import CharacterDraft
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title
from world.societies.models import Organization


class IdentityMapDeleteTests(TestCase):
    """Each check reads the cached instance with ``get()``, which the identity
    map answers with the very object the delete left behind."""

    def _held_title(self, org: Organization) -> Title:
        title = plant_rung(realm=RealmFactory(), tier=TitleTier.COUNTY, name=f"Seat of {org.name}")
        title.house = org
        title.save(update_fields=["house"])
        return title

    def test_instance_delete_nulls_cached_referrers(self) -> None:
        org = OrganizationFactory()
        title = self._held_title(org)
        org.delete()
        cached = Title.objects.get(pk=title.pk)
        assert cached is title, "the identity map hands back the resident instance"
        assert cached.house_id is None
        assert cached.house is None

    def test_queryset_delete_nulls_cached_referrers(self) -> None:
        """The admin's bulk "delete selected" goes through ``queryset.delete()``."""
        org = OrganizationFactory()
        title = self._held_title(org)
        Organization.objects.filter(pk=org.pk).delete()
        assert Title.objects.get(pk=title.pk).house_id is None

    def test_a_cascade_nulls_the_referrers_of_what_it_removes(self) -> None:
        """Organization CASCADEs to Vacancy; CharacterDraft.selected_vacancy is
        SET_NULL. The draft only ever pointed at the vacancy, never the org."""
        vacancy = VacancyFactory()
        draft = CharacterDraftFactory(selected_vacancy=vacancy)
        vacancy.organization.delete()
        assert CharacterDraft.objects.get(pk=draft.pk).selected_vacancy_id is None

    def test_other_cached_referrers_keep_their_link(self) -> None:
        org = OrganizationFactory()
        kept = OrganizationFactory()
        title = self._held_title(org)
        other = self._held_title(kept)
        org.delete()
        assert Title.objects.get(pk=title.pk).house_id is None
        assert Title.objects.get(pk=other.pk).house_id == kept.pk

    def test_the_manager_has_no_whole_table_delete(self) -> None:
        assert not hasattr(Organization.objects, "delete")
