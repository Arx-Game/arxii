"""Kinship graph services (#2062): writers + viewer-aware derivation walks.

Every relationship readout is derived by walking typed facts — nothing like
"cousin" is ever stored. All reads are **viewer-aware**: a fact is visible
when it is on the public record, when the viewer has learned the secret
gating it, or when the caller passes the ``OMNISCIENT`` sentinel (staff).
``viewer=None`` is an anonymous knows-nothing viewer (public record only) —
web/telnet surfaces pass the viewing character's ``RosterEntry``.

Truth resolution: a public-but-false fact renders as fact to anyone who has
not learned the hidden truth; a knower sees the true fact and the false one
flagged ``believed_lie``. Renderers get both and choose presentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.roster.constants import (
    DefinitionTier,
    MembershipBasis,
    MembershipEndReason,
    ParentageKind,
    RelationshipType,
)
from world.roster.models import (
    Family,
    FamilyMembership,
    KinSlotPool,
    Kinsperson,
    ParentageEdge,
    Soul,
    SoulIncarnation,
    Union,
    UnionKind,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.secrets.models import Secret


class KinshipServiceError(Exception):
    """A kinship-service refusal, carrying a player-safe message."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


# Staff/omniscient viewer sentinel: sees everything, including hidden facts
# with no secret at all (staff-only facts). ``viewer=None`` means an
# anonymous/knows-nothing viewer (mid-CG browsers): public record only.
OMNISCIENT = object()


