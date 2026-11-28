"""Kindled resonances (#5124): which of a character's resonances the situation kindles now.

A resonance is *kindled* while a situation authored on it (a ``KindlingSituation`` row on the
resonance, or on its affinity) holds, or while a Rally or a GM has named it for this fight or
scene (a live ``Kindling``). Everything is computed on demand and never stored, the way vow
perk situations are. Code compares only a strength's ``rank``; the word players read is the
``KindledStrengthTier.name`` staff wrote.

Each row runs through the covenants ``SituationCheck``, so the 26 vow situations work as
kindling rows unchanged. The six kindling situations (``THREAD_ANCHOR_PRESENT``,
``OWN_FEELING``, ``SHARED_FEELING``, ``TARGET_IN_STATE_THEY_CAUSED``, ``SOMEONE_IN_TROUBLE``,
``MISSION_THEME``) are registered covenants evaluators too, so a vow perk can use them. Their
shared reads are the ``*_evidence`` finders below: a finder returns what made the situation
hold (with the bond tier or condition severity a strength can be reached through), and the
registered evaluator is ``bool(finder(...))``, so the two cannot disagree.

``SituationContext.act`` is ``None`` for "does this hold now" and a ``KindlingAct`` for "does
this act feed it"; the finders read it where the spec's "act that earns it" column differs from
"holds while".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from django.db.models import F, FloatField
from django.db.models.expressions import ExpressionWrapper

from actions.constants import ActionCategory
from world.covenants.perks.constants import Situation
from world.covenants.perks.context import SituationContext, SituationParams
from world.covenants.perks.services import SituationCheck
from world.magic.constants import (
    AFFINITY_PRIMAL,
    GainSource,
    KindlingActKind,
    KindlingSource,
    TargetKind,
)
from world.magic.models import (
    KindledDeedAward,
    KindledStrengthTier,
    Kindling,
    KindlingConfig,
    KindlingSituation,
    RallyKindlingStrength,
    RecordedAct,
    RecordedActSuggestion,
    Resonance,
    ResonanceGrant,
    Thread,
)
from world.magic.services.resonance_checks import act_stat, gain_bonus_clause, roll_gain_bonus
from world.magic.services.threads import relationship_side_from_row
from world.magic.types.kindling import KindledResonance, KindlingAct, KindlingEvidence

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.combat.models import CombatEncounter
    from world.conditions.models import ConditionInstance
    from world.magic.models import Technique
    from world.magic.types.resonance_checks import GainBonus
    from world.missions.models import MissionInstance
    from world.scenes.models import Scene
    from world.traits.models import CheckOutcome

#: The act kinds that feed a thread anchor: an act aimed at the person.
_ANCHOR_FEEDING_ACTS = frozenset(
    {KindlingActKind.ATTACK, KindlingActKind.DEFEND, KindlingActKind.TECHNIQUE}
)

#: The situations whose condition property falls back to the resonance's ``feeling``.
_FEELING_SITUATIONS = frozenset(
    {
        Situation.OWN_FEELING,
        Situation.SHARED_FEELING,
        Situation.TARGET_IN_STATE_THEY_CAUSED,
    }
)

#: The situations in which the act is itself a declared choice of the deed (#5308): she takes a
#: mission option that carries the theme. Only a row on one of these pays a Celestial or Abyssal
#: resonance to a character who does not hold it. Every other situation, including a state she
#: caused in her target, kindles the resonance only for a character who holds it, because the
#: game cannot read intent from a state. The owner's rule (2026-11-27): "there needs to be a
#: measure of *intent* to gaining that resonance. Like a paladin hunting a vampire to protect
#: people from it would probably make the vampire feel hunted, but unless he's trying to
#: *deliberately* make the vampire feel terrorized, he could not gain abyssal resonance from
#: it". The other declared ways into a resonance she does not hold are a pose that reaches for
#: it (``services/reach.py``) and the entrance flourish; neither is a kindled deed.
CHOSEN_DEED_SITUATIONS = frozenset({Situation.MISSION_THEME})

#: "Badly hurt" for ``SOMEONE_IN_TROUBLE``: the same fraction ``ALLY_LOW_HEALTH`` uses.
_BADLY_HURT_FRACTION = 0.5


# --- Presence -------------------------------------------------------------------------


@dataclass(frozen=True)
class _Presence:
    """Who is here, as ids. A character's sheet id is its ObjectDB id (shared primary key)."""

    everyone: frozenset[int]
    opponents: frozenset[int]
    in_fight: bool


def _presence(ctx: SituationContext) -> _Presence:
    """The holder's room contents plus, in a fight, its active roster and its opponents.

    A room occupant the holder cannot perceive (concealed and not yet detected by her) is
    left out; a fighter is perceived by construction. An opponent counts by its ObjectDB id
    and, for a story NPC, by its persona's sheet id.
    """
    from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent, CombatParticipant  # noqa: PLC0415
    from world.conditions.services import concealed_from  # noqa: PLC0415
    from world.covenants.perks.evaluators import _resolution_participant  # noqa: PLC0415

    everyone: set[int] = set()
    character = ctx.holder.character
    location = character.location if character is not None else None
    if location is not None:
        occupants = {obj.pk for obj in location.contents}
        everyone.update(occupants - concealed_from(ctx.holder, occupants))

    participant = _resolution_participant(ctx.resolution)
    opponents: set[int] = set()
    if participant is not None:
        everyone.update(
            CombatParticipant.objects.filter(
                encounter_id=participant.encounter_id, status=ParticipantStatus.ACTIVE
            ).values_list("character_sheet_id", flat=True)
        )
        for objectdb_id, persona_sheet_id in CombatOpponent.objects.filter(
            encounter_id=participant.encounter_id, status=OpponentStatus.ACTIVE
        ).values_list("objectdb_id", "persona__character_sheet_id"):
            opponents.update(i for i in (objectdb_id, persona_sheet_id) if i is not None)
        everyone.update(opponents)
    return _Presence(
        everyone=frozenset(everyone),
        opponents=frozenset(opponents),
        in_fight=participant is not None,
    )


def _allies_present(ctx: SituationContext, presence: _Presence | None) -> frozenset[int]:
    """Everyone here but the holder and the opponents."""
    presence = presence or _presence(ctx)
    return presence.everyone - presence.opponents - {ctx.holder.pk}


