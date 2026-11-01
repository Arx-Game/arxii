"""Which distinctions a draft can pick where, and the picks its choices carry (#3675).

One authored ``DistinctionOffer`` row per place a distinction is shown. This module
is the only reader: ``offers_for`` lists a chapter's priced choices, ``closed_for``
the route's closed list, and ``reconcile_offer_picks`` applies carried and bundled
offers and removes picks whose offer has gone.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, NamedTuple

from django.db.models import Q

from world.character_creation.constants import (
    AGE_PICKS_CAP_AGE,
    AGE_PICKS_FROM_AGE,
    AGE_PICKS_YEARS_PER_PICK,
    BEAT_COVER_OFFER_ID,
    BEAT_FIGURES,
    BEAT_SECRET_OFFER_IDS,
    CG_MODIFIER_CATEGORY,
    LIFE_LOADED_FOR_KEY,
    MAGIC_TRAINING_POINTS_TARGET,
    STAGE_DESCRIPTIONS_KEY,
    ActorSheetPrompt,
    BeatSelection,
    FinalTouchesPrompt,
    LifeStage,
    OfferArrival,
    OfferChapter,
    QuestionKind,
    TraditionState,
    schooling_max_rank,
)
from world.character_creation.models import (
    BeginningTradition,
    CharacterDraft,
    DistinctionOffer,
    LifeBeat,
    LifeBeatExclusion,
    OfferFirstLook,
    SchoolingLine,
    TraditionStateLine,
)
from world.character_creation.questionnaire import DraftAnswers, anchor_for, visible_slot_ids
from world.character_creation.types import (
    BeatPoolEntry,
    ClosedDistinction,
    FinalTouchesCard,
    OfferEffectTerm,
    OfferTerm,
    OrganizationChoice,
    VisibleOffer,
)
from world.character_sheets.types import EnemyDegree
from world.classes.models import Aspect, Path
from world.distinctions.models import Distinction, DistinctionEffect
from world.distinctions.types import (
    DraftDistinctionEntry,
    build_distinction_entry,
    feature_of,
)
from world.societies.models import Organization, OrganizationType

if TYPE_CHECKING:
    from world.character_creation.models import Beginnings
    from world.magic.models import Tradition


#: Where the Appearance chapter's feature-rows lines (#3739) sort relative to its
#: sections. Sections carry ``AppearanceSection.sort_order``; a feature-rows line
#: belongs to no section, so it sorts after every one of them.
_FEATURE_ROWS_GROUP_ORDER = 1_000_000


def tradition_is_self_taught(tradition: Tradition) -> bool:
    """Whether ``tradition`` is SELF_TAUGHT on any Beginning's slate (#3675).

    Runtime code's only sanctioned way to answer "is this CG's tradition-agnostic
    default" - never a name match against "Unbound." Called by
    ``world.character_creation.services._finalize_academy_entrance_obligation``
    and ``world.progression.services.durance_registration``.
    """
    return BeginningTradition.objects.filter(
        tradition=tradition, state=TraditionState.SELF_TAUGHT
    ).exists()


def slate_state(beginning: Beginnings, tradition: Tradition) -> TraditionState | None:
    """The slate state ``tradition`` reads as on ``beginning``, if the pairing exists.

    ``None`` when the tradition isn't on this Beginning's slate at all. Callers that
    already hold a ``BeginningTradition`` row should read its ``state`` field
    directly; this is for callers that only hold the (beginning, tradition) pair.
    """
    raw = (
        BeginningTradition.objects.filter(beginning=beginning, tradition=tradition)
        .values_list("state", flat=True)
        .first()
    )
    return TraditionState(raw) if raw is not None else None


def self_taught_drawback() -> Distinction | None:
    """The drawback the SELF_TAUGHT ``TraditionStateLine`` carries, if any (#3675).

    Called by ``world.magic.services.tradition_membership._reapply_unbound_drawback``
    on leaving a tradition - the live-play "traditionless once again" re-grant, never
    a tag or slug lookup.
    """
    line = TraditionStateLine.objects.filter(state=TraditionState.SELF_TAUGHT).first()
    return line.carries if line is not None else None


def _slate_line(draft: CharacterDraft) -> BeginningTradition | None:
    """The draft's picked tradition's row on its Beginning's slate, if any.

    Called by ``_context`` (to gate Tradition Step offers) and ``_carried_offer``
    (to find the state whose drawback the pick carries).
    """
    if draft.selected_beginnings_id is None or draft.selected_tradition_id is None:
        return None
    return next(
        (
            bt
            for bt in draft.selected_beginnings.cached_beginning_traditions
            if bt.tradition_id == draft.selected_tradition_id
        ),
        None,
    )


def schooling_training_points(lines: Iterable[SchoolingLine]) -> dict[int, int]:
    """The Magic-skill training points each stance gives, keyed by rank (slice 2 of #4659).

    A stance's points are its ``grants`` distinction's ``magic_training_points`` effect
    at the stance's rank; 0 for rank 0, a line that grants nothing, or a distinction
    with no such effect. One query for every line. Read by the tradition serializer's
    stance rows and the tradition slate page's derived line; the draft itself reads
    its pool through ``CharacterDraft.magic_training_pool``.
    """
    lines = list(lines)
    effects = {
        effect.distinction_id: effect
        for effect in DistinctionEffect.objects.filter(
            distinction_id__in={line.grants_id for line in lines if line.grants_id},
            target__name=MAGIC_TRAINING_POINTS_TARGET,
            target__category__name=CG_MODIFIER_CATEGORY,
        )
    }
    return {
        line.rank: (
            effects[line.grants_id].get_value_at_rank(line.rank)
            if line.rank and line.grants_id in effects
            else 0
        )
        for line in lines
    }


#: A life's stages in the order a life has them, for pooling and grouping beats;
#: the choice values sort alphabetically, which is not that order.
LIFE_STAGE_ORDER: dict[str, int] = {value: i for i, value in enumerate(LifeStage.values)}

#: The ``draft_data`` key holding a draft's beats: ``{"<beat_id>": {"taken": bool,
#: "unknown": bool, "line": str, "secret_offer_ids": [int], "cover_offer_id": int | None,
#: "figures": {"<offer_id>": str}}``. A beat absent from the map is not taken. The last
#: three are the life page's (#4872): the picks on the beat marked secret, the answer
#: shown in a secret's place, and the figure named on a person card.
BEATS_KEY = "beats"


#: The optional text a life ends on, under ``draft_data`` (#4830).
RECENT_HISTORY_KEY = "recent_history"


def beat_pool(draft: CharacterDraft) -> list[LifeBeat]:
    """Every active library beat this draft's Beginning offers, stage by stage (#4124).

    The library applies to every Beginning unless a ``LifeBeatExclusion`` says
    otherwise, or the Beginning strikes the beat's whole stage out (#4395: the
    Sleeper strikes the three stages before the Glimpse; a struck stage is absent,
    not greyed). With no Beginning picked there is no pool. Called by ``beats_for``
    and ``_context``.
    """
    beginning_id = draft.selected_beginnings_id
    if beginning_id is None:
        return []
    struck = draft.selected_beginnings.struck_stages()
    excluded = set(
        LifeBeatExclusion.objects.filter(beginning_id=beginning_id).values_list(
            "beat_id", flat=True
        )
    )
    beats = [
        b
        for b in LifeBeat.objects.filter(is_active=True)
        if b.pk not in excluded and b.life_stage not in struck
    ]
    beats.sort(key=lambda b: (LIFE_STAGE_ORDER.get(b.life_stage, 99), b.sort_order, b.pk))
    return beats


def age_pick_allowance(age: int | None) -> int:
    """How many career points an age-scaled beat allows (#4395, re-ruled #4829).

    One point at or under ``AGE_PICKS_FROM_AGE``, one more for every
    ``AGE_PICKS_YEARS_PER_PICK`` full years lived past it, and no more past
    ``AGE_PICKS_CAP_AGE``: nineteen is one, twenty-four two, fifty seven, fifty-nine and
    older nine. A point buys a card on the beat or a rank on one, so the beat counts
    ranks (``beat_pick_conflicts``). No age yet reads as the floor.
    """
    if age is None or age <= AGE_PICKS_FROM_AGE:
        return 1
    counted = min(age, AGE_PICKS_CAP_AGE)
    return 1 + (counted - AGE_PICKS_FROM_AGE) // AGE_PICKS_YEARS_PER_PICK


def youngest_age_for_points(points: int) -> int:
    """The youngest age whose allowance is at least ``points`` (#4829), for the age floor.

    The inverse of ``age_pick_allowance``: one point at nineteen, each further point
    five years later. ``AGE_PICKS_CAP_AGE`` bounds it: no age holds more than the cap's
    allowance, so a count past that reads as the cap.
    """
    if points <= 1:
        return AGE_PICKS_FROM_AGE
    return min(AGE_PICKS_FROM_AGE + (points - 1) * AGE_PICKS_YEARS_PER_PICK, AGE_PICKS_CAP_AGE)


def beat_allowance(beat: LifeBeat, age: int | None) -> int | None:
    """How many answers ``beat`` allows a character of ``age``; None is any number (#4395).

    A beat whose picks scale with age reads ``age_pick_allowance``; otherwise one-of
    allows one and any-that-apply allows any.
    """
    if beat.picks_scale_with_age:
        return age_pick_allowance(age)
    return 1 if beat.selection == BeatSelection.ONE_OF else None


def picked_offer_ids(draft: CharacterDraft) -> set[int]:
    """Every offer id the draft's distinction picks name."""
    return {
        offer_id
        for entry in draft.draft_data.get("distinctions", [])
        for offer_id in entry.get("offer_ids", [])
        if isinstance(offer_id, int)
    }


def _draft_beat_states(draft: CharacterDraft) -> dict[int, dict]:
    """The draft's own state per beat id, read off ``draft_data[BEATS_KEY]``."""
    raw = draft.draft_data.get(BEATS_KEY) or {}
    out: dict[int, dict] = {}
    if not isinstance(raw, dict):
        return out
    for key, state in raw.items():
        try:
            beat_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(state, dict):
            out[beat_id] = state
    return out


class BeatMarks(NamedTuple):
    """What the life page marked on a draft's beats besides the picks (#4872).

    Read off ``draft_data[BEATS_KEY]`` by ``beat_marks``. ``secret`` and ``cover`` are
    keyed by beat id; ``figures`` by offer id. The validator checks shape only, so a
    stale mark (an offer no longer picked) is simply ignored by every reader here.
    """

    secret: dict[int, set[int]]
    cover: dict[int, int]
    figures: dict[int, str]


def beat_marks(draft: CharacterDraft) -> BeatMarks:
    """The secret picks, covers and figure names on the draft's beats (#4872)."""
    secret: dict[int, set[int]] = {}
    cover: dict[int, int] = {}
    figures: dict[int, str] = {}
    for beat_id, state in _draft_beat_states(draft).items():
        ids = state.get(BEAT_SECRET_OFFER_IDS) or []
        if isinstance(ids, list):
            secret[beat_id] = {x for x in ids if isinstance(x, int)}
        cover_id = state.get(BEAT_COVER_OFFER_ID)
        if isinstance(cover_id, int):
            cover[beat_id] = cover_id
        raw_figures = state.get(BEAT_FIGURES) or {}
        if isinstance(raw_figures, dict):
            for key, name in raw_figures.items():
                if isinstance(name, str) and name.strip() and str(key).isdecimal():
                    figures[int(key)] = name.strip()
    return BeatMarks(secret=secret, cover=cover, figures=figures)


def stage_descriptions(draft: CharacterDraft) -> dict[str, str]:
    """Life stage value -> the paragraph the player wrote for it (#4872), blanks dropped."""
    raw = draft.draft_data.get(STAGE_DESCRIPTIONS_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    return {
        stage: text.strip()
        for stage, text in raw.items()
        if stage in LifeStage.values and isinstance(text, str) and text.strip()
    }


def beats_for(draft: CharacterDraft) -> list[BeatPoolEntry]:
    """The beat pool as this draft meets it, with the draft's state on each (#4124).

    Called by the draft's ``beats`` endpoint. A beat is taken only when the draft says
    so (the one-kept mode, under which the Beginning took its pool itself, was retired in
    #4830: a beginning that keeps no stage strikes them all instead).
    """
    pool = beat_pool(draft)
    states = _draft_beat_states(draft)
    picked = picked_offer_ids(draft)
    out: list[BeatPoolEntry] = []
    for beat in pool:
        state = states.get(beat.pk, {})
        answer_ids = [offer.pk for offer in beat.answers]
        line = str(state.get("line") or "")
        unknown = bool(state.get("unknown"))
        # A beat is taken by a pick under it, a line, or the unknown mark (#4395: the
        # grids never ask the player to "add" a beat first); an explicit taken flag
        # still counts.
        taken = (
            bool(state.get("taken"))
            or unknown
            or bool(line)
            or any(offer_id in picked for offer_id in answer_ids)
        )
        out.append(
            BeatPoolEntry(
                beat_id=beat.pk,
                name=beat.name,
                prompt=beat.prompt,
                life_stage=beat.life_stage,
                selection=beat.selection,
                taken=taken,
                unknown=unknown,
                line=line,
                answer_offer_ids=answer_ids,
                allowance=beat_allowance(beat, draft.age),
                allowance_is_points=bool(beat.picks_scale_with_age),
            )
        )
    return out


def taken_beat_ids(draft: CharacterDraft) -> set[int]:
    """Ids of the beats the draft has taken and not marked unknown."""
    return {e.beat_id for e in beats_for(draft) if e.taken and not e.unknown}


def open_beat_ids(draft: CharacterDraft) -> set[int]:
    """Ids of the beats whose answers are open to this draft (#4395): in the pool and
    not marked unknown. A grid is open as soon as the Beginning offers it."""
    return {e.beat_id for e in beats_for(draft) if not e.unknown}


class BeatConflict(NamedTuple):
    """One beat answered past its allowance (``beat_pick_conflicts``)."""

    name: str
    allowance: int
    #: True when the beat spends career points, so ``allowance`` counts ranks (#4829).
    points: bool


def beat_pick_conflicts(
    offers: Iterable[DistinctionOffer],
    *,
    age: int | None,
    ranks: Mapping[int, int] | None = None,
) -> list[BeatConflict]:
    """Each beat ``offers`` would answer past its allowance.

    Called by the distinctions sync view before it saves (#4124, #4395): a one-of beat
    takes one answer, so two distinct cards on it conflict; an age-scaled beat allows
    ``age_pick_allowance(age)`` career points, and a point buys a card or a rank
    (#4829), so the ranks of its cards are summed (``ranks`` maps a distinction id to the
    rank the payload asks for; a missing entry is rank one). Offers on an unbounded
    any-that-apply beat never conflict.
    """
    by_beat: dict[int, set[int]] = defaultdict(set)
    beats: dict[int, LifeBeat] = {}
    for offer in offers:
        if offer.beat_id is None:
            continue
        by_beat[offer.beat_id].add(offer.distinction_id)
        beats[offer.beat_id] = offer.beat
    out: list[BeatConflict] = []
    for beat_id, dists in by_beat.items():
        beat = beats[beat_id]
        allowance = beat_allowance(beat, age)
        if allowance is None:
            continue
        if beat.picks_scale_with_age:
            spent = sum(max(1, (ranks or {}).get(dist_id, 1)) for dist_id in dists)
        else:
            spent = len(dists)
        if spent > allowance:
            out.append(BeatConflict(beat.name, allowance, bool(beat.picks_scale_with_age)))
    return out


def age_scaled_points_spent(draft: CharacterDraft) -> list[tuple[str, int]]:
    """``(card name, rank)`` for each pick the draft holds on a beat that spends career
    points (#4829), read the way the leaf and finalize read a pick: its entry's rank.

    Called by the draft serializer's age validation, so lowering the age under the points
    already spent is refused and names what to unpick.
    """
    entries = [
        e
        for e in draft.draft_data.get("distinctions", [])
        if isinstance(e, dict) and isinstance(e.get("rank"), int)
    ]
    offer_ids = {
        offer_id
        for entry in entries
        for offer_id in entry.get("offer_ids", [])
        if isinstance(offer_id, int)
    }
    if not offer_ids:
        return []
    scaled = set(
        DistinctionOffer.objects.filter(
            pk__in=offer_ids, beat__picks_scale_with_age=True
        ).values_list("pk", flat=True)
    )
    return [
        (str(entry.get("distinction_name") or entry.get("distinction_id")), int(entry["rank"]))
        for entry in entries
        if any(offer_id in scaled for offer_id in entry.get("offer_ids", []))
    ]


def _opener_satisfied(offer: DistinctionOffer, ctx: dict) -> bool:
    """Whether the draft has satisfied this offer's opener.

    Called by ``visible_offers`` for every active offer row. ``ctx`` (built by
    ``_context``) already carries every piece of draft state an opener check needs.
    """
    chapter = OfferChapter(offer.chapter)
    membership = {
        OfferChapter.GLIMPSE: (offer.glimpse_tag_id, "tag_ids"),
        OfferChapter.LINEAGE: (offer.origin_choice_id, "choice_ids"),
        OfferChapter.BACKGROUNDS: (offer.beat_id, "open_beat_ids"),
    }
    if chapter in membership:
        value, context_key = membership[chapter]
        return value in ctx[context_key]
    if chapter == OfferChapter.TRADITION_STEP:
        # The state decides how many stances it opens (#4457): a living tradition all
        # three, an orphaned one ranks 0 and 1, a self-taught one none. A line saved
        # without its schooling stance (the database does not require one) is never open.
        line = ctx["slate_line"]
        max_rank = schooling_max_rank(line.state) if line is not None else None
        if max_rank is None or offer.schooling_line_id is None:
            return False
        return offer.schooling_line.rank <= max_rank
    if chapter == OfferChapter.ACTORS_SHEET:
        # The question is always on the leaf; the prompt only says which block (#3709).
        return bool(offer.prompt)
    if chapter == OfferChapter.APPEARANCE:
        # A feature-rows line (#3739) is opened by the chapter itself: it is offered
        # on every trait row and every marking, so there is no section to satisfy.
        return offer.appearance_section_id is not None or offer.feature_rows
    if chapter == OfferChapter.ENEMY:
        if offer.enemy_reason_id is not None:
            return offer.enemy_reason_id == ctx["enemy_reason_id"]
        return bool(offer.enemy_degree) and offer.enemy_degree == ctx["enemy_degree"]
    if chapter == OfferChapter.FINAL_TOUCHES:
        # A card the draft holds unlocks the line (#4846); unpicking the card hides it
        # again, and ``reconcile_offer_picks`` drops whatever it had opened.
        return offer.unlocked_by_id is not None and offer.unlocked_by_id in ctx["held_ids"]
    return False


def _context(draft: CharacterDraft) -> dict:
    """The draft state every opener check needs, computed once per call.

    Called by ``visible_offers``.
    """
    answers = DraftAnswers.from_draft(draft)
    visible = visible_slot_ids(draft)
    enemy = draft.draft_data.get("enemy") or {}
    return {
        "tag_ids": set(draft.draft_data.get("glimpse_tag_ids", [])),
        "choice_ids": {cid for sid, cid in answers.picks.items() if sid in visible},
        "slate_line": _slate_line(draft),
        # The enemy chapter's two openers (#3709): the reason picked, the degree picked.
        "enemy_reason_id": enemy.get("reason_id"),
        "enemy_degree": enemy.get("degree", ""),
        # The Backgrounds chapter's opener (#4124, #4395): the beats open to the draft.
        "open_beat_ids": open_beat_ids(draft),
        # The Final Touches chapter's opener (#4846): the cards the draft holds.
        "held_ids": held_distinction_ids(draft),
    }


def held_distinction_ids(draft: CharacterDraft) -> set[int]:
    """The distinctions the draft holds right now, from any line or grant.

    Called by ``_context`` (the Final Touches opener) and ``final_touches_prompts``.
    """
    return {entry["distinction_id"] for entry in draft.draft_data.get("distinctions", [])}


def held_cards(draft: CharacterDraft) -> list[Distinction]:
    """The cards the draft holds, with their grant sidecars joined, by name (#4852).

    Called by ``final_touches_cards`` and by finalize's grant writers, so one query serves
    every ask and every grant a draft's cards raise.
    """
    held = held_distinction_ids(draft)
    if not held:
        return []
    return list(
        Distinction.objects.filter(pk__in=held)
        .select_related(
            "prestige_grant",
            "organization_grant",
            "path_aspect_grant",
            "persona_grant",
            "organization_tie__org_type",
        )
        .order_by("name")
    )


def strongest_path_aspect(path: Path | None) -> Aspect | None:
    """The Aspect that weighs most on a Path, ties by name; ``None`` with no Path or rows.

    The Path's own reading of "stronger" (``PathAspect.weight``): where Capable Mentor's
    bonus lands (#4852). Called by ``final_touches_cards`` and finalize.
    """
    if path is None:
        return None
    rows = sorted(path.cached_path_aspects, key=lambda pa: (-pa.weight, pa.aspect.name))
    return rows[0].aspect if rows else None


def final_touches_cards(draft: CharacterDraft) -> list[FinalTouchesCard]:
    """Every ask the draft's held cards raise at Final Touches, one per card and prompt.

    A card asks what staff set on it (``Distinction.final_touches_prompt``, #4846) and what
    its grant sidecars raise on their own (#4852): a prestige grant asks the story, an
    organization grant with no fixed organization asks for the pick, a path aspect grant
    shows the line naming the Path's stronger Aspect (``detail``, blank until a Path is
    picked). Enum order, then card name. Called by ``CharacterDraftSerializer``.
    """
    cards = held_cards(draft)
    if not cards:
        return []
    aspect = strongest_path_aspect(draft.selected_path)
    # One organizations query for every ask that offers them (review on #4863): the realm's
    # admitting organizations, filtered per tie by type in Python.
    needs_organizations = any(
        (
            card.organization_grant_or_none is not None
            and card.organization_grant_or_none.organization_id is None
        )
        or card.organization_tie_or_none is not None
        for card in cards
    )
    realm_organizations = organization_choices(draft) if needs_organizations else []
    asks: list[FinalTouchesCard] = []
    for card in cards:
        asks.extend(_asks_of(card, aspect, realm_organizations))
    order = {prompt.value: index for index, prompt in enumerate(FinalTouchesPrompt)}
    asks.sort(key=lambda ask: (order[ask.prompt], ask.name))
    return asks


def _asks_of(
    card: Distinction,
    aspect: Aspect | None,
    realm_organizations: list[Organization],
) -> list[FinalTouchesCard]:
    """One card's asks: its staff-set prompt and the ones its sidecars raise (#4852, #4856).
    ``realm_organizations`` is the realm's admitting list, fetched once by the caller."""

    def ask(prompt: str, detail: str = "", choices: tuple = ()) -> FinalTouchesCard:
        return FinalTouchesCard(card.pk, card.name, prompt, detail, choices)

    asks: list[FinalTouchesCard] = []
    if card.final_touches_prompt:
        asks.append(ask(card.final_touches_prompt))
    if card.prestige_grant_or_none is not None:
        asks.append(ask(FinalTouchesPrompt.PRESTIGE_STORY))
    org_grant = card.organization_grant_or_none
    if org_grant is not None and org_grant.organization_id is None:
        choices = _organization_choice_rows(realm_organizations)
        asks.append(ask(FinalTouchesPrompt.ORGANIZATION, choices=choices))
    if card.path_aspect_grant_or_none is not None:
        asks.append(ask(FinalTouchesPrompt.PATH_ASPECT, aspect.name if aspect is not None else ""))
    persona_grant = card.persona_grant_or_none
    if persona_grant is not None:
        worn = FinalTouchesPrompt.OFFICIALLY_DEAD
        asks.append(ask(worn if persona_grant.worn else FinalTouchesPrompt.ALTER_EGO))
    tie = card.organization_tie_or_none
    if tie is not None:
        of_kind = [
            org
            for org in realm_organizations
            if tie.org_type_id is None or org.org_type_id == tie.org_type_id
        ]
        choices = _organization_choice_rows(of_kind)
        detail = tie.org_type.name if tie.org_type_id else ""
        asks.append(ask(FinalTouchesPrompt.TIE, detail, choices))
    return asks


def final_touches_prompts(draft: CharacterDraft) -> list[str]:
    """The optional questions the draft's cards ask at Final Touches (#4846), in enum order.

    Called by ``CharacterDraftSerializer`` (the leaf's chapter gate) and by finalize, which
    writes an answer only while a held card still asks for it. Empty for most drafts: the
    leaf hides the chapter when this and the chapter's offers are both empty. The cards
    behind each prompt are ``final_touches_cards``.
    """
    prompts: list[str] = []
    for ask in final_touches_cards(draft):
        if ask.prompt not in prompts:
            prompts.append(ask.prompt)
    return prompts


def organization_choices(
    draft: CharacterDraft, *, org_type: OrganizationType | None = None
) -> list[Organization]:
    """The organizations a card may seat the character in, or tie them to.

    The organizations of the draft's realm (the realm page's own reading, #3725: the
    society's realm is the starting area's) that ``admits_player_characters``, covenants
    excluded, by name; with ``org_type``, those of that kind only (a tie's gang or temple,
    #4856). A covert organization is listed too: the parent's leak table has the list shown
    to its own player only. Called by ``final_touches_cards``, ``CharacterDraftSerializer``
    and the draft's answer validation (#4852).
    """
    if draft.selected_area_id is None or draft.selected_area.realm_id is None:
        return []
    rows = Organization.objects.filter(
        society__realm_id=draft.selected_area.realm_id,
        admits_player_characters=True,
        covenant__isnull=True,
    )
    if org_type is not None:
        rows = rows.filter(org_type=org_type)
    return list(rows.order_by("name"))


def _organization_choice_rows(orgs: Iterable[Organization]) -> tuple[OrganizationChoice, ...]:
    return tuple(OrganizationChoice(org.pk, org.name, org.is_covert) for org in orgs)


def load_default_life(draft: CharacterDraft) -> list[DraftDistinctionEntry]:
    """Load the beginning's suggested life into the draft (#4865, slice 7 of #4813).

    The draft's visible Backgrounds offers whose pin for its beginning is ``preselected``,
    in the grid's own order (``offers_for``, so the route's closed list and the
    beginning's strikes already apply): a one-of beat takes the first of its starred
    cards, an age-scaled beat as many as ``age_pick_allowance(draft.age)`` points buy, an
    any beat all of them; a card the draft already holds from another chapter, or one
    excluded by a card held or taken, is left out. The draft's Backgrounds picks are
    replaced by those entries (the sync's own shape), every other chapter's pick kept,
    the carried and bundled picks reconciled after, and
    ``draft_data[LIFE_LOADED_FOR_KEY]`` stamped with the beginning's id. Called by the
    draft's ``load-default-life`` action; nothing without a beginning. Returns what it
    loaded.
    """
    beginning_id = draft.selected_beginnings_id
    if beginning_id is None:
        return []
    visible = visible_offers(draft)
    grid = [
        visible[row.offer_id]
        for row in offers_for(draft, OfferChapter.BACKGROUNDS)
        if row.offer_id in visible
    ]
    starred = set(
        OfferFirstLook.objects.filter(
            beginning_id=beginning_id, preselected=True, offer_id__in=[o.pk for o in grid]
        ).values_list("offer_id", flat=True)
    )
    # The picks the load leaves alone count as held (review on #4866): a card already
    # picked in another chapter is not entered twice, and its exclusion partners stay out.
    kept = _entries_outside_the_life(draft)
    held: set[int] = {e["distinction_id"] for e in kept if feature_of(e) == ("", 0)}
    exclusions = _mutual_exclusions({o.distinction_id for o in grid if o.pk in starred} | held)
    taken_per_beat: dict[int, int] = defaultdict(int)
    entries: list[DraftDistinctionEntry] = []
    for offer in grid:
        if offer.pk not in starred or offer.distinction_id in held:
            continue
        if exclusions.get(offer.distinction_id, set()) & held:
            continue
        allowance = beat_allowance(offer.beat, draft.age) if offer.beat_id else None
        if allowance is not None and taken_per_beat[offer.beat_id] >= allowance:
            continue
        taken_per_beat[offer.beat_id] += 1
        held.add(offer.distinction_id)
        entries.append(
            build_distinction_entry(
                offer.distinction, 1, "", offer=offer, source=opener_label(offer, draft=draft)
            )
        )
    draft.draft_data["distinctions"] = [*kept, *entries]
    draft.draft_data[LIFE_LOADED_FOR_KEY] = beginning_id
    draft.save(update_fields=["draft_data", "updated_at"])
    reconcile_offer_picks(draft)
    return entries


def clear_life(draft: CharacterDraft) -> None:
    """Start blank (#4865): drop the draft's Backgrounds picks and its beat states, keep
    every other chapter's pick and the ``LIFE_LOADED_FOR_KEY`` stamp (so the suggested
    life does not come back over an emptied one), and reconcile. Called by the draft's
    ``clear-life`` action."""
    draft.draft_data["distinctions"] = _entries_outside_the_life(draft)
    draft.draft_data[BEATS_KEY] = {}
    draft.save(update_fields=["draft_data", "updated_at"])
    reconcile_offer_picks(draft)


def _entries_outside_the_life(draft: CharacterDraft) -> list[DraftDistinctionEntry]:
    """The draft's entries that name no Backgrounds offer (#4865): what a load or a clear
    of the life leaves alone. A legacy entry with no offer list is kept too."""
    entries = draft.draft_data.get("distinctions", [])
    offer_ids = {oid for e in entries for oid in e.get("offer_ids", []) if isinstance(oid, int)}
    life_offer_ids = set(
        DistinctionOffer.objects.filter(
            pk__in=offer_ids, chapter=OfferChapter.BACKGROUNDS
        ).values_list("pk", flat=True)
    )
    return [e for e in entries if not (set(e.get("offer_ids", [])) & life_offer_ids)]


def _closed_ids(draft: CharacterDraft) -> set[int]:
    """Ids the draft's route has closed. Called by ``visible_offers``."""
    route = draft.selected_origin_template
    if route is None:
        return set()
    return set(route.closed_distinctions.values_list("id", flat=True))


def _innate_ids(draft: CharacterDraft) -> set[int]:
    """Ids granted automatically by the draft's species. Called by ``visible_offers``."""
    if draft.selected_species_id is None:
        return set()
    from world.species.services import species_innate_distinction_ids  # noqa: PLC0415

    return set(species_innate_distinction_ids(draft.selected_species))


def visible_offers(draft: CharacterDraft) -> dict[int, DistinctionOffer]:
    """Every active offer whose opener the draft satisfies, minus closed and innate.

    Called by ``offers_for`` and ``reconcile_offer_picks``.
    """
    ctx = _context(draft)
    hidden = _closed_ids(draft) | _innate_ids(draft)
    rows = DistinctionOffer.objects.filter(is_active=True).select_related(
        "distinction__category",
        "glimpse_tag",
        "origin_choice__slot",
        "schooling_line",
        "enemy_reason",
        "appearance_section",
        "beat",
        "unlocked_by",
    )
    return {o.id: o for o in rows if o.distinction_id not in hidden and _opener_satisfied(o, ctx)}


def _origin_opener_label(offer: DistinctionOffer, draft: CharacterDraft | None) -> str:
    """Return an origin choice label, including its anchored organization."""
    label = offer.origin_choice.name
    if draft is None:
        return label
    slot = offer.origin_choice.slot
    if slot.kind != QuestionKind.GROUP:
        return label
    answers = DraftAnswers.from_draft(draft)
    org_id = anchor_for(slot, draft, answers)
    if org_id is None:
        return label

    from world.societies.models import Organization  # noqa: PLC0415

    org = Organization.objects.filter(pk=org_id).first()
    return f"{label}, {org.name}" if org is not None else label


def opener_label(offer: DistinctionOffer, *, draft: CharacterDraft | None = None) -> str:
    """The name of the thing that opens this offer, for display and as a source string.

    Called by ``offers_for`` (a ``VisibleOffer``'s ``opener_label``, no ``draft`` --
    a not-yet-picked offer in the picker has nothing to anchor against) and, with
    ``draft`` given, by ``reconcile_offer_picks`` and the sync path in
    ``distinctions/views.py`` to record an entry's ``source`` / ``sources`` (review
    round 2, ruling B): the pairing table this offer replaced
    (pre-#3675 ``_grant_connection_distinctions``) recorded which GROUP answer's
    anchored organization a connection distinction was about, not just the answer's
    own name, and ``CharacterDistinction.source_description`` needs that same
    provenance. Only a LINEAGE offer on a GROUP question carries an anchor to
    resolve; every other opener is unaffected by ``draft``.
    """
    if offer.prompt:
        return ActorSheetPrompt(offer.prompt).label
    if offer.enemy_reason_id:
        return offer.enemy_reason.name
    if offer.enemy_degree:
        return EnemyDegree(offer.enemy_degree).label
    if offer.appearance_section_id:
        return offer.appearance_section.name
    if offer.feature_rows:
        # #3739: which feature is not knowable from the offer -- the same line is
        # offered on every one. The sync view overwrites this with the feature's own
        # name once it has resolved it, so ``source_description`` reads "Hair Color"
        # rather than the generic word; this is the fallback for a caller that has
        # no feature in hand (the picker, a closed-distinction hint).
        return "a feature"
    if offer.origin_choice_id:
        return _origin_opener_label(offer, draft)
    # The openers that are a named row: a Glimpse tag, a schooling line, a beat, the
    # card that unlocks a Final Touches line (#4846).
    for field in ("glimpse_tag", "schooling_line", "beat", "unlocked_by"):
        if getattr(offer, f"{field}_id"):
            return getattr(offer, field).name
    return ""


def _mutual_exclusions(dist_ids: set[int]) -> dict[int, set[int]]:
    """Every id in ``dist_ids``'s mutual-exclusion partners, in one flat query.

    Reads the symmetrical M2M's through table directly instead of
    ``Distinction.mutually_exclusive_with.all()`` per distinction (#3675 final fix
    B2) -- never a to-attr ``Prefetch`` (ADR-0278) and never
    ``cached_mutually_exclusive_with``, both of which only help a query already
    scoped to one model's rows. Checks both through-table columns rather than
    trusting Django's symmetrical-insert behavior to have written both directions.
    Called by ``offers_for``.
    """
    if not dist_ids:
        return {}
    through = Distinction.mutually_exclusive_with.through
    rows = through.objects.filter(
        Q(from_distinction_id__in=dist_ids) | Q(to_distinction_id__in=dist_ids)
    ).values_list("from_distinction_id", "to_distinction_id")
    exclusions: dict[int, set[int]] = defaultdict(set)
    for from_id, to_id in rows:
        if from_id in dist_ids:
            exclusions[from_id].add(to_id)
        if to_id in dist_ids:
            exclusions[to_id].add(from_id)
    return exclusions


def _effect_value(effect: DistinctionEffect) -> int | None:
    """The per-rank number an effect carries, or None when it has none."""
    value = effect.value_per_rank
    if value is None and effect.scaling_values:
        value = effect.scaling_values[0]
    if value is None and effect.amplifies_sources_by is not None:
        value = effect.amplifies_sources_by
    return value


def _effect_word(effect: DistinctionEffect) -> str:
    """One effect as the leaf prints it: ``+Deception``, ``-Willpower``, ``Immune to X``."""
    name = effect.target.name.replace("_", " ").strip().capitalize()
    if effect.grants_immunity_to_negative:
        return f"Immune to negative {name}"
    value = _effect_value(effect)
    if value is None:
        return name
    sign = "-" if value < 0 else "+"
    return f"{sign}{name}"


def term_label(target_name: str) -> str:
    """A modifier target's name as a card prints it: ``physical_development`` -> ``physical
    development``. Lowercase on purpose; the card's line reads ``+10 sailing``."""
    return target_name.replace("_", " ").strip().lower()


def effect_terms(effects: list[DistinctionEffect]) -> tuple[OfferEffectTerm, ...]:
    """The effect rows with their magnitudes, for the life page's cards (#4872)."""
    return tuple(
        OfferEffectTerm(
            target=effect.target.name,
            label=term_label(effect.target.name),
            value=None if effect.grants_immunity_to_negative else _effect_value(effect),
            immune=effect.grants_immunity_to_negative,
        )
        for effect in effects
    )


def terms_for(offers: Iterable[VisibleOffer]) -> list[OfferTerm]:
    """Every term the offers' effects name, each with its definition (#4872).

    Called by the offers view, once per response. The definition comes from the row
    that owns the term (ruled 2026-10-19): ``Trait.description`` for a target bound to
    a stat or skill, ``Aspect.description`` for one bound to an aspect, otherwise the
    target's own ``description``. One query over the targets, joined to both.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    names = {term.target for offer in offers for term in offer.effects}
    if not names:
        return []
    targets = ModifierTarget.objects.filter(name__in=names).select_related(
        "target_trait", "target_aspect"
    )
    out: list[OfferTerm] = []
    for target in sorted(targets, key=lambda t: t.name):
        if target.target_trait_id is not None:
            definition = target.target_trait.description
        elif target.target_aspect_id is not None:
            definition = target.target_aspect.description
        else:
            definition = target.description
        out.append(
            OfferTerm(name=target.name, label=term_label(target.name), definition=definition)
        )
    return out


def effect_line(effects: list[DistinctionEffect]) -> str:
    """The compact mechanics line under an offer, ``+Deception; -Willpower`` (#3709).

    Called by ``offers_for``. Sign and target name only: the numbers are the
    distinction's own business and the leaf is not a rules sheet.
    """
    return "; ".join(_effect_word(e) for e in effects)


def _effects_by_distinction(dist_ids: set[int]) -> dict[int, list[DistinctionEffect]]:
    out: dict[int, list[DistinctionEffect]] = defaultdict(list)
    rows = DistinctionEffect.objects.filter(distinction_id__in=dist_ids).select_related("target")
    for effect in rows.order_by("id"):
        out[effect.distinction_id].append(effect)
    return out


def _pinned_offer_ids(draft: CharacterDraft, offer_ids: set[int]) -> set[int]:
    """The offers the draft's Beginning pinned into the first look (#3709)."""
    if draft.selected_beginnings_id is None or not offer_ids:
        return set()
    rows = OfferFirstLook.objects.filter(
        beginning_id=draft.selected_beginnings_id, offer_id__in=offer_ids
    )
    return set(rows.values_list("offer_id", flat=True))


def offers_for(draft: CharacterDraft, chapter: OfferChapter) -> list[VisibleOffer]:
    """The priced choices this draft can see in one chapter, with lock state.

    Called by each chapter's view/serializer to render its offer list. Pinned
    (first look) offers sort first, then ``sort_order``, then id (#3709).
    """
    # A per-feature distinction (#3739) can be held several times over, so an entry
    # list is grouped by distinction rather than keyed by it. "Held" for the
    # exclusion checks below still means "the draft has this distinction at all".
    entries_by_dist: dict[int, list[DraftDistinctionEntry]] = defaultdict(list)
    for entry in draft.draft_data.get("distinctions", []):
        entries_by_dist[entry["distinction_id"]].append(entry)
    held = set(entries_by_dist)
    chapter_offers = [
        offer
        for offer in visible_offers(draft).values()
        if offer.chapter == chapter and offer.arrives_as == OfferArrival.CHOICE
    ]
    exclusions = _mutual_exclusions({offer.distinction_id for offer in chapter_offers})
    conflict_ids = {cid for ids in exclusions.values() for cid in ids if cid in held}
    conflict_names = dict(Distinction.objects.filter(id__in=conflict_ids).values_list("id", "name"))
    effects = _effects_by_distinction({offer.distinction_id for offer in chapter_offers})
    pinned = _pinned_offer_ids(draft, {offer.id for offer in chapter_offers})

    out: list[VisibleOffer] = []
    for offer in chapter_offers:
        dist = offer.distinction
        conflict_id = next((x for x in exclusions.get(dist.id, ()) if x in held), None)
        conflict_name = conflict_names.get(conflict_id) if conflict_id is not None else None
        dist_entries = entries_by_dist.get(dist.id, [])
        # Held elsewhere: the draft has it, and not from this line (a legacy entry with
        # no offer_ids key counts as elsewhere too). A per-feature line is never held
        # elsewhere -- it is offered on every feature and the leaf reads its own
        # per-feature state off the draft entries, which carry the feature.
        held_elsewhere = not dist.taken_per_feature and any(
            offer.id not in e.get("offer_ids", []) for e in dist_entries
        )
        out.append(
            VisibleOffer(
                offer_id=offer.id,
                distinction_id=dist.id,
                name=offer.name,
                distinction_name=dist.name,
                player_line=offer.player_line,
                chapter=offer.chapter,
                arrives_as=offer.arrives_as,
                opener_label=opener_label(offer),
                cost_per_rank=dist.cost_per_rank,
                max_rank=dist.max_rank,
                is_locked=conflict_name is not None,
                lock_reason=f"Cannot be held with {conflict_name}" if conflict_name else "",
                opener_key=offer.opener_key,
                first_look=offer.id in pinned,
                held=held_elsewhere,
                effect_line=effect_line(effects.get(dist.id, [])),
                taken_per_feature=dist.taken_per_feature,
                opens_feature=dist.opens_feature,
                requires_feature_opened=dist.requires_feature_opened,
                cg_max_rank=dist.cg_max_rank,
                group=offer.group,
                asks_figure_name=dist.asks_figure_name,
                effects=effect_terms(effects.get(dist.id, [])),
            )
        )
    # Appearance groups by section, in the sections' own order; within a group the
    # pinned lines lead, then sort_order, then id.
    group_orders = {
        offer.id: (offer.appearance_section.sort_order if offer.appearance_section_id else 0)
        for offer in chapter_offers
    }
    # #3739: a feature-rows line belongs to no section, and the leaf mounts it on the
    # feature rows themselves. Sorting it after every section keeps a section's own
    # block contiguous for the mounts that group by ``opener_key``.
    for offer in chapter_offers:
        if offer.feature_rows:
            group_orders[offer.id] = _FEATURE_ROWS_GROUP_ORDER
    # Backgrounds groups by beat, in the pool's own order (stage, then the beat's
    # sort order), so one beat's answers stay contiguous for the leaf's mounts (#4124).
    if chapter == OfferChapter.BACKGROUNDS:
        beat_rank = {beat.pk: i for i, beat in enumerate(beat_pool(draft))}
        for offer in chapter_offers:
            group_orders[offer.id] = beat_rank.get(offer.beat_id, len(beat_rank))
    sort_orders = {offer.id: offer.sort_order for offer in chapter_offers}
    out.sort(
        key=lambda o: (
            group_orders[o.offer_id],
            not o.first_look,
            sort_orders[o.offer_id],
            o.offer_id,
        )
    )
    return out


def degree_marks() -> dict[str, list[str]]:
    """Degree value -> the distinction names its bundled enemy-chapter lines carry (#3709).

    Called by ``enemies.degree_grants`` so the leaf's degree row can say "bundles X"
    before anyone picks. Read from the authored offer lines, never from a constant.
    """
    rows = DistinctionOffer.objects.filter(
        is_active=True,
        chapter=OfferChapter.ENEMY,
        arrives_as=OfferArrival.BUNDLED,
    ).exclude(enemy_degree="")
    out: dict[str, list[str]] = defaultdict(list)
    for offer in rows.select_related("distinction").order_by("sort_order", "id"):
        out[offer.enemy_degree].append(offer.distinction.name)
    return dict(out)


def closed_for(draft: CharacterDraft, chapter: OfferChapter) -> list[ClosedDistinction]:
    """The route's closed-distinction list, for the one chapter that would have shown them.

    Called by each chapter's view/serializer alongside ``offers_for``. Each row
    carries ``opener_labels``: the opener labels of this chapter's own active
    CHOICE offers for the closed distinction whose opener the draft has satisfied
    (the same ``_opener_satisfied`` check ``visible_offers`` applies, evaluated
    directly here since ``visible_offers`` itself excludes anything closed before
    a caller ever sees it). Empty when no offer in this chapter opens it (the
    route closed something a different chapter offers); since #3709 every
    chapter's offers carry an opener (a prompt, a reason or degree, a section). A chapter
    mount (``GlimpseAxes``) uses this to print the closed hint once, under the
    specific pick that would have opened it, instead of under every pick.
    ``opener_ids`` (#3675 final fix B4) carries the same offers' ids, index-aligned
    with ``opener_labels``, so a caller can match a closed row to a specific offer
    (e.g. a Glimpse tag's own offer ids) without a name/label match.
    """
    route = draft.selected_origin_template
    if route is None:
        return []
    closed = list(route.closed_distinctions.all())
    if not closed:
        return []
    closed_ids = {d.id for d in closed}
    ctx = _context(draft)
    rows = DistinctionOffer.objects.filter(
        is_active=True,
        chapter=chapter,
        arrives_as=OfferArrival.CHOICE,
        distinction_id__in=closed_ids,
    ).select_related(
        "glimpse_tag",
        "origin_choice",
        "schooling_line",
        "enemy_reason",
        "appearance_section",
        "unlocked_by",
    )
    openers: dict[int, list[str]] = defaultdict(list)
    opener_ids: dict[int, list[int]] = defaultdict(list)
    for offer in rows:
        if _opener_satisfied(offer, ctx):
            label = opener_label(offer)
            if label:
                openers[offer.distinction_id].append(label)
                opener_ids[offer.distinction_id].append(offer.id)
    return [
        ClosedDistinction(
            distinction_id=d.id,
            name=d.name,
            reason=route.closed_reason,
            opener_labels=openers.get(d.id, []),
            opener_ids=opener_ids.get(d.id, []),
        )
        for d in closed
    ]


def entry_price(entry: DraftDistinctionEntry, distinction: Distinction) -> int:
    """The CG-point price of a draft entry: free if any source arrived bundled or carried.

    Called by ``reconcile_offer_picks`` when repricing a kept entry.
    """
    if any(a in (OfferArrival.BUNDLED, OfferArrival.CARRIED) for a in entry.get("arrivals", [])):
        return 0
    return distinction.calculate_total_cost(entry.get("rank", 1))


def _carried_offer(draft: CharacterDraft) -> tuple[TraditionStateLine, Distinction] | None:
    """The drawback the draft's tradition pick carries, and its state line, if any.

    Called by ``reconcile_offer_picks``.
    """
    line = _slate_line(draft)
    if line is None:
        return None
    state_line = TraditionStateLine.objects.filter(state=line.state).first()
    if state_line is None or state_line.carries_id is None:
        return None
    return state_line, state_line.carries


def _drop_vanished_sources(
    entries: list[DraftDistinctionEntry],
    visible: dict[int, DistinctionOffer],
    carried_key: str | None,
) -> list[str]:
    """Strip an entry's sources whose offer is no longer visible, in place.

    Called by ``reconcile_offer_picks`` before the carried/bundled offers are applied,
    so a source that vanished this call (e.g. a tradition switch) never survives
    alongside a still-live one. An entry with no ``offer_ids`` key at all is a legacy
    pick: drafts saved before 0106 (when the offers system landed) hold catalogue
    picks the player made against no ``DistinctionOffer`` at all, since none existed
    yet, and there is nothing to re-derive their offer from now. Such an entry is
    left exactly as stored -- not touched here, not dropped or repriced in
    ``_drop_empty_and_reprice`` -- until the player changes it through a path that
    does carry ``offer_ids`` (review round 2, ruling A).
    """
    changed: list[str] = []
    for entry in entries:
        if "offer_ids" not in entry:  # noqa: STRING_LITERAL
            continue
        srcs = entry.setdefault("sources", [])
        arrs = entry.setdefault("arrivals", [])
        ids = entry["offer_ids"]
        keep = [(oid in visible) or (isinstance(oid, str) and oid == carried_key) for oid in ids]
        if not all(keep):
            entry["offer_ids"] = [x for x, k in zip(ids, keep, strict=True) if k]
            entry["sources"] = [x for x, k in zip(srcs, keep, strict=True) if k]
            entry["arrivals"] = [x for x, k in zip(arrs, keep, strict=True) if k]
            changed.append(entry["distinction_name"])
    return changed


def _apply_carried(
    entries: list[DraftDistinctionEntry],
    by_dist: dict[int, DraftDistinctionEntry],
    carried: tuple[TraditionStateLine, Distinction] | None,
) -> list[str]:
    """Add or restore the tradition state's carried drawback, in place.

    Called by ``reconcile_offer_picks``. A carried drawback has no ``DistinctionOffer``
    row, so its source key is the synthetic ``"state:<TraditionState value>"`` string.
    """
    if carried is None:
        return []
    state_line, drawback = carried
    carried_key = f"state:{state_line.state}"
    entry = by_dist.get(drawback.id)
    if entry is None:
        entry = build_distinction_entry(drawback, rank=1)
        entry["offer_ids"] = [carried_key]
        entry["sources"] = [state_line.entry_line]
        entry["arrivals"] = [OfferArrival.CARRIED]
        entry["cost"] = drawback.cost_per_rank
        entries.append(entry)
        by_dist[drawback.id] = entry
        return [drawback.name]
    if carried_key not in entry.get("offer_ids", []):
        # A legacy entry (see _drop_vanished_sources) has no offer_ids key at all;
        # setdefault converts it into an offer-tracked entry the moment a live
        # source actually needs to record itself against it, without disturbing it
        # on every other reconcile pass.
        entry.setdefault("offer_ids", []).append(carried_key)
        entry.setdefault("sources", []).append(state_line.entry_line)
        entry.setdefault("arrivals", []).append(OfferArrival.CARRIED)
        return [drawback.name]
    return []


def _group_offer_anchors(
    offers: list[DistinctionOffer], draft: CharacterDraft, answers: DraftAnswers
) -> tuple[dict[int, int | None], set[int]]:
    """Resolve GROUP-question anchors and collect their organization ids."""
    anchor_by_offer: dict[int, int | None] = {}
    org_ids: set[int] = set()
    for offer in offers:
        if not offer.origin_choice_id:
            continue
        slot = offer.origin_choice.slot
        if slot.kind != QuestionKind.GROUP:
            continue
        org_id = anchor_for(slot, draft, answers)
        anchor_by_offer[offer.id] = org_id
        if org_id is not None:
            org_ids.add(org_id)
    return anchor_by_offer, org_ids


def _bundled_label(
    offer: DistinctionOffer,
    anchor_by_offer: dict[int, int | None],
    orgs: dict[int, Organization],
    enemy_name: str = "",
) -> str:
    """Build a bundled offer label using the prefetched organization cache.

    An enemy-chapter line's source names the enemy too ("They want you ruined: the
    Rouault"), the way a Lineage line names its anchored organization (#3709);
    ``enemy_name`` is resolved once by the caller.
    """
    label = opener_label(offer)
    if offer.chapter == OfferChapter.ENEMY:
        return f"{label}: {enemy_name}" if enemy_name else label
    org_id = anchor_by_offer.get(offer.id)
    if org_id is None:
        return label
    org = orgs.get(org_id)
    return f"{label}, {org.name}" if org is not None else label


def _bundled_opener_labels(offers: list[DistinctionOffer], draft: CharacterDraft) -> dict[int, str]:
    """``opener_label(offer, draft=draft)`` for every ``offers`` row, batched.

    Called by ``_apply_bundled``. Mirrors ``questionnaire.bundled_distinctions``'s
    own batching: every GROUP-question offer's anchor is resolved first, the
    Organizations it names are bulk-fetched once, then each label is built from
    that shared cache -- never one ``Organization.objects.filter(pk=...)`` query
    per offer, which the naive per-offer ``opener_label(draft=...)`` call did
    (#3675 fix round 3).
    """
    if not offers:
        return {}
    answers = DraftAnswers.from_draft(draft)
    anchor_by_offer, org_ids = _group_offer_anchors(offers, draft, answers)

    from world.societies.models import Organization  # noqa: PLC0415

    orgs = {o.pk: o for o in Organization.objects.filter(pk__in=org_ids)} if org_ids else {}
    enemy_name = ""
    if any(offer.chapter == OfferChapter.ENEMY for offer in offers):
        from world.character_creation.enemies import resolve_enemy  # noqa: PLC0415

        resolved = resolve_enemy(draft)
        enemy_name = resolved.name if resolved is not None else ""
    return {offer.id: _bundled_label(offer, anchor_by_offer, orgs, enemy_name) for offer in offers}


def _apply_bundled(
    entries: list[DraftDistinctionEntry],
    by_dist: dict[int, DraftDistinctionEntry],
    visible: dict[int, DistinctionOffer],
    draft: CharacterDraft,
) -> list[str]:
    """Add or extend every distinction bundled free with an answer the draft holds.

    Called by ``reconcile_offer_picks``.
    """
    changed: list[str] = []
    bundled = [o for o in visible.values() if o.arrives_as == OfferArrival.BUNDLED]
    labels = _bundled_opener_labels(bundled, draft)
    for offer in bundled:
        entry = by_dist.get(offer.distinction_id)
        label = labels[offer.id]
        if entry is None:
            entry = build_distinction_entry(offer.distinction, rank=1, offer=offer, source=label)
            entries.append(entry)
            by_dist[offer.distinction_id] = entry
            changed.append(offer.distinction.name)
        elif offer.id not in entry.get("offer_ids", []):
            # See _apply_carried's identical setdefault: converts a legacy entry
            # (no offer_ids key) into an offer-tracked one only when a live offer
            # actually needs to record itself against it.
            entry.setdefault("offer_ids", []).append(offer.id)
            entry.setdefault("sources", []).append(label)
            entry.setdefault("arrivals", []).append(OfferArrival.BUNDLED)
            changed.append(offer.distinction.name)
    return changed


def opened_features(draft_data: dict) -> set[tuple[str, int]]:
    """The features this draft has made distinctive, as ``(trait name, marking id)``.

    One query. The single reader of "is this feature unlocked?" for everything
    downstream of the draft (#3739): the Appearance validator's palette check,
    ``services._apply_form_trait_descriptors`` at finalize, and the form-options
    view's widened palette. A feature is unlocked exactly while an ``opens_feature``
    entry naming it sits in ``draft_data["distinctions"]`` — refund the pick and the
    widened palette, the description and the axes all close again together.
    """
    entries = draft_data.get("distinctions") or []
    if not entries:
        return set()
    opens = set(
        Distinction.objects.filter(
            id__in={e["distinction_id"] for e in entries if e.get("distinction_id")},
            opens_feature=True,
        ).values_list("id", flat=True)
    )
    if not opens:
        return set()
    return {feature_of(e) for e in entries if e.get("distinction_id") in opens}


def opened_feature_traits(draft_data: dict) -> set[str]:
    """The names of the trait rows this draft has made distinctive (#3739).

    ``opened_features`` narrowed to trait features; markings are unlocked the same
    way but are addressed by id, and their description is free either way.
    """
    return {trait for trait, _ in opened_features(draft_data) if trait}


def _drop_vanished_features(
    entries: list[DraftDistinctionEntry],
    draft: CharacterDraft,
) -> tuple[list[DraftDistinctionEntry], list[str]]:
    """Drop per-feature picks whose feature or whose unlock has gone (#3739).

    Called by ``reconcile_offer_picks`` after the carried/bundled passes. Two
    things can strand a per-feature entry between syncs:

    * the **feature** itself is gone -- the player deleted the ``DraftMarking``
      the pick names. (A trait row cannot vanish: every trait the species offers
      is always on the page, whether or not an option is chosen for it.)
    * the **unlock** is gone -- the axis lines (``requires_feature_opened``) may
      only be held where "Make it distinctive" (``opens_feature``) is held on the
      same feature, so dropping the unlock drops the axes bought under it.

    Both are refunded by dropping the entry, which ``_drop_empty_and_reprice``
    then leaves alone; the returned names go into the caller's changed list so
    the player is told what the change cost them.
    """
    feature_entries = [e for e in entries if feature_of(e) != ("", 0)]
    if not feature_entries:
        return entries, []

    live_marking_ids = set(draft.markings.values_list("id", flat=True))
    flags = Distinction.objects.filter(
        id__in={e["distinction_id"] for e in feature_entries}
    ).values_list("id", "opens_feature", "requires_feature_opened")
    opens = {did for did, o, _ in flags if o}
    needs_open = {did for did, _, r in flags if r}

    opened_features = {feature_of(e) for e in feature_entries if e["distinction_id"] in opens}

    kept: list[DraftDistinctionEntry] = []
    changed: list[str] = []
    for entry in entries:
        feature = feature_of(entry)
        marking_id = feature[1]
        if marking_id and marking_id not in live_marking_ids:
            changed.append(entry["distinction_name"])
            continue
        if entry["distinction_id"] in needs_open and feature not in opened_features:
            changed.append(entry["distinction_name"])
            continue
        kept.append(entry)
    return kept, changed


def _drop_empty_and_reprice(
    entries: list[DraftDistinctionEntry],
) -> tuple[list[DraftDistinctionEntry], list[str]]:
    """Drop entries whose last source just vanished, and reprice every survivor.

    Called by ``reconcile_offer_picks``. A carried-only entry is priced at the
    drawback's own ``cost_per_rank`` (Decision 3 of the #3675 spec: the refund
    lands even though it wasn't a choice); everything else goes through
    ``entry_price``. A legacy entry with no ``offer_ids`` key (see
    ``_drop_vanished_sources``) is kept exactly as stored and never repriced -- it
    predates the offers system, so there is no offer to price it against.
    """
    changed: list[str] = []
    kept: list[DraftDistinctionEntry] = []
    dists = Distinction.objects.in_bulk([e["distinction_id"] for e in entries])
    for entry in entries:
        if "offer_ids" not in entry:  # noqa: STRING_LITERAL
            kept.append(entry)
            continue
        if not entry["offer_ids"]:
            changed.append(entry["distinction_name"])
            continue
        dist = dists[entry["distinction_id"]]
        carried_only = OfferArrival.CARRIED in entry["arrivals"] and len(entry["arrivals"]) == 1
        price = dist.cost_per_rank if carried_only else entry_price(entry, dist)
        if price != entry.get("cost"):
            entry["cost"] = price
            if entry["distinction_name"] not in changed:
                changed.append(entry["distinction_name"])
        kept.append(entry)
    return kept, changed


def reconcile_offer_picks(draft: CharacterDraft) -> list[str]:
    """Apply carried and bundled offers, drop picks whose offer has gone, reprice.

    Called after every draft patch that could change which offers are open (a
    Glimpse tag pick, a Lineage answer, a tradition select). Returns the
    distinction names dropped or repriced. Saves ``draft_data`` when anything
    changed.
    """
    original = draft.draft_data.get("distinctions", [])
    entries: list[DraftDistinctionEntry] = list(original)
    visible = visible_offers(draft)
    # Carried and bundled offers are never per-feature (#3739), so they index by
    # distinction alone -- and must never match a per-feature entry, which would let
    # a bundled grant reprice "Alluring on your scar" to the bundle's free price.
    by_dist = {e["distinction_id"]: e for e in entries if feature_of(e) == ("", 0)}
    carried = _carried_offer(draft)
    carried_key = f"state:{carried[0].state}" if carried else None

    changed: list[str] = []
    changed += _drop_vanished_sources(entries, visible, carried_key)
    changed += _apply_carried(entries, by_dist, carried)
    changed += _apply_bundled(entries, by_dist, visible, draft)
    entries, dropped_features = _drop_vanished_features(entries, draft)
    changed += dropped_features
    kept, repriced = _drop_empty_and_reprice(entries)
    changed += repriced

    if kept != original or changed:
        draft.draft_data["distinctions"] = kept
        draft.save(update_fields=["draft_data"])

    # de-duplicate while keeping order
    seen: set[str] = set()
    return [n for n in changed if not (n in seen or seen.add(n))]