def _viewer_knows(secret: Secret | None, viewer: object) -> bool:
    """Whether ``viewer`` has learned ``secret`` (explicit knowledge only).

    Deliberately does NOT give the secret's subject an implicit pass — a
    Misbegotten's own hidden parentage is unknown to them until a
    SecretKnowledge row says otherwise (``Secret.subject_aware`` gates the
    own-secrets shelf the same way).
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    if secret is None or not isinstance(viewer, RosterEntry):
        return False
    from world.secrets.services import secret_known_to  # noqa: PLC0415

    return secret_known_to(secret, viewer)


def fact_visible(fact: object, viewer: object) -> bool:
    """Whether a truth-carrying row (edge/union/incarnation) is visible.

    ``viewer`` is a RosterEntry, ``None`` (anonymous — public record only),
    or the ``OMNISCIENT`` sentinel (staff — everything).
    """
    if viewer is OMNISCIENT:
        return True
    if fact.is_public_record:
        return True
    return _viewer_knows(fact.secret, viewer)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def create_person(  # noqa: PLR0913 — keyword-only; each arg is a distinct node field
    *,
    name: str = "",
    tier: str = DefinitionTier.NAME_ONLY,
    sheet: CharacterSheet | None = None,
    family: Family | None = None,
    description: str = "",
    age: int | None = None,
    gender: object | None = None,
    is_deceased: bool = False,
    created_by: object | None = None,
) -> Kinsperson:
    """Create a Kinsperson node; sheet-bound nodes derive tier from the sheet."""
    if sheet is not None and tier in (DefinitionTier.NAME_ONLY, DefinitionTier.FUNCTIONARY):
        tier = DefinitionTier.SHEETED
    person = Kinsperson.objects.create(
        name=name,
        definition_tier=tier,
        sheet=sheet,
        family=family,
        description=description,
        age=age,
        gender=gender,
        is_deceased=is_deceased,
        created_by=created_by,
    )
    if family is not None:
        FamilyMembership.objects.create(
            kinsperson=person,
            family=family,
            basis=MembershipBasis.BORN,
            started_at=timezone.now(),
        )
    return person


def _mint_hidden_secret(
    *,
    about: Kinsperson,
    fallback: Kinsperson | None,
    content: str,
    level: int,
) -> Secret | None:
    """Mint the Secret gating a hidden kinship fact, when a sheet exists to anchor it.

    The subject is the sheet-bound party the fact is about (child first for
    parentage). The secret starts ``subject_aware=False`` — hidden kinship
    truths are unknown even to their subject until discovery grants
    knowledge. No sheet on either side → no secret → the fact is staff-only.
    """
    from world.secrets.constants import SecretProvenance  # noqa: PLC0415
    from world.secrets.services import author_secret  # noqa: PLC0415

    subject_sheet = about.sheet or (fallback.sheet if fallback is not None else None)
    if subject_sheet is None:
        return None
    secret = author_secret(
        subject_sheet=subject_sheet,
        provenance=SecretProvenance.GM_AUTHORED,
        level=level,
        content=content,
    )
    secret.subject_aware = False
    secret.save(update_fields=["subject_aware"])
    return secret


@transaction.atomic
def record_parentage(  # noqa: PLR0913 — keyword-only; each arg is a distinct edge field
    *,
    child: Kinsperson,
    parent: Kinsperson,
    kind: str = ParentageKind.BIOLOGICAL,
    is_public_record: bool = True,
    is_true: bool = True,
    born_within_union: Union | None = None,
    secret: Secret | None = None,
    secret_content: str = "",
    secret_level: int | None = None,
) -> ParentageEdge:
    """Record a typed parent→child edge.

    Hidden edges (``is_public_record=False``) anchor a Secret: pass one, or
    let this mint a GM-authored, subject-unaware one (``secret_content`` /
    ``secret_level``). Hidden with no sheet on either side stays staff-only.
    """
    if child.pk == parent.pk:
        msg = "a person cannot be their own parent"
        raise KinshipServiceError(msg, user_message="A person cannot be their own parent.")
    if not is_public_record and secret is None and secret_content:
        from world.secrets.constants import SecretLevel  # noqa: PLC0415

        secret = _mint_hidden_secret(
            about=child,
            fallback=parent,
            content=secret_content,
            level=secret_level or SecretLevel.UNCOMMON_KNOWLEDGE,
        )
    return ParentageEdge.objects.create(
        child=child,
        parent=parent,
        kind=kind,
        is_public_record=is_public_record,
        is_true=is_true,
        born_within_union=born_within_union,
        secret=secret,
    )


@transaction.atomic
def record_union(  # noqa: PLR0913 — keyword-only
    *,
    kind: UnionKind,
    members: list[Kinsperson],
    started_at: object | None = None,
    is_public_record: bool = True,
    is_true: bool = True,
    secret: Secret | None = None,
) -> Union:
    """Record a union between two or more people."""
    min_members = 2
    if len(members) < min_members:
        msg = f"a union needs at least {min_members} members, got {len(members)}"
        raise KinshipServiceError(msg, user_message="A union needs at least two members.")
    union = Union.objects.create(
        kind=kind,
        started_at=started_at,
        is_public_record=is_public_record,
        is_true=is_true,
        secret=secret,
    )
    union.members.set(members)
    return union


@transaction.atomic
def record_incarnation(  # noqa: PLR0913 — keyword-only
    *,
    soul: Soul | None,
    kinsperson: Kinsperson,
    sequence: int | None = None,
    is_public_record: bool = False,
    is_true: bool = True,
    secret: Secret | None = None,
    secret_content: str = "",
) -> SoulIncarnation:
    """Add a life to a soul's chain (minting the soul when None).

    ``sequence`` defaults to appending after the chain's latest life.
    """
    if soul is None:
        soul = Soul.objects.create()
    if sequence is None:
        last = soul.incarnations.order_by("-sequence").first()
        sequence = (last.sequence + 1) if last is not None else 1
    if not is_public_record and secret is None and secret_content:
        from world.secrets.constants import SecretLevel  # noqa: PLC0415

        secret = _mint_hidden_secret(
            about=kinsperson,
            fallback=None,
            content=secret_content,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
        )
    return SoulIncarnation.objects.create(
        soul=soul,
        kinsperson=kinsperson,
        sequence=sequence,
        is_public_record=is_public_record,
        is_true=is_true,
        secret=secret,
    )


@transaction.atomic
def add_membership(
    *,
    kinsperson: Kinsperson,
    family: Family,
    basis: str,
    is_primary: bool = True,
) -> FamilyMembership:
    """Add a family membership claim; primary claims update the surname denorm."""
    membership = FamilyMembership.objects.create(
        kinsperson=kinsperson,
        family=family,
        basis=basis,
        is_primary=is_primary,
        started_at=timezone.now(),
    )
    if is_primary:
        FamilyMembership.objects.filter(
            kinsperson=kinsperson, is_primary=True, ended_at__isnull=True
        ).exclude(pk=membership.pk).update(is_primary=False)
        kinsperson.family = family
        kinsperson.save(update_fields=["family"])
    return membership


@transaction.atomic
def end_membership(
    *,
    membership: FamilyMembership,
    reason: str = MembershipEndReason.RENOUNCED,
) -> FamilyMembership:
    """End a membership claim; clears the surname denorm when it was primary."""
    membership.ended_at = timezone.now()
    membership.end_reason = reason
    membership.save(update_fields=["ended_at", "end_reason"])
    person = membership.kinsperson
    if membership.is_primary and person.family_id == membership.family_id:
        person.family = None
        person.save(update_fields=["family"])
    return membership


@transaction.atomic
def mint_from_pool(
    pool: KinSlotPool, *, name: str = "", created_by: object | None = None
) -> Kinsperson:
    """Mint an appable child node from a slot pool, decrementing capacity.

    The minted node carries pre-authored parentage edges to the pool's
    parents and the pool's constraints; CG finalization then binds the
    claimant's sheet via ``claim_appable_node``.
    """
    locked = KinSlotPool.objects.select_for_update().get(pk=pool.pk)
    if locked.count_remaining <= 0:
        msg = f"pool {pool.pk} is exhausted"
        raise KinshipServiceError(msg, user_message="No positions remain in that pool.")
    locked.count_remaining -= 1
    locked.save(update_fields=["count_remaining"])

    person = Kinsperson.objects.create(
        name=name,
        definition_tier=DefinitionTier.NAME_ONLY,
        family=locked.family,
        age_min=locked.age_min,
        age_max=locked.age_max,
        is_appable=True,
        created_by=created_by,
    )
    person.allowed_genders.set(locked.allowed_genders.all())
    FamilyMembership.objects.create(
        kinsperson=person,
        family=locked.family,
        basis=MembershipBasis.BORN,
        started_at=timezone.now(),
    )
    for parent in locked.parents.all():
        ParentageEdge.objects.create(child=person, parent=parent)
    return person


def _check_slot_constraints(node: Kinsperson, sheet: CharacterSheet) -> None:
    """Refuse a claim whose sheet violates the slot's authored constraints."""
    if node.age_min is not None and sheet.age is not None and sheet.age < node.age_min:
        msg = f"sheet age {sheet.age} below slot minimum {node.age_min}"
        raise KinshipServiceError(msg, user_message="Your age is below this position's range.")
    if node.age_max is not None and sheet.age is not None and sheet.age > node.age_max:
        msg = f"sheet age {sheet.age} above slot maximum {node.age_max}"
        raise KinshipServiceError(msg, user_message="Your age is above this position's range.")
    allowed = list(node.allowed_genders.all())
    if allowed and sheet.gender not in allowed:
        msg = "sheet gender not in slot's allowed set"
        raise KinshipServiceError(
            msg, user_message="This position is constrained to a different gender."
        )


