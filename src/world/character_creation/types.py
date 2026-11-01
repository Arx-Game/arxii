"""Type declarations for character creation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from world.magic.types.teaching_fit import TeachingFit

# Stage number → list of human-readable error messages.
# Empty list means the stage is complete.
type StageValidationErrors = dict[int, list[str]]


@dataclass(frozen=True)
class OfferEffectTerm:
    """One effect of an offered card as the life page prints it (#4872).

    ``target`` is the modifier target's name, the key into the response's ``terms``;
    ``label`` the words on the card; ``value`` the per-rank magnitude, None when the
    effect carries none (an immunity, a grant with no number).
    """

    target: str
    label: str
    value: int | None
    immune: bool = False


@dataclass(frozen=True)
class OfferTerm:
    """A term on a card's mechanics line and its definition (#4872).

    Built by ``offers.terms_for`` once per offers response. The definition is read from
    the row that owns the term: ``Trait.description`` for a target bound to a stat or
    skill, ``Aspect.description`` for one bound to an aspect, else the target's own.
    """

    name: str
    label: str
    definition: str


@dataclass(frozen=True)
class VisibleOffer:
    """One priced choice a draft can see in a CG chapter (#3675).

    Built by ``world.character_creation.offers.offers_for`` for each chapter's
    serializer/view to render; carries its own mutual-exclusion lock state so
    the frontend never has to re-derive it.
    """

    offer_id: int
    distinction_id: int
    name: str
    player_line: str
    chapter: str
    arrives_as: str
    opener_label: str
    cost_per_rank: int
    max_rank: int
    is_locked: bool
    lock_reason: str
    #: What opens this offer, as a stable grouping key (#3709): ``prompt:never_do``,
    #: ``reason:<id>``, ``degree:ruined``, ``section:<id>``; the leaf mounts one block
    #: per key. ``DistinctionOffer.opener_key``.
    opener_key: str = ""
    #: The draft's Beginning pinned this line into the few shown at rest (#3709).
    first_look: bool = False
    #: The distinction's own name (#4395): a grid card reads the offer's label and,
    #: when the label is the author's own words, the distinction under it.
    distinction_name: str = ""
    #: The distinction is already in the draft from a different offer (#3709): the
    #: leaf prints it held, never offers it twice.
    held: bool = False
    #: The compact mechanics line, "+Deception; -Willpower" (#3709), built from the
    #: distinction's effect rows by ``offers.effect_line``.
    effect_line: str = ""
    #: Held once per feature rather than once per character (#3739): the Appearance
    #: leaf renders this line on every trait row and marking instead of once under a
    #: section, and the draft can hold it several times over.
    taken_per_feature: bool = False
    #: This is the one-point pick that makes a feature distinctive (#3739): taking it
    #: opens that feature's description, its full palette, and the axis lines below it.
    opens_feature: bool = False
    #: Offerable on a feature only where ``opens_feature`` is already held there
    #: (#3739): the Alluring / Menacing / Majestic axes.
    requires_feature_opened: bool = False
    #: The rank ceiling character creation applies, when lower than ``max_rank``
    #: (#3739: the axes reach 5 in play but stop at 3 in CG). ``0`` means
    #: ``max_rank`` governs in CG too.
    cg_max_rank: int = 0
    #: The heading this answer is listed under on the life page (#4872), blank for
    #: none; ``DistinctionOffer.group``.
    group: str = ""
    #: The card is a person and takes a figure's name when picked (#4872);
    #: ``Distinction.asks_figure_name``.
    asks_figure_name: bool = False
    #: The effect rows with their magnitudes (#4872), for a grid card that prints
    #: ``+10 sailing`` and links each term to its definition. ``effect_line`` stays the
    #: sign-and-name line the list layouts print.
    effects: tuple[OfferEffectTerm, ...] = ()


@dataclass(frozen=True)
class BeatPoolEntry:
    """One beat of the Backgrounds library as this draft meets it (#4124).

    Built by ``world.character_creation.offers.beats_for`` for the Lineage stage:
    the beat's own words, which stage it belongs to, how many answers it takes,
    and the draft's state on it (taken, unknown, the optional line). The answers
    themselves are the ``BACKGROUNDS`` chapter's offers whose ``opener_key`` is
    ``beat:<beat_id>``, fetched through the ordinary offers endpoint.
    """

    beat_id: int
    name: str
    prompt: str
    life_stage: str
    selection: str
    taken: bool
    unknown: bool
    line: str
    answer_offer_ids: list[int]
    #: How many answers this beat allows this draft (#4395): one for a one-of beat,
    #: ``offers.age_pick_allowance`` for a beat whose picks scale with age, None for any.
    allowance: int | None = None
    #: True when ``allowance`` is career points spent by rank (#4829): a rank-four card
    #: spends four. False when it counts cards.
    allowance_is_points: bool = False


@dataclass(frozen=True)
class ClosedDistinction:
    """One distinction a route's ``closed_distinctions`` hides from every chapter (#3675).

    Built by ``world.character_creation.offers.closed_for`` so a chapter can print
    the route's closed line instead of silently omitting the option.
    """

    distinction_id: int
    name: str
    reason: str
    #: Opener labels of the requesting chapter's own active offers for this
    #: distinction whose opener the draft satisfies (#3675 fix round 2); lets a
    #: chapter mount (the Glimpse's ``GlimpseAxes``) print the closed hint once,
    #: under the specific pick that would have opened it, instead of under every
    #: pick. Empty when no offer in this chapter opens it (every chapter's offers
    #: carry an opener since #3709: a prompt, a reason or degree, a section).
    opener_labels: list[str]
    #: The same offers' ids, index-aligned with ``opener_labels`` (#3675 final fix
    #: B4). A caller that needs to match a closed row to a specific offer (a
    #: Glimpse tag's own offer ids) uses this, never a name/label match.
    opener_ids: list[int]


class StatAdjustment(TypedDict):
    """Result of a stat cap enforcement adjustment."""

    stat: str
    old_display: int
    new_display: int
    reason: str


class CGPointBreakdownEntry(TypedDict):
    """A single line item in the CG points breakdown."""

    category: str
    item: str
    cost: int


@dataclass(frozen=True)
class DistinctionBonusSource:
    """One distinction, at one rank, feeding a ModifierTarget: what its effect adds.

    ``max_rank`` is the distinction's own: a breakdown names the rank held only when
    the distinction has more than one ("Tradition Training, rank 1", but "Studious").
    """

    name: str
    rank: int
    points: int
    max_rank: int


@dataclass(frozen=True)
class MagicTrainingPool:
    """The points a draft spends on Magic skills, with the breakdown (slice 2 of #4659).

    ``base`` is the distinctions' sum; ``gift_bonus`` / ``affinity_bonus`` are the
    Tradition's fit bonuses (0 when ``base`` is 0). ``total`` is rounded down to a whole
    skill tier; ``required_spend`` is what the draft must spend (capped by what the
    Magic skills can hold). ``sources`` is one ``DistinctionBonusSource`` per
    contributing (distinction, rank).
    """

    base: int
    gift_bonus: int
    affinity_bonus: int
    total: int
    required_spend: int
    fit: "TeachingFit"
    sources: list[DistinctionBonusSource]


@dataclass(frozen=True)
class OrganizationChoice:
    """One organization an ask may seat the character in (#4852, #4856)."""

    id: int
    name: str
    is_covert: bool


@dataclass(frozen=True)
class FinalTouchesCard:
    """One ask a held card raises at Final Touches (#4852, slice 6 of #4813).

    ``prompt`` is a ``FinalTouchesPrompt`` value; ``detail`` carries what the leaf prints
    beside it when the prompt has nothing to answer (the Path's stronger Aspect's name for
    ``path_aspect``), else blank; ``choices`` the organizations an ``organization`` or ``tie``
    ask picks from (#4856), empty for every other prompt. Built by ``offers.final_touches_cards``.
    """

    distinction_id: int
    name: str
    prompt: str
    detail: str
    choices: tuple[OrganizationChoice, ...] = ()
