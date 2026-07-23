"""Mission after-action reporting (#1753).

The RESOLVED → COMPLETE step: a player reports a resolved mission's outcome to a
**Functionary** of the mission's report-to role (#1766), choosing a *style* that modulates
the payout. Money is delivered here (``apply_deed_rewards``), not at resolution — a mission
with no one to report to never reaches this path (it completes at resolution; legend spreads,
no coin).

Styles (Apostate's design):
- **Humble** — +1 Bene resonance, lower fame/prestige, baseline money.
- **Accurate** — baseline money + fame/prestige (the promised payout).
- **Embellished** — a manipulation check against the giver (charm + Persuasion, +Manipulation
  specialization if held; difficulty from the giver's standing). Success doubles the money and
  raises fame/prestige; failure keeps the baseline. Grants +1 Insidia. Only offered to a
  reporter who has the Persuasion skill.
- **Mostly-accurate** — a check to report around the truth (#1765): success dodges the criminal
  consequences (heat + the society sting) a CRIME_WATCH line would mint; failure applies them.
  Never grants the fame/prestige swing either way. Rides **Con** (charm + Persuasion +
  Manipulation — ratified 2026-07-03).

Reporting a masked deed barefaced (the run was accepted under a different persona than the one
reporting) risks the *association chance* (#1765): a failed check copies the mask's pursuit heat
onto the reporting persona — the rep-with-thieves-but-not-with-nobles tradeoff.

Magnitudes are PLACEHOLDER pending a tuning pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    MissionStatus,
    ReportStyle,
)
from world.missions.services._situation import mission_situation_ctx
from world.missions.services.play import BeatActionError, participant_for
from world.missions.services.rewards import apply_deed_rewards

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionDeedRecord, MissionInstance
    from world.npc_services.models import Functionary, NPCRole
    from world.skills.models import Specialization

# PLACEHOLDER tuning — fame/prestige swing per report style, and the resonance a style grants.
_FAME_PRESTIGE_DELTA = 5
_STYLE_RESONANCE = {ReportStyle.HUMBLE: "Bene", ReportStyle.EMBELLISHED: "Insidia"}


class MissionReportError(BeatActionError):
    """A report request that can't proceed (wrong state / no giver / not co-located / no skill)."""


@dataclass(frozen=True)
class MissionReportResult:
    """Outcome of a mission report."""

    instance: MissionInstance
    style: str
    functionary: Functionary
    # None unless the style was EMBELLISHED; then True/False for the manipulation check.
    embellish_success: bool | None = None
    # None unless the style was MOSTLY_ACCURATE; then True/False for the dodge check (#1765).
    dodge_success: bool | None = None


def report_to_role_for(instance: MissionInstance) -> NPCRole | None:
    """The NPCRole a run reports to: the template's ``report_to_role``, else the giver's role.

    Returns ``None`` when there is no NPC to report to (a trigger/environment giver) — such a
    run completes at resolution instead of pausing at RESOLVED.
    """
    role = instance.template.report_to_role
    if role is not None:
        return role
    offer = instance.source_offer
    return offer.role if offer is not None else None


def _report_functionary(character: ObjectDB, role: NPCRole) -> Functionary | None:
    """A Functionary of ``role`` standing in ``character``'s current room, or None (#1766)."""
    from world.npc_services.functionaries import functionaries_in_location  # noqa: PLC0415

    return functionaries_in_location(character.location).filter(role=role).first()


def _terminal_deed(instance: MissionInstance) -> MissionDeedRecord | None:
    """The deed carrying this run's emitted reward lines (the terminal/anchor deed)."""
    return instance.deeds.filter(reward_lines__isnull=False).distinct().order_by("-pk").first()


def _base_money_for(deed: MissionDeedRecord, reporter: ObjectDB) -> int:
    """Total authored IMMEDIATE/MONEY the reporter is due on this deed."""
    total = deed.reward_lines.filter(
        recipient=reporter,
        kind=DeedRewardKind.IMMEDIATE,
        sink=DeedRewardSink.MONEY,
    ).aggregate(total=Sum("amount"))["total"]
    return total or 0


# ---------------------------------------------------------------------------
# Embellished — the manipulation check
# ---------------------------------------------------------------------------


def reporter_can_embellish(reporter: ObjectDB) -> bool:
    """True when the reporter has the Persuasion skill (the gate that offers Embellished)."""
    from world.skills.models import CharacterSkillValue  # noqa: PLC0415

    return CharacterSkillValue.objects.filter(
        character_id=reporter.pk, skill__trait__name__iexact="Persuasion", value__gt=0
    ).exists()