@transaction.atomic
def claim_appable_node(*, node: Kinsperson, sheet: CharacterSheet) -> Kinsperson:
    """Bind a finalizing OC's sheet to an appable node (CG claim).

    Constraint-checked; the node keeps its pre-authored edges (the claimant
    inherits a living tree). Name-locked slots keep their name.
    """
    if not node.is_appable:
        msg = f"node {node.pk} is not appable"
        raise KinshipServiceError(msg, user_message="That position is not open for claiming.")
    if node.sheet_id is not None:
        msg = f"node {node.pk} already claimed"
        raise KinshipServiceError(msg, user_message="That position was already claimed.")
    _check_slot_constraints(node, sheet)
    node.sheet = sheet
    node.definition_tier = DefinitionTier.PC
    node.is_appable = False
    if not node.name_locked:
        node.name = ""
    node.save(update_fields=["sheet", "definition_tier", "is_appable", "name"])
    return node


def ensure_node_for_sheet(sheet: CharacterSheet, *, family: Family | None = None) -> Kinsperson:
    """Get-or-create the Kinsperson for a sheet (self-serve CG path)."""
    existing = Kinsperson.objects.filter(sheet=sheet).first()
    if existing is not None:
        return existing
    return create_person(tier=DefinitionTier.PC, sheet=sheet, family=family)


