"""Journeys for Tradition teaching (#5326): who may train a Magic skill with whom.

Staff tick, on each Tradition, whether its teachers teach Heroism and Villainy (every
Tradition teaches Reflection, and a fighting style's Traditions teach its skill). No Magic
skill is learned by self-study: a character trains one with a mentor whose active Tradition
teaches it and who holds a rating in it, or through an Academy course, unless a distinction
carries the self-teaching lever. Two journeys live here:

* The weekly run pays an allocation the rule still allows, skips one it no longer allows
  with one line to the character and no action points spent, and a prodigy trains alone.
* Staff tick a Tradition's skills in the admin and author the self-teaching effect on a
  distinction, and the mentor's answer and the creation list follow.
* A mentor must agree (ruled 2026-11-28): naming a mentor only asks her, the training counts as
  having no mentor until she agrees, and she answers from her own account's list, over telnet and
  the REST training endpoint, a game master who holds an NPC included.

The other rows of the feature live where the rest of their story is told:
``test_earning_your_keep_journeys`` (the training command), ``test_tradition_training_journeys``
(character creation) and ``test_academy_skill_course_journeys`` (Academy courses). Those
files import the helpers in ``integration_tests.tradition_teaching_helpers``.

The numbers are hand-worked from the skills docs: weekly training pays ``5 x AP x path level``
development points, plus a mentor's bonus of ``AP x (mentor rating / student rating) x
(relationship tier + 1)`` when mentored, and a step from 11 to 12 costs 10. At rating 11 on both
sides with no relationship, two AP pay 12 mentored (one step, 2 kept) and 10 alone (one step).
Names are invented.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from integration_tests.tradition_teaching_helpers import (
    MENTOR_CANNOT_TEACH_LINE,
    TEACHER_LINE,
    author_the_three_skills,
    filled,
    hold_rating,
    tradition_teaching,
)
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_creation.factories import CharacterDraftFactory
from world.character_sheets.models import CharacterSheet
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import DistinctionEffect
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.magic.factories import (
    CharacterTraditionFactory,
)
from world.magic.models import Tradition
from world.mechanics.constants import SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME
from world.mechanics.test_helpers import grant_lever, lever_target
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.roster.factories import RosterFactory
from world.roster.models import RosterTenure
from world.roster.models.choices import RosterType
from world.skills.models import Skill, TrainingAllocation
from world.skills.services import run_weekly_skill_cron
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitType,
)


def rating_of(sheet: CharacterSheet, skill: Skill) -> int:
    return CharacterTraitValue.objects.get(character=sheet, trait=skill).value


class _TeachingCase(JourneyCase):
    """Ysmay (Dawn Vigil), Hobb (Ashen Court, a Villainy mentor) and the three affinity skills."""

    def setUp(self) -> None:
        super().setUp()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        CheckSystemSetupFactory.create()
        # One check point per rating point, so a skill's points are its rating.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.skills = author_the_three_skills()
        self.villainy = self.skills["Villainy"]
        self.heroism = self.skills["Heroism"]
        self.dawn = tradition_teaching("Dawn Vigil", self.heroism)
        self.ashen = tradition_teaching("Ashen Court", self.villainy)
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        CharacterTraditionFactory(character=self.ysmay.sheet_data, tradition=self.dawn)
        CharacterTraditionFactory(character=self.hobb.sheet_data, tradition=self.ashen)

    def persona_of(self, character) -> int:
        return character.sheet_data.primary_persona.pk

    def ap_of(self, character) -> int:
        return ActionPointPool.get_or_create_for_character(character).current

    def notices(self, character) -> list[str]:
        """The system lines the game has sent ``character``, oldest first."""
        return list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=character.sheet_data,
                message__category=NarrativeCategory.SYSTEM,
            )
            .order_by("pk")
            .values_list("message__body", flat=True)
        )


class TheWeeklyRunAndTheTraditionRule(_TeachingCase):
    """The weekly run asks the rule again for every standing allocation (#5326)."""

    def setUp(self) -> None:
        super().setUp()
        self.pell = self.make_player("Pell", room=self.lantern)
        CharacterTraditionFactory(character=self.pell.sheet_data, tradition=self.dawn)
        self.mira = self.make_player("Mira", room=self.lantern)
        for character, skill in (
            (self.ysmay, self.villainy),
            (self.ysmay, self.heroism),
            (self.hobb, self.villainy),
            (self.pell, self.heroism),
            (self.mira, self.villainy),
        ):
            hold_rating(character.sheet_data, skill, 11)

    def ask_and_agree(self, student, skill, mentor) -> None:
        """The student names the mentor, and the mentor agrees to the one request waiting."""
        self.assertIn(
            f"You ask {mentor.db_key} to teach you {skill.name}. Your training waits until "
            f"{mentor.db_key} agrees.",
            self.telnet(
                student, f"training add skill={skill.pk} ap=2 mentor={self.persona_of(mentor)}"
            ),
        )
        self.assertIn(
            f"You agree to teach {student.db_key} {skill.name}.",
            self.telnet(mentor, "training accept 1"),
        )

    def test_a_mentored_week_is_paid_and_a_stale_allocation_is_skipped_with_a_notice(self) -> None:
        self.ask_and_agree(self.ysmay, self.villainy, self.hobb)
        self.ask_and_agree(self.ysmay, self.heroism, self.pell)
        # Staff take Villainy off the Ashen Court's list before the week turns, so Hobb's
        # Tradition no longer teaches what she asked him for.
        self.ashen.taught_skills.remove(self.villainy)
        ap_before = self.ap_of(self.ysmay)

        run_weekly_skill_cron()

        # Heroism with Pell pays as any mentored week does: 10 of her own and 2 of his
        # make 12, a step from 11 to 12 with 2 kept.
        self.assertEqual(rating_of(self.ysmay.sheet_data, self.heroism), 12)
        # Villainy with Hobb did not run: no development, no action points, one line why.
        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 11)
        self.assertEqual(self.ap_of(self.ysmay), ap_before - 2)
        self.assertEqual(
            self.notices(self.ysmay),
            [
                "Hobb agreed to teach you Villainy.",
                "Pell agreed to teach you Heroism.",
                "Your weekly training in Villainy did not run, and no action points were "
                "spent. " + MENTOR_CANNOT_TEACH_LINE.format(mentor="Hobb", skill="Villainy"),
            ],
        )
        # The row stays, so she can choose another mentor and have it run next week.
        self.assertTrue(
            TrainingAllocation.objects.filter(
                character=self.ysmay.sheet_data, skill=self.villainy
            ).exists()
        )

    def test_a_week_with_nothing_stale_sends_no_notice(self) -> None:
        self.ask_and_agree(self.ysmay, self.villainy, self.hobb)

        run_weekly_skill_cron()

        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 12)
        self.assertEqual(self.notices(self.ysmay), ["Hobb agreed to teach you Villainy."])

    def test_a_week_before_the_mentor_agrees_pays_nothing_and_says_who_has_not(self) -> None:
        self.telnet(
            self.ysmay,
            f"training add skill={self.villainy.pk} ap=2 mentor={self.persona_of(self.hobb)}",
        )
        ap_before = self.ap_of(self.ysmay)

        run_weekly_skill_cron()

        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 11)
        self.assertEqual(self.ap_of(self.ysmay), ap_before)
        self.assertEqual(
            self.notices(self.ysmay),
            [
                "Your weekly training in Villainy did not run, and no action points were "
                "spent. Hobb has not agreed to teach you yet."
            ],
        )

    def test_the_prodigy_trains_alone_and_a_character_without_the_lever_does_not(self) -> None:
        # A distinction effect on the self-teaching target, the way staff author it.
        grant_lever(self.mira.sheet_data, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)

        self.assertIn(
            "Training allocation set for Villainy.",
            self.telnet(self.mira, f"training add skill={self.villainy.pk} ap=2"),
        )
        self.assertIn(
            TEACHER_LINE.format(skill="Villainy"),
            self.telnet(self.ysmay, f"training add skill={self.villainy.pk} ap=2"),
        )
        mira_ap = self.ap_of(self.mira)

        run_weekly_skill_cron()

        # Alone, 5 x 2 AP x path level 1 is 10 development points: one step from 11 to 12.
        self.assertEqual(rating_of(self.mira.sheet_data, self.villainy), 12)
        self.assertEqual(self.ap_of(self.mira), mira_ap - 2)
        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 11)
        self.assertFalse(
            TrainingAllocation.objects.filter(character=self.ysmay.sheet_data).exists()
        )

    def test_an_allocation_saved_before_the_rule_with_no_mentor_is_skipped_with_a_notice(
        self,
    ) -> None:
        """A row with no mentor that predates the rule is skipped, not paid, and she is told."""
        TrainingAllocation.objects.create(
            character=self.ysmay.sheet_data, skill=self.villainy, ap_amount=2
        )
        ap_before = self.ap_of(self.ysmay)

        run_weekly_skill_cron()

        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 11)
        self.assertEqual(self.ap_of(self.ysmay), ap_before)
        self.assertEqual(
            self.notices(self.ysmay),
            [
                "Your weekly training in Villainy did not run, and no action points were "
                "spent. " + TEACHER_LINE.format(skill="Villainy")
            ],
        )