def shown_names(
    viewer: CharacterSheet | None, sheet_ids: Iterable[int], *, is_staff: bool = False
) -> dict[int, str]:
    """The name ``viewer`` knows each sheet's character by, keyed by sheet id.

    The face each sheet presents (its active persona, else its primary) read through the
    viewer's eyes, so a mask the viewer has not seen through keeps its mask. A viewer of None
    plays nobody, and staff see through every mask. A sheet with no persona is absent from
    the map.
    """
    from world.scenes.persona_display import build_persona_display_map  # noqa: PLC0415
    from world.scenes.services import personas_for_sheets  # noqa: PLC0415

    personas = personas_for_sheets(sheet_ids)
    if not personas:
        return {}
    display = build_persona_display_map(personas.values(), viewer_sheet=viewer, is_staff=is_staff)
    return {sheet_id: display[persona.pk][0] for sheet_id, persona in personas.items()}


# --- Evidence finders -----------------------------------------------------------------


def thread_anchor_evidence(
    ctx: SituationContext, params: SituationParams, presence: _Presence | None = None
) -> list[KindlingEvidence]:
    """The holder's thread anchors that are here (opponents only with ``enemies_only``).

    A person anchor is the other side of a relationship thread or capstone thread, and its
    bond tier is the holder's OWN side's claimed tier. An organization anchor is here while
    one of its active members is; it has no bond tier, so its strength comes from the row.
    With an act in context, the act must be aimed at the anchor (an attack, a defense or a
    technique on that person or one of the organization's members here). A person is named
    as the holder knows them.
    """
    act = ctx.act
    if act is not None and (act.kind not in _ANCHOR_FEEDING_ACTS or act.target is None):
        return []
    threads = list(
        Thread.objects.filter(
            owner=ctx.holder,
            retired_at__isnull=True,
            target_kind__in=(
                TargetKind.RELATIONSHIP_TRACK,
                TargetKind.RELATIONSHIP_CAPSTONE,
                TargetKind.ORGANIZATION,
            ),
        ).select_related(
            "target_relationship",
            "target_capstone__relationship",
            "target_organization",
        )
    )
    if not threads:
        return []
    presence = presence or _presence(ctx)
    pool = presence.opponents if params.enemies_only else presence.everyone - {ctx.holder.pk}
    if not pool:
        return []
    aimed_at = act.target.pk if act is not None and act.target is not None else None
    hits = [hit for t in threads if (hit := _anchor_hit(t, pool, aimed_at)) is not None]
    names = shown_names(ctx.holder, [sheet_id for sheet_id, _, _ in hits if sheet_id is not None])
    return [
        KindlingEvidence(
            reason=_anchor_reason(
                org_name if sheet_id is None else names.get(sheet_id, "Someone"),
                params.enemies_only,
            ),
            bond_tier=bond_tier,
        )
        for sheet_id, org_name, bond_tier in hits
    ]


def _anchor_hit(
    thread: Thread, pool: frozenset[int], aimed_at: int | None
) -> tuple[int | None, str, int] | None:
    """``(person sheet id or None, organization name, bond tier)`` when the thread's anchor is
    among ``pool`` (and the act, if any, is aimed at it), else None."""
    if thread.target_kind == TargetKind.ORGANIZATION:
        organization = thread.target_organization
        if organization is None:
            return None
        members = _member_sheet_ids(organization.pk, pool)
        if not members or (aimed_at is not None and aimed_at not in members):
            return None
        return None, organization.name, 0
    row = thread.target_relationship or thread.target_capstone
    if row is None:
        return None
    side = relationship_side_from_row(row)
    if side.target_id is None or side.target_id not in pool:
        return None
    if aimed_at is not None and aimed_at != side.target_id:
        return None
    return side.target_id, "", side.tier


def _anchor_reason(name: str, enemies_only: bool) -> str:
    return f"{name} stands against you here" if enemies_only else f"{name} is here"


def _member_sheet_ids(organization_id: int, pool: frozenset[int]) -> frozenset[int]:
    """Sheet ids among ``pool`` of the organization's active members."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return frozenset(
        OrganizationMembership.objects.filter(
            organization_id=organization_id,
            left_at__isnull=True,
            exiled_at__isnull=True,
            persona__character_sheet_id__in=pool,
        ).values_list("persona__character_sheet_id", flat=True)
    )


def _feeling_instances(
    object_ids: Iterable[int], params: SituationParams, *, visible_only: bool = False
) -> list[ConditionInstance]:
    """Active conditions on ``object_ids`` carrying the row's property, at the row's severity.

    The property is on the condition's template or its current stage. ``count_threshold`` is
    the minimum effective severity. No property means nothing qualifies. ``visible_only``
    drops conditions whose template is hidden from others (``is_visible_to_others``), for
    reads of other people's conditions.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.covenants.perks.evaluators import _carries_property_q  # noqa: PLC0415

    if params.condition_property is None:
        return []
    instances = (
        ConditionInstance.objects.filter(
            _carries_property_q(params.condition_property), target_id__in=list(object_ids)
        )
        .select_related("condition", "current_stage", "target")
        .distinct()
    )
    floor = params.count_threshold or 0
    if visible_only:
        instances = instances.filter(condition__is_visible_to_others=True)
    return [i for i in instances if i.effective_severity >= floor]


def own_feeling_evidence(ctx: SituationContext, params: SituationParams) -> list[KindlingEvidence]:
    """The holder bears a condition with the feeling. Any act while bearing it feeds it."""
    return [
        KindlingEvidence(
            reason=f"You carry {instance.condition.name}", severity=instance.effective_severity
        )
        for instance in _feeling_instances([ctx.holder.pk], params)
    ]


def shared_feeling_evidence(
    ctx: SituationContext, params: SituationParams, presence: _Presence | None = None
) -> list[KindlingEvidence]:
    """Someone else here bears a condition with the feeling. Any act alongside them feeds it.

    "Others present" is literal: opponents count too.

    A condition the holder laid that carries ``KindlingConfig.harm_property`` does not count;
    those are Abyssal, and ``TARGET_IN_STATE_THEY_CAUSED`` catches them.
    """
    others = (presence or _presence(ctx)).everyone - {ctx.holder.pk}
    if not others:
        return []
    instances = _feeling_instances(others, params, visible_only=True)
    harm = KindlingConfig.objects.cached_singleton()
    if instances and harm is not None and harm.harm_property_id is not None:
        harmful = {
            i.pk
            for i in _feeling_instances(
                others, SituationParams(condition_property=harm.harm_property)
            )
            if i.source_character_id == ctx.holder.pk
        }
        instances = [i for i in instances if i.pk not in harmful]
    return [
        KindlingEvidence(
            reason=f"Those around you carry {instance.condition.name}",
            severity=instance.effective_severity,
        )
        for instance in instances
    ]


