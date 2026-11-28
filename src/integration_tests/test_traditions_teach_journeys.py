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

The other rows of the feature live where the rest of their story is told:
``test_earning_your_keep_journeys`` (the training command), ``test_tradition_training_journeys``
(character creation) and ``test_academy_skill_course_journeys`` (Academy courses). Those
files import the three helpers below.

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
from integration_tests.test_refused_admin_saves_journeys import _filled
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.sheet_writers import set_skill_values
from world.character_sheets.models import CharacterSheet
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import DistinctionEffect
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.magic.factories import (
    CharacterTraditionFactory,
    TraditionFactory,
    ensure_conversion_pairs,
)
from world.magic.models import Affinity, Tradition
from world.mechanics.constants import SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME
from world.mechanics.test_helpers import grant_lever, lever_target
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.skills.factories import MagicSkillFactory
from world.skills.models import Skill, TrainingAllocation
from world.skills.services import run_weekly_skill_cron
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitChangeSource,
    TraitType,
)

TEACHER_LINE = "{skill} needs a teacher. Choose a mentor whose Tradition teaches it."
WRONG_TRADITION_LINE = (
    "{mentor}'s Tradition does not teach {skill}. Choose a mentor whose Tradition does."
)


def author_the_three_skills() -> dict[str, Skill]:
    """Staff link one Magic skill to each affinity: Heroism, Reflection and Villainy.

    Returns the skills by name. Reflection is the Primal affinity's skill, so every Tradition
    teaches it; Heroism (Celestial) and Villainy (Abyssal) are taught only when ticked.
    """
    celestial, primal, abyssal = ensure_conversion_pairs()
    skills: dict[str, Skill] = {}
    for affinity, name in ((celestial, "Heroism"), (primal, "Reflection"), (abyssal, "Villainy")):
        skill = MagicSkillFactory(name=name)
        affinity.skill = skill
        affinity.save()
        skills[name] = skill
    Affinity.objects.clear_cache()
    return skills


def tradition_teaching(name: str, *ticked: Skill) -> Tradition:
    """A Tradition whose teachers teach the ticked affinity skills (and Reflection, unticked)."""
    tradition = TraditionFactory(name=name)
    tradition.taught_skills.add(*ticked)
    return tradition


def hold_rating(sheet: CharacterSheet, skill: Skill, rating: int) -> None:
    """The character leaves creation holding ``skill`` at ``rating``, as a mentor must."""
    set_skill_values(
        sheet,
        {skill: rating},
        {},
        source=TraitChangeSource.CHARACTER_CREATION,
        enforce_caps=False,
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

    def test_a_mentored_week_is_paid_and_a_stale_allocation_is_skipped_with_a_notice(self) -> None:
        self.assertIn(
            "Training allocation set for Villainy.",
            self.telnet(
                self.ysmay,
                f"training add skill={self.villainy.pk} ap=2 mentor={self.persona_of(self.hobb)}",
            ),
        )
        self.assertIn(
            "Training allocation set for Heroism.",
            self.telnet(
                self.ysmay,
                f"training add skill={self.heroism.pk} ap=2 mentor={self.persona_of(self.pell)}",
            ),
        )
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
                "Your weekly training in Villainy did not run, and no action points were "
                "spent. " + WRONG_TRADITION_LINE.format(mentor="Hobb", skill="Villainy")
            ],
        )
        # The row stays, so she can choose another mentor and have it run next week.
        self.assertTrue(
            TrainingAllocation.objects.filter(
                character=self.ysmay.sheet_data, skill=self.villainy
            ).exists()
        )

    def test_a_week_with_nothing_stale_sends_no_notice(self) -> None:
        self.telnet(
            self.ysmay,
            f"training add skill={self.villainy.pk} ap=2 mentor={self.persona_of(self.hobb)}",
        )

        run_weekly_skill_cron()

        self.assertEqual(rating_of(self.ysmay.sheet_data, self.villainy), 12)
        self.assertEqual(self.notices(self.ysmay), [])

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
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            data.update(_filled(inline.formset.management_form))
            for form in inline.formset.forms:
                data.update(_filled(form))
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
        self.assertIn(
            WRONG_TRADITION_LINE.format(mentor="Hobb", skill="Villainy"),
            self.telnet(self.ysmay, line),
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

        self.assertIn("Training allocation set for Villainy.", self.telnet(self.ysmay, line))
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
