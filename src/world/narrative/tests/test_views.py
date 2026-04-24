"""Tests for narrative read API — my-messages and acknowledge endpoints."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.factories import (
    NarrativeMessageDeliveryFactory,
    NarrativeMessageFactory,
)

MY_MESSAGES_URL = reverse("narrative-my-messages")


def _sheet_for_account(account):
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class MyNarrativeMessagesAuthTest(APITestCase):
    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(MY_MESSAGES_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_authenticated_empty(self):
        user = AccountFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(MY_MESSAGES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0


class MyNarrativeMessagesListTest(APITestCase):
    def test_lists_only_own_deliveries(self):
        user = AccountFactory()
        other = AccountFactory()
        mine = _sheet_for_account(user)
        not_mine = _sheet_for_account(other)
        my_delivery = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=mine,
        )
        NarrativeMessageDeliveryFactory(recipient_character_sheet=not_mine)

        self.client.force_authenticate(user=user)
        response = self.client.get(MY_MESSAGES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == my_delivery.pk

    def test_excludes_ooc_note_from_player_payload(self):
        user = AccountFactory()
        sheet = _sheet_for_account(user)
        msg = NarrativeMessageFactory(ooc_note="Staff only")
        NarrativeMessageDeliveryFactory(
            message=msg,
            recipient_character_sheet=sheet,
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(MY_MESSAGES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert "ooc_note" not in response.data["results"][0]["message"]

    def test_filter_by_category(self):
        user = AccountFactory()
        sheet = _sheet_for_account(user)
        story_msg = NarrativeMessageFactory(category=NarrativeCategory.STORY)
        atmos_msg = NarrativeMessageFactory(category=NarrativeCategory.ATMOSPHERE)
        NarrativeMessageDeliveryFactory(message=story_msg, recipient_character_sheet=sheet)
        NarrativeMessageDeliveryFactory(message=atmos_msg, recipient_character_sheet=sheet)

        self.client.force_authenticate(user=user)
        response = self.client.get(MY_MESSAGES_URL, {"category": NarrativeCategory.STORY})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["message"]["category"] == NarrativeCategory.STORY


class AcknowledgeDeliveryTest(APITestCase):
    def test_recipient_can_acknowledge(self):
        user = AccountFactory()
        sheet = _sheet_for_account(user)
        delivery = NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet)
        url = reverse("narrative-delivery-acknowledge", kwargs={"pk": delivery.pk})
        self.client.force_authenticate(user=user)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        delivery.refresh_from_db()
        assert delivery.acknowledged_at is not None

    def test_acknowledge_is_idempotent(self):
        user = AccountFactory()
        sheet = _sheet_for_account(user)
        delivery = NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet)
        url = reverse("narrative-delivery-acknowledge", kwargs={"pk": delivery.pk})
        self.client.force_authenticate(user=user)
        first = self.client.post(url)
        delivery.refresh_from_db()
        first_ts = delivery.acknowledged_at
        second = self.client.post(url)
        delivery.refresh_from_db()
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert delivery.acknowledged_at == first_ts  # unchanged on second call

    @suppress_permission_errors
    def test_non_recipient_rejected(self):
        owner = AccountFactory()
        other = AccountFactory()
        sheet = _sheet_for_account(owner)
        delivery = NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet)
        url = reverse("narrative-delivery-acknowledge", kwargs={"pk": delivery.pk})
        self.client.force_authenticate(user=other)
        response = self.client.post(url)
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_staff_can_acknowledge_any_delivery(self):
        owner = AccountFactory()
        staff = AccountFactory(is_staff=True)
        sheet = _sheet_for_account(owner)
        delivery = NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet)
        url = reverse("narrative-delivery-acknowledge", kwargs={"pk": delivery.pk})
        self.client.force_authenticate(user=staff)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
