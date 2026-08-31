"""`honor_deed` (#3466): the Rite of Honors service.

Refusals must consume nothing — every test in ``HonorDeedRefusalTests`` asserts that
directly (no Hare redeemed, no journal written, no ``LegendHonor`` row), not merely
that an exception was raised. Posthumous tests assert the absence of any life-state
gate, per Decision 7 — honoring the dead is unrestricted by design.
"""

from django.test import TestCase
from django.utils import timezone

from world.achievements.models import PersonaTitle
from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.currency.models import FavorTokenDetails
from world.currency.services import mint_favor_token
from world.journals.models import JournalEntry, WeeklyJournalXP
from world.scenes.constants import PersonaType
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.services import set_active_persona
from world.societies.constants import DeedKnowledgeSource
from world.societies.factories import (
    LegendEntryFactory,
    LegendEventFactory,
    LegendHonorFactory,
    LegendLevelCalibrationFactory,
    OrganizationFactory,
)
from world.societies.honors import (
    AlreadyHonoredError,
    CannotHonorOwnDeedError,
    DeedAtCeilingError,
    DeedNotActiveError,
    EventMintedNothingRefusal,
    HonoreeAlreadyAnchoredError,
    HonoreeNotPresentToEstablishError,
    InsufficientHaresError,
    NotPresentToEstablishError,
    UnknownDeedError,
    honor_deed,
)
from world.societies.knowledge_services import grant_deed_knowledge, knows_deed
from world.societies.models import LegendEntry, LegendHonor
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import retire_character


def _sheet_with_persona():
    """A fresh CharacterSheet plus its auto-created PRIMARY persona."""
    sheet = CharacterSheetFactory()
    return sheet, sheet.primary_persona