@transaction.atomic
def define_deferred(  # noqa: PLR0913 — keyword-only
    *,
    actor_sheet: CharacterSheet,
    node: Kinsperson,
    name: str,
    description: str = "",
    age: int | None = None,
    gender: object | None = None,
) -> Kinsperson:
    """Fill a deliberately-deferred position (post-CG, holder-only).

    Only the sheet recorded as ``deferred_definer`` may define it; the
    immersion judgment ("would everyone have already known this") is the
    review step wrapping this call — the service enforces only the holder
    gate and one-shot consumption.
    """
    if node.deferred_definer_id != actor_sheet.pk:
        msg = f"sheet {actor_sheet.pk} may not define node {node.pk}"
        raise KinshipServiceError(
            msg, user_message="You are not the holder of that deferred position."
        )
    node.name = name
    node.description = description
    node.age = age
    if gender is not None:
        node.gender = gender
    node.deferred_definer = None
    node.save(update_fields=["name", "description", "age", "gender", "deferred_definer"])
    return node


# ---------------------------------------------------------------------------
# Derivation walks (viewer-aware)
# ---------------------------------------------------------------------------


@dataclass
class KinFact:
    """One visible kinship fact about a person, ready for rendering."""

    person: Kinsperson
    label: str
    kind: str = ""
    is_true: bool = True
    via_secret: bool = False


def _visible_edges(q: Q, viewer: object) -> list[ParentageEdge]:
    edges = ParentageEdge.objects.filter(q).select_related("child", "parent", "secret")
    return [e for e in edges if fact_visible(e, viewer)]


def parents_of(
    person: Kinsperson,
    viewer: object,
    *,
    include_foster: bool = False,
) -> list[ParentageEdge]:
    """Visible parent edges of ``person`` (foster excluded from lineage by default)."""
    edges = _visible_edges(Q(child=person), viewer)
    if not include_foster:
        edges = [e for e in edges if e.kind != ParentageKind.FOSTER]
    return edges


def children_of(
    person: Kinsperson,
    viewer: object,
    *,
    include_foster: bool = False,
) -> list[ParentageEdge]:
    """Visible child edges of ``person``."""
    edges = _visible_edges(Q(parent=person), viewer)
    if not include_foster:
        edges = [e for e in edges if e.kind != ParentageKind.FOSTER]
    return edges


def unions_of(person: Kinsperson, viewer: object) -> list[Union]:
    """Visible unions ``person`` belongs to."""
    unions = person.unions.select_related("kind", "secret").prefetch_related("members")  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel (leak)
    return [u for u in unions if fact_visible(u, viewer)]


def spouses_of(person: Kinsperson, viewer: object) -> list[Kinsperson]:
    """Visible union partners (active unions only)."""
    partners: list[Kinsperson] = []
    for union in unions_of(person, viewer):
        if union.ended_at is None:
            partners.extend(m for m in union.members.all() if m.pk != person.pk)
    return partners


def siblings_of(person: Kinsperson, viewer: object) -> dict[int, str]:
    """Visible siblings: pk → full/half label, from shared visible parents."""
    my_parents = {e.parent_id for e in parents_of(person, viewer)}
    if not my_parents:
        return {}
    sibling_parents: dict[int, set[int]] = {}
    edges = _visible_edges(Q(parent_id__in=my_parents), viewer)
    for edge in edges:
        if edge.child_id == person.pk or edge.kind == ParentageKind.FOSTER:
            continue
        sibling_parents.setdefault(edge.child_id, set()).add(edge.parent_id)
    if not sibling_parents:
        return {}
    # One batched fetch of every candidate's full visible parent set (no
    # per-sibling queries — see feedback_review_query_discipline).
    all_their_edges = _visible_edges(Q(child_id__in=sibling_parents.keys()), viewer)
    their_parent_sets: dict[int, set[int]] = {}
    for edge in all_their_edges:
        if edge.kind != ParentageKind.FOSTER:
            their_parent_sets.setdefault(edge.child_id, set()).add(edge.parent_id)
    labels: dict[int, str] = {}
    for child_id, shared in sibling_parents.items():
        their_all = their_parent_sets.get(child_id, set())
        full = shared == my_parents and shared == their_all and len(my_parents) > 1
        labels[child_id] = RelationshipType.SIBLING if full else RelationshipType.HALF_SIBLING
    return labels


def _people_by_id(ids: set[int]) -> dict[int, Kinsperson]:
    """Batch-fetch nodes (identity-map served for already-loaded rows)."""
    return {p.pk: p for p in Kinsperson.objects.filter(pk__in=ids)}