def target_in_state_evidence(
    ctx: SituationContext, params: SituationParams
) -> list[KindlingEvidence]:
    """The target bears a condition with the feeling that the holder laid.

    The target is the act's target, else (in a fight) the opponent the holder declared this
    round, as ``TARGET_HAS_CONDITION_PROPERTY`` reads it.
    """
    from world.covenants.perks.evaluators import _target_bearer_id  # noqa: PLC0415

    bearer_id = _target_bearer_id(ctx)
    if bearer_id is None:
        return []
    caused = [
        i for i in _feeling_instances([bearer_id], params) if i.source_character_id == ctx.holder.pk
    ]
    if not caused:
        return []
    name = shown_names(ctx.holder, [bearer_id]).get(bearer_id) or caused[0].target.db_key
    return [
        KindlingEvidence(
            reason=f"You left {name} in the grip of {instance.condition.name}",
            severity=instance.effective_severity,
        )
        for instance in caused
    ]


def someone_in_trouble_evidence(
    ctx: SituationContext,
    params: SituationParams,  # noqa: ARG001
    presence: _Presence | None = None,
) -> list[KindlingEvidence]:
    """Someone here (not an opponent) is in peril, badly hurt or held.

    Peril is bearing the Bleeding Out or Plummeting condition staff designated; badly hurt is
    health below the ``ALLY_LOW_HEALTH`` fraction; held is being on the held side of an active
    lock clash. An act that aids (cover, interpose, succor, a heal, freeing them) feeds it.
    """
    if ctx.act is not None and not ctx.act.aids:
        return []
    others = _allies_present(ctx, presence)
    if not others or not _anyone_in_trouble(ctx, others):
        return []
    return [KindlingEvidence(reason="Someone here is in trouble")]


def _anyone_in_trouble(ctx: SituationContext, others: frozenset[int]) -> bool:
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    hurt = CharacterVitals.objects.filter(character_sheet_id__in=others, max_health__gt=0).filter(
        health__lt=ExpressionWrapper(F("max_health") * _BADLY_HURT_FRACTION, FloatField())
    )
    return hurt.exists() or _in_peril(others) or _held(ctx, others)


def _in_peril(others: frozenset[int]) -> bool:
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.vitals.peril_designations import (  # noqa: PLC0415
        bleed_out_condition_id,
        plummeting_condition_id,
    )

    condition_ids = [
        i for i in (bleed_out_condition_id(), plummeting_condition_id()) if i is not None
    ]
    return (
        bool(condition_ids)
        and ConditionInstance.objects.filter(
            condition_id__in=condition_ids,
            target_id__in=others,
            resolved_at__isnull=True,
            is_suppressed=False,
        ).exists()
    )


def _held(ctx: SituationContext, others: frozenset[int]) -> bool:
    """Someone is the held side of an active lock clash in the holder's fight.

    In a LOCK/ESCAPING clash the NPC holds the clash's ``initiator``; a PC who contributes
    is helping them break free, not held.
    """
    from world.combat.constants import ClashFlavor, ClashStatus, LockPcRole  # noqa: PLC0415
    from world.combat.models import Clash  # noqa: PLC0415
    from world.covenants.perks.evaluators import _resolution_participant  # noqa: PLC0415

    participant = _resolution_participant(ctx.resolution)
    if participant is None:
        return False
    return Clash.objects.filter(
        encounter_id=participant.encounter_id,
        flavor=ClashFlavor.LOCK,
        lock_pc_role=LockPcRole.ESCAPING,
        status=ClashStatus.ACTIVE,
        initiator_id__in=others,
    ).exists()


def mission_theme_evidence(
    ctx: SituationContext, params: SituationParams
) -> list[KindlingEvidence]:
    """The current mission carries the row's theme; an act must be taking an option that does."""
    theme = params.mission_theme
    if ctx.mission is None or theme is None:
        return []
    if ctx.act is not None:
        option = ctx.act.mission_option
        carries = option is not None and option.themes.filter(pk=theme.pk).exists()
    else:
        carries = ctx.mission.template.themes.filter(pk=theme.pk).exists()
    return [KindlingEvidence(reason=theme.player_text or theme.name)] if carries else []


#: The finders that read who is here; ``_evaluate`` computes that once and passes it in.
_PRESENCE_SITUATIONS = frozenset(
    {
        Situation.THREAD_ANCHOR_PRESENT,
        Situation.SHARED_FEELING,
        Situation.SOMEONE_IN_TROUBLE,
    }
)

#: The six kindling situations' finders; each registered evaluator is ``bool(finder(...))``.
KINDLING_EVIDENCE_FINDERS: dict[str, Callable[..., list[KindlingEvidence]]] = {
    Situation.THREAD_ANCHOR_PRESENT: thread_anchor_evidence,
    Situation.OWN_FEELING: own_feeling_evidence,
    Situation.SHARED_FEELING: shared_feeling_evidence,
    Situation.TARGET_IN_STATE_THEY_CAUSED: target_in_state_evidence,
    Situation.SOMEONE_IN_TROUBLE: someone_in_trouble_evidence,
    Situation.MISSION_THEME: mission_theme_evidence,
}


# --- Strength -------------------------------------------------------------------------


def _reached_rank(evidence: KindlingEvidence, tiers: Iterable[KindledStrengthTier]) -> int:
    """The highest rank whose reach the evidence meets. A reach of 0 is never met."""
    best = 0
    for tier in tiers:
        by_bond = tier.min_bond_tier > 0 and evidence.bond_tier >= tier.min_bond_tier
        by_severity = tier.min_severity > 0 and evidence.severity >= tier.min_severity
        if by_bond or by_severity:
            best = max(best, tier.rank)
    return best


@dataclass(frozen=True)
class _Contribution:
    """One source's claim on a resonance: a rank (with a tier row), reasons, maybe a row."""

    rank: int
    reasons: tuple[str, ...]
    situation: KindlingSituation | None
    chosen: bool = False


def _row_contribution(
    row: KindlingSituation,
    evidence: list[KindlingEvidence],
    tiers: list[KindledStrengthTier],
    by_rank: dict[int, KindledStrengthTier],
) -> _Contribution | None:
    """The row's strength and reasons, or None when it kindles nothing.

    A row with a ``strength`` kindles at that rank whatever its evidence. Without one, each
    piece of evidence reaches a rank through its bond tier or severity. A rank with no tier
    row gives nothing for that source.
    """
    scored = [
        (row.strength if row.strength is not None else _reached_rank(item, tiers), item)
        for item in evidence
    ]
    scored = [(rank, item) for rank, item in scored if rank in by_rank]
    if not scored:
        return None
    scored.sort(key=lambda pair: -pair[0])
    reasons = (row.reason_text,) if row.reason_text else tuple(item.reason for _, item in scored)
    return _Contribution(
        rank=scored[0][0],
        reasons=reasons,
        situation=row,
        chosen=row.situation in CHOSEN_DEED_SITUATIONS,
    )


