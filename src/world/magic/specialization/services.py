"""Specialization engine services (#1578, ADR-0055).

- ``provision_latent_gift_thread`` — CG provisioning of the latent level-0 GIFT thread.
- ``gift_resonances_for`` — the derive-on-read resonance seam (replaces
  ``technique.gift.resonances.all()`` at the four cast sites).
- ``resolve_specialized_variant`` — the single resolver (generalizes
  ``resolve_effective_role``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import (
    AFFINITY_ABYSSAL,
    AFFINITY_CELESTIAL,
    AFFINITY_PRIMAL,
    AcquisitionOrigin,
    TargetKind,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole
    from world.magic.models import Thread
    from world.magic.models.affinity import Resonance
    from world.magic.models.gifts import CharacterGift, Gift
    from world.magic.models.techniques import Technique, TechniqueMoraleEffect


# Sentinel: caller has not yet fetched the sheet (distinct from None = "no sheet").
_SHEET_UNSET: object = object()
# Sentinel: caller has not yet read the worn alternate self's resonance (None = "none worn").
ALT_RESONANCE_UNSET: object = object()


def provision_latent_gift_thread(
    sheet: CharacterSheet,
    gift: Gift,
    *,
    resonances: Sequence[Resonance],
) -> Thread:
    """Create the latent level-0 GIFT thread for ``gift``, holding ``resonances`` at zero.

    One thread per gift (#5123): it holds every resonance on its ``ThreadResonance``
    rows, written at amount 0 in the order given, so the first leads a tie. Idempotent
    on ``(owner, gift)``: if an active GIFT thread on the gift already exists, return it
    unchanged.

    Acquiring a gift IS intuitively weaving a (latent) thread — the Glimpse.
    Weaving (Rite of Weaving) commits a resonance; imbuing raises the level;
    crossing a variant's unlock_thread_level resolves the variant.
    """
    from world.magic.services.thread_rows import (  # noqa: PLC0415
        refresh_leading_resonance,
        write_resonance_rows,
    )

    if not resonances:
        msg = "A gift thread needs at least one resonance."
        raise ValueError(msg)
    character = sheet.character
    existing = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
        ),
        None,
    )
    if existing is not None:
        return existing

    from world.magic.models import Thread  # noqa: PLC0415

    thread = Thread(
        owner=sheet,
        resonance=resonances[0],
        target_kind=TargetKind.GIFT,
        target_gift=gift,
        level=0,
    )
    thread.full_clean()
    with transaction.atomic():
        thread.save()
        write_resonance_rows(thread, resonances)
        refresh_leading_resonance(thread)
    # Invalidate the cached thread list so the new row is visible to the next
    # read through ``character.threads`` (mirrors the covenant-role invalidation
    # contract in covenants/services._invalidate_role_caches).
    character.threads.invalidate()
    return thread


def _first_gift_thread_resonance(sheet: CharacterSheet) -> Resonance | None:
    """The character's main resonance: their earliest active GIFT thread's (the CG pick)."""
    threads = [
        t
        for t in sheet.character.threads.all()
        if t.target_kind == TargetKind.GIFT and t.retired_at is None
    ]
    if not threads:
        return None
    return min(threads, key=lambda t: t.pk).resonance


def _resolve_grant_resonance(
    sheet: CharacterSheet, gift: Gift, *, preferred: Resonance | None = None
) -> Resonance:
    """Grant-time resonance policy (#2971). The gift's ``resonances`` list is a default
    here, never a limit (#5123).

    In order, taking the first that resolves:

    1. ``preferred`` (the caller's explicit pick), whatever the gift's list holds.
    2. An existing active GIFT thread already covering ``gift`` (lineage-aware, via
       ``gift_threads_for``) — its resonance, regardless of the supported-set shape.
       Without this step, an unconditional re-grant (e.g. ``grant_path_magic`` looping
       over ``PathGiftGrant`` rows for a gift the character already owns) could
       resolve a DIFFERENT resonance from the set/claim policy below and mint a
       second thread on the same gift; this makes a re-grant a true no-op.
    3. A non-empty supported set: the member the character has already claimed, else
       the set's first member.
    4. An empty supported set with no thread on this gift yet: the character's
       earliest active GIFT thread's resonance, on ANY gift (their "main" one).
    5. The character's highest-``lifetime_earned`` claimed resonance.
    6. The character's anima-ritual resonance.

    Raises ``GiftResonanceUnresolvable`` when none of the above resolves anything.
    """
    from world.magic.exceptions import GiftResonanceUnresolvable  # noqa: PLC0415
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    supported = gift.cached_resonances
    if preferred is not None:
        return preferred
    covering = gift_threads_for(sheet.character, gift)
    if covering:
        # ``gift_threads_for`` sorts direct-hold-first (a thread whose
        # ``target_gift`` is this exact gift beats an ancestor-gift thread) —
        # take covering[0], not the lowest-pk thread, or a lower-pk ancestor
        # thread could win over a direct hold and mint a second thread on the
        # same gift (idempotency in ``provision_latent_gift_thread`` is keyed
        # on the exact (owner, gift, resonance) triple, not "any covering
        # thread").
        return covering[0].resonance
    if supported:
        claimed_ids = set(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                "resonance_id", flat=True
            )
        )
        return next((r for r in supported if r.pk in claimed_ids), supported[0])
    thread_resonance = _first_gift_thread_resonance(sheet)
    if thread_resonance is not None:
        return thread_resonance
    claimed = (
        CharacterResonance.objects.filter(character_sheet=sheet)
        .select_related("resonance")
        .order_by("-lifetime_earned", "resonance_id")
        .first()
    )
    if claimed is not None:
        return claimed.resonance
    from world.magic.services.gain import anima_ritual_resonance  # noqa: PLC0415

    main = anima_ritual_resonance(sheet)
    if main is not None:
        return main
    raise GiftResonanceUnresolvable


def grant_gift_to_character(
    sheet: CharacterSheet,
    gift: Gift,
    *,
    resonances: Sequence[Resonance] = (),
    origin: str = AcquisitionOrigin.CHARACTER_CREATION,
) -> tuple[CharacterGift, bool]:
    """Mint (idempotently) the CharacterGift link + the latent GIFT thread.

    The shared gift-acquisition primitive: a character gains a gift by linking it
    (``CharacterGift``) and provisioning its latent level-0 GIFT thread. Used by the
    path-crossing grant (#1579) and species-gift provisioning (#1580) so there is
    one place that does this, not a per-source copy.

    ``resonances`` are the caller's preferred resonances for the latent thread, leading
    first (character creation's weighted picks, heaviest first); empty (the default)
    means "resolve one for me" through ``_resolve_grant_resonance`` (#2971). Every pick
    is kept: the gift's ``resonances`` list limits nothing, it is the default that
    resolver reaches for when no pick is named (#5123). A thread is ALWAYS
    provisioned — a granted gift with an empty supported set no longer silently
    skips thread provisioning, since that left characters holding a gift and its
    techniques with no GIFT thread to read a resonance from anywhere downstream
    (cast resolution, dramatic-moment grants, ...). Resolution runs BEFORE the
    ``CharacterGift`` row is minted, so a ``GiftResonanceUnresolvable`` raise leaves
    no trace — a partially-granted gift (a ``CharacterGift`` with no thread) is the
    exact corrupted state #2971 eliminates, and minting first would just move it to
    the failure path. Raises ``GiftResonanceUnresolvable`` when nothing resolves.

    ``origin`` (#3055) — the ``AcquisitionOrigin`` this call site represents; stamped
    on a freshly-minted ``CharacterGift`` only (an already-owned gift keeps its
    original origin — a re-grant is a no-op, not a re-provenance). Defaults to
    ``CHARACTER_CREATION`` since that is this function's oldest/most common caller.

    A gift that names a natural weapon (#4898) also gets that weapon made and equipped,
    once per character (``provision_natural_weapon`` is idempotent), so every way a gift
    is gained gives the claws with it.

    Returns ``(character_gift, created)``.
    """
    from world.magic.models import CharacterGift  # noqa: PLC0415

    held = list(resonances) or [_resolve_grant_resonance(sheet, gift)]
    character_gift, created = CharacterGift.objects.get_or_create(
        character=sheet, gift=gift, defaults={"origin": origin}
    )
    provision_latent_gift_thread(sheet, gift, resonances=held)
    from world.items.services.natural_weapons import provision_natural_weapon  # noqa: PLC0415

    provision_natural_weapon(sheet, gift)
    return character_gift, created


def active_alt_self_resonance(sheet: CharacterSheet) -> Resonance | None:
    """Return the resonance of the character's active alternate self, if any.

    When a character has assumed an ``AlternateSelf`` that carries a
    ``resonance`` FK, that resonance replaces the GIFT thread's own
    resonance in variant resolution only (#1619); ``gift_resonances_for`` is
    unchanged by it. The thread's *level* still gates which variant tier
    unlocks. Also read by ``acting_aura`` for the aura the character acts with.

    Derive-on-read (ADR-0014): no snapshot, no write-on-assume. Uses a
    direct DB query rather than the cached reverse OneToOne accessor
    (``sheet.active_alternate_self``) because the sheet object may have
    been loaded before the ``ActiveAlternateSelf`` row was created — the
    cached accessor would return stale ``None``/``DoesNotExist`` in that
    case. A single ``select_related`` query is cheap and always fresh.

    Returns ``None`` when no alt-self is active, the active alt-self has no
    ``resonance`` set, or the lookup raises (defensive — never blocks casting).
    """
    from world.forms.models import ActiveAlternateSelf  # noqa: PLC0415

    try:
        active = (
            ActiveAlternateSelf.objects.select_related("alternate_self__resonance")
            .filter(character_id=sheet.pk, alternate_self__isnull=False)
            .first()
        )
    except ActiveAlternateSelf.DoesNotExist:
        return None
    if active is None or active.alternate_self_id is None:
        return None
    alt = active.alternate_self
    if alt is None:
        return None
    return alt.resonance


def gift_threads_for(character, gift: Gift) -> list:
    """The character's GIFT threads that cover ``gift`` (#2891).

    A thread covers ``gift`` when its ``target_gift`` is ``gift`` itself or a
    descendant of it — a Vulpi thread covers the Khati techniques Vulpi inherits.
    Without the lineage test, every cast-time read of an inherited technique
    would find no thread and fall back to the ancestor gift's authored defaults.

    Reads the cached ``character.threads`` handler with a list-comp filter, not a
    fresh ``Thread.objects.filter()`` — per project cached-property rule. A
    direct hold sorts first so it wins when a character somehow holds both.
    """
    covering = [
        t
        for t in character.threads.all()
        if t.target_kind == TargetKind.GIFT
        and t.target_gift_id is not None
        and gift.pk in t.target_gift.lineage_ids
    ]
    covering.sort(key=lambda t: t.target_gift_id != gift.pk)
    return covering


def gift_resonances_for(
    character, gift: Gift, *, sheet: CharacterSheet | None | object = _SHEET_UNSET
) -> list[Resonance]:
    """The resonance(s) this gift manifests as FOR THIS character.

    Derived on read from the character's active GIFT thread covering ``gift``:
    the thread's resonances in row order (leading first; #5123) if one exists, else
    ``gift.resonances`` (the supported set). Replaces ``technique.gift.resonances.all()`` at
    the four cast sites
    (#1578). "Covering" walks the gift lineage (#2891) — a Vulpi thread manifests
    the Khati techniques Vulpi inherits, at the Vulpi thread's resonance.

    An active ``AlternateSelf``'s resonance does NOT change this list; it is
    applied later, in the variant resolver (#1619), which decides the variant
    that manifests.

    Reads the thread through the cached ``character.threads`` handler (the
    single cached queryset for a character's threads) with a list-comp filter,
    not a fresh ``Thread.objects.filter()`` — per project cached-property rule.

    A sheetless ``Character`` (e.g. an NPC) has no GIFT thread, so it manifests
    the supported set; the sheet guard handles that precondition rather than
    catching the ``sheet_data`` raise from the handler. A non-Character object
    (no ``.threads``) is a caller bug and is left to raise ``AttributeError``
    rather than papered over with a ``hasattr`` check.

    ``sheet`` is the character's sheet when the caller already holds it (``None`` for a
    sheetless character); left out, it is read here. A caller listing several techniques reads
    it once and passes it in (#5231).
    """
    if sheet is _SHEET_UNSET:
        from world.magic.services.techniques import (  # noqa: PLC0415
            _get_character_sheet,
        )

        sheet = _get_character_sheet(character)
    if sheet is None:
        return gift.cached_resonances

    # #1619 / #5123: the gift's one thread holds several resonances on its rows;
    # the caller gets them all, leading first, and may present a cast-time picker.
    #
    # The alt-self resonance override is NOT applied here — it's applied in
    # the variant resolver (_resolve_technique_variant), which is the single
    # place that decides which variant manifests. This avoids an extra DB
    # query in gift_resonances_for (which is called from multiple cast sites)
    # and keeps the query-scaling budget intact.
    gift_threads = gift_threads_for(character, gift)
    if gift_threads:
        return character.threads.resonances_of(gift_threads[0])
    return gift.cached_resonances


def resolve_specialized_variant(
    *,
    entity,
    character,
    character_technique=None,
    preferred_resonance: Resonance | None = None,
    _sheet: object = _SHEET_UNSET,
):
    """Return the resonance-specialized variant of ``entity`` for ``character``,
    else ``entity`` unchanged. Derive-on-read (ADR-0014).

    For a Technique: finds the character's active GIFT thread on the technique's
    gift, reads resonance + level, and returns a ``ResolvedTechnique`` wrapping
    the parent + matching variant (or just the parent). For a CovenantRole:
    reads the active COVENANT_ROLE thread via the cached ``character.threads``
    handler and returns the matching sub-role variant (proven path, #1578).

    ``character_technique`` (#2022): when the technique being resolved was
    role-granted (``CharacterTechnique.role_source`` is set), the resolver reads
    the COVENANT_ROLE thread level instead of the GIFT thread level — so a
    role-granted technique specializes by the vow's depth, not the personal
    gift's depth.

    ``preferred_resonance`` (#1619): the resonance the player chose at cast time,
    one of the gift thread's resonances (#5123). It takes priority over the
    alt-self resonance override, which takes priority over the thread's leading
    resonance. The thread has one level, read whichever resonance wins.

    ``_sheet`` is an internal optimisation parameter: callers that have already
    fetched the ``CharacterSheet`` for ``character`` may pass it here to avoid a
    redundant DB round-trip inside the variant resolver.  Pass the sentinel
    ``_SHEET_UNSET`` (the default) to let the resolver fetch it itself.
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    if isinstance(entity, Technique):
        return _resolve_technique_variant(
            entity,
            character,
            character_technique=character_technique,
            preferred_resonance=preferred_resonance,
            _sheet=_sheet,
        )
    if isinstance(entity, CovenantRole):
        return _resolve_covenant_role_variant(entity, character)
    return entity


def _role_thread_for(character, character_technique):
    """The COVENANT_ROLE thread for the role that granted ``character_technique`` (#2022).

    A role-granted technique specializes by the vow's depth, not the personal
    gift's depth.
    """
    role_source = character_technique.role_source
    return next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role_id == role_source.covenant_role_id
            and t.retired_at is None
        ),
        None,
    )


def _gift_thread_for_variant(character, technique: Technique):
    """The GIFT thread whose level and resonance govern ``technique``'s variant.

    Covering threads are those on the technique's own gift OR on a descendant
    gift the character holds (#2891) — an inherited technique specializes from
    the child gift's thread, since that is the only thread its holder has.

    One thread per gift (#5123): the cast-time picker (``preferred_resonance``) chooses
    among that thread's resonances in ``_effective_variant_resonance``, and the thread's
    level is read for whichever resonance wins.
    """
    if technique.gift_id is None:
        return None
    covering = gift_threads_for(character, technique.gift)
    return covering[0] if covering else None


def _effective_variant_resonance(
    sheet, thread, preferred_resonance, alt_resonance=ALT_RESONANCE_UNSET
):
    """Choose cast-time, alt-self, or thread resonance in priority order.

    ``alt_resonance`` is the worn alternate self's resonance when the caller already read it
    (``None`` for none worn); left out, it is read here.
    """
    if preferred_resonance is not None:
        return preferred_resonance
    resonance = (
        active_alt_self_resonance(sheet) if alt_resonance is ALT_RESONANCE_UNSET else alt_resonance
    )
    return thread.resonance if resonance is None else resonance


def _threads_the_forms_come_from(
    # the thread handler takes the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
) -> list[Thread]:
    """The threads this caster's forms of ``technique`` come from (#5231, WB2).

    The Gift's thread (``_gift_thread_for_variant``, lineage-aware) and every thread
    ``technique_forms._candidate_threads`` lists, the one list the form picker reads: for a
    technique a covenant role granted that is the role's thread.
    """
    # technique_forms imports this module at call time; the import here is lazy for the cycle.
    from world.magic.services.technique_forms import _candidate_threads  # noqa: PLC0415

    threads: list[Thread] = []
    gift_thread = _gift_thread_for_variant(character, technique)
    if gift_thread is not None:
        threads.append(gift_thread)
    threads.extend(
        thread
        for thread in _candidate_threads(
            character, technique, character.techniques.hold_for(technique)
        )
        if thread not in threads
    )
    return threads


def resonance_on_gift_thread(
    # the thread handler and sheet lookups take the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
    resonance: Resonance | None,
    *,
    sheet: CharacterSheet | None | object = _SHEET_UNSET,
) -> Resonance | None:
    """The named ``resonance`` when a thread this caster's forms come from holds a row for it.

    None when nothing is named, the technique has no Gift, the caster has no such thread (a
    sheetless NPC included), or no such thread holds a row for the resonance. The threads are
    the Gift's thread and the one a covenant role's technique lists its forms from
    (``_threads_the_forms_come_from``), so picking a form the screen offers is never refused.
    It is the one test behind every refusal and every fall-back: ``cast_resonance_for``
    refuses a named resonance for which this returns None, and a stored choice for which it
    returns None is cast in the default resonance instead (#5231).
    """
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    if resonance is None or technique.gift_id is None:
        return None
    if (_get_character_sheet(character) if sheet is _SHEET_UNSET else sheet) is None:
        return None
    for thread in _threads_the_forms_come_from(character, technique):
        if character.threads.amount_of(thread, resonance) is not None:
            return resonance
    return None


_NO_THREAD_AFFINITY_ORDER = (AFFINITY_PRIMAL, AFFINITY_CELESTIAL, AFFINITY_ABYSSAL)


def _first_unthreaded_resonance(gift: Gift) -> Resonance | None:
    """The Gift's own first resonance for a caster with no thread on it: Primal, then
    Celestial, then Abyssal, the Gift's own order within an affinity (#5231, WB3).

    Nobody is corrupted by a default she did not pick, so the Abyssal one is last.
    """
    resonances = gift.cached_resonances
    if not resonances:
        return None
    return min(
        resonances,
        key=lambda r: (
            _NO_THREAD_AFFINITY_ORDER.index(r.affinity.name)
            if r.affinity.name in _NO_THREAD_AFFINITY_ORDER
            else len(_NO_THREAD_AFFINITY_ORDER)
        ),
    )


def cast_resonance_for(  # noqa: PLR0913 - the named pick, the refusal switch, two lookups read once
    # the thread handler and sheet lookups take the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
    preferred: Resonance | None = None,
    *,
    refuse_off_thread: bool = True,
    sheet: CharacterSheet | None | object = _SHEET_UNSET,
    alt_resonance: Resonance | None | object = ALT_RESONANCE_UNSET,
) -> Resonance | None:
    """The one resonance a cast of ``technique`` is worked in (#5231).

    The named ``preferred`` resonance, else the worn alternate self's, else the leading
    resonance of the Gift's thread (``_effective_variant_resonance``'s own order). A named
    resonance that no thread her forms come from holds a row for (``resonance_on_gift_thread``)
    raises ``ResonanceNotOnGiftThread`` while ``refuse_off_thread`` is set, and is ignored (the
    default is used) when it is not. A caster with no thread on the Gift, a sheetless NPC
    included, works the resonance she named if a role thread holds it, else the Gift's own
    first one in the order Primal, Celestial, Abyssal (``_first_unthreaded_resonance``). A
    technique with no Gift, or a Gift with no resonances, is worked in none. Choosing the base
    form does not change the answer: the form and the resonance are separate choices.

    A caller listing several techniques for one character reads her ``sheet`` and her worn
    alternate self's resonance (``alt_resonance``, None for none worn) once and passes them in,
    so the list costs no sheet or alternate-self query per technique.
    """
    from world.magic.exceptions import ResonanceNotOnGiftThread  # noqa: PLC0415
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    if technique.gift_id is None:
        return None
    if sheet is _SHEET_UNSET:
        sheet = _get_character_sheet(character)
    named = resonance_on_gift_thread(character, technique, preferred, sheet=sheet)
    if preferred is not None and named is None and refuse_off_thread:
        raise ResonanceNotOnGiftThread
    thread = _gift_thread_for_variant(character, technique) if sheet is not None else None
    if thread is None:
        return named if named is not None else _first_unthreaded_resonance(technique.gift)
    return _effective_variant_resonance(sheet, thread, named, alt_resonance)


def cast_working_resonances(
    # the thread handler and sheet lookups take the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
    cast_resonance: Resonance | None,
) -> list[Resonance]:
    """The resonances a cast's resonance-tied power draws on (#5231, E1).

    The one resonance the cast is worked in, as a one-entry list, whenever the cast has one.
    Only where no cast resonance exists (a caller that is not a cast, a sheetless caster, a
    technique with no Gift) does it fall back to every resonance the Gift manifests as for her
    (``gift_resonances_for``). Every reader of a resonance-tied power (touchstones, resonance
    standing, a resonance-scoped power or effect target, the aura alignment, the place's
    reaction) reads through here, so a cast worked in her Primal resonance never collects power
    tied to her Abyssal one while taking none of its corruption.
    """
    if cast_resonance is not None:
        return [cast_resonance]
    if technique.gift_id is None:
        return []
    return gift_resonances_for(character, technique.gift)


def _prefer_early_form(character, technique, resonance, variant):
    """Use an eligible purchased early form when it outranks the natural form."""
    hold = character.techniques.hold_for(technique)
    early = hold.early_form if hold is not None else None
    if early is None or hold.role_source_id is not None:
        return variant
    if early.resonance_id != resonance.pk:
        return variant
    if variant is not None and early.unlock_thread_level <= variant.unlock_thread_level:
        return variant
    return early


def _resolve_technique_variant(
    technique: Technique,
    character,
    *,
    character_technique=None,
    preferred_resonance: Resonance | None = None,
    _sheet: object = _SHEET_UNSET,
) -> Technique | _ResolvedTechnique:
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    # #2022: When the technique was role-granted (CharacterTechnique.role_source
    # is set), resolve the variant using the COVENANT_ROLE thread level instead
    # of the GIFT thread level. The role-granted technique specializes by the
    # vow's depth, not the personal gift's depth.
    use_role_thread = (
        character_technique is not None and character_technique.role_source_id is not None
    )

    # Read the active GIFT thread through the cached ``character.threads``
    # handler (the same cached queryset the covenant path reads), not a fresh
    # ``Thread.objects.filter()`` — per project cached-property rule. A sheetless
    # Character (e.g. an NPC) has no GIFT thread, so it gets the parent technique
    # unchanged; the sheet guard handles that precondition rather than catching
    # the handler's ``sheet_data`` raise. A non-Character object has no
    # ``.threads`` and is left to raise ``AttributeError``.
    #
    # ``_sheet`` may be a pre-fetched CharacterSheet (or explicit None for NPCs)
    # from the caller; use it directly to avoid a redundant DB round-trip.
    if _sheet is _SHEET_UNSET:
        from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

        sheet = _get_character_sheet(character)
    else:
        sheet = _sheet  # type: ignore[assignment]  # caller verified type
    if sheet is None:
        return technique

    if use_role_thread:
        thread = _role_thread_for(character, character_technique)
    else:
        thread = _gift_thread_for_variant(character, technique)
    if thread is None:
        return technique

    effective_resonance = _effective_variant_resonance(sheet, thread, preferred_resonance)
    variant = TechniqueVariant.matching_variant(
        technique,
        resonance=effective_resonance,
        thread_level=thread.level,
    )
    if not use_role_thread:
        variant = _prefer_early_form(character, technique, effective_resonance, variant)

    if variant is None:
        return technique
    return _ResolvedTechnique(technique, variant=variant)


def _resolve_covenant_role_variant(role, character) -> CovenantRole:
    """Resonance-specialized sub-role for a base ``role`` (proven path, #1578).

    Single-depth: a role that is already a sub-role (has ``parent_role``) is
    returned unchanged — never re-promote. Reads the active COVENANT_ROLE
    thread via the cached ``character.threads`` handler (same read mechanism as
    the legacy ``resolve_effective_role``) to preserve cache coherence.
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if role.parent_role_id is not None:
        return role  # already a sub-role; never re-promote (single-depth)
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role_id == role.pk
            and t.retired_at is None
        ),
        None,
    )
    if thread is None:
        return role
    variant = CovenantRole.matching_variant(
        role, resonance=thread.resonance, thread_level=thread.level
    )
    return variant if variant is not None else role


class _ResolvedTechnique:
    """Derive-on-read view over a Technique + its resolved TechniqueVariant.

    Surfaces name/intensity/control/payload as parent + variant delta/override.
    Callers read these instead of ``technique.name`` / ``technique.intensity``.
    """

    def __init__(self, technique: Technique, *, variant) -> None:
        self.technique = technique
        self.variant = variant

    @property
    def name(self) -> str:
        if self.variant is not None and self.variant.name_override:
            return self.variant.name_override
        return self.technique.name

    @property
    def intensity(self) -> int:
        base = self.technique.intensity
        if self.variant is not None:
            return base + self.variant.intensity_delta
        return base

    @property
    def control(self) -> int:
        base = self.technique.control
        if self.variant is not None:
            return base + self.variant.control_delta
        return base

    # Payload accessors: variant's payload if it has any, else parent's. Each
    # reads its source's single ``cached_<payload>`` list once (mirrors the
    # ``cached_restrictions`` convention in techniques.py) rather than issuing a
    # ``.exists()`` + ``.all()`` pair per access. To invalidate after a payload
    # mutation: ``del instance.cached_<payload>`` on the mutated owner.
    @property
    def damage_profiles(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_damage_profiles
            if payload:
                return payload
        return self.technique.cached_damage_profiles

    @property
    def capability_grants(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_capability_grants
            if payload:
                return payload
        return self.technique.cached_capability_grants

    @property
    def condition_applications(self) -> list:
        if self.variant is not None:
            payload = self.variant.cached_condition_applications
            if payload:
                return payload
        return self.technique.cached_condition_applications

    # ``cached_<payload>`` aliases (#2901). Every payload *reader* in the codebase
    # — ``summarize_technique_effects``, ``is_technique_hostile``,
    # ``derive_target_relationship`` — reads the ``cached_`` names, not the bare
    # ones above. Without these aliases ``__getattr__`` forwards those reads
    # straight to the parent ``Technique``, so a variant that swaps its damage
    # rows summarises as the *base* form under the variant's name and nothing
    # fails. The aliases make a payload read resolve the same way whether the
    # caller asks for ``damage_profiles`` or ``cached_damage_profiles``.
    @property
    def cached_damage_profiles(self) -> list:
        return self.damage_profiles

    @property
    def cached_capability_grants(self) -> list:
        return self.capability_grants

    @property
    def cached_condition_applications(self) -> list:
        return self.condition_applications

    @property
    def cached_removed_conditions(self) -> list:
        """Dispel rows, always the parent's.

        There is no ``TechniqueVariantRemovedCondition`` model, so a variant
        cannot override which conditions the technique strips. Declared
        explicitly rather than left to ``__getattr__`` so the asymmetry is
        visible next to the three payloads a variant *can* override.
        """
        return self.technique.cached_removed_conditions

    @property
    def cached_treatments(self) -> list:
        """Treatment rows, always the parent's (#3682).

        Same asymmetry as ``cached_removed_conditions``: there is no
        ``TechniqueVariantTreatment`` model, so a variant cannot override which
        treatments the technique performs. Declared explicitly rather than left
        to ``__getattr__`` so the asymmetry stays visible.
        """
        return self.technique.cached_treatments

    @property
    def cached_morale_effect(self) -> TechniqueMoraleEffect | None:
        """Morale row, always the parent's (#4619).

        Same asymmetry as ``cached_treatments``: there is no variant morale
        model, so a variant cannot override how much morale the technique shakes.
        """
        return self.technique.cached_morale_effect

    # Pass-through for the cast pipeline's other technique reads.
    def __getattr__(self, item):
        return getattr(self.technique, item)