def _manipulation_specialization(reporter: ObjectDB) -> Specialization | None:
    """The Manipulation specialization if the reporter holds it (folds into the check)."""
    from world.skills.models import CharacterSpecializationValue  # noqa: PLC0415

    held = (
        CharacterSpecializationValue.objects.filter(
            character_id=reporter.pk, specialization__name__iexact="Manipulation", value__gt=0
        )
        .select_related("specialization")
        .first()
    )
    return held.specialization if held is not None else None


def _embellish_difficulty(functionary: Functionary) -> int:  # noqa: ARG001
    """Difficulty of the embellish check, from the giver's standing toward the reporter (#1697).

    Class-1 Functionaries carry no persistent standing, so this is NORMAL today; when class-2
    Standing NPCs become report targets the difficulty reads their ``NPCStanding.affection``.
    """
    from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice  # noqa: PLC0415

    return DIFFICULTY_VALUES[DifficultyChoice.NORMAL]


def _run_embellish_check(
    reporter: ObjectDB, functionary: Functionary, instance: MissionInstance
) -> bool:
    """Roll the manipulation check against the giver. Raises if the reporter can't embellish."""
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    if not reporter_can_embellish(reporter):
        msg = "You lack the Persuasion to embellish your account."
        raise MissionReportError(msg)
    check_type = CheckType.objects.filter(name__iexact="Persuasion").first()
    if check_type is None:
        msg = "There is no one here who will hear an embellished account."
        raise MissionReportError(msg)
    result = perform_check(
        reporter,
        check_type,
        target_difficulty=_embellish_difficulty(functionary),
        specialization=_manipulation_specialization(reporter),
        situation_ctx=mission_situation_ctx(reporter, instance),
    )
    return result.outcome is not None and result.outcome.success_level >= 0