def situation_reason(row: KindlingSituation) -> str:
    """The reason a player reads for ``row`` when no live scene is at hand, or "".

    The row's own ``reason_text``, else the player text of its mission theme, which is what
    the panel shows for a theme situation. A situation whose reason needs the scene (an
    anchor's name, a bearer's name) has none to give here.
    """
    if row.reason_text:
        return row.reason_text
    theme = row.mission_theme
    return (theme.player_text or theme.name) if theme is not None else ""


def _effective_params(row: KindlingSituation, resonance: Resonance) -> SituationParams:
    """The row's params; the feeling situations fall back to the resonance's ``feeling``."""
    params = row.params
    if row.situation in _FEELING_SITUATIONS and params.condition_property is None:
        return replace(params, condition_property=resonance.feeling)
    return params


@dataclass
class _Evaluation:
    """The locals of one ``kindled_resonances`` call: the context, who is here (read once),
    and what each (situation, params) pair found. Thrown away when the call returns."""

    ctx: SituationContext
    check: SituationCheck
    presence: _Presence | None
    found: dict[tuple[str, SituationParams], list[KindlingEvidence]]

    def evidence(self, situation: str, params: SituationParams) -> list[KindlingEvidence]:
        """What made the situation hold; empty when it does not. Asked once per pair, so an
        affinity row shared by several resonances costs one read."""
        key = (situation, params)
        if key not in self.found:
            self.found[key] = self._read(situation, params)
        return self.found[key]

    def _read(self, situation: str, params: SituationParams) -> list[KindlingEvidence]:
        finder = KINDLING_EVIDENCE_FINDERS.get(situation)
        if finder is not None:
            if situation in _PRESENCE_SITUATIONS:
                return finder(self.ctx, params, presence=self.presence)
            return finder(self.ctx, params)
        if self.check.holds(situation, params, self.ctx.holder):
            return [KindlingEvidence(reason=Situation(situation).label)]
        return []


def _live_kindlings(sheet: CharacterSheet) -> list[Kindling]:
    """Rally and GM kindlings for the sheet's active fight or its active scene."""
    from django.db.models import Q  # noqa: PLC0415

    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    encounter_ids = list(
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__completed_at__isnull=True,
        ).values_list("encounter_id", flat=True)
    )
    character = sheet.character
    scene = get_active_scene(character.location) if character is not None else None
    if not encounter_ids and scene is None:
        return []
    live = Q(encounter_id__in=encounter_ids)
    if scene is not None:
        live |= Q(scene_id=scene.pk)
    return list(
        Kindling.objects.filter(character_sheet=sheet).filter(live).select_related("kindled_by")
    )


def _live_reason(kindling: Kindling, viewer: CharacterSheet) -> str:
    if kindling.source == KindlingSource.RALLY:
        by_id = kindling.kindled_by_id
        name = shown_names(viewer, [by_id]).get(by_id) if by_id is not None else None
        return f"{name} rallied you" if name else "An ally rallied you"
    return "The GM has kindled it"


# --- Public API -----------------------------------------------------------------------


def _named_unheld_resonances(held_ids: set[int]) -> list[Resonance]:
    """Each Celestial or Abyssal resonance an active row names directly that she does not hold.

    Never a Primal one: Primal is what she feels, so it kindles only for its holder (#5327).
    """
    return list(
        Resonance.objects.filter(kindling_situations__is_active=True)
        .exclude(pk__in=held_ids)
        .exclude(affinity__name=AFFINITY_PRIMAL)
        .select_related("affinity", "feeling")
        .distinct()
    )


def kindled_resonances(
    sheet: CharacterSheet,
    *,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
    act: KindlingAct | None = None,
    include_named_unheld: bool = False,
) -> list[KindledResonance]:
    """One entry per resonance the character holds, kindled or not.

    "Holds" is a ``CharacterResonance`` row (the character is associated with the resonance;
    the same identity ``CharacterSheet.cached_resonances`` and the drift code use). The list
    follows the resonance model's own ordering (affinity, then name).

    ``resolution`` is the live round context in a fight (or ``None``), ``mission`` the live
    ``MissionInstance`` for a mission check, and ``act`` the act to test: with an act, a
    situation counts only if that act feeds it (see the module docstring). Rally and GM
    ``Kindling`` rows for the character's active fight or scene count at their stored
    strength whatever the act.

    ``include_named_unheld`` adds, after the held ones, each Celestial or Abyssal resonance
    that an active row names directly and the character does not hold (#5327). Such an entry
    carries ``fed_*`` from every row that names it, so it can be suggested beside an act, and
    ``chosen_*`` from the chosen-deed rows (``CHOSEN_DEED_SITUATIONS``) alone, which are the
    only rows that pay. A Primal resonance is never added: it is what she feels, so it
    kindles only for its holder. A situation for a whole affinity names no single resonance,
    so it feeds held resonances only. Only the earn path and the mission preview ask for
    this; the panel and the casts read held resonances only.
    """
    resonances = list(
        Resonance.objects.filter(character_resonances__character_sheet=sheet).select_related(
            "affinity", "feeling"
        )
    )
    unheld_ids: frozenset[int] = frozenset()
    if include_named_unheld:
        named = _named_unheld_resonances({resonance.pk for resonance in resonances})
        unheld_ids = frozenset(resonance.pk for resonance in named)
        resonances.extend(named)
    return _evaluate_acts(
        sheet,
        resonances,
        [act],
        resolution=resolution,
        mission=mission,
        direct_only=unheld_ids,
    )[0]


@dataclass(frozen=True)
class KindlingContext:
    """The live surroundings a kindling read needs when no caller supplies them.

    ``resolution`` is a ``CombatRoundContext`` for the sheet's active fight (or None) and
    ``mission`` the sheet's newest ACTIVE ``MissionInstance`` she takes part in (or None).
    """

    resolution: object | None = None
    mission: MissionInstance | None = None


def active_mission_for(sheet: CharacterSheet) -> MissionInstance | None:
    """The newest ACTIVE ``MissionInstance`` the sheet takes part in, or None."""
    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInstance  # noqa: PLC0415

    return (
        MissionInstance.objects.filter(status=MissionStatus.ACTIVE, participants__character=sheet)
        .select_related("template")
        .order_by("-pk")
        .first()
    )