class HonorDeedRefusalTests(TestCase):
    """Every refusal must leave no Hare redeemed, no journal written, no LegendHonor row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        # Level 0 is what a freshly built CharacterSheetFactory sheet carries
        # (no CharacterClassLevel rows) — one calibration row covers every
        # refusal scenario below.
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def setUp(self) -> None:
        self.honorer_sheet, self.honorer_persona = _sheet_with_persona()
        self.honoree_sheet, self.honoree_persona = _sheet_with_persona()
        self.scene = SceneFactory()
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )

    def _mint_hare(self) -> FavorTokenDetails:
        return mint_favor_token(self.academy, self.honorer_sheet, provenance_note="A deed done")

    def _assert_nothing_consumed(
        self, token: FavorTokenDetails | None, deed_count_before: int | None = None
    ) -> None:
        if token is not None:
            token.refresh_from_db()
            assert token.redeemed_at is None
        assert not JournalEntry.objects.exists()
        assert not LegendHonor.objects.exists()
        if deed_count_before is not None:
            assert LegendEntry.objects.count() == deed_count_before

    def test_cannot_honor_your_own_deed(self) -> None:
        own_deed = LegendEntryFactory(
            persona=self.honorer_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=own_deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        token = self._mint_hare()
        with self.assertRaises(CannotHonorOwnDeedError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honorer_persona,
                deed=own_deed,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token)

    def test_cannot_honor_own_deed_even_through_a_different_mask(self) -> None:
        """The check is CharacterSheet-level, not persona-level (honors.py's own-deed check).

        A naive ``deed.persona_id == honorer_persona.pk`` comparison would miss this: the
        deed is authored by a SECOND, established persona on the honorer's own sheet, not
        by the persona attempting to honor it.
        """
        masked_persona = PersonaFactory(
            character_sheet=self.honorer_sheet, persona_type=PersonaType.ESTABLISHED
        )
        masked_deed = LegendEntryFactory(
            persona=masked_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=masked_deed,
            personas=[self.honorer_persona],
            source=DeedKnowledgeSource.WITNESSED,
        )
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(CannotHonorOwnDeedError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=masked_persona,
                deed=masked_deed,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_cannot_honor_the_same_deed_twice(self) -> None:
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        LegendHonorFactory(deed=self.deed, honorer=self.honorer_persona)
        token = self._mint_hare()
        journal_count_before = JournalEntry.objects.count()
        honor_count_before = LegendHonor.objects.count()
        with self.assertRaises(AlreadyHonoredError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=self.deed,
                journal_title="t",
                journal_body="b",
            )
        token.refresh_from_db()
        assert token.redeemed_at is None
        assert JournalEntry.objects.count() == journal_count_before
        assert LegendHonor.objects.count() == honor_count_before

    def test_event_that_minted_nothing_is_refused(self) -> None:
        empty_event = LegendEventFactory(base_value=100)
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(EventMintedNothingRefusal):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=empty_event,
                deed_title="An uncredited act",
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_struck_deed_does_not_count_as_proof_of_peril(self) -> None:
        """A staff-struck (is_active=False) entry doesn't prove the event minted anything."""
        struck_only_event = LegendEventFactory(base_value=100)
        LegendEntryFactory(
            persona=PersonaFactory(),
            event=struck_only_event,
            base_value=50,
            earned_at_level=0,
            is_active=False,
        )
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(EventMintedNothingRefusal):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=struck_only_event,
                deed_title="An uncredited act",
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_deed_already_at_ceiling_is_refused(self) -> None:
        at_ceiling = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=100, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=at_ceiling, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        token = self._mint_hare()
        with self.assertRaises(DeedAtCeilingError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=at_ceiling,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token)

    def test_insufficient_hares_is_refused(self) -> None:
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        # No Hare minted at all.
        with self.assertRaises(InsufficientHaresError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=self.deed,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(None)

    def test_establishing_without_presence_is_refused(self) -> None:
        # A fresh event the honoree has no deed on yet — self.event already carries
        # self.deed for self.honoree_persona, which would trip the "already anchored"
        # refusal instead of the one this test targets.
        unwitnessed_event = LegendEventFactory(base_value=100, scene=SceneFactory())
        LegendEntryFactory(
            persona=PersonaFactory(), event=unwitnessed_event, base_value=10, earned_at_level=0
        )
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(NotPresentToEstablishError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=unwitnessed_event,
                deed_title="An uncredited act",
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_establishing_refused_when_honoree_was_not_present(self) -> None:
        """#3466 whole-branch-review C2: gating only the honorer's presence would let a
        witness mint a full-ceiling deed for someone who was never at the event --
        inventing peril the honoree never faced. The honoree must witness too.
        """
        honoree_absent_event = LegendEventFactory(base_value=100, scene=self.scene)
        LegendEntryFactory(
            persona=PersonaFactory(),
            event=honoree_absent_event,
            base_value=10,
            earned_at_level=0,
        )
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(HonoreeNotPresentToEstablishError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=honoree_absent_event,
                deed_title="An uncredited act",
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_amplifying_a_struck_deed_is_refused(self) -> None:
        """#3466 whole-branch-review I1: a struck deed is worth nothing everywhere its
        value is read, so amplifying it must be refused explicitly, not merely fall
        through to DeedAtCeilingError by coincidence.
        """
        struck = LegendEntryFactory(
            persona=self.honoree_persona,
            event=self.event,
            base_value=20,
            earned_at_level=0,
            is_active=False,
        )
        grant_deed_knowledge(
            deed=struck, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        token = self._mint_hare()
        with self.assertRaises(DeedNotActiveError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=struck,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token)

    def test_establishing_refused_when_honoree_already_has_a_settled_deed_on_event(
        self,
    ) -> None:
        """One deed per act (#3466 Finding 2): many voices grow ONE deed, not one each.

        self.deed (from setUp) already anchors self.honoree_persona to self.event, exactly
        as an automatic settlement pass would have. Establishing a second one for the same
        act must be refused in favor of honoring the existing deed.
        """
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        token = self._mint_hare()
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(HonoreeAlreadyAnchoredError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=self.event,
                deed_title="A second telling of the same act",
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token, deed_count_before)

    def test_establishing_refused_when_honoree_already_has_an_established_deed_on_event(
        self,
    ) -> None:
        """Same rule, but the pre-existing deed came from an EARLIER honor, not settlement."""
        fresh_event = LegendEventFactory(base_value=100, scene=self.scene)
        LegendEntryFactory(
            persona=PersonaFactory(), event=fresh_event, base_value=10, earned_at_level=0
        )
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        InteractionFactory(persona=self.honoree_persona, scene=self.scene)
        self._mint_hare()
        honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=fresh_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )

        second_honorer_sheet, second_honorer_persona = _sheet_with_persona()
        InteractionFactory(persona=second_honorer_persona, scene=self.scene)
        second_token = mint_favor_token(
            self.academy, second_honorer_sheet, provenance_note="A deed done"
        )
        deed_count_before = LegendEntry.objects.count()
        with self.assertRaises(HonoreeAlreadyAnchoredError):
            honor_deed(
                character_sheet=second_honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                event=fresh_event,
                deed_title="A different telling of the same act",
                journal_title="t2",
                journal_body="b2",
            )
        second_token.refresh_from_db()
        assert second_token.redeemed_at is None
        assert LegendEntry.objects.count() == deed_count_before
        assert not LegendHonor.objects.filter(honorer=second_honorer_persona).exists()

    def test_amplifying_without_knowledge_is_refused(self) -> None:
        token = self._mint_hare()
        with self.assertRaises(UnknownDeedError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=self.deed,
                journal_title="t",
                journal_body="b",
            )
        self._assert_nothing_consumed(token)

    def test_refusal_consumes_no_hare_and_writes_no_journal(self) -> None:
        """A refusal that reaches the Hare-resolution step still redeems nothing."""
        at_ceiling = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=100, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=at_ceiling, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        token = self._mint_hare()
        with self.assertRaises(DeedAtCeilingError):
            honor_deed(
                character_sheet=self.honorer_sheet,
                ritual=None,
                honoree_persona=self.honoree_persona,
                deed=at_ceiling,
                journal_title="t",
                journal_body="b",
            )
        token.refresh_from_db()
        assert token.redeemed_at is None
        assert not JournalEntry.objects.exists()
        assert not LegendHonor.objects.exists()


class HonorDeedSuccessTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=30
        )

    def setUp(self) -> None:
        self.honorer_sheet, self.honorer_persona = _sheet_with_persona()
        self.honoree_sheet, self.honoree_persona = _sheet_with_persona()
        self.scene = SceneFactory()
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        self.token = mint_favor_token(
            self.academy, self.honorer_sheet, provenance_note="A deed done"
        )
        # A SEPARATE event for the establish-path tests below: self.event already
        # anchors self.honoree_persona (via self.deed), which the "one deed per act"
        # refusal (#3466 Finding 2) would otherwise trip. This one has someone else's
        # deed (proving it minted something) but nothing yet for the honoree.
        self.establish_event = LegendEventFactory(base_value=100, scene=self.scene)
        LegendEntryFactory(
            persona=PersonaFactory(), event=self.establish_event, base_value=10, earned_at_level=0
        )
        # The HONOREE must also have witnessed the anchoring event (#3466
        # whole-branch-review C2) -- every establish-path test below shares this
        # scene, so this covers them all in one place.
        InteractionFactory(persona=self.honoree_persona, scene=self.scene)

    def test_amplifying_raises_base_value_by_the_calibrated_amount(self) -> None:
        honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        self.deed.refresh_from_db()
        assert self.deed.base_value == 30

    def test_value_is_clamped_to_the_event_ceiling(self) -> None:
        self.deed.base_value = 95
        self.deed.save(update_fields=["base_value"])
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        self.deed.refresh_from_db()
        assert self.deed.base_value == 100
        assert honor.value_added == 5

    def test_establishing_creates_a_solo_deed_anchored_to_the_event(self) -> None:
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )
        assert honor.established_deed is True
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        assert new_deed.pk != self.deed.pk
        assert new_deed.event_id == self.establish_event.pk
        assert new_deed.title == "He held the door"
        assert new_deed.persona_id == self.honoree_persona.pk

    def test_established_deed_station_is_min_of_honoree_level_and_event_max(self) -> None:
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        # self.establish_event already carries a station-0 sibling (from setUp);
        # add a higher-station one too.
        LegendEntryFactory(
            persona=PersonaFactory(), event=self.establish_event, base_value=10, earned_at_level=5
        )
        CharacterClassLevelFactory(character=self.honoree_sheet, level=3)
        self.honoree_sheet.invalidate_class_level_cache()
        # The established deed lands at station 3; maybe_grant_deed_title's bare
        # .get() at the end of honor_deed needs a calibration row for it too.
        LegendLevelCalibrationFactory(
            level=3, honor_hares_required=1, honor_value_added=10, deed_title_threshold=1000
        )
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        assert new_deed.earned_at_level == 3

    def test_struck_deed_does_not_count_toward_station_max(self) -> None:
        """A staff-struck sibling (is_active=False) must not raise the established station."""
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        LegendEntryFactory(
            persona=PersonaFactory(),
            event=self.establish_event,
            base_value=10,
            earned_at_level=9,
            is_active=False,
        )
        CharacterClassLevelFactory(character=self.honoree_sheet, level=9)
        self.honoree_sheet.invalidate_class_level_cache()
        # Station lands at 0 (see the assertion below), and setUpTestData already
        # carries a level=0 calibration row (unique per level) — nothing more to seed.
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        # min(honoree level 9, max ACTIVE station 0 from setUp's baseline entry) == 0,
        # not 9 — the struck level-9 sibling must not count.
        assert new_deed.earned_at_level == 0

    def test_struck_deed_on_event_does_not_block_establishing_a_live_one(self) -> None:
        """A struck deed for the SAME honoree does not poison the event slot (ruling, #3466).

        Staff strike a farcical deed by setting is_active=False, which zeroes its value
        everywhere else (get_total_value, both matviews) — it must not also bar the
        honoree's genuine act from ever being recognized on this event again.
        """
        struck_deed = LegendEntryFactory(
            persona=self.honoree_persona,
            event=self.establish_event,
            base_value=50,
            earned_at_level=0,
            is_active=False,
        )
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="The real account of what happened",
            journal_title="t",
            journal_body="b",
        )
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        assert new_deed.pk != struck_deed.pk
        assert new_deed.is_active is True
        assert new_deed.persona_id == self.honoree_persona.pk
        assert new_deed.event_id == self.establish_event.pk

    def test_journal_is_public_and_earns_no_weekly_xp(self) -> None:
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        journal = JournalEntry.objects.get(pk=honor.journal_entry_id)
        assert journal.is_public is True
        assert not WeeklyJournalXP.objects.filter(character_sheet=self.honorer_sheet).exists()

    def test_deed_story_mirrors_the_journal_body(self) -> None:
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="what he did mattered",
        )
        assert honor.deed_story is not None
        assert honor.deed_story.text == "what he did mattered"
        assert honor.deed_story.author_id == self.honorer_persona.pk

    def test_hares_are_redeemed_and_recorded(self) -> None:
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        self.token.refresh_from_db()
        assert self.token.redeemed_at is not None
        assert honor.hares_spent == 1
        assert list(honor.hares.all()) == [self.token]

    def test_honorer_gains_deed_knowledge(self) -> None:
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        assert knows_deed(persona=self.honorer_persona, deed=new_deed) is True

    def test_crossing_the_threshold_mints_a_title(self) -> None:
        self.deed.base_value = 25
        self.deed.save(update_fields=["base_value"])
        honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        self.deed.refresh_from_db()
        assert self.deed.base_value == 35
        title = PersonaTitle.objects.get(persona=self.honoree_persona, legend_entry=self.deed)
        assert title.display_name == self.deed.title

    def test_establishing_succeeds_when_honoree_was_present(self) -> None:
        """The success half of #3466 whole-branch-review C2's presence gate.

        setUp already grants ``self.honoree_persona`` an Interaction in
        ``self.scene`` — this asserts that presence is sufficient, not merely that
        its absence refuses (covered by ``HonorDeedRefusalTests
        .test_establishing_refused_when_honoree_was_not_present``).
        """
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            event=self.establish_event,
            deed_title="He held the door",
            journal_title="t",
            journal_body="b",
        )
        assert LegendHonor.objects.filter(pk=honor.pk).exists()

    def test_honorer_recorded_as_primary_persona_even_when_masked(self) -> None:
        """#3466 whole-branch-review C1: the rite is always performed as yourself.

        A mask worn at rite time must never be recorded as ``LegendHonor.honorer`` —
        the public journal (authored by ``character_sheet``) and the mirrored scene
        pose (``_post_declaration``, always the PRIMARY persona) already reveal the
        real identity, so recording the mask there would be a deterministic
        mask-to-real link.
        """
        mask = PersonaFactory(
            character_sheet=self.honorer_sheet, persona_type=PersonaType.TEMPORARY
        )
        set_active_persona(self.honorer_sheet, mask)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        assert honor.honorer_id == self.honorer_persona.pk
        assert honor.honorer_id != mask.pk


class HonorDeedPosthumousTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def _prepare(self) -> None:
        self.honorer_sheet, self.honorer_persona = _sheet_with_persona()
        self.honoree_sheet, self.honoree_persona = _sheet_with_persona()
        self.event = LegendEventFactory(base_value=100)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        mint_favor_token(self.academy, self.honorer_sheet, provenance_note="A deed done")

    def test_dead_honoree_can_be_honored(self) -> None:
        self._prepare()
        CharacterVitalsFactory(
            character_sheet=self.honoree_sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        assert LegendHonor.objects.filter(pk=honor.pk).exists()

    def test_retired_dead_honoree_can_be_honored(self) -> None:
        self._prepare()
        CharacterVitalsFactory(
            character_sheet=self.honoree_sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        retire_character(self.honoree_sheet)
        honor = honor_deed(
            character_sheet=self.honorer_sheet,
            ritual=None,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="t",
            journal_body="b",
        )
        assert LegendHonor.objects.filter(pk=honor.pk).exists()