class AMentorAnswersHerRequests(_TeachingCase):
    """Ysmay names Hobb; Hobb is asked, lists the request, agrees, and the week then pays (#5326).

    Maintainer (2026-11-28): "The mentor must agree". Until Hobb agrees the allocation counts as
    having no mentor, so a magical skill does not train.
    """

    def setUp(self) -> None:
        super().setUp()
        hold_rating(self.ysmay.sheet_data, self.villainy, 11)
        hold_rating(self.hobb.sheet_data, self.villainy, 11)
        self.pronoun = self.ysmay.sheet_data.pronoun_object
        self.add = f"training add skill={self.villainy.pk} ap=2 mentor={self.persona_of(self.hobb)}"

    def test_a_player_mentor_is_asked_listed_and_agrees_and_the_week_pays(self) -> None:
        asked = self.telnet(self.ysmay, self.add)
        self.assertIn(
            "You ask Hobb to teach you Villainy. Your training waits until Hobb agrees.", asked
        )
        self.assertIn(f"Ysmay asks you to teach {self.pronoun} Villainy.", self.notices(self.hobb))
        self.assertIn(
            "(mentor: Hobb, waiting for Hobb to agree)", self.telnet(self.ysmay, "training")
        )
        ap_before = self.ap_of(self.ysmay)

        run_weekly_skill_cron()

        # Before Hobb agrees, the week counts as having no mentor: nothing is paid.
        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 11)
        self.assertEqual(self.ap_of(self.ysmay), ap_before)
        self.assertEqual(
            self.notices(self.ysmay),
            [
                "Your weekly training in Villainy did not run, and no action points were "
                "spent. Hobb has not agreed to teach you yet."
            ],
        )

        listed = self.telnet(self.hobb, "training requests")
        self.assertIn("Asked to teach:", listed)
        self.assertIn(f"1. Ysmay asks Hobb to teach {self.pronoun} Villainy", listed)
        self.assertIn(
            "You agree to teach Ysmay Villainy.", self.telnet(self.hobb, "training accept 1")
        )
        self.assertEqual(self.notices(self.ysmay)[-1], "Hobb agreed to teach you Villainy.")
        self.assertIn("Hobb teaches Ysmay Villainy", self.telnet(self.hobb, "training requests"))
        self.assertIn("(mentor: Hobb)", self.telnet(self.ysmay, "training"))

        run_weekly_skill_cron()

        # Mentored, two AP pay 12: one step from 11 to 12, and two points kept.
        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 12)
        self.assertEqual(self.ap_of(self.ysmay), ap_before - 2)

    def test_declining_and_stopping_clear_the_mentor_and_tell_the_student(self) -> None:
        self.telnet(self.ysmay, self.add)

        self.assertIn(
            "You decline to teach Ysmay Villainy.", self.telnet(self.hobb, "training decline 1")
        )

        row = TrainingAllocation.objects.get(character=self.ysmay.sheet_data)
        self.assertIsNone(row.mentor_id)
        self.assertEqual(self.notices(self.ysmay), ["Hobb declined to teach you Villainy."])
        self.assertIn(
            "Nobody has asked you to teach, and you teach nobody.",
            self.telnet(self.hobb, "training requests"),
        )
        self.telnet(self.ysmay, f"training update id={row.pk} mentor={self.persona_of(self.hobb)}")
        self.telnet(self.hobb, "training accept 1")

        self.assertIn(
            "You stop teaching Ysmay Villainy.", self.telnet(self.hobb, "training stop Ysmay")
        )

        row.refresh_from_db()
        self.assertIsNone(row.mentor_id)
        self.assertIsNone(row.mentor_accepted_at)
        self.assertEqual(self.notices(self.ysmay)[-1], "Hobb stopped teaching you Villainy.")
        self.assertIn(
            "You are not teaching anyone called Ysmay.",
            self.telnet(self.hobb, "training stop Ysmay"),
        )

    def test_nobody_else_may_answer_for_hobb(self) -> None:
        self.telnet(self.ysmay, self.add)
        pell = self.make_player("Pell", room=self.lantern)

        for character in (self.ysmay, pell):
            self.assertIn(
                "Nobody has asked you to teach, and you teach nobody.",
                self.telnet(character, "training requests"),
            )
            self.assertIn(
                "No request number 1. Type training requests to see them.",
                self.telnet(character, "training accept 1"),
            )
        row = TrainingAllocation.objects.get(character=self.ysmay.sheet_data)
        self.assertIsNone(row.mentor_accepted_at)


