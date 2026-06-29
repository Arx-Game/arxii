"""API tests for the fashion presentation + judging endpoints (#514).

Models the endorsement API tests in ``world/magic/tests/test_gain_views.py``:
the acting sheet (presenter / judge) is resolved from the requesting account's
active tenure, never supplied by the client. The presentation check is forced
deterministic via ``force_check_outcome``.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.events.factories import EventFactory
from world.items.constants import (
    FASHION_PRESENTATION_CHECK_TYPE_NAME,
    FASHION_PRESENTATION_ENDORSEMENT_WEIGHT,
    FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
)
from world.items.models import FashionPresentation
from world.magic.models.endorsement import PresentationEndorsement
from world.magic.services.gain import account_for_sheet
from world.mechanics.factories import ModifierTargetFactory
from world.roster.factories import RosterTenureFactory
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory


class FashionPresentationAPITests(APITestCase):
    """Cover present-outfit, judge, and presentation-list endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.modifier_target = ModifierTargetFactory(
            name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
        )
        cls.check_type = CheckTypeFactory(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)
        cls.outcome_success = CheckOutcomeFactory(name="fashion-api-success", success_level=3)

        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)

        # Presenter: a sheet with an active tenure → resolvable from its account.
        presenter_tenure = RosterTenureFactory()
        cls.presenter = presenter_tenure.roster_entry.character_sheet
        cls.presenter_account = account_for_sheet(cls.presenter)

        # Judge: a different sheet/account.
        judge_tenure = RosterTenureFactory()
        cls.judge = judge_tenure.roster_entry.character_sheet
        cls.judge_account = account_for_sheet(cls.judge)

    # -- present_outfit -----------------------------------------------------

    def test_present_creates_presentation_for_request_sheet(self) -> None:
        """POST present → 201 + a FashionPresentation for the request user's sheet."""
        self.client.force_authenticate(user=self.presenter_account)
        with force_check_outcome(self.outcome_success):
            response = self.client.post(
                "/api/items/fashion-presentations/",
                data={"event": self.event.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        presentations = FashionPresentation.objects.filter(presenter=self.presenter)
        self.assertEqual(presentations.count(), 1)
        self.assertEqual(response.data["presenter"], self.presenter.pk)
        self.assertEqual(response.data["event"], self.event.pk)
        self.assertEqual(response.data["base_score"], 3)
        self.assertEqual(response.data["acclaim"], 3)

    def test_present_endpoint_dispatches_present_outfit_action(self) -> None:
        """The web POST converges on PresentOutfitAction, not a serializer bypass (#1508).

        Spies on the real ``run`` (it still executes, creating + serializing the
        presentation → 201) and asserts it was the path taken. A regression back to the
        serializer's direct ``present_outfit`` call would not call ``run`` and fail here.
        """
        from unittest.mock import patch

        from actions.definitions.fashion import PresentOutfitAction

        real_run = PresentOutfitAction.run
        self.client.force_authenticate(user=self.presenter_account)
        with (
            force_check_outcome(self.outcome_success),
            patch.object(
                PresentOutfitAction, "run", autospec=True, side_effect=real_run
            ) as mock_run,
        ):
            response = self.client.post(
                "/api/items/fashion-presentations/",
                data={"event": self.event.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        mock_run.assert_called_once()

    def test_present_does_not_accept_presenter_from_client(self) -> None:
        """A client-supplied presenter is ignored; the request sheet is used."""
        self.client.force_authenticate(user=self.presenter_account)
        with force_check_outcome(self.outcome_success):
            response = self.client.post(
                "/api/items/fashion-presentations/",
                data={"event": self.event.pk, "presenter": self.judge.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["presenter"], self.presenter.pk)

    def test_present_no_host_society_returns_400(self) -> None:
        """An event with no host society → 400 with the friendly message."""
        event = EventFactory(host_society=None)
        self.client.force_authenticate(user=self.presenter_account)
        response = self.client.post(
            "/api/items/fashion-presentations/",
            data={"event": event.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "This event has no host society to judge fashion.",
            str(response.content),
        )

    def test_present_unauthenticated_rejected(self) -> None:
        response = self.client.post(
            "/api/items/fashion-presentations/",
            data={"event": self.event.pk},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    # -- judge_presentation -------------------------------------------------

    def _present(self) -> FashionPresentation:
        with force_check_outcome(self.outcome_success):
            from world.items.services.fashion_presentation import present_outfit

            return present_outfit(self.presenter, self.event)

    def test_judge_by_other_creates_endorsement_and_raises_acclaim(self) -> None:
        """POST judge by a different user → 201 + endorsement + acclaim rose."""
        presentation = self._present()
        base = presentation.base_score
        self.client.force_authenticate(user=self.judge_account)
        response = self.client.post(
            "/api/items/fashion-judgements/",
            data={"presentation": presentation.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PresentationEndorsement.objects.count(), 1)
        endorsement = PresentationEndorsement.objects.get()
        self.assertEqual(endorsement.endorser_sheet, self.judge)
        self.assertEqual(endorsement.endorsee_sheet, self.presenter)
        presentation.refresh_from_db()
        self.assertEqual(
            presentation.acclaim,
            base + FASHION_PRESENTATION_ENDORSEMENT_WEIGHT,
        )

    def test_self_judge_returns_400(self) -> None:
        """A presenter judging their own presentation → 400."""
        presentation = self._present()
        self.client.force_authenticate(user=self.presenter_account)
        response = self.client.post(
            "/api/items/fashion-judgements/",
            data={"presentation": presentation.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "You cannot judge your own presentation.",
            str(response.content),
        )
        self.assertEqual(PresentationEndorsement.objects.count(), 0)

    def test_judge_unauthenticated_rejected(self) -> None:
        presentation = self._present()
        response = self.client.post(
            "/api/items/fashion-judgements/",
            data={"presentation": presentation.pk},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    # -- presentations list -------------------------------------------------

    def test_list_filters_by_event(self) -> None:
        """GET presentations?event=<id> → only that event's presentations."""
        target = self._present()
        other_event = EventFactory(host_society=self.society)
        with force_check_outcome(self.outcome_success):
            from world.items.services.fashion_presentation import present_outfit

            present_outfit(self.presenter, other_event)

        self.client.force_authenticate(user=self.judge_account)
        response = self.client.get(
            "/api/items/fashion-presentations/",
            data={"event": self.event.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], target.pk)
        self.assertEqual(results[0]["event"], self.event.pk)
