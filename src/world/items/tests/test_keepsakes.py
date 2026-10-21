"""Keepsakes, trophies and the rail that reads them (#4530, #4462 section 6.4).

A keepsake counts by what it stands for, after a wait, and never by the player's words.
A trophy counts by the legend of the deed it was won on. Example numbers: wait 14 days,
subject cap 3, +2 when the subject is the being, a tie by its claimed tier, a deed by legend
over 10.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import KeepsakeSubject, MeaningSignalKind, OwnershipEventType
from world.items.exceptions import KeepsakeRefused
from world.items.factories import ItemInstanceFactory, KeepsakeFactory
from world.items.models import OwnershipEvent
from world.items.services.crafted_display import crafted_provenance_line
from world.items.services.holding import set_item_holder
from world.items.services.keepsakes import (
    KeepsakeSubjectRef,
    declare_keepsake,
    find_subject_by_name,
    keepsake_state,
    keepsake_status,
    release_keepsake,
)
from world.items.services.meaning import item_meaning
from world.items.services.meaning_display import keepsake_rail
from world.items.services.trophies import link_trophy
from world.relationships.factories import CharacterRelationshipFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendEntryFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.invocation_services import get_devotion_config


def _kinds(meaning) -> dict[str, int]:
    return {signal.kind: signal.points for signal in meaning.signals}


class KeepsakeMeaningTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_devotion_config()
        cls.keeper = CharacterSheetFactory()
        cls.other = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory()

    def _item(self, days: int = 3):
        return ItemInstanceFactory(
            holder_character_sheet=self.keeper,
            held_since=timezone.now() - timedelta(days=days),
        )

    def test_a_keepsake_waits_then_counts_one_for_a_place(self) -> None:
        item = self._item()
        keepsake = KeepsakeFactory(item_instance=item, declared_days_ago=3)

        self.assertEqual(item_meaning(item, self.keeper, config=self.config).points, 0)

        keepsake.created_at = timezone.now() - timedelta(days=15)
        keepsake.save(update_fields=["created_at"])

        self.assertEqual(
            _kinds(item_meaning(item, self.keeper, config=self.config)),
            {MeaningSignalKind.KEEPSAKE: 1},
        )

    def test_the_words_are_never_scored(self) -> None:
        short = KeepsakeFactory(item_instance=self._item(), text="Mine.")
        long = KeepsakeFactory(item_instance=self._item(), text="A very long tale. " * 30)

        self.assertEqual(
            item_meaning(short.item_instance, self.keeper, config=self.config).points,
            item_meaning(long.item_instance, self.keeper, config=self.config).points,
        )

    def test_a_tie_is_its_claimed_tier_plus_one_up_to_the_cap(self) -> None:
        item = self._item()
        side = CharacterRelationshipFactory(source=self.keeper, target=self.other, tier=2)
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.TIE,
            subject_label="",
            subject_relationship=side,
        )

        self.assertEqual(
            _kinds(item_meaning(item, self.keeper, config=self.config)),
            {MeaningSignalKind.KEEPSAKE: 3},
        )

    def test_a_tie_keepsake_of_the_giver_adds_the_tie_tier_as_a_match(self) -> None:
        item = self._item(days=3)
        side = CharacterRelationshipFactory(source=self.keeper, target=self.other, tier=2)
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=self.other,
            to_character_sheet=self.keeper,
        )
        set_item_holder(item, self.keeper, event=event)
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.TIE,
            subject_label="",
            subject_relationship=side,
        )

        kinds = _kinds(item_meaning(item, self.keeper, config=self.config))

        self.assertEqual(kinds[MeaningSignalKind.KEEPSAKE], 3)
        self.assertEqual(kinds[MeaningSignalKind.KEEPSAKE_MATCH], 2)

    def test_a_deed_is_its_legend_over_ten_and_a_trophy_of_it_adds_one(self) -> None:
        deed = LegendEntryFactory(persona=self.keeper.primary_persona, base_value=20)
        plain = self._item()
        KeepsakeFactory(
            item_instance=plain,
            subject_kind=KeepsakeSubject.DEED,
            subject_label="",
            subject_deed=deed,
        )
        won = self._item()
        won.legend_deeds.add(deed)
        KeepsakeFactory(
            item_instance=won,
            subject_kind=KeepsakeSubject.DEED,
            subject_label="",
            subject_deed=deed,
        )

        self.assertEqual(
            _kinds(item_meaning(plain, self.keeper, config=self.config)),
            {MeaningSignalKind.KEEPSAKE: 3},
        )
        # The trophy scores the deed (1 + 20 / 10 = 3); the keepsake adds a flat 1.
        self.assertEqual(
            _kinds(item_meaning(won, self.keeper, config=self.config)),
            {MeaningSignalKind.TROPHY: 3, MeaningSignalKind.KEEPSAKE: 1},
        )

    def test_a_keepsake_of_the_being_matches_only_when_the_reading_is_for_it(self) -> None:
        item = self._item()
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.BEING,
            subject_label="",
            subject_being=self.being,
        )

        elsewhere = WorshippedBeingFactory()
        self.assertEqual(
            _kinds(item_meaning(item, self.keeper, config=self.config, being=self.being)),
            {MeaningSignalKind.KEEPSAKE: 1, MeaningSignalKind.KEEPSAKE_MATCH: 2},
        )
        self.assertEqual(
            _kinds(item_meaning(item, self.keeper, config=self.config, being=elsewhere)),
            {MeaningSignalKind.KEEPSAKE: 1},
        )

    def test_a_keepsake_means_nothing_to_whoever_the_piece_passes_to(self) -> None:
        item = self._item()
        KeepsakeFactory(item_instance=item)

        self.assertEqual(item_meaning(item, self.other, config=self.config).points, 0)

    def test_a_deed_credited_to_someone_else_scores_nothing(self) -> None:
        item = self._item()
        deed = LegendEntryFactory(persona=PersonaFactory(), base_value=50)
        KeepsakeFactory(
            item_instance=item,
            subject_kind=KeepsakeSubject.DEED,
            subject_label="",
            subject_deed=deed,
        )

        self.assertEqual(item_meaning(item, self.keeper, config=self.config).points, 0)


class TrophyMeaningTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_devotion_config()
        cls.keeper = CharacterSheetFactory()

    def test_a_trophy_is_one_plus_the_deeds_legend_over_ten_to_the_cap(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)
        item.legend_deeds.add(
            LegendEntryFactory(persona=self.keeper.primary_persona, base_value=25)
        )

        # Earned by risk: no carry gate, so a piece won this morning counts.
        self.assertEqual(
            _kinds(item_meaning(item, self.keeper, config=self.config)),
            {MeaningSignalKind.TROPHY: 3},
        )

    def test_a_deed_credited_to_someone_else_is_not_the_holders_trophy(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)
        item.legend_deeds.add(LegendEntryFactory(persona=PersonaFactory(), base_value=90))

        self.assertEqual(item_meaning(item, self.keeper, config=self.config).points, 0)

    def test_link_trophy_links_only_the_holders_deeds_and_makes_the_row_physical(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)
        mine = LegendEntryFactory(persona=self.keeper.primary_persona)
        theirs = LegendEntryFactory(persona=PersonaFactory())
        self.assertIsNone(item.game_object)

        linked = link_trophy(item, [mine, theirs])

        self.assertTrue(linked)
        self.assertEqual(list(item.legend_deeds.all()), [mine])
        item.refresh_from_db()
        self.assertIsNotNone(item.game_object)

    def test_link_trophy_with_no_deed_of_the_holders_links_nothing(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)

        self.assertFalse(link_trophy(item, [LegendEntryFactory(persona=PersonaFactory())]))
        self.assertFalse(item.legend_deeds.exists())

    def test_examine_names_the_deed_and_shows_a_chosen_keepsake_line(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)
        deed = LegendEntryFactory(persona=self.keeper.primary_persona, title="Cliff rescue")
        item.legend_deeds.add(deed)
        KeepsakeFactory(item_instance=item, shown_on_examine=True, text="[player words]")

        line = crafted_provenance_line(item)

        self.assertIn("Trophy of Cliff rescue.", line)
        self.assertIn("Kept as a keepsake by", line)
        self.assertIn("[player words]", line)

    def test_examine_hides_a_private_keepsake(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.keeper)
        KeepsakeFactory(item_instance=item, shown_on_examine=False, text="[private words]")

        self.assertNotIn("[private words]", crafted_provenance_line(item) or "")


class DeclareKeepsakeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = get_devotion_config()
        cls.keeper = CharacterSheetFactory()
        cls.other = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory(name="The Highwind")

    def _item(self):
        return ItemInstanceFactory(holder_character_sheet=self.keeper)

    def _declare(self, item, **kwargs):
        defaults = {
            "subject": KeepsakeSubjectRef(kind=KeepsakeSubject.PLACE, label="the harbor"),
            "text": "[player words]",
        }
        return declare_keepsake(self.keeper, item, **{**defaults, **kwargs})

    def test_declaring_stores_the_players_words_as_written(self) -> None:
        keepsake = self._declare(self._item(), text="  Words kept as written.  ")

        self.assertEqual(keepsake.text, "Words kept as written.")
        self.assertEqual(keepsake.subject_name, "the harbor")

    def test_only_a_held_item_can_be_kept(self) -> None:
        stranger = ItemInstanceFactory(holder_character_sheet=self.other)

        with self.assertRaises(KeepsakeRefused):
            self._declare(stranger)

    def test_an_item_is_kept_once(self) -> None:
        item = self._item()
        self._declare(item)

        with self.assertRaises(KeepsakeRefused):
            self._declare(item)

    def test_words_are_required_and_limited(self) -> None:
        for text in ("   ", "x" * 601):
            with self.assertRaises(KeepsakeRefused):
                self._declare(self._item(), text=text)

    def test_a_character_keeps_at_most_the_configured_number(self) -> None:
        for _ in range(self.config.keepsakes_per_character):
            self._declare(self._item())

        with self.assertRaises(KeepsakeRefused) as refused:
            self._declare(self._item())

        self.assertIn("release one first", refused.exception.user_message)

    def test_releasing_frees_a_slot_and_restarts_the_wait(self) -> None:
        item = self._item()
        first = self._declare(item)
        used = keepsake_status(self.keeper).used

        release_keepsake(self.keeper, item)

        self.assertEqual(keepsake_status(self.keeper).used, used - 1)
        again = self._declare(item)
        self.assertGreaterEqual(again.created_at, first.created_at)
        with self.assertRaises(KeepsakeRefused):
            release_keepsake(self.keeper, self._item())

    def test_a_tie_must_be_one_of_the_characters_own_sides(self) -> None:
        theirs = CharacterRelationshipFactory(source=self.other, target=self.keeper)

        with self.assertRaises(KeepsakeRefused):
            self._declare(
                self._item(), subject=KeepsakeSubjectRef(KeepsakeSubject.TIE, pk=theirs.pk)
            )

    def test_a_deed_must_be_credited_to_the_character(self) -> None:
        mine = LegendEntryFactory(persona=self.keeper.primary_persona)
        theirs = LegendEntryFactory(persona=self.other.primary_persona)

        keepsake = self._declare(
            self._item(), subject=KeepsakeSubjectRef(KeepsakeSubject.DEED, pk=mine.pk)
        )
        self.assertEqual(keepsake.subject_deed, mine)
        with self.assertRaises(KeepsakeRefused):
            self._declare(
                self._item(), subject=KeepsakeSubjectRef(KeepsakeSubject.DEED, pk=theirs.pk)
            )

    def test_a_person_can_be_anyone_but_the_character_themselves(self) -> None:
        keepsake = self._declare(
            self._item(),
            subject=KeepsakeSubjectRef(KeepsakeSubject.PERSON, pk=self.other.primary_persona.pk),
        )
        self.assertEqual(keepsake.subject_persona, self.other.primary_persona)
        with self.assertRaises(KeepsakeRefused):
            self._declare(
                self._item(),
                subject=KeepsakeSubjectRef(
                    KeepsakeSubject.PERSON, pk=self.keeper.primary_persona.pk
                ),
            )

    def test_a_place_needs_a_name(self) -> None:
        with self.assertRaises(KeepsakeRefused):
            self._declare(
                self._item(), subject=KeepsakeSubjectRef(KeepsakeSubject.PLACE, label=" ")
            )

    def test_a_typed_name_finds_its_subject(self) -> None:
        deed = LegendEntryFactory(persona=self.keeper.primary_persona, title="Cliff rescue")

        self.assertEqual(
            find_subject_by_name(self.keeper, KeepsakeSubject.DEED, "cliff rescue").pk, deed.pk
        )
        self.assertEqual(
            find_subject_by_name(self.keeper, KeepsakeSubject.BEING, "the highwind").pk,
            self.being.pk,
        )
        with self.assertRaises(KeepsakeRefused):
            find_subject_by_name(self.keeper, KeepsakeSubject.BEING, "nobody")

    def test_the_state_lists_what_the_character_could_keep_it_for(self) -> None:
        item = self._item()
        CharacterRelationshipFactory(source=self.keeper, target=self.other)
        LegendEntryFactory(persona=self.keeper.primary_persona, title="Cliff rescue")

        state = keepsake_state(self.keeper, item)

        self.assertIsNone(state.keepsake)
        self.assertEqual(
            [label for _pk, label in state.subjects[KeepsakeSubject.DEED]], ["Cliff rescue"]
        )
        self.assertEqual(len(state.subjects[KeepsakeSubject.TIE]), 1)


class KeepsakeRailTests(TestCase):
    def test_the_rail_reads_the_subject_never_the_words_and_says_when_it_counts(self) -> None:
        keeper = CharacterSheetFactory()
        item = ItemInstanceFactory(holder_character_sheet=keeper)
        keepsake = KeepsakeFactory(item_instance=item, declared_days_ago=2, text="[words]")

        rail = keepsake_rail(keepsake)

        self.assertFalse(rail.counts_now)
        self.assertEqual([(line.label, line.points) for line in rail.lines], [("Keepsake", 1)])
        self.assertTrue(all("[words]" not in line.detail for line in rail.lines))
        self.assertGreater(rail.counts_from, timezone.now())