class AGameMasterAnswersForAnNpc(_TeachingCase):
    """A game master who holds Magister Vey answers for her from her own list (#5326).

    Maintainer (2026-11-28): "The mentor is also not unlikely to be a GM'd NPC, so we need to
    accomodate that as well". The list belongs to the account, and each row names which of the
    account's characters was asked.
    """

    def setUp(self) -> None:
        super().setUp()
        self.reflection = self.skills["Reflection"]
        self.odalys = self.make_player("Odalys", room=self.lantern)
        self.vey = self.make_player("Magister Vey", room=self.lantern)
        # Vey stands on the NPC shelf and Odalys's account holds her tenure.
        entry = self.vey.sheet_data.roster_entry
        entry.roster = RosterFactory(roster_type=RosterType.NPC)
        entry.save()
        tenure = RosterTenure.objects.get(roster_entry=entry, end_date__isnull=True)
        tenure.player_data = RosterTenure.objects.get(
            roster_entry__character_sheet=self.odalys.sheet_data, end_date__isnull=True
        ).player_data
        tenure.save()
        CharacterTraditionFactory(character=self.vey.sheet_data, tradition=self.dawn)
        hold_rating(self.vey.sheet_data, self.reflection, 11)
        self.pronoun = self.ysmay.sheet_data.pronoun_object

    def ask_vey(self, student, skill) -> None:
        self.telnet(
            student,
            f"training add skill={skill.pk} ap=2 mentor={self.persona_of(self.vey)}",
        )

    def test_the_gm_reads_and_answers_the_requests_addressed_to_her_npc(self) -> None:
        self.ask_vey(self.ysmay, self.reflection)

        listed = self.telnet(self.odalys, "training requests")

        self.assertIn(f"1. Ysmay asks Magister Vey to teach {self.pronoun} Reflection", listed)
        self.assertIn(
            "You agree to teach Ysmay Reflection.", self.telnet(self.odalys, "training accept 1")
        )
        self.assertIn("Magister Vey agreed to teach you Reflection.", self.notices(self.ysmay))
        row = TrainingAllocation.objects.get(character=self.ysmay.sheet_data)
        self.assertIsNotNone(row.mentor_accepted_at)

    def test_an_npc_that_cannot_teach_is_refused_by_name_not_as_you(self) -> None:
        # The Dawn Vigil does not tick Villainy, and Vey holds no rating in it either.
        hold_rating(self.ysmay.sheet_data, self.villainy, 11)
        self.ask_vey(self.ysmay, self.villainy)

        told = self.telnet(self.odalys, "training accept 1")

        self.assertIn("Magister Vey's Tradition does not teach Villainy.", told)
        self.assertNotIn("Your Tradition", told)
        row = TrainingAllocation.objects.get(character=self.ysmay.sheet_data)
        self.assertIsNone(row.mentor_accepted_at)
        self.assertNotIn(
            "Magister Vey's Tradition does not teach Villainy.", self.notices(self.ysmay)
        )

    def test_a_character_the_gm_does_not_hold_has_no_say(self) -> None:
        self.ask_vey(self.ysmay, self.reflection)

        for character in (self.hobb, self.ysmay):
            self.assertIn(
                "No request number 1. Type training requests to see them.",
                self.telnet(character, "training accept 1"),
            )


