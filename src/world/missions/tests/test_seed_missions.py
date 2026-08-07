"""Tests for the mission board content bootstrap (#2121).

Proves the two acceptance criteria from the issue: a fresh (seeded, not
factory-built) DB's ``mission opportunities`` shows content from the starting
room, and re-running the seed on a populated DB is a no-op. Uses
``seed_dev_database()`` (the Big Button) rather than calling
``seed_missions_dev()`` in isolation — the starter templates' authored CHECK
option needs the "checks" cluster's CheckOutcome catalog and the
character_creation cluster's "wits" stat Trait, exactly as a real deploy
seeds them (cluster ordering in ``world.seeds.clusters``).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse
from world.missions.constants import MissionStatus
from world.missions.models import MissionGiver, MissionNode, MissionTemplate
from world.missions.services.opportunities import opportunities_for_character
from world.missions.services.play import resolve_beat_option
from world.missions.services.report import report_mission
from world.missions.services.run import staff_assign_mission
from world.npc_services.functionaries import functionaries_in_location
from world.seeds.database import seed_dev_database
from world.seeds.tests.content_stub import stub_content_root
from world.seeds.tests.press_helpers import seed_dev_database_with_sample_topup
from world.traits.models import CheckOutcome


class SeedMissionsDevTests(TestCase):
    """The "missions" cluster's row shape + idempotency."""

    #: The three starter templates this cluster itself authors (#2121). Scoped
    #: by name rather than "every template on the giver" because #1035's
    #: tutorial chain deliberately reuses this SAME board giver for its T4
    #: "A Simple Job" template (same room, one shared notice board) — the
    #: giver legitimately carries a 4th template post-#1035 that this test
    #: must not count against the starter set's own shape.
    _STARTER_TEMPLATE_NAMES = frozenset(
        {"The Lost Ledger", "Whispers at the Gate", "The Merchant's Debt"}
    )

    @stub_content_root()
    def test_seeds_one_board_giver_and_three_open_templates(self) -> None:
        seed_dev_database_with_sample_topup()

        # #2862 added a second BOARD giver (the covert Back Room Wall) — fetch
        # the starter board by name, same scoping the template set already uses.
        giver = MissionGiver.objects.get(name="Arx City Notice Board")
        self.assertTrue(giver.is_publishable)
        templates = [t for t in giver.templates.all() if t.name in self._STARTER_TEMPLATE_NAMES]
        self.assertEqual(len(templates), 3)
        risk_tiers = {t.risk_tier for t in templates}
        self.assertEqual(len(risk_tiers), 3, "risk_tier must be distinct across the 3 templates")
        for template in templates:
            self.assertTrue(template.is_active)
            self.assertEqual(template.visibility, "open")
            # #3040 — a BOARD-taken run carries no source_offer, so without
            # an explicit report_to_role the authored MONEY line is orphaned
            # (report_to_role_for returns None, _finish_terminal jumps
            # straight to COMPLETE).
            self.assertIsNotNone(template.report_to_role_id)
            entry = template.nodes.get(is_entry=True)
            option = entry.options.get()
            # Every canonical CheckOutcome tier is covered — resolve_option
            # never raises "route-set incompleteness" for this graph.
            tier_ids = option.routes.values_list("outcome_tier", flat=True)
            outcome_names = set(
                CheckOutcome.objects.filter(pk__in=tier_ids).values_list("name", flat=True)
            )
            self.assertEqual(
                outcome_names,
                {
                    "Critical Failure",
                    "Failure",
                    "Partial Success",
                    "Success",
                    "Critical Success",
                },
            )

    @stub_content_root()
    def test_rerun_is_idempotent_no_op(self) -> None:
        seed_dev_database_with_sample_topup()
        giver_count = MissionGiver.objects.count()
        template_count = MissionTemplate.objects.count()
        node_count = MissionNode.objects.count()

        seed_dev_database()

        self.assertEqual(MissionGiver.objects.count(), giver_count)
        self.assertEqual(MissionTemplate.objects.count(), template_count)
        self.assertEqual(MissionNode.objects.count(), node_count)

    @stub_content_root()
    def test_rerun_preserves_staff_edit_to_template(self) -> None:
        seed_dev_database_with_sample_topup()
        template = MissionTemplate.objects.first()
        template.summary = "Staff-rewritten summary."
        template.save(update_fields=["summary"])

        seed_dev_database()

        template.refresh_from_db()
        self.assertEqual(template.summary, "Staff-rewritten summary.")


class MissionOpportunitiesFromSeededStartingRoomTests(TestCase):
    """The symptom fix: `mission opportunities` shows content from spawn (#2121)."""

    @stub_content_root()
    def test_here_group_non_empty_at_the_seeded_starting_room(self) -> None:
        from world.seeds.character_creation import ensure_canonical_fallback_room

        seed_dev_database_with_sample_topup()
        room = ensure_canonical_fallback_room()

        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        character.location = room
        character.save()

        result = opportunities_for_character(character)

        self.assertTrue(result.here, "mission opportunities' 'here' group must not be empty")
        self.assertTrue(any("Notice Board" in row.source_flavor for row in result.here))


class StarterBoardMissionReportDeliversMoneyTests(TestCase):
    """#3040 — the whole loop, not just the RESOLVED transition.

    Before this fix, the 3 starter BOARD templates never set
    ``report_to_role``: a BOARD-taken run carries no ``source_offer``, so
    ``report_to_role_for`` returned ``None`` and ``_finish_terminal`` jumped
    straight to COMPLETE, silently orphaning the authored MONEY reward line.
    No existing test ever asserted the reporter's purse actually changed —
    this is that regression test.
    """

    @stub_content_root()
    def test_lost_ledger_report_pays_the_reporter(self) -> None:
        from world.seeds.character_creation import ensure_canonical_fallback_room

        seed_dev_database_with_sample_topup()
        room = ensure_canonical_fallback_room()

        template = MissionTemplate.objects.get(name="The Lost Ledger")
        self.assertIsNotNone(template.report_to_role_id)

        # The tutorial cluster's "Threshold Warden" Functionary sits in the
        # SAME canonical starting room as the notice board (#3040) — the
        # reporter never has to travel to find someone to report to.
        self.assertTrue(
            functionaries_in_location(room).filter(role=template.report_to_role).exists(),
            "a Threshold Warden Functionary must stand in the canonical starting room",
        )

        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        character.location = room
        character.save()

        instance = staff_assign_mission(template, character)
        entry = template.nodes.get(is_entry=True)
        option = entry.options.get()

        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success):
            resolve_beat_option(instance, character, option_id=option.pk)

        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.RESOLVED)

        purse = get_or_create_purse(sheet)
        balance_before_report = purse.balance

        report_mission(instance=instance, style="accurate", reporter=character)

        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.COMPLETE)
        purse.refresh_from_db()
        self.assertGreater(
            purse.balance,
            balance_before_report,
            "the authored MONEY reward line must actually reach the reporter's purse",
        )