def step_parents_of(person: Kinsperson, viewer: object) -> list[Kinsperson]:
    """Derived step-parents: a parent's union partner with no parentage edge to person."""
    parent_ids = {e.parent_id for e in parents_of(person, viewer, include_foster=True)}
    steps: list[Kinsperson] = []
    for parent_edge in parents_of(person, viewer, include_foster=True):
        steps.extend(
            partner
            for partner in spouses_of(parent_edge.parent, viewer)
            if partner.pk not in parent_ids and partner.pk != person.pk
        )
    return steps


def incarnation_chain_of(person: Kinsperson, viewer: object) -> list[SoulIncarnation]:
    """Visible lives sharing a soul with ``person`` — requires the viewer to see
    BOTH ``person``'s membership and the other life's membership (knowledge is
    per-life; an intermediate hidden life stays undiscovered)."""
    own = [
        inc
        for inc in person.incarnations.select_related("soul", "secret")
        if fact_visible(inc, viewer)
    ]
    chain: list[SoulIncarnation] = []
    for inc in own:
        others = inc.soul.incarnations.exclude(kinsperson=person).select_related(
            "kinsperson", "secret"
        )
        chain.extend(o for o in others if fact_visible(o, viewer))
    return chain


def derive_relationship(  # noqa: C901, PLR0911, PLR0912 — a labeled precedence walk is irreducibly branchy
    a: Kinsperson, b: Kinsperson, viewer: object
) -> str | None:
    """Label the visible relationship from ``a`` to ``b`` (or None).

    Precedence: self → parent/child (typed; foster labeled distinctly) →
    sibling/half → spouse → step → grandparent/grandchild → aunt/uncle →
    niece/nephew → cousin → in-law → soul chain. Blood vs marriage vs foster
    is never ambiguous: the label carries it.
    """
    if a.pk == b.pk:
        return RelationshipType.SELF

    a_parents = parents_of(a, viewer, include_foster=True)
    for edge in a_parents:
        if edge.parent_id == b.pk:
            return (
                RelationshipType.FOSTER_PARENT
                if edge.kind == ParentageKind.FOSTER
                else RelationshipType.PARENT
            )
    for edge in children_of(a, viewer, include_foster=True):
        if edge.child_id == b.pk:
            return (
                RelationshipType.FOSTER_CHILD
                if edge.kind == ParentageKind.FOSTER
                else RelationshipType.CHILD
            )

    sibling_label = siblings_of(a, viewer).get(b.pk)
    if sibling_label is not None:
        return sibling_label

    if any(s.pk == b.pk for s in spouses_of(a, viewer)):
        return RelationshipType.SPOUSE
    if any(s.pk == b.pk for s in step_parents_of(a, viewer)):
        return RelationshipType.STEP_PARENT
    if any(s.pk == b.pk for s in step_parents_of(b, viewer)):
        return RelationshipType.STEP_CHILD

    # Foster-sibling: share a foster parent.
    a_foster = {e.parent_id for e in _visible_edges(Q(child=a, kind=ParentageKind.FOSTER), viewer)}
    b_foster = {e.parent_id for e in _visible_edges(Q(child=b, kind=ParentageKind.FOSTER), viewer)}
    if a_foster & b_foster:
        return RelationshipType.FOSTER_SIBLING

    lineage_parents = [e.parent for e in parents_of(a, viewer)]
    for parent in lineage_parents:
        if any(e.parent_id == b.pk for e in parents_of(parent, viewer)):
            return RelationshipType.GRANDPARENT
    for edge in children_of(a, viewer):
        if any(e.child_id == b.pk for e in children_of(edge.child, viewer)):
            return RelationshipType.GRANDCHILD
    for parent in lineage_parents:
        if b.pk in siblings_of(parent, viewer):
            return RelationshipType.AUNT_UNCLE
    my_siblings = _people_by_id(set(siblings_of(a, viewer)))
    for sibling in my_siblings.values():
        if any(e.child_id == b.pk for e in children_of(sibling, viewer)):
            return RelationshipType.NIECE_NEPHEW
    for parent in lineage_parents:
        aunts = _people_by_id(set(siblings_of(parent, viewer)))
        for aunt in aunts.values():
            if any(e.child_id == b.pk for e in children_of(aunt, viewer)):
                return RelationshipType.COUSIN

    # In-law: spouse's blood relative, or blood relative's spouse.
    for spouse in spouses_of(a, viewer):
        if derive_blood_only(spouse, b, viewer):
            return RelationshipType.IN_LAW
    for sibling in my_siblings.values():
        if any(s.pk == b.pk for s in spouses_of(sibling, viewer)):
            return RelationshipType.IN_LAW

    for inc in incarnation_chain_of(a, viewer):
        if inc.kinsperson_id == b.pk:
            own_seqs = [i.sequence for i in a.incarnations.all() if fact_visible(i, viewer)]
            if own_seqs and inc.sequence < max(own_seqs):
                return RelationshipType.PAST_INCARNATION
            return RelationshipType.LATER_INCARNATION

    return None