class AMentorAnswersOverTheWeb(_TeachingCase):
    """The training viewset carries the same mentoring answers as the command (#5326)."""

    url = "/api/skills/training-allocations/"

    def setUp(self) -> None:
        super().setUp()
        hold_rating(self.ysmay.sheet_data, self.villainy, 11)
        hold_rating(self.hobb.sheet_data, self.villainy, 11)
        self.pell = self.make_player("Pell", room=self.lantern)
        telnet_line = (
            f"training add skill={self.villainy.pk} ap=2 mentor={self.persona_of(self.hobb)}"
        )
        self.telnet(self.ysmay, telnet_line)
        self.row = TrainingAllocation.objects.get(character=self.ysmay.sheet_data)
        self.hobb_client = self.api(self.account_of(self.hobb))

    def test_the_mentor_lists_her_request_and_the_row_carries_no_account(self) -> None:
        listed = self.hobb_client.get(f"{self.url}mentoring/")

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(
            listed.json(),
            {
                "requests": [
                    {
                        "allocation_id": self.row.pk,
                        "student_name": "Ysmay",
                        "student_pronoun": self.ysmay.sheet_data.pronoun_object,
                        "mentor_name": "Hobb",
                        "skill_name": "Villainy",
                    }
                ],
                "students": [],
            },
        )
        stranger = self.api(self.account_of(self.pell)).get(f"{self.url}mentoring/")
        self.assertEqual(stranger.json(), {"requests": [], "students": []})

    def test_an_id_outside_what_the_requester_may_answer_for_is_a_404(self) -> None:
        for character in (self.ysmay, self.pell):
            client = self.api(self.account_of(character))
            for action in ("accept-mentoring", "decline-mentoring", "stop-mentoring"):
                response = client.post(f"{self.url}{self.row.pk}/{action}/")
                self.assertEqual(response.status_code, 404, (character.db_key, action))
        missing = self.hobb_client.post(f"{self.url}99999/accept-mentoring/")
        self.assertEqual(missing.status_code, 404)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.mentor_accepted_at)

    def test_accepting_declining_and_stopping_answer_as_the_telnet_command_does(self) -> None:
        accepted = self.hobb_client.post(f"{self.url}{self.row.pk}/accept-mentoring/")

        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.json(), {"detail": "You agree to teach Ysmay Villainy."})
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.mentor_accepted_at)
        students = self.hobb_client.get(f"{self.url}mentoring/").json()
        self.assertEqual([row["skill_name"] for row in students["students"]], ["Villainy"])
        self.assertEqual(students["requests"], [])
        own = self.api(self.account_of(self.ysmay)).get(self.url).json()["allocations"][0]
        self.assertIsNotNone(own["mentor_accepted_at"])
        self.assertFalse(own["mentor_waiting"])

        declined = self.hobb_client.post(f"{self.url}{self.row.pk}/decline-mentoring/")
        self.assertEqual(declined.status_code, 400, declined.content)
        self.assertEqual(declined.json(), {"detail": "You already agreed to teach Ysmay Villainy."})
        stopped = self.hobb_client.post(f"{self.url}{self.row.pk}/stop-mentoring/")
        self.assertEqual(stopped.status_code, 200, stopped.content)
        self.assertEqual(stopped.json(), {"detail": "You stop teaching Ysmay Villainy."})
        self.row.refresh_from_db()
        self.assertIsNone(self.row.mentor_id)
        self.assertEqual(self.notices(self.ysmay)[-1], "Hobb stopped teaching you Villainy.")

    def test_a_mentor_who_cannot_teach_is_refused_with_the_sentence(self) -> None:
        # Staff take Villainy off the Ashen Court's list after Ysmay asked.
        self.ashen.taught_skills.remove(self.villainy)

        refused = self.hobb_client.post(f"{self.url}{self.row.pk}/accept-mentoring/")

        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(refused.json(), {"detail": "Your Tradition does not teach Villainy."})
        self.row.refresh_from_db()
        self.assertIsNone(self.row.mentor_accepted_at)

    def test_declining_over_the_web_clears_the_mentor(self) -> None:
        declined = self.hobb_client.post(f"{self.url}{self.row.pk}/decline-mentoring/")

        self.assertEqual(declined.status_code, 200, declined.content)
        self.assertEqual(declined.json(), {"detail": "You decline to teach Ysmay Villainy."})
        self.row.refresh_from_db()
        self.assertIsNone(self.row.mentor_id)
        self.assertEqual(self.notices(self.ysmay), ["Hobb declined to teach you Villainy."])

    def test_staff_may_answer_for_any_mentor(self) -> None:
        staff = AccountFactory(is_staff=True)

        accepted = self.api(staff).post(f"{self.url}{self.row.pk}/accept-mentoring/")

        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.mentor_accepted_at)