def kindling_context_for(sheet: CharacterSheet) -> KindlingContext:
    """Build the live fight and mission context for ``sheet``, for any read outside a roll.

    A panel, a telnet list or a Dig deep read has no round of its own, so this finds the
    character's active combat participant (``resolve_combat_round_context``: ACTIVE in a
    live encounter, newest first) and the newest ACTIVE mission she participates in. A caller
    that already holds a round context (a cast, a pull) passes its own to ``kindled_for`` /
    ``kindled_resonances`` instead.
    """
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415

    return KindlingContext(
        resolution=resolve_combat_round_context(sheet), mission=active_mission_for(sheet)
    )


def kindled_resonances_now(sheet: CharacterSheet) -> list[KindledResonance]:
    """``kindled_resonances`` read in the character's live fight and mission (no act).

    What the "Your resonances" panel and telnet ``resonances`` show; the same context a
    surge or a cast reads, so the panel never disagrees with what happens. Kindled rows come
    first, strongest first; the rest follow in the resonance model's own order.
    """
    context = kindling_context_for(sheet)
    rows = kindled_resonances(sheet, resolution=context.resolution, mission=context.mission)
    return sorted(rows, key=lambda row: -row.tier.rank if row.tier is not None else 1)


def kindled_tiers(
    sheet: CharacterSheet,
    *,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
) -> dict[int, KindledStrengthTier]:
    """Resonance id -> its strength tier, for each held resonance that is kindled now.

    One ``kindled_resonances`` pass; a pull reads it once and looks every payer up in it.
    """
    return {
        entry.resonance.pk: entry.tier
        for entry in kindled_resonances(sheet, resolution=resolution, mission=mission)
        if entry.tier is not None
    }


def kindled_for(
    sheet: CharacterSheet,
    resonance: Resonance,
    *,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
    act: KindlingAct | None = None,
) -> KindledResonance:
    """The kindling answer for one resonance (a payer or a named ally resonance).

    Evaluated whether or not the sheet holds a row for it; the caller decides who may name it.
    """
    return _evaluate(sheet, [resonance], resolution=resolution, mission=mission, act=act)[0]


def kindled_strength_now(
    sheet: CharacterSheet, resonance: Resonance, *, resolution: object | None = None
) -> KindledStrengthTier | None:
    """The strength row ``resonance`` is kindled at for the character now, or None.

    None unless she holds the resonance (``sheet.cached_resonances``). Read in her live
    fight and mission (``kindling_context_for``) with no act, the same context the "Your
    resonances" panel, a cast and giving in to Fury read, so they never disagree. A caller
    that already holds the round it is resolving in passes it as ``resolution`` and the
    fight is not looked up again; her mission is still her newest active one.
    """
    if not any(held.resonance_id == resonance.pk for held in sheet.cached_resonances):
        return None
    if resolution is None:
        context = kindling_context_for(sheet)
        resolution, mission = context.resolution, context.mission
    else:
        mission = active_mission_for(sheet)
    return kindled_for(sheet, resonance, resolution=resolution, mission=mission).tier


def kindled_for_each(
    sheet: CharacterSheet,
    resonances: list[Resonance],
    *,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
) -> list[KindledResonance]:
    """``kindled_for`` for many resonances at once, one answer per resonance in order.

    The strengths, rows and Rally and GM kindlings are read once for the whole list.
    """
    return _evaluate(sheet, resonances, resolution=resolution, mission=mission, act=None)


def _evaluate(
    sheet: CharacterSheet,
    resonances: list[Resonance],
    *,
    resolution: object | None,
    mission: MissionInstance | None,
    act: KindlingAct | None,
) -> list[KindledResonance]:
    return _evaluate_acts(sheet, resonances, [act], resolution=resolution, mission=mission)[0]


def kindled_resonances_for_acts(
    sheet: CharacterSheet,
    acts: list[KindlingAct],
    *,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
    include_named_unheld: bool = False,
) -> list[list[KindledResonance]]:
    """``kindled_resonances`` once per act, reading the strengths, rows and Rally and GM
    kindlings once for all of them (a beat with many options asks this once)."""
    resonances = list(
        Resonance.objects.filter(character_resonances__character_sheet=sheet).select_related(
            "affinity", "feeling"
        )
    )
    unheld_ids: frozenset[int] = frozenset()
    if include_named_unheld:
        named = _named_unheld_resonances({resonance.pk for resonance in resonances})
        unheld_ids = frozenset(resonance.pk for resonance in named)
        resonances.extend(named)
    return _evaluate_acts(
        sheet, resonances, acts, resolution=resolution, mission=mission, direct_only=unheld_ids
    )


def _evaluate_acts(  # noqa: PLR0913 - the shared reads plus which resonances are direct-only
    sheet: CharacterSheet,
    resonances: list[Resonance],
    acts: list[KindlingAct | None],
    *,
    resolution: object | None,
    mission: MissionInstance | None,
    direct_only: frozenset[int] = frozenset(),
) -> list[list[KindledResonance]]:
    from django.db.models import Q  # noqa: PLC0415

    if not resonances:
        return [[] for _ in acts]
    tiers = list(KindledStrengthTier.objects.all())
    by_rank = {tier.rank: tier for tier in tiers}
    rows = list(
        KindlingSituation.objects.filter(is_active=True)
        .filter(
            Q(resonance__in=resonances) | Q(for_affinity_id__in={r.affinity_id for r in resonances})
        )
        .select_related("condition_property", "mission_theme", "affinity")
    )
    live = _live_kindlings(sheet)
    # Who is here does not depend on the act, so it is read once for all of them.
    presence = (
        _presence(
            SituationContext(
                holder=sheet, subject=sheet, target=None, resolution=resolution, mission=mission
            )
        )
        if any(row.situation in _PRESENCE_SITUATIONS for row in rows)
        else None
    )
    return [
        _evaluate_act(
            sheet,
            resonances,
            act,
            rows=rows,
            live=live,
            tiers=tiers,
            by_rank=by_rank,
            presence=presence,
            resolution=resolution,
            mission=mission,
            direct_only=direct_only,
        )
        for act in acts
    ]


