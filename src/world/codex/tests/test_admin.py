"""The Codex entry admin leads with who knows an entry (#3775)."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import BeginningsFactory
from world.character_sheets.factories import ProfileBeginningsFactory
from world.clues.factories import ClueFactory, RoomClueFactory
from world.codex.factories import CodexEntryFactory
from world.codex.models import BeginningsCodexGrant, CharacterCodexKnowledge
from world.roster.factories import RosterEntryFactory

CHANGELIST = reverse("admin:arxii_codexentry_changelist")


class CodexEntryAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(username="staffer", is_staff=True, is_superuser=True)
        cls.public = CodexEntryFactory(name="The Shroud", is_public=True)
        cls.granted = CodexEntryFactory(name="The Five Castes")
        cls.beginnings = BeginningsFactory(name="The Blessed")
        cls.grant = BeginningsCodexGrant.objects.create(
            beginnings=cls.beginnings, entry=cls.granted, is_perspective=True
        )
        cls.clued = CodexEntryFactory(name="Under the Catacombs")
        cls.clue = ClueFactory(target_codex_entry=cls.clued, slug="catacomb-ledger")
        cls.unreachable = CodexEntryFactory(name="The Citadel of Absolution")

    def setUp(self):
        self.client.force_login(self.staff)

    def test_changelist_shows_public_and_known_via(self):
        response = self.client.get(CHANGELIST)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Known via", body)
        self.assertIn("1 beginnings", body)
        self.assertIn("(perspective: The Blessed)", body)

    def test_reach_filter_unreachable(self):
        response = self.client.get(CHANGELIST, {"reach": "unreachable"})
        names = [entry.name for entry in response.context["cl"].result_list]
        self.assertEqual(names, [self.unreachable.name])

    def test_reach_filter_buckets(self):
        for value, expected in (
            ("public", {self.public.name}),
            ("granted", {self.granted.name}),
            ("clue", {self.clued.name}),
        ):
            response = self.client.get(CHANGELIST, {"reach": value})
            names = {entry.name for entry in response.context["cl"].result_list}
            self.assertEqual(names, expected, value)

    def test_publish_flips_rows_and_skips_clue_targets(self):
        response = self.client.post(
            CHANGELIST,
            {
                "action": "publish_entries",
                "_selected_action": [self.granted.pk, self.clued.pk],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.granted.refresh_from_db()
        self.clued.refresh_from_db()
        self.assertTrue(self.granted.is_public)
        self.assertFalse(self.clued.is_public)
        self.assertContains(response, "Under the Catacombs")

    def test_unpublish_clears_featured(self):
        featured = CodexEntryFactory(
            name="Featured", is_public=True, is_featured=True, featured_order=1
        )
        self.client.post(
            CHANGELIST,
            {"action": "unpublish_entries", "_selected_action": [featured.pk]},
            follow=True,
        )
        featured.refresh_from_db()
        self.assertFalse(featured.is_public)
        self.assertFalse(featured.is_featured)
        self.assertIsNone(featured.featured_order)

    def test_grant_to_holders_creates_knowledge(self):
        holder = RosterEntryFactory()
        ProfileBeginningsFactory(
            profile=holder.character_sheet.true_profile, beginnings=self.beginnings
        )
        response = self.client.post(
            CHANGELIST,
            {
                "action": "grant_to_holders",
                "_selected_action": [self.granted.pk, self.unreachable.pk],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(roster_entry=holder, entry=self.granted).exists()
        )
        self.assertContains(response, "1 entries still unreachable")

    def test_change_form_renders_grant_inlines(self):
        response = self.client.get(reverse("admin:arxii_codexentry_change", args=[self.granted.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Who knows this", body)
        self.assertIn("beginnings_grants", body)
        self.assertIn("tradition_grants", body)
        self.assertIn("organization_grants", body)

    def test_change_form_clue_inline_shows_placements(self):
        RoomClueFactory(clue=self.clue)
        response = self.client.get(reverse("admin:arxii_codexentry_change", args=[self.clued.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("1 room, 0 triggers", body)

    def test_saving_a_new_grant_inline_reaches_existing_holders(self):
        holder = RosterEntryFactory()
        other = BeginningsFactory(name="The Simple")
        ProfileBeginningsFactory(profile=holder.character_sheet.true_profile, beginnings=other)
        url = reverse("admin:arxii_codexentry_change", args=[self.unreachable.pk])
        response = self.client.get(url)
        data = _form_data(response)
        data.update(
            {
                "beginnings_grants-TOTAL_FORMS": "1",
                "beginnings_grants-INITIAL_FORMS": "0",
                "beginnings_grants-0-beginnings": str(other.pk),
                "beginnings_grants-0-is_perspective": "",
            }
        )
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=holder, entry=self.unreachable
            ).exists()
        )


class OrganizationGrantAdminTests(TestCase):
    def test_creating_a_grant_reaches_current_members(self):
        from world.roster.factories import RosterTenureFactory
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory

        staff = AccountFactory(username="staffer2", is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        organization = OrganizationFactory()
        # OrganizationMembershipFactory's default PersonaFactory builds a bare
        # CharacterSheet with no RosterEntry; a member needs one to be reachable,
        # so build the character through the roster stack instead (#3775).
        tenure = RosterTenureFactory()
        roster_entry = tenure.roster_entry
        persona = roster_entry.character_sheet.primary_persona
        OrganizationMembershipFactory(organization=organization, persona=persona)
        entry = CodexEntryFactory(name="Inner doctrine")
        response = self.client.post(
            reverse("admin:arxii_organizationcodexgrant_add"),
            {"organization": organization.pk, "entry": entry.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry, entry=entry).exists()
        )


def _form_data(response) -> dict:
    """Every field of the rendered admin form, as the browser would post it."""
    data = {}
    for form in (
        response.context["adminform"].form,
        *[fs.formset.management_form for fs in response.context["inline_admin_formsets"]],
    ):
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "on" if value else ""
            elif isinstance(value, list):
                value = [str(v) for v in value]
            data[form.add_prefix(name)] = value
    for fs in response.context["inline_admin_formsets"]:
        prefix = fs.formset.prefix
        data.setdefault(f"{prefix}-TOTAL_FORMS", "0")
        data.setdefault(f"{prefix}-INITIAL_FORMS", "0")
        data.setdefault(f"{prefix}-MIN_NUM_FORMS", "0")
        data.setdefault(f"{prefix}-MAX_NUM_FORMS", "1000")
    return data