def derive_blood_only(a: Kinsperson, b: Kinsperson, viewer: object) -> bool:
    """Whether ``b`` is a visible blood/lineage relative of ``a`` (no unions)."""
    if any(e.parent_id == b.pk for e in parents_of(a, viewer)):
        return True
    if any(e.child_id == b.pk for e in children_of(a, viewer)):
        return True
    return b.pk in siblings_of(a, viewer)


# ---------------------------------------------------------------------------
# Tree payload
# ---------------------------------------------------------------------------


@dataclass
class FamilyTreePayload:
    """Viewer-appropriate graph payload for a family's tree."""

    family: Family
    nodes: list[dict] = field(default_factory=list)
    parentage: list[dict] = field(default_factory=list)
    unions: list[dict] = field(default_factory=list)


def family_tree_for(family: Family, viewer: object) -> FamilyTreePayload:
    """Assemble the visible tree for ``family``: members + married-in partners.

    Nodes: everyone with an active membership, plus visible union partners
    of members (so in-laws render). Edges: visible parentage among included
    nodes; visible unions with 2+ included members. Hidden facts the viewer
    knows are included flagged ``via_secret``; false public facts are
    included flagged ``is_true=False`` only for viewers who know the truth.
    """
    member_ids = set(
        FamilyMembership.objects.filter(family=family, ended_at__isnull=True).values_list(
            "kinsperson_id", flat=True
        )
    )
    people = {p.pk: p for p in Kinsperson.objects.filter(pk__in=member_ids)}
    for person in list(people.values()):
        for partner in spouses_of(person, viewer):
            people.setdefault(partner.pk, partner)

    payload = FamilyTreePayload(family=family)
    for person in people.values():
        payload.nodes.append(
            {
                "id": person.pk,
                "name": person.display_name,
                "tier": person.definition_tier,
                "family_id": person.family_id,
                "is_deceased": person.is_deceased,
                "is_appable": person.is_appable and person.sheet_id is None,
                "gender": person.gender.name if person.gender_id else "",
                "age": person.age,
                "description": person.description,
            }
        )

    edges = _visible_edges(Q(child_id__in=people.keys()) | Q(parent_id__in=people.keys()), viewer)
    for edge in edges:
        if edge.child_id not in people or edge.parent_id not in people:
            continue
        truth_known = edge.secret is not None and _viewer_knows(edge.secret, viewer)
        payload.parentage.append(
            {
                "child_id": edge.child_id,
                "parent_id": edge.parent_id,
                "kind": edge.kind,
                "is_true": edge.is_true,
                "via_secret": not edge.is_public_record and (viewer is None or truth_known),
            }
        )

    seen_unions: set[int] = set()
    for person in people.values():
        for union in unions_of(person, viewer):
            if union.pk in seen_unions:
                continue
            member_pks = [m.pk for m in union.members.all() if m.pk in people]
            min_rendered = 2
            if len(member_pks) < min_rendered:
                continue
            seen_unions.add(union.pk)
            payload.unions.append(
                {
                    "id": union.pk,
                    "kind": union.kind.name,
                    "member_ids": member_pks,
                    "ended": union.ended_at is not None,
                }
            )
    return payload


def open_slots_for(family: Family) -> tuple[list[Kinsperson], list[KinSlotPool]]:
    """CG surface: unclaimed appable nodes + non-empty pools for a family."""
    nodes = list(
        Kinsperson.objects.filter(
            family=family, is_appable=True, sheet__isnull=True
        ).prefetch_related("allowed_genders")  # noqa: PREFETCH_STRING — see above
    )
    pools = list(
        KinSlotPool.objects.filter(family=family, count_remaining__gt=0).prefetch_related(
            "parents",  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel (leak)
            "allowed_genders",  # noqa: PREFETCH_STRING
        )
    )
    return nodes, pools