class StaffChoosingWhatATraditionTeaches(_TeachingCase):
    """Staff tick a Tradition's skills and author the self-teaching effect in the admin."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        # The Ashen Court's list starts empty: staff have not ticked anything on it yet.
        self.ashen.taught_skills.clear()
        self.reflection = self.skills["Reflection"]
        hold_rating(self.hobb.sheet_data, self.villainy, 11)
        self.mira = self.make_player("Mira", room=self.lantern)
        hold_rating(self.mira.sheet_data, self.villainy, 11)

    def tick(self, tradition: Tradition, *skills: Skill):
        """Post the Tradition's change form with exactly these skills ticked."""
        url = reverse("admin:arxii_tradition_change", args=[tradition.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            data.update(filled(inline.formset.management_form))
            for form in inline.formset.forms:
                data.update(filled(form))
        data["taught_skills"] = [str(skill.pk) for skill in skills]
        return self.client.post(url, data)

    def creation_list(self, tradition: Tradition) -> list[str]:
        """The Magic skills a draft of ``tradition`` is offered on the Gift stage."""
        account = AccountFactory()
        draft = CharacterDraftFactory(account=account, selected_tradition=tradition)
        response = self.api(account).get(f"/api/character-creation/drafts/{draft.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return [skill["name"] for skill in response.json()["magic_training"]["skills"]]

    def test_a_tick_opens_the_skill_to_mentors_and_to_creation(self) -> None:
        mentor = self.persona_of(self.hobb)
        line = f"training add skill={self.villainy.pk} ap=2 mentor={mentor}"
        # Asking checks nothing about Hobb, so Ysmay learns nothing about him; he is the one
        # told, when he answers, that his Tradition does not teach it.
        self.assertIn(
            "You ask Hobb to teach you Villainy. Your training waits until Hobb agrees.",
            self.telnet(self.ysmay, line),
        )
        self.assertIn(
            "Your Tradition does not teach Villainy.", self.telnet(self.hobb, "training accept 1")
        )
        self.assertEqual(self.creation_list(self.ashen), ["Reflection"])

        # Reflection is taught by every Tradition, so the chooser does not list it.
        refused = self.tick(self.ashen, self.reflection)
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "Select a valid choice")
        self.assertFalse(self.ashen.taught_skills.exists())

        saved = self.tick(self.ashen, self.villainy)
        self.assertEqual(saved.status_code, 302, saved.context and saved.context.get("errors"))
        self.assertEqual(list(self.ashen.taught_skills.all()), [self.villainy])

        self.assertIn(
            "You agree to teach Ysmay Villainy.", self.telnet(self.hobb, "training accept 1")
        )
        self.assertEqual(self.creation_list(self.ashen), ["Reflection", "Villainy"])
        self.assertEqual(self.creation_list(self.dawn), ["Heroism", "Reflection"])

    def test_the_self_teaching_effect_staff_author_lets_its_holder_train_alone(self) -> None:
        target = lever_target(SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME)
        prodigy = DistinctionFactory(name="Magical Prodigy")
        posted = self.client.post(
            reverse("admin:arxii_distinctioneffect_add"),
            {
                "distinction": prodigy.pk,
                "target": target.pk,
                "value_per_rank": "1",
                "amplifies_sources_by": "",
                "modifier_size": "",
                "description": "",
                "amount_input": "",
                "amount_per": "1",
                "amount_cap": "",
                "amount_check_type": "",
                "amount_thread_trait": "",
                "amount_thread_facet": "",
                "rank_sizes-TOTAL_FORMS": "0",
                "rank_sizes-INITIAL_FORMS": "0",
                "rank_sizes-MIN_NUM_FORMS": "0",
                "rank_sizes-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(posted.status_code, 302, posted.content)
        self.assertEqual(DistinctionEffect.objects.get(distinction=prodigy).target, target)

        line = f"training add skill={self.villainy.pk} ap=2"
        # Holding the distinction is what grants it: before she does, Mira needs a teacher.
        self.assertIn(TEACHER_LINE.format(skill="Villainy"), self.telnet(self.mira, line))
        grant_distinction(self.mira.sheet_data, prodigy, origin=DistinctionOrigin.GM_AWARD)

        self.assertIn("Training allocation set for Villainy.", self.telnet(self.mira, line))
        self.assertIn(TEACHER_LINE.format(skill="Villainy"), self.telnet(self.ysmay, line))
