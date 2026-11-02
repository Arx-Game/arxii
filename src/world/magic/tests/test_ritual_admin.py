"""Staff pick a SERVICE ritual's service in the Ritual admin, from the registered list.

Ruled by the maintainer (ledger row service-ritual-path-picked-in-admin): the Rite of
Re-swearing (#4940) and every other SERVICE rite are made on the Ritual admin page by
choosing the service from ``world.magic.service_rituals``; a path not listed is refused.
"""

import importlib

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.required_content import _probe_reswear_ritual
from world.covenants.focus_picks import RESWEAR_SERVICE_PATH
from world.magic.constants import (
    GHOST_TUTOR_SERVICE_PATH,
    IMBUING_SERVICE_PATH,
    RitualExecutionKind,
)
from world.magic.factories import RitualFactory
from world.magic.models import Ritual
from world.magic.service_rituals import SERVICE_RITUAL_FUNCTIONS
from world.magic.services.thread_resonance import THREAD_RESONANCE_SERVICE_PATH
from world.societies.honors import HONORS_SERVICE_PATH

ADD_URL = "admin:arxii_ritual_add"


def _add_form(**fields: str) -> dict:
    """The Ritual add page's fields as a browser posts them, with no inline rows."""
    data = {
        "name": "Rite of Re-swearing",
        "description": "A vow sworn again, one promise traded for another.",
        "narrative_prose": "The oath is spoken a second time.",
        "anima_requirement": "10",
        "participation_rule": "SINGLE_ACTOR",
        "service_function_path": RESWEAR_SERVICE_PATH,
    }
    for prefix in ("requirements", "check_config"):
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "0",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    data.update(fields)
    return data


class PickingTheServiceInTheAdmin(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")

    def setUp(self) -> None:
        self.client.force_login(self.root)

    def test_staff_make_the_rite_of_re_swearing_and_the_required_row_passes(self) -> None:
        self.assertFalse(_probe_reswear_ritual().present)
        page = self.client.get(reverse(ADD_URL))
        choices = dict(page.context["adminform"].form.fields["service_function_path"].choices)
        self.assertEqual(choices[RESWEAR_SERVICE_PATH], "Covenants: Rite of Re-swearing")

        response = self.client.post(reverse(ADD_URL), _add_form())

        self.assertEqual(response.status_code, 302, response.context and response.context["errors"])
        rite = Ritual.objects.get(name="Rite of Re-swearing")
        self.assertEqual(rite.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(rite.service_function_path, RESWEAR_SERVICE_PATH)
        self.assertEqual(rite.anima_requirement, 10)
        self.assertTrue(_probe_reswear_ritual().present)

    def test_an_unregistered_path_is_refused(self) -> None:
        response = self.client.post(reverse(ADD_URL), _add_form(service_function_path="os.system"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("service_function_path", response.context["adminform"].form.errors)
        self.assertFalse(Ritual.objects.filter(name="Rite of Re-swearing").exists())

    def test_a_new_ritual_must_name_its_service(self) -> None:
        response = self.client.post(reverse(ADD_URL), _add_form(service_function_path=""))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["adminform"].form.errors["service_function_path"],
            ["Choose the service this ritual runs."],
        )

    def test_a_rite_holding_an_unlisted_path_stays_editable(self) -> None:
        rite = RitualFactory(name="Old Rite", service_function_path="world.old.rite")
        url = reverse("admin:arxii_ritual_change", args=[rite.pk])

        response = self.client.post(
            url,
            _add_form(
                name="Old Rite",
                anima_requirement="3",
                service_function_path="world.old.rite",
            ),
        )

        self.assertEqual(response.status_code, 302)
        rite.refresh_from_db()
        self.assertEqual(rite.anima_requirement, 3)
        moved = self.client.post(
            url, _add_form(name="Old Rite", service_function_path="world.other.rite")
        )
        self.assertIn("service_function_path", moved.context["adminform"].form.errors)


class TheServiceRegistry(TestCase):
    def test_every_listed_path_imports_to_a_callable(self) -> None:
        for path in SERVICE_RITUAL_FUNCTIONS:
            with self.subTest(path=path):
                module, _, name = path.rpartition(".")
                self.assertTrue(callable(getattr(importlib.import_module(module), name)))

    def test_the_paths_services_find_their_rites_by_are_listed(self) -> None:
        for path in (
            RESWEAR_SERVICE_PATH,
            THREAD_RESONANCE_SERVICE_PATH,
            IMBUING_SERVICE_PATH,
            GHOST_TUTOR_SERVICE_PATH,
            HONORS_SERVICE_PATH,
        ):
            with self.subTest(path=path):
                self.assertIn(path, SERVICE_RITUAL_FUNCTIONS)