def _resonance_contributions(  # noqa: PLR0913 - one resonance's share of the act's reads
    resonance: Resonance,
    sheet: CharacterSheet,
    *,
    rows: list[KindlingSituation],
    live: list[Kindling],
    tiers: list[KindledStrengthTier],
    by_rank: dict[int, KindledStrengthTier],
    evaluation: _Evaluation,
    direct_only: frozenset[int],
) -> list[_Contribution]:
    """What feeds one resonance in one act: the rows that name it or cover its affinity, then
    the live kindlings on it. A resonance id in ``direct_only`` is one the character does not
    hold: it is fed only by the rows that name it, never by a row for its whole affinity."""
    held = resonance.pk not in direct_only
    contributions: list[_Contribution] = []
    for row in rows:
        names_it = row.resonance_id == resonance.pk
        covers_it = row.for_affinity_id == resonance.affinity_id
        if held and not (names_it or covers_it):
            continue
        if not held and not names_it:
            continue
        evidence = evaluation.evidence(row.situation, _effective_params(row, resonance))
        contribution = _row_contribution(row, evidence, tiers, by_rank) if evidence else None
        if contribution is not None:
            contributions.append(contribution)
    contributions.extend(
        _Contribution(rank=k.strength, reasons=(_live_reason(k, sheet),), situation=None)
        for k in live
        if k.resonance_id == resonance.pk and k.strength in by_rank
    )
    return contributions


def _evaluate_act(  # noqa: PLR0913 - the shared reads and the one act's context
    sheet: CharacterSheet,
    resonances: list[Resonance],
    act: KindlingAct | None,
    *,
    rows: list[KindlingSituation],
    live: list[Kindling],
    tiers: list[KindledStrengthTier],
    by_rank: dict[int, KindledStrengthTier],
    presence: _Presence | None,
    resolution: object | None,
    mission: MissionInstance | None,
    direct_only: frozenset[int] = frozenset(),
) -> list[KindledResonance]:
    """One act's answer per resonance. A resonance id in ``direct_only`` is fed only by the
    rows that name it, never by a row for its whole affinity."""
    target = act.target if act is not None else None
    ctx = SituationContext(
        holder=sheet,
        subject=sheet,
        target=target,
        resolution=resolution,
        mission=mission,
        act=act,
    )
    check = SituationCheck(
        subject=sheet, target=target, resolution=resolution, mission=mission, act=act
    )
    evaluation = _Evaluation(
        ctx=ctx,
        check=check,
        presence=presence,
        found={},
    )

    results: list[KindledResonance] = []
    for resonance in resonances:
        contributions = _resonance_contributions(
            resonance,
            sheet,
            rows=rows,
            live=live,
            tiers=tiers,
            by_rank=by_rank,
            evaluation=evaluation,
            direct_only=direct_only,
        )
        results.append(_result(resonance, contributions, by_rank))
    return results


def _result(
    resonance: Resonance,
    contributions: list[_Contribution],
    by_rank: dict[int, KindledStrengthTier],
) -> KindledResonance:
    if not contributions:
        return KindledResonance(resonance=resonance, tier=None, reasons=(), situations=())
    ordered = sorted(contributions, key=lambda c: -c.rank)  # stable: row order breaks ties
    reasons = tuple(dict.fromkeys(reason for c in ordered for reason in c.reasons))
    fed = [c for c in ordered if c.situation is not None]
    chosen = [c for c in fed if c.chosen]
    return KindledResonance(
        resonance=resonance,
        tier=by_rank[ordered[0].rank],
        reasons=reasons,
        situations=tuple(c.situation for c in fed),
        fed_tier=by_rank[fed[0].rank] if fed else None,
        fed_reasons=tuple(dict.fromkeys(reason for c in fed for reason in c.reasons)),
        chosen_tier=by_rank[chosen[0].rank] if chosen else None,
        chosen_situation=chosen[0].situation if chosen else None,
        chosen_reasons=tuple(dict.fromkeys(reason for c in chosen for reason in c.reasons)),
    )


# --- Writes: a Rally or a GM names a resonance ----------------------------------------


def holds_resonance(sheet: CharacterSheet, resonance: Resonance) -> bool:
    """Whether the sheet holds ``resonance`` (a ``CharacterResonance`` row)."""
    return any(held.resonance_id == resonance.pk for held in sheet.cached_resonances)


def held_resonance_names(sheet_ids: Iterable[int]) -> dict[int, list[tuple[int, str]]]:
    """Sheet id -> ``(resonance id, name)`` for each resonance the sheet holds, in one query.

    Names only, in the resonance model's own order (affinity, then name): what a Rally's
    picker lists for an ally, never an amount or whether it is kindled.
    """
    held: dict[int, list[tuple[int, str]]] = {}
    rows = (
        Resonance.objects.filter(character_resonances__character_sheet_id__in=list(sheet_ids))
        .values_list("character_resonances__character_sheet_id", "pk", "name")
        .order_by("affinity__pk", "name")
    )
    for sheet_id, pk, name in rows:
        held.setdefault(sheet_id, []).append((pk, name))
    return held


def record_rally_kindling(  # noqa: PLR0913 - keyword-only fields of one kindling write
    *,
    ally: CharacterSheet,
    resonance: Resonance,
    rallier: CharacterSheet,
    encounter: CombatEncounter,
    outcome: CheckOutcome | None,
    already_kindled: bool,
) -> Kindling | None:
    """Write the kindling a Rally's roll earns the ally's resonance for this fight.

    The strength is the ``RallyKindlingStrength`` row for the roll's outcome; an outcome with
    no row (a failure, say) writes nothing. The ally keeps one Rally row per resonance per
    fight: a second Rally raises its strength if the roll earned a stronger one and otherwise
    leaves it. ``already_kindled`` says the resonance was kindled before this Rally (by a
    situation, a GM or an earlier Rally); then no new row is made, only a stronger strength
    lifts an existing Rally row.
    """
    if outcome is None:
        return None
    award = RallyKindlingStrength.objects.filter(outcome_tier=outcome).first()
    if award is None:
        return None
    existing = Kindling.objects.filter(
        character_sheet=ally,
        resonance=resonance,
        encounter=encounter,
        source=KindlingSource.RALLY,
    ).first()
    if existing is not None:
        if award.strength > existing.strength:
            existing.strength = award.strength
            existing.kindled_by = rallier
            existing.save(update_fields=["strength", "kindled_by"])
        return existing
    if already_kindled:
        return None
    return Kindling.objects.create(
        character_sheet=ally,
        resonance=resonance,
        strength=award.strength,
        source=KindlingSource.RALLY,
        encounter=encounter,
        kindled_by=rallier,
    )


def kindle_by_gm(
    *,
    sheet: CharacterSheet,
    resonance: Resonance,
    tier: KindledStrengthTier,
    scene: Scene,
    gm: CharacterSheet | None,
) -> Kindling:
    """A GM kindles ``resonance`` on the character for this scene at the strength ``tier``.

    One GM row per character, resonance and scene; kindling it again sets the new strength.
    """
    existing = Kindling.objects.filter(
        character_sheet=sheet, resonance=resonance, scene=scene, source=KindlingSource.GM
    ).first()
    if existing is not None:
        existing.strength = tier.rank
        existing.kindled_by = gm
        existing.save(update_fields=["strength", "kindled_by"])
        return existing
    return Kindling.objects.create(
        character_sheet=sheet,
        resonance=resonance,
        strength=tier.rank,
        source=KindlingSource.GM,
        scene=scene,
        kindled_by=gm,
    )


