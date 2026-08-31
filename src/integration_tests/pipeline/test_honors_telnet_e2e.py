"""Telnet E2E: the whole Rite of Honors arc, including posthumous (#3466 Task 11).

One journey, on the telnet seam (``CmdRitual`` for every honor, ``CmdSheet`` for the
title read-out), proving the arc end to end rather than each piece in isolation:

1. A battle is settled (``conclude_battle``) so a ``LegendEvent`` and its winning-side
   ``LegendEntry`` deeds exist (``world.battles.legend_wiring.apply_battle_legend_awards``).
2. A witnessing survivor holding a Golden Hare ESTABLISHES a fresh deed
   (``ritual Rite of Honors ... event=<id> deed_title=...``) for a losing-side
   participant's act the battle's automatic Victory mint never credits.
3. The new deed is anchored to that event, at station
   ``min(honoree level, the event's max active station)``.
4. Its mirrored journal is public, and honoring never taps weekly post-count XP
   (``award_weekly_xp=False`` -> no ``WeeklyJournalXP`` row).
5. A second witness amplifies the same deed (``deed=<id>``); ``base_value`` rises again.
6. A third honor's authored value would overshoot the event's remaining headroom -- the
   value actually added is clamped to the event's ceiling (``anchor_event.base_value``),
   and that same honor crosses the deed's station's title threshold.
7. ``sheet/titles`` shows the minted title.
8. The honoree is killed, then honored again -- posthumous is unrestricted by design, so a
   second, still-open event lets an honorer establish them a further deed after death.

SQLite-tier note: ``CharacterLegendSummary``/``get_character_legend_total`` are
Postgres-only materialized views (16 pre-existing SQLite failures documented in
``world.societies.tests.test_services``) -- this journey asserts on ``LegendEntry
.base_value``/``get_total_value()`` directly instead, never on those matviews.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone

from commands.account.sheet import CmdSheet
from commands.ritual import CmdRitual
from world.achievements.models import PersonaTitle
from world.battles import conclusion_hooks
from world.battles.conclusion_hooks import (
    clear_battle_conclusion_hooks,
    register_battle_conclusion_hook,
)
from world.battles.constants import BattleOutcome, BattleSideRole
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.battles.legend_wiring import apply_battle_legend_awards
from world.battles.services import conclude_battle
from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.currency.services import mint_favor_token
from world.journals.models import WeeklyJournalXP
from world.magic.factories import CharacterAuraFactory
from world.scenes.factories import InteractionFactory, PersonaFactory
from world.societies.constants import DeedKnowledgeSource, RenownRisk
from world.societies.factories import (
    LegendEntryFactory,
    LegendEventFactory,
    LegendLevelCalibrationFactory,
    OrganizationFactory,
)
from world.societies.knowledge_services import grant_deed_knowledge
from world.societies.models import LegendEntry, LegendEvent, LegendHonor
from world.societies.seeds import ensure_rite_of_honors_ritual
from world.stories.constants import StakeResolutionColumn
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StakeFactory,
    StakeOutcomeFactory,
)
from world.stories.models import StakeContractActivation
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory

# The staked beat's risk/level, matching world/battles/tests/test_legend_wiring.py's
# proven recipe: EXTREME against target_level 3 clears the Legend risk floor (HIGH) and
# falls back to RISK_LEGEND_AWARDS (no RiskCalibration authored in this test), pricing
# the Victory event at exactly 1_500 with a single fully-held WIN stake.
_TARGET_LEVEL = 3
_EXPECTED_EVENT_BASE_VALUE = 1_500


def _make_ritual_cmd(caller: object, args: str) -> CmdRitual:
    cmd = CmdRitual()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"ritual {args}"
    return cmd


def _sheet_at_level(level: int):
    """A fresh ``CharacterSheet`` (+ its auto-created PRIMARY persona) at ``level``."""
    sheet = CharacterSheetFactory()
    CharacterClassLevelFactory(character=sheet, level=level, is_primary=True)
    return sheet


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_rite_of_honors_ritual gates on #2698
class RiteOfHonorsJourneyE2ETest(TestCase):
    """The whole Rite of Honors arc, proven on one seam, including posthumous."""

    def setUp(self) -> None:
        # Isolate the battle-conclusion hook registry (mirrors
        # world/battles/tests/test_legend_wiring.py) so this journey settles exactly the
        # Legend hook the assertions below depend on, regardless of what other suites'
        # probe hooks may have left registered in this test process.
        self._saved_hooks = list(conclusion_hooks._HOOKS)
        self.addCleanup(self._restore_hooks)
        clear_battle_conclusion_hooks()
        register_battle_conclusion_hook(apply_battle_legend_awards)

        self.rite = ensure_rite_of_honors_ritual()
        self.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)

    def _restore_hooks(self) -> None:
        conclusion_hooks._HOOKS[:] = self._saved_hooks

    def test_rite_of_honors_full_journey_including_posthumous(self) -> None:  # noqa: PLR0915
        # ================================================================
        # Step 1: settle a battle so a LegendEvent + its participant deeds exist.
        # ================================================================
        battle = BattleFactory(name="Siege of the Rite E2E")
        attacker_side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        defender_side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)

        episode = EpisodeFactory()
        EpisodeSceneFactory(episode=episode, scene=battle.scene)
        beat = BeatFactory(episode=episode, risk=RenownRisk.EXTREME, target_level=_TARGET_LEVEL)
        activation = StakeContractActivation.objects.create(
            beat=beat,
            party_average_level=_TARGET_LEVEL,
            declared_target_level=_TARGET_LEVEL,
            declared_risk=RenownRisk.EXTREME,
            effective_risk=RenownRisk.EXTREME,
            is_ready=True,
        )
        stake = StakeFactory(beat=beat)
        StakeOutcomeFactory(stake=stake, activation=activation, column=StakeResolutionColumn.WIN)

        winner_sheet = _sheet_at_level(_TARGET_LEVEL)
        BattleParticipantFactory(battle=battle, side=attacker_side, character_sheet=winner_sheet)

        # The honoree: a LOSING-side survivor. Only the winning side + its unit
        # commanders earn the shared Victory deed, so this act starts uncredited --
        # exactly the gap the Rite of Honors exists to fill.
        honoree_sheet = _sheet_at_level(5)
        honoree_persona = honoree_sheet.primary_persona
        BattleParticipantFactory(battle=battle, side=defender_side, character_sheet=honoree_sheet)
        # The HONOREE must also have witnessed the anchoring event (#3466
        # whole-branch-review C2) -- HonoreeNotPresentToEstablishError otherwise.
        # Being a BattleParticipant alone does not record scene presence.
        InteractionFactory(persona=honoree_persona, scene=battle.scene)

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        event = LegendEvent.objects.get(scene=battle.scene)
        assert event.base_value == _EXPECTED_EVENT_BASE_VALUE
        assert not LegendEntry.objects.filter(event=event, persona=honoree_persona).exists(), (
            "fixture bug: the honoree must start uncredited by the automatic mint"
        )
        winner_entry = LegendEntry.objects.get(event=event, persona=winner_sheet.primary_persona)
        assert winner_entry.earned_at_level == _TARGET_LEVEL  # this event's only station so far

        # Calibration rows for every level this journey touches: the three honorers'
        # own levels (price + Hares) AND the deed's station (3) -- maybe_grant_deed_title
        # runs after EVERY honor_deed call keyed on the DEED's earned_at_level, not the
        # acting honorer's.
        LegendLevelCalibrationFactory(
            level=2, honor_hares_required=1, honor_value_added=600, deed_title_threshold=999_999
        )
        LegendLevelCalibrationFactory(
            level=4, honor_hares_required=1, honor_value_added=700, deed_title_threshold=999_999
        )
        LegendLevelCalibrationFactory(
            level=1, honor_hares_required=1, honor_value_added=900, deed_title_threshold=999_999
        )
        LegendLevelCalibrationFactory(
            level=_TARGET_LEVEL,
            honor_hares_required=1,
            honor_value_added=10,
            deed_title_threshold=_EXPECTED_EVENT_BASE_VALUE,
        )

        # ================================================================
        # Step 2/3/4: a witnessing survivor holding a Golden Hare ESTABLISHES the
        # honoree's uncredited act as a fresh deed, via telnet.
        # ================================================================
        honorer1_sheet = _sheet_at_level(2)
        honorer1_persona = honorer1_sheet.primary_persona
        CharacterAuraFactory(character=honorer1_sheet)  # Gifted gate: hedge_accessible=False
        InteractionFactory(persona=honorer1_persona, scene=battle.scene)  # a scene witness
        mint_favor_token(self.academy, honorer1_sheet, provenance_note="Witnessed her stand")
        honorer1_char = honorer1_sheet.character
        honorer1_char.msg = MagicMock()

        establish_args = (
            f"Rite of Honors honoree={honoree_persona.name} event={event.pk} "
            "deed_title=Held the Line Alone title=A Song for the Fallen Line "
            "body=She held the retreat and let the rest of us live."
        )
        _make_ritual_cmd(honorer1_char, establish_args).func()

        deed = LegendEntry.objects.get(event=event, persona=honoree_persona)
        assert deed.is_active
        # Station = min(honoree level 5, this event's max active station 3).
        assert deed.earned_at_level == _TARGET_LEVEL
        assert deed.base_value == 600  # honorer1's calibrated honor_value_added, unclamped
        assert deed.get_total_value() == 600  # no spreads yet -- base_value alone

        establish_honor = LegendHonor.objects.get(deed=deed, honorer=honorer1_persona)
        assert establish_honor.established_deed is True
        journal = establish_honor.journal_entry
        assert journal.is_public is True
        assert not WeeklyJournalXP.objects.filter(character_sheet=honorer1_sheet).exists(), (
            "honoring must never consume the honorer's own weekly post-count XP"
        )

        # ================================================================
        # Step 5: a second witness amplifies the same deed; base_value rises again.
        # ================================================================
        honorer2_sheet = _sheet_at_level(4)
        honorer2_persona = honorer2_sheet.primary_persona
        CharacterAuraFactory(character=honorer2_sheet)
        grant_deed_knowledge(
            deed=deed, personas=[honorer2_persona], source=DeedKnowledgeSource.WITNESSED
        )
        mint_favor_token(self.academy, honorer2_sheet, provenance_note="Heard the tale told")
        honorer2_char = honorer2_sheet.character
        honorer2_char.msg = MagicMock()

        amplify_args_2 = (
            f"Rite of Honors honoree={honoree_persona.name} deed={deed.pk} "
            "title=Echoing the Song body=I add my voice to what she did."
        )
        _make_ritual_cmd(honorer2_char, amplify_args_2).func()

        deed.refresh_from_db()
        assert deed.base_value == 600 + 700  # = 1300, risen again

        # ================================================================
        # Step 6: a third honor's authored value (900) would overshoot the event's
        # remaining headroom (1500 - 1300 = 200) -- clamped to the ceiling, not
        # exceeding it. This same honor also crosses the station's title threshold.
        # ================================================================
        honorer3_sheet = _sheet_at_level(1)
        honorer3_persona = honorer3_sheet.primary_persona
        CharacterAuraFactory(character=honorer3_sheet)
        grant_deed_knowledge(
            deed=deed, personas=[honorer3_persona], source=DeedKnowledgeSource.WITNESSED
        )
        mint_favor_token(self.academy, honorer3_sheet, provenance_note="Heard it too")
        honorer3_char = honorer3_sheet.character
        honorer3_char.msg = MagicMock()

        amplify_args_3 = (
            f"Rite of Honors honoree={honoree_persona.name} deed={deed.pk} "
            "title=One Final Verse body=Let it be known everywhere."
        )
        _make_ritual_cmd(honorer3_char, amplify_args_3).func()

        deed.refresh_from_db()
        third_honor = LegendHonor.objects.get(deed=deed, honorer=honorer3_persona)
        assert third_honor.value_added == 200  # clamped: 900 authored, only 200 headroom left
        assert deed.base_value == _EXPECTED_EVENT_BASE_VALUE  # exactly the event's ceiling
        assert deed.base_value == event.base_value  # never exceeds anchor_event.base_value

        # ================================================================
        # Step 7: the deed crossed its station's deed_title_threshold -- a title minted.
        # ================================================================
        title = PersonaTitle.objects.get(persona=honoree_persona, legend_entry=deed)
        assert title.display_name == deed.title

        honoree_caller = MagicMock()
        honoree_caller.is_staff = False
        honoree_caller.puppet = honoree_sheet.character
        titles_cmd = CmdSheet()
        titles_cmd.caller = honoree_caller
        titles_cmd.args = ""
        titles_cmd.switches = ["titles"]
        titles_cmd.func()
        titles_output = honoree_caller.msg.call_args[0][0]
        assert deed.title in titles_output

        # ================================================================
        # Step 8: kill the honoree, then honor them again -- posthumous is
        # unrestricted by design (no life-state gate anywhere in honor_deed). The
        # original deed is at its event's ceiling now, so this is a SEPARATE,
        # still-open event -- proving the posthumous rule on the establish path.
        # ================================================================
        second_event = LegendEventFactory(base_value=300, scene=battle.scene)
        LegendEntryFactory(
            persona=PersonaFactory(),
            event=second_event,
            base_value=50,
            earned_at_level=1,
            is_active=True,
        )

        CharacterVitalsFactory(
            character_sheet=honoree_sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )

        mint_favor_token(
            self.academy, honorer1_sheet, provenance_note="One more tale, after she fell"
        )
        honorer1_char.msg.reset_mock()
        posthumous_args = (
            f"Rite of Honors honoree={honoree_persona.name} event={second_event.pk} "
            "deed_title=Her Last Stand, Remembered title=A Posthumous Honor "
            "body=Though she is gone, let this be known too."
        )
        _make_ritual_cmd(honorer1_char, posthumous_args).func()

        posthumous_deed = LegendEntry.objects.get(event=second_event, persona=honoree_persona)
        assert posthumous_deed.is_active
        assert LegendHonor.objects.filter(
            deed=posthumous_deed, honorer=honorer1_persona
        ).exists(), "honoring a dead honoree must still succeed end to end"