def _run_consequence_dodge_check(
    reporter: ObjectDB, functionary: Functionary, instance: MissionInstance
) -> bool:
    """The mostly-accurate check: report around the truth to dodge the criminal fallout (#1765).

    Ratified (Apostate 2026-07-03): rides **Con** (charm + Persuasion +
    Manipulation — talking someone into a curated version of events) against
    the giver-standing difficulty. Unlike Embellished there is no skill gate —
    anyone may try to talk around the truth; the dice decide. Unseeded worlds
    fail closed (falls back to the bare Persuasion check when Con is absent).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    check_type = (
        CheckType.objects.filter(name__iexact="Con").first()
        or CheckType.objects.filter(name__iexact="Persuasion").first()
    )
    if check_type is None:
        return False  # unseeded world: the dodge simply fails, consequences apply.
    result = perform_check(
        reporter,
        check_type,
        target_difficulty=_embellish_difficulty(functionary),
        situation_ctx=mission_situation_ctx(reporter, instance),
    )
    return result.outcome is not None and result.outcome.success_level >= 0


def _apply_masked_deed_association(
    instance: MissionInstance, reporter: ObjectDB, functionary: Functionary
) -> None:
    """The association chance (#1765): reporting a masked run barefaced risks the link.

    When the run was accepted under one persona (the mask) and the report is collected under
    another (the face taking the renown), a failed check copies the mask's pursuit heat onto
    the reporting persona via :func:`world.justice.services.associate_heat` — the same seam
    the #1334 secrets-outing writer uses later. Success means nobody made the connection.
    Ratified (Apostate 2026-07-03): **Deceive** (presence + Persuasion + Manipulation) —
    fooling people in the moment is the disguise-adjacent frame; the full crafted-disguise
    quality/identification loop is the appearance epic's later scope. Unseeded worlds fail
    harsh (association happens without a roll) — consistent with the dodge failing closed.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.justice.services import associate_heat  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    mask = instance.accepted_as_persona
    sheet = reporter.character_sheet
    if mask is None or sheet is None or mask.character_sheet_id != sheet.pk:
        return
    reporting_persona = active_persona_for_sheet(sheet)
    if reporting_persona is None or reporting_persona.pk == mask.pk:
        return
    check_type = (
        CheckType.objects.filter(name__iexact="Deceive").first()
        or CheckType.objects.filter(name__iexact="Persuasion").first()
    )
    if check_type is not None:
        result = perform_check(
            reporter,
            check_type,
            target_difficulty=_embellish_difficulty(functionary),
            situation_ctx=mission_situation_ctx(reporter, instance),
        )
        if result.outcome is not None and result.outcome.success_level >= 0:
            return  # slipped away clean — nobody connected the faces.
    associate_heat(from_persona=mask, to_persona=reporting_persona)


# ---------------------------------------------------------------------------
# Style effects
# ---------------------------------------------------------------------------


def _deliver_bonus_money(reporter: ObjectDB, amount: int) -> None:
    from world.currency.services import deliver_mission_money  # noqa: PLC0415

    sheet = reporter.character_sheet
    if sheet is not None and amount > 0:
        deliver_mission_money(recipient_sheet=sheet, amount=amount, ref="mission-embellish-bonus")


def _apply_fame_prestige(reporter: ObjectDB, delta: int) -> None:
    if delta == 0:
        return
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.societies.renown import award_deed_prestige, set_persona_fame  # noqa: PLC0415

    sheet = reporter.character_sheet
    if sheet is None:
        return
    persona = sheet.personas.filter(persona_type=PersonaType.PRIMARY).first()
    if persona is None:
        return
    set_persona_fame(persona, persona.fame_points + delta)
    award_deed_prestige(persona, delta)


def _grant_style_resonance(reporter: ObjectDB, style: str) -> None:
    name = _STYLE_RESONANCE.get(style)
    if name is None:
        return
    sheet = reporter.character_sheet
    if sheet is None:
        return
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models import Resonance  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    resonance = Resonance.objects.filter(name__iexact=name).first()
    if resonance is None:
        return  # not seeded — skip the thematic flourish
    grant_resonance(sheet, resonance, 1, source=GainSource.MISSION_REPORT)


def _apply_style_payout(
    *,
    instance: MissionInstance,
    style: str,
    reporter: ObjectDB,
    functionary: Functionary,
) -> tuple[bool | None, bool | None]:
    """Deliver money / fame-prestige / resonance for the style.

    Returns ``(embellish_success, dodge_success)`` — each None unless its style ran.
    """
    deed = _terminal_deed(instance)
    base_money = _base_money_for(deed, reporter) if deed is not None else 0

    embellish_success: bool | None = None
    if style == ReportStyle.EMBELLISHED:
        embellish_success = _run_embellish_check(reporter, functionary, instance)
    dodge_success: bool | None = None
    if style == ReportStyle.MOSTLY_ACCURATE:
        dodge_success = _run_consequence_dodge_check(reporter, functionary, instance)

    # Baseline money (all styles) — the authored lines. CRIME_WATCH is live
    # (#1765): it mints at the report room unless the dodge succeeded; RUMOR
    # stays skip_unbuilt. The association chance runs regardless of style —
    # dodging the *new* consequence doesn't erase the risk of being connected
    # to the mask that already carries the heat.
    if deed is not None:
        apply_deed_rewards(
            deed,
            skip_unbuilt=True,
            room=reporter.location,
            skip_criminal=bool(dodge_success),
        )
        _apply_masked_deed_association(instance, reporter, functionary)

    # Embellished success doubles the money.
    if style == ReportStyle.EMBELLISHED and embellish_success and base_money > 0:
        _deliver_bonus_money(reporter, base_money)

    # Fame/prestige: humble lower, embellish-success higher, accurate flat.
    if style == ReportStyle.HUMBLE:
        _apply_fame_prestige(reporter, -_FAME_PRESTIGE_DELTA)
    elif style == ReportStyle.EMBELLISHED and embellish_success:
        _apply_fame_prestige(reporter, _FAME_PRESTIGE_DELTA)

    _grant_style_resonance(reporter, style)
    # NOTE: a failed embellish should sting the giver's affection toward the reporter; class-1
    # Functionaries carry no persistent NPCStanding, so that's a no-op until class-2 Standing
    # NPCs become report targets — the seam lives here for then.
    return embellish_success, dodge_success


def report_mission(
    *, instance: MissionInstance, style: str, reporter: ObjectDB
) -> MissionReportResult:
    """Report a RESOLVED mission to its report-to Functionary and deliver the styled payout.

    Gates: *reporter* is a participant (404 otherwise); the run is RESOLVED; a Functionary of
    the report-to role stands in the reporter's room; the style is offerable (Embellished needs
    Persuasion). On success, delivers the style's money / fame-prestige / resonance, records the
    style, and transitions RESOLVED → COMPLETE.
    """
    if style not in ReportStyle.values:
        msg = f"Unknown reporting style '{style}'."
        raise MissionReportError(msg)
    participant_for(instance, reporter)  # NotParticipantError (404) if not on this mission
    if instance.status != MissionStatus.RESOLVED:
        msg = "This mission is not awaiting a report."
        raise MissionReportError(msg)
    role = report_to_role_for(instance)
    if role is None:
        msg = "There is no one to report this mission to."
        raise MissionReportError(msg)
    functionary = _report_functionary(reporter, role)
    if functionary is None:
        msg = f"You must find a {role.name} to report to."
        raise MissionReportError(msg)

    with transaction.atomic():
        embellish_success, dodge_success = _apply_style_payout(
            instance=instance, style=style, reporter=reporter, functionary=functionary
        )
        instance.report_style = style
        instance.reported_at = timezone.now()
        instance.status = MissionStatus.COMPLETE
        instance.completed_at = timezone.now()
        instance.save(update_fields=["report_style", "reported_at", "status", "completed_at"])
    return MissionReportResult(
        instance=instance,
        style=style,
        functionary=functionary,
        embellish_success=embellish_success,
        dodge_success=dodge_success,
    )