# --- Earning: a deed on a kindling situation --------------------------------------------


def lowest_success_outcome() -> CheckOutcome | None:
    """The plainest successful roll result: the ``CheckOutcome`` with the lowest positive
    ``success_level`` (lowest pk on a tie), or None when none is authored.

    An act with no roll of its own (covering an ally, an auto-succeeding approach) earns at
    this tier's ``KindledDeedAward``.
    """
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    return CheckOutcome.objects.filter(success_level__gt=0).order_by("success_level", "pk").first()


def sheet_name(viewer: CharacterSheet, sheet: CharacterSheet | None) -> str | None:
    """The name ``viewer`` knows ``sheet``'s character by, or None for no sheet or no persona."""
    if sheet is None:
        return None
    return shown_names(viewer, [sheet.pk]).get(sheet.pk)


def act_label(what: str, target_name: str | None = None, joiner: str = " ") -> str:
    """An act in the player's own words: ``what`` and, when there is one, who it was aimed at.

    "Struck Mira" (``joiner`` a space) or "Pyromancy on Mira" (``joiner=" on "``). The label
    is what a kindled-deed grant records, so keep ``what`` to the act's own name.
    """
    return f"{what}{joiner}{target_name}" if target_name else what


def award_scene_act(  # noqa: PLR0913 - the act, its roll's outcome and check type
    initiator: CharacterSheet,
    target: CharacterSheet | None,
    technique: Technique | None,
    outcome: CheckOutcome | None,
    *,
    action_name: str = "",
    check_type: CheckType | None = None,
) -> list[ResonanceGrant]:
    """Earn what a scene act feeds (#5124), scaled by its roll: the one place a scene act's
    kind is decided.

    An act made with a ``technique`` is a TECHNIQUE act and any other is a SOCIAL act. A
    beneficial technique on someone else aids them. The deed is labelled by the technique's
    name, else by ``action_name`` (the scene action's own name). ``check_type`` is the
    act's own roll, whose stat the bonus resonance check borrows (#5308).
    """
    from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415

    what = technique.name if technique is not None else action_name
    return award_kindled_deeds(
        initiator,
        act=KindlingAct(
            kind=KindlingActKind.TECHNIQUE if technique else KindlingActKind.SOCIAL,
            target=target,
            aids=technique is not None
            and target is not None
            and target != initiator
            and not is_technique_hostile(technique),
            label=act_label(what, sheet_name(initiator, target), " on " if technique else " "),
            category=technique.action_category if technique is not None else "",
            check_type=check_type,
        ),
        outcome=outcome,
        act_check_type=check_type,
    )


def get_kindling_config() -> KindlingConfig:
    """Get-or-create the kindling config singleton (pk=1), so the defaults apply with no row."""
    config = KindlingConfig.objects.cached_singleton()
    if config is None:
        config, _ = KindlingConfig.objects.get_or_create(pk=1)
    return config


# The fatigue pool a gain from an act of each kind charges, when the call site names none. A
# technique act names its own ``action_category`` at the site; this is only the fallback.
_KIND_FATIGUE_CATEGORY: dict[str, str] = {
    KindlingActKind.ATTACK: ActionCategory.PHYSICAL,
    KindlingActKind.DEFEND: ActionCategory.PHYSICAL,
    KindlingActKind.AID: ActionCategory.PHYSICAL,
    KindlingActKind.TECHNIQUE: ActionCategory.PHYSICAL,
    KindlingActKind.SOCIAL: ActionCategory.SOCIAL,
    KindlingActKind.MISSION_OPTION: ActionCategory.SOCIAL,
    KindlingActKind.OTHER: ActionCategory.PHYSICAL,
}


def act_fatigue_category(act: KindlingAct) -> str:
    """The fatigue pool (an ``ActionCategory`` value) a gain from ``act`` charges.

    The category the call site passed, else the one the act's kind implies: attacks, defenses
    and aid are physical, social acts and mission options are social (#5327).
    """
    return act.category or _KIND_FATIGUE_CATEGORY.get(act.kind, ActionCategory.PHYSICAL)


def award_kindled_deeds(  # noqa: PLR0913 - keyword-only: the act, its roll and its surroundings
    sheet: CharacterSheet,
    *,
    act: KindlingAct,
    outcome: CheckOutcome | None,
    resolution: object | None = None,
    mission: MissionInstance | None = None,
    context: KindlingContext | None = None,
    act_check_type: CheckType | None = None,
) -> list[ResonanceGrant]:
    """Pay each resonance an authored choice names, and record the act so it can be marked.

    Called once after a player character's roll resolves, with the roll's result tier (an act
    with no roll of its own passes ``lowest_success_outcome()``). Only a deed she chose pays
    (#5327): a resonance a chosen-deed row (``CHOSEN_DEED_SITUATIONS``: a mission option's
    theme) fed with this act in context earns ``KindledDeedAward(outcome).amount x
    earn_percent / 100`` of that row's strength, rounded down, at once and in full as one
    ``KINDLED_DEED`` grant naming the row, whether or not she holds the resonance and whatever
    its affinity, except a Primal one she lacks. Every other situation only suggests: it
    never pays, whether the resonance is Primal, Celestial or Abyssal and in her aura or not.
    No award row for the tier, no strength tier or a share of 0 pays nothing. Non-player
    characters earn and record nothing.

    When no chosen deed paid, the act is written down as one ``RecordedAct`` with a
    ``RecordedActSuggestion`` for each resonance a situation reached (its strength and first
    reason), for her player to point a mark at, and her unmarked acts older than
    ``KindlingConfig.recorded_act_days`` are pruned.

    The bonus resonance check (#5308) rolls once per affinity the act pays, with the stat of
    the act's own roll (``act_check_type``, else ``act.check_type``, passed by the callers that
    hold one) or, when none is passed, the stat staff set for kindled deeds; its percent grows
    the grant.

    With neither ``resolution`` nor ``mission`` given the sheet's own live fight and mission
    are read. A caller that knows its surroundings and has no round (a standoff is a
    negotiation, round zero) passes ``context``, which is used as it stands, a ``None``
    resolution included. Each grant is told to the actor alone ("You earned ...") once the
    surrounding transaction commits, through a private narrative message that reports the
    amount the ledger recorded after the earn rate. Returns the grants written.
    """
    from world.roster.services.activity import is_player_character  # noqa: PLC0415

    if outcome is None:
        return []
    # The one-row award lookup comes first: an NPC attack calls this for every strike.
    award = KindledDeedAward.objects.filter(outcome_tier=outcome).first()
    if award is None or not is_player_character(sheet):
        return []
    if context is None and resolution is None and mission is None:
        context = kindling_context_for(sheet)
    if context is not None:
        resolution, mission = context.resolution, context.mission
    entries = kindled_resonances(
        sheet,
        resolution=resolution,
        mission=mission,
        act=act,
        include_named_unheld=True,
    )
    check_type = act_check_type if act_check_type is not None else act.check_type
    chosen = [
        entry
        for entry in entries
        if entry.chosen_tier is not None
        and entry.chosen_situation is not None
        and award.amount * entry.chosen_tier.earn_percent // 100 > 0
    ]
    stat = act_stat(check_type) if check_type is not None and chosen else None
    bonuses: dict[int, GainBonus] = {}
    grants: list[ResonanceGrant] = []
    for entry in chosen:
        affinity = entry.resonance.affinity
        if affinity.pk not in bonuses:
            bonuses[affinity.pk] = roll_gain_bonus(
                sheet, affinity, source=GainSource.KINDLED_DEED, stat=stat
            )
        _earn_kindled_entry(sheet, entry, award.amount, act, grants, bonuses[affinity.pk])
    if not grants:
        _record_act(sheet, act, outcome, check_type, entries)
    return grants


