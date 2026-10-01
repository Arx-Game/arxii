"""Tests for core.deletion: a delete's SET_NULL updates reach cached referrers (#4086).

``TestCase`` runs every test inside a transaction, so a delete here takes the
evict branch; the in-place branch is exercised through
``clear_set_null_referrers`` directly.
"""

from django.db import transaction
from django.test import TestCase

from core.deletion import clear_set_null_referrers
from world.character_creation.factories import CharacterDraftFactory, RealmFactory
from world.character_creation.models import CharacterDraft
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title
from world.societies.models import Organization


class _Rollback(Exception):
    pass


class IdentityMapDeleteTests(TestCase):
    def _held_title(self, org: Organization) -> Title:
        title = plant_rung(realm=RealmFactory(), tier=TitleTier.COUNTY, name=f"Seat of {org.name}")
        title.house = org
        title.save(update_fields=["house"])
        return title

    def test_instance_delete_evicts_cached_referrers_inside_a_transaction(self) -> None:
        org = OrganizationFactory()
        title = self._held_title(org)
        org.delete()
        fresh = Title.objects.get(pk=title.pk)
        assert fresh is not title, "the stale instance left the identity map"
        assert fresh.house_id is None
        assert fresh.house is None

    def test_queryset_delete_evicts_cached_referrers(self) -> None:
        """The admin's bulk "delete selected" goes through ``queryset.delete()``."""
        org = OrganizationFactory()
        title = self._held_title(org)
        Organization.objects.filter(pk=org.pk).delete()
        assert Title.objects.get(pk=title.pk).house_id is None

    def test_a_cascade_clears_the_referrers_of_what_it_removes(self) -> None:
        """Organization CASCADEs to Vacancy; CharacterDraft.selected_vacancy is
        SET_NULL. The draft only ever pointed at the vacancy, never the org."""
        vacancy = VacancyFactory()
        draft = CharacterDraftFactory(selected_vacancy=vacancy)
        vacancy.organization.delete()
        assert CharacterDraft.objects.get(pk=draft.pk).selected_vacancy_id is None

    def test_a_rolled_back_delete_leaves_the_link_intact(self) -> None:
        """The reviewed delete can remove rows and then roll them all back; a
        referrer nulled in memory would write NULL over its restored link."""
        org = OrganizationFactory()
        title = self._held_title(org)
        org_pk = org.pk  # Django nulls a deleted instance's pk, rollback or not
        try:
            with transaction.atomic():
                org.delete()
                raise _Rollback
        except _Rollback:
            pass
        assert Title.objects.get(pk=title.pk).house_id == org_pk

    def test_other_cached_referrers_are_untouched(self) -> None:
        org = OrganizationFactory()
        kept = OrganizationFactory()
        self._held_title(org)
        other = self._held_title(kept)
        org.delete()
        assert Title.objects.get(pk=other.pk) is other
        assert other.house_id == kept.pk

    def test_outside_a_transaction_the_link_is_nulled_in_place(self) -> None:
        org = OrganizationFactory()
        title = self._held_title(org)
        clear_set_null_referrers(Organization, [org.pk])
        assert Title.objects.get(pk=title.pk) is title
        assert title.house_id is None
        assert title.house is None

    def test_the_manager_has_no_whole_table_delete(self) -> None:
        assert not hasattr(Organization.objects, "delete")
