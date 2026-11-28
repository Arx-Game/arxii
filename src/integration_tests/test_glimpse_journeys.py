"""Journeys for the Glimpse (#5292): an answer gives its card free in character creation,
a memory state is marked by a card, and a Glimpse written in play gives the same cards.

The owner's rules behind these: each of Trigger, The Reflection, Tone and Consequence
gives one bonus, a Glimpse-only card; every part takes one answer; nothing pays CG points;
"people get the bonuses when they finally do find out their glimpse and it is defined in
play".
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.character_creation.constants import OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import GlimpseMemory, GlimpseState, GlimpseTagAxis
from world.magic.factories import GlimpseTagFactory
from world.magic.models import CharacterAura, CharacterGlimpseTag
from world.roster.factories import RosterTenureFactory
from world.roster.models import RosterEntry


def _answer(name: str, axis: GlimpseTagAxis, card: str | None = None, **card_kwargs):
    """A Glimpse answer and, when ``card`` is named, the card it gives."""
    tag = GlimpseTagFactory(name=name, axis=axis, slug=f"journey-{name.lower()}")
    if card is None:
        return tag, None
    # The card's own price plays no part: a Glimpse card is free whatever it costs.
    distinction = DistinctionFactory(name=card, cost_per_rank=20, **card_kwargs)
    DistinctionOfferFactory(distinction=distinction, chapter=OfferChapter.GLIMPSE, glimpse_tag=tag)
    return tag, distinction


class GlimpseJourneyBase(FinalizationTestMixin, JourneyCase):
    """Four card-giving answers, a second Tone answer, two that give nothing, the mystery card."""

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Glimpse", height_min=900, height_max=1000)
        self.crisis, self.crisisborn = _answer("Crisis", GlimpseTagAxis.TRIGGER, "Crisisborn")
        self.radiant, self.glimmering = _answer("Radiant", GlimpseTagAxis.REFLECTION, "Glimmering")
        self.wonder, self.wonderstruck = _answer("Wonder", GlimpseTagAxis.TONE, "Wonderstruck")
        self.terror, self.dreadmarked = _answer("Terror", GlimpseTagAxis.TONE, "Dreadmarked")
        self.loss, self.bereft = _answer(
            "Loss", GlimpseTagAxis.CONSEQUENCE, "Bereft", secret_by_default=True
        )
        self.public, _ = _answer("Public", GlimpseTagAxis.WITNESS)
        self.mystery = DistinctionFactory(name="Glimpse Mystery", cost_per_rank=0)
        for state in (GlimpseMemory.BLACKED_OUT, GlimpseMemory.NO_MEMORY):
            DistinctionOfferFactory(
                distinction=self.mystery, chapter=OfferChapter.GLIMPSE, glimpse_memory=state
            )
        self.client = self.api(self.account)

    def save(self, draft, **draft_data):
        return self.client.patch(
            f"/api/character-creation/drafts/{draft.id}/",
            {"draft_data": draft_data},
            format="json",
        )

    @staticmethod
    def cards(response) -> dict[str, int]:
        """Card name -> the price the draft holds it at."""
        return {
            entry["distinction_name"]: entry["cost"]
            for entry in response.data["draft_data"]["distinctions"]
        }

    @staticmethod
    def held(sheet) -> set[str]:
        return set(
            CharacterDistinction.objects.filter(character=sheet).values_list(
                "distinction__name", flat=True
            )
        )

    def play(self, sheet):
        """Put the journey's account in the finished character's seat; return the aura."""
        entry = RosterEntry.objects.get(character_sheet=sheet)
        RosterTenureFactory(
            player_data=PlayerData.objects.get_or_create(account=self.account)[0],
            roster_entry=entry,
        )
        # A factory row is not a tenure service: the entry's memoised tenures are the
        # ones finalize read, so they are dropped by hand.
        entry.invalidate_tenure_cache()
        return CharacterAura.objects.get(character=sheet)


class TheGlimpseInCharacterCreation(GlimpseJourneyBase):
    def test_an_answer_gives_its_card_free_and_the_card_leaves_with_the_answer(self) -> None:
        draft = self._create_base_draft()
        url = f"/api/character-creation/drafts/{draft.id}/"
        points = self.client.get(url).data["cg_points_remaining"]

        answered = self.save(
            draft,
            glimpse_tag_ids=[
                self.crisis.id,
                self.radiant.id,
                self.wonder.id,
                self.loss.id,
                self.public.id,
            ],
        )
        self.assertEqual(answered.status_code, 200, answered.content)
        # Four cards, none for the Witness answer, each free; the points do not move.
        self.assertEqual(
            self.cards(answered),
            {"Crisisborn": 0, "Glimmering": 0, "Wonderstruck": 0, "Bereft": 0},
        )
        self.assertEqual(answered.data["cg_points_remaining"], points)

        # A second answer replaces the first on the page; the save carries the new one
        # and the card swaps.
        swapped = self.save(
            draft,
            glimpse_tag_ids=[
                self.crisis.id,
                self.radiant.id,
                self.terror.id,
                self.loss.id,
                self.public.id,
            ],
        )
        self.assertEqual(
            self.cards(swapped),
            {"Crisisborn": 0, "Glimmering": 0, "Dreadmarked": 0, "Bereft": 0},
        )
        self.assertEqual(swapped.data["cg_points_remaining"], points)

        # Two answers in one part are refused, and nothing changes.
        both = self.save(draft, glimpse_tag_ids=[self.wonder.id, self.terror.id])
        self.assertEqual(both.status_code, 400, both.content)
        self.assertIn("Tone takes one answer.", str(both.data))

        dropped = self.save(draft, glimpse_tag_ids=[self.public.id])
        self.assertEqual(self.cards(dropped), {})
        self.assertEqual(dropped.data["cg_points_remaining"], points)

    def test_a_blackout_and_no_memory_are_marked_by_a_card_and_cost_nothing(self) -> None:
        draft = self._create_base_draft()
        url = f"/api/character-creation/drafts/{draft.id}/"
        points = self.client.get(url).data["cg_points_remaining"]
        answers = [self.crisis.id, self.radiant.id, self.wonder.id, self.loss.id]
        self.save(draft, glimpse_tag_ids=answers)

        # A blackout takes The Reflection and Tone together and keeps the rest.
        blackout = self.save(draft, glimpse_memory=GlimpseMemory.BLACKED_OUT)
        self.assertEqual(self.cards(blackout), {"Crisisborn": 0, "Bereft": 0, "Glimpse Mystery": 0})
        self.assertEqual(blackout.data["cg_points_remaining"], points)
        listed = self.client.get(f"{url}offers/?chapter=glimpse")
        self.assertEqual(listed.data["offers"], [])
        self.assertEqual(
            [(card["name"], card["axis"]) for card in listed.data["glimpse_cards"]],
            [("Crisisborn", "TRIGGER"), ("Bereft", "CONSEQUENCE"), ("Glimpse Mystery", "")],
        )

        # Unticking brings the earlier answers and their cards back.
        remembered = self.save(draft, glimpse_memory=GlimpseMemory.REMEMBERED)
        self.assertEqual(
            self.cards(remembered),
            {"Crisisborn": 0, "Glimmering": 0, "Wonderstruck": 0, "Bereft": 0},
        )

        # No memory asks no part and gives the marking card alone; later gives nothing.
        amnesiac = self.save(draft, glimpse_memory=GlimpseMemory.NO_MEMORY)
        self.assertEqual(self.cards(amnesiac), {"Glimpse Mystery": 0})
        later = self.save(draft, glimpse_memory=GlimpseMemory.LATER)
        self.assertEqual(self.cards(later), {})
        for response in (amnesiac, later):
            self.assertEqual(response.data["cg_points_remaining"], points)
        # The answers are still in the draft for a change of mind.
        self.assertEqual(later.data["draft_data"]["glimpse_tag_ids"], answers)

    def test_a_remembered_glimpse_reaches_the_character(self) -> None:
        draft = self._create_base_draft()
        self.save(
            draft,
            glimpse_tag_ids=[self.crisis.id, self.wonder.id, self.public.id],
            glimpse_story="The lamps all bowed.",
        )
        draft.refresh_from_db()
        sheet = finalize_character(draft, add_to_roster=True).sheet_data
        aura = CharacterAura.objects.get(character=sheet)

        self.assertEqual(aura.glimpse_memory, GlimpseMemory.REMEMBERED)
        self.assertEqual(aura.glimpse_story, "The lamps all bowed.")
        self.assertEqual(
            set(CharacterGlimpseTag.objects.filter(aura=aura).values_list("tag__name", flat=True)),
            {"Crisis", "Wonder", "Public"},
        )
        for card in (self.crisisborn, self.wonderstruck):
            held = CharacterDistinction.objects.get(character=sheet, distinction=card)
            self.assertEqual(held.from_glimpse_id, aura.pk)
        staff = self.api(AccountFactory(is_staff=True))
        shown = staff.get(f"/api/character-sheets/{sheet.pk}/").data["magic"]["aura"]
        self.assertEqual(shown["glimpse_memory"], GlimpseMemory.REMEMBERED)

    def test_a_blackout_reaches_the_character_without_what_it_took(self) -> None:
        draft = self._create_base_draft()
        self.save(
            draft,
            glimpse_tag_ids=[self.crisis.id, self.radiant.id, self.wonder.id],
            glimpse_memory=GlimpseMemory.BLACKED_OUT,
            glimpse_story="Then I was standing in the ash.",
        )
        draft.refresh_from_db()
        sheet = finalize_character(draft, add_to_roster=True).sheet_data
        aura = CharacterAura.objects.get(character=sheet)

        self.assertEqual(aura.glimpse_memory, GlimpseMemory.BLACKED_OUT)
        self.assertEqual(aura.glimpse_story, "Then I was standing in the ash.")
        self.assertEqual(
            list(CharacterGlimpseTag.objects.filter(aura=aura).values_list("tag__name", flat=True)),
            ["Crisis"],
        )
        self.assertEqual(self.held(sheet), {"Crisisborn", "Glimpse Mystery"})
        marker = CharacterDistinction.objects.get(character=sheet, distinction=self.mystery)
        self.assertEqual(marker.from_glimpse_id, aura.pk)

    def test_a_beginning_with_no_memory_of_the_glimpse_asks_nothing(self) -> None:
        self.beginnings.no_glimpse_memory = True
        self.beginnings.save()
        draft = self._create_base_draft()
        saved = self.save(
            draft,
            glimpse_tag_ids=[self.crisis.id, self.wonder.id],
            glimpse_memory=GlimpseMemory.REMEMBERED,
            glimpse_story="A story nobody asked for.",
        )
        # Whatever the draft holds, the Sleeper has no memory.
        self.assertEqual(self.cards(saved), {"Glimpse Mystery": 0})
        draft.refresh_from_db()
        sheet = finalize_character(draft, add_to_roster=True).sheet_data
        aura = CharacterAura.objects.get(character=sheet)

        self.assertEqual(aura.glimpse_memory, GlimpseMemory.NO_MEMORY)
        self.assertEqual(aura.glimpse_story, "")
        self.assertEqual(aura.glimpse_state, GlimpseState.NOT_STARTED)
        self.assertFalse(CharacterGlimpseTag.objects.filter(aura=aura).exists())
        self.assertEqual(self.held(sheet), {"Glimpse Mystery"})


class TheGlimpseInPlay(GlimpseJourneyBase):
    def finished(self, **draft_data):
        """A character made with these Glimpse choices, played by the journey's account."""
        draft = self._create_base_draft()
        self.save(draft, **draft_data)
        draft.refresh_from_db()
        sheet = finalize_character(draft, add_to_roster=True).sheet_data
        return sheet, self.play(sheet)

    def answer(self, aura, **answers):
        """POST answers by axis name, e.g. ``answer(aura, TONE=self.wonder)``."""
        return self.client.post(
            f"/api/magic/character-auras/{aura.pk}/set-glimpse-tags/",
            {"answers": [{"axis": axis, "tag_ids": [tag.id]} for axis, tag in answers.items()]},
            format="json",
        )

    def test_a_glimpse_left_for_later_gives_its_cards_when_written_and_is_then_final(self) -> None:
        sheet, aura = self.finished(glimpse_memory=GlimpseMemory.LATER)
        # Stored as remembered and unwritten: nothing given yet.
        self.assertEqual(aura.glimpse_memory, GlimpseMemory.REMEMBERED)
        self.assertEqual(aura.glimpse_state, GlimpseState.NOT_STARTED)
        self.assertEqual(self.held(sheet), set())
        own = self.client.get(f"/api/character-sheets/{sheet.pk}/").data["magic"]["aura"]
        self.assertTrue(own["can_finish_glimpse"])

        written = self.answer(aura, TRIGGER=self.crisis, REFLECTION=self.radiant, TONE=self.wonder)
        self.assertEqual(written.status_code, 200, written.content)
        self.assertEqual(self.held(sheet), {"Crisisborn", "Glimmering", "Wonderstruck"})
        for held in CharacterDistinction.objects.filter(character=sheet):
            self.assertEqual(held.origin, DistinctionOrigin.GAMEPLAY)
            self.assertEqual(held.from_glimpse_id, aura.pk)

        # An answered part is final for the player.
        changed = self.answer(aura, TONE=self.terror)
        self.assertEqual(changed.status_code, 400, changed.content)
        self.assertEqual(
            changed.data["detail"], "Tone is already answered, and the answer is final."
        )
        self.assertNotIn("Dreadmarked", self.held(sheet))

        # A part left unanswered is still open after the story is written, and gives its
        # card then; a card that is secret by default arrives with its secret.
        story = self.client.post(
            f"/api/magic/character-auras/{aura.pk}/set-glimpse-prose/",
            {"text": "It began with the bells."},
            format="json",
        )
        self.assertEqual(story.status_code, 200, story.content)
        own = self.client.get(f"/api/character-sheets/{sheet.pk}/").data["magic"]["aura"]
        self.assertTrue(own["can_finish_glimpse"])
        late = self.answer(aura, CONSEQUENCE=self.loss)
        self.assertEqual(late.status_code, 200, late.content)
        bereft = CharacterDistinction.objects.get(character=sheet, distinction=self.bereft)
        self.assertIsNotNone(bereft.secret_id)

    def test_staff_change_an_answer_and_the_old_card_stays(self) -> None:
        sheet, aura = self.finished(glimpse_tag_ids=[self.wonder.id])
        self.assertEqual(self.held(sheet), {"Wonderstruck"})
        staff = self.api(AccountFactory(is_staff=True))
        changed = staff.post(
            f"/api/magic/character-auras/{aura.pk}/set-glimpse-tags/",
            {"answers": [{"axis": "TONE", "tag_ids": [self.terror.id]}]},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(self.held(sheet), {"Wonderstruck", "Dreadmarked"})

    def test_no_memory_is_a_storys_to_settle(self) -> None:
        sheet, aura = self.finished(glimpse_memory=GlimpseMemory.NO_MEMORY)
        self.assertEqual(self.held(sheet), {"Glimpse Mystery"})
        own = self.client.get(f"/api/character-sheets/{sheet.pk}/").data["magic"]["aura"]
        self.assertEqual(own["glimpse_memory"], GlimpseMemory.NO_MEMORY)
        self.assertFalse(own["can_finish_glimpse"])

        refused = self.answer(aura, TONE=self.wonder)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(refused.data["detail"], "This character has no memory of their Glimpse.")
        story = self.client.post(
            f"/api/magic/character-auras/{aura.pk}/set-glimpse-prose/",
            {"text": "I remember."},
            format="json",
        )
        self.assertEqual(story.status_code, 400, story.content)

        # The player cannot flip the state; staff do, when a story has returned it.
        url = f"/api/character-sheets/{sheet.pk}/staff-glimpse-memory/"
        body = {"memory": GlimpseMemory.REMEMBERED}
        self.assertEqual(self.client.put(url, body, format="json").status_code, 404)
        staff = self.api(AccountFactory(is_staff=True))
        flipped = staff.put(url, body, format="json")
        self.assertEqual(flipped.status_code, 200, flipped.content)
        self.assertEqual(flipped.data["magic"]["aura"]["glimpse_memory"], GlimpseMemory.REMEMBERED)

        accepted = self.answer(aura, TONE=self.wonder)
        self.assertEqual(accepted.status_code, 200, accepted.content)
        # The card that marked the mystery stays as history.
        self.assertEqual(self.held(sheet), {"Glimpse Mystery", "Wonderstruck"})

    def test_after_a_blackout_tone_is_refused_and_witness_is_accepted(self) -> None:
        sheet, aura = self.finished(glimpse_memory=GlimpseMemory.BLACKED_OUT)
        refused = self.answer(aura, TONE=self.wonder)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(
            refused.data["detail"], "This character blacked out, and has no answer to Tone."
        )
        accepted = self.answer(aura, WITNESS=self.public, TRIGGER=self.crisis)
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(self.held(sheet), {"Glimpse Mystery", "Crisisborn"})