def _act_phrase(
    sheet: CharacterSheet, target: CharacterSheet | None, label: str, fallback: str
) -> str:
    """``label`` without the name of ``target``, or "" when it names no such person.

    The label was built with the target's name as ``sheet`` knows them (``act_label``), so it
    ends in that name. A reader of the pose shows the phrase and the target named as that
    reader knows them (``pose_marks``). An act aimed at no one, or at a target with no sheet (a
    game-run monster, whose name is no secret), has no phrase and shows its label as it is.
    """
    name = sheet_name(sheet, target)
    if not name or not label.endswith(name):
        return ""
    # A label that was only the name (an act with no action name) falls back to the act's kind,
    # so the phrase is never empty for a targeted act and the name never leaks through the label.
    return label[: -len(name)].strip() or fallback


def _record_act(
    sheet: CharacterSheet,
    act: KindlingAct,
    outcome: CheckOutcome,
    check_type: CheckType | None,
    entries: list[KindledResonance],
) -> None:
    """Write ``act`` down for her player to mark, then prune her acts that waited too long.

    One ``RecordedAct`` and one suggestion per resonance a situation reached (``fed_tier``),
    written strongest first so the oldest suggestion row is the strongest. The act's label is
    the one a deed grant records. Her unmarked acts older than ``recorded_act_days`` go in one
    delete; a marked act is never pruned, because its grant keeps it.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.db import transaction  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    suggested = sorted(
        (entry for entry in entries if entry.fed_tier is not None),
        key=lambda entry: -entry.fed_tier.rank,
    )
    kind_label = KindlingActKind(act.kind).label if act.kind in KindlingActKind.values else act.kind
    label = act.label or kind_label
    with transaction.atomic():
        recorded = RecordedAct.objects.create(
            character_sheet=sheet,
            label=label[:200],
            act_phrase=_act_phrase(sheet, act.target, label, kind_label)[:200],
            outcome=outcome,
            check_type=check_type,
            target_sheet=act.target,
            fatigue_category=act_fatigue_category(act),
        )
        RecordedActSuggestion.objects.bulk_create(
            RecordedActSuggestion(
                act=recorded,
                resonance=entry.resonance,
                strength=entry.fed_tier,
                reason=(entry.fed_reasons[0] if entry.fed_reasons else "")[:300],
            )
            for entry in suggested
        )
        cutoff = timezone.now() - timedelta(days=get_kindling_config().recorded_act_days)
        RecordedAct.objects.filter(
            character_sheet=sheet, marked_grant__isnull=True, created_at__lt=cutoff
        ).delete()


def _earn_kindled_entry(  # noqa: PLR0913 - the sheet, the entry and the shared earn inputs
    sheet: CharacterSheet,
    entry: KindledResonance,
    award_amount: int,
    act: KindlingAct,
    grants: list[ResonanceGrant],
    gain_bonus: GainBonus,
) -> None:
    """Earn one chosen resonance's share of a deed and tell the actor once it commits.

    Appends the grant ``grant_resonance`` writes to ``grants``. A resonance no authored
    choice named, or one whose earn rate rounds the award to 0, earns nothing. ``gain_bonus``
    is the bonus check result rolled for this resonance's affinity; it grows the grant inside
    ``grant_resonance``.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    situation = entry.chosen_situation
    if entry.chosen_tier is None or situation is None:
        return
    amount = award_amount * entry.chosen_tier.earn_percent // 100
    if amount <= 0:
        return
    grant_resonance(
        sheet,
        entry.resonance,
        amount,
        source=GainSource.KINDLED_DEED,
        kindling_situation=situation,
        deed_label=act.label or None,
        ledger_out=grants,
        gain_bonus=gain_bonus,
    )
    line = f"You earned {grants[-1].amount} {entry.resonance.name}."
    clause = gain_bonus_clause(entry.resonance.affinity, gain_bonus.percent)
    if clause:
        line += f" {clause}"
    transaction.on_commit(_told_of_deed(sheet, line))


def _told_of_deed(sheet: CharacterSheet, line: str) -> Callable[[], None]:
    """The after-commit send of one grant line to its actor alone."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    def _send() -> None:
        send_narrative_message(
            recipients=[sheet],
            body=line,
            category=NarrativeCategory.SYSTEM,
            ooc_note="Kindled deed",
            frame_tags={"earned_resonance": True},
        )

    return _send


__all__ = [
    "KINDLING_EVIDENCE_FINDERS",
    "act_fatigue_category",
    "act_label",
    "award_kindled_deeds",
    "award_scene_act",
    "get_kindling_config",
    "held_resonance_names",
    "holds_resonance",
    "kindle_by_gm",
    "kindled_for",
    "kindled_resonances",
    "kindled_resonances_for_acts",
    "lowest_success_outcome",
    "mission_theme_evidence",
    "own_feeling_evidence",
    "record_rally_kindling",
    "shared_feeling_evidence",
    "sheet_name",
    "situation_reason",
    "someone_in_trouble_evidence",
    "target_in_state_evidence",
    "thread_anchor_evidence",
]
