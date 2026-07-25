"""Per-character handlers for the resonance/thread surface (Spec A §3.7).

These handlers wire onto the ``Character`` typeclass alongside the established
``character.traits`` etc. handlers. They cache per-character data via
``django.utils.functional.cached_property`` and rely on service functions to
call ``.invalidate()`` after mutation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django.utils.functional import cached_property

from world.magic.constants import EffectKind, TargetKind
from world.magic.models import CharacterResonance, Thread, ThreadPullEffect
from world.magic.models.techniques import Technique
from world.magic.services.pull_effects import get_pull_effects_for_thread
from world.magic.services.resonance import _anchor_ambiently_active, resolve_involved_gift_ids
from world.magic.services.threads import thread_level_multiplier

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.conditions.models import DamageType
    from world.magic.models import Facet, Resonance
    from world.magic.types.pull import PullActionContext

logger = logging.getLogger(__name__)


class CharacterThreadHandler:
    """Handler for a character's owned threads (Spec A §3.7).

    Cached list of all threads owned by the character's CharacterSheet, with
    select_related on the resonance + each typed-FK target column so anchor
    walks don't fire follow-up queries.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _all(self) -> list[Thread]:
        # CharacterSheet uses the ObjectDB pk as its own pk (primary_key=True
        # on CharacterSheet.character), so owner_id == character.pk.  Filtering
        # by the raw id avoids a round-trip SELECT on character_sheets_charactersheet
        # that the ``self.character.sheet_data`` reverse accessor would trigger
        # — the Django FK descriptor cache is not reliably populated across the
        # SharedMemoryModel identity-map boundary, so every ``character.sheet_data``
        # access without a prior cache warm-up issues a fresh query (#1581).
        return list(
            Thread.objects.filter(
                owner_id=self.character.pk, retired_at__isnull=True
            ).select_related(
                "resonance__affinity",
                "target_trait",
                "target_technique",
                "target_relationship_track__relationship",
                "target_capstone__relationship",
                "target_facet",
                "target_covenant_role",
                "target_gift",
                "target_mantle__item_instance",
                "target_sanctum_details__feature_instance__room_profile",
            )
        )

    def all(self) -> list[Thread]:
        """Return all threads owned by this character."""
        return self._all

    def by_resonance(self, resonance: Resonance) -> list[Thread]:
        """Return threads filtered to a single resonance."""
        return [t for t in self._all if t.resonance_id == resonance.pk]

    def thread_for_facet(self, facet: Facet) -> Thread | None:
        """Return the active FACET-kind thread anchored to ``facet``, if any."""
        for thread in self._all:
            if thread.target_kind == TargetKind.FACET and thread.target_facet_id == facet.pk:
                return thread
        return None

    def threads_of_kind(self, kind: str) -> list[Thread]:
        """Return all active threads with the given ``target_kind``."""
        return [t for t in self._all if t.target_kind == kind]

    def with_anchor_involved(self, action_context: object) -> list[Thread]:
        """Return threads whose anchor is in scope for the given action.

        Spec §3.7 lines 974–976. Implementation is deferred to a future phase
        that lands the action-context plumbing needed to decide "anchor in
        scope" outside the pull pipeline. Passive VITAL_BONUS routing (Phase
        13) does not need this because all Thread typed FKs use
        ``on_delete=PROTECT`` — see ``passive_vital_bonuses`` for details.
        """
        msg = "with_anchor_involved awaits action-context plumbing in a future phase."
        raise NotImplementedError(msg)

    def passive_vital_bonuses(self, vital_target: str) -> int:
        """Sum tier-0 VITAL_BONUS scaled values across the character's threads.

        Spec §3.7 lines 977–979, §5.5 lines 1533–1547, §5.8 lines 1640–1657.

        Aggregates passive (tier-0) VITAL_BONUS rows for every thread the
        character owns, filtered by ``vital_target``. Scaling uses the same
        formula as active pulls: ``level_multiplier = thread_level_multiplier(thread.level)``
        (#1718) times the authored ``vital_bonus_amount``. ``min_thread_level``
        filters rows that require a higher thread investment.

        Anchor-in-scope filter: §5.8 requires that only threads "whose anchor
        is currently in scope" contribute passively. All typed FKs on Thread
        use ``on_delete=PROTECT``, so any deletion of a referenced anchor
        object raises ProtectedError — the thread itself can never outlive its
        anchor. Therefore every existing Thread row always has its anchor in
        scope; no runtime filter is needed. (Do not replace this comment with a
        call to ``with_anchor_involved`` — that stub is for action-scoped
        queries, a different concept.)

        Query strategy: batch-fetch all matching ThreadPullEffect rows in a
        single query keyed by ``(target_kind, resonance_id)`` pairs, then
        apply per-thread level multipliers in Python to avoid N+1 queries.
        Pulled (tier 1+) contributions live on ``CharacterCombatPullHandler``.
        """
        threads = self._all
        if not threads:
            return 0

        from django.db.models import Q  # noqa: PLC0415

        # GIFT threads require gift-specific preference logic and are handled
        # separately from the non-GIFT batch to avoid cross-gift row leakage.
        gift_threads = [t for t in threads if t.target_kind == TargetKind.GIFT]
        non_gift_threads = [t for t in threads if t.target_kind != TargetKind.GIFT]

        # --- Non-GIFT batch (unchanged behaviour) ---
        # Build lookup: (target_kind, resonance_id) → HIGHEST thread level for
        # that key, so we apply the right multiplier after the batched query.
        # Two threads of one kind on the same resonance (e.g. two COVENANT_ROLE
        # roles, or two TRAIT anchors) share a key; the bonus applies once,
        # scaled by the best qualifying thread (#1009). A plain dict
        # comprehension would let the last-iterated thread win
        # nondeterministically (Thread has no Meta.ordering).
        thread_level: dict[tuple[str, int], int] = {}
        for t in non_gift_threads:
            key = (t.target_kind, t.resonance_id)
            thread_level[key] = max(thread_level.get(key, 0), t.level)

        non_gift_effects: list[ThreadPullEffect] = []
        if thread_level:
            q = Q()
            for target_kind, resonance_id in thread_level:
                q |= Q(target_kind=target_kind, resonance_id=resonance_id)
            non_gift_effects = list(
                ThreadPullEffect.objects.filter(
                    q,
                    tier=0,
                    effect_kind=EffectKind.VITAL_BONUS,
                    vital_target=vital_target,
                    target_gift__isnull=True,  # exclude gift-specific rows from batch
                ).exclude(vital_bonus_amount__isnull=True)
            )

        # --- GIFT threads: prefer gift-specific, fall back to null (per-thread) ---
        total = 0
        for t in gift_threads:
            rows = get_pull_effects_for_thread(
                t,
                tier=0,
                effect_kind=EffectKind.VITAL_BONUS,
                vital_target=vital_target,
            )
            level = t.level
            multiplier = thread_level_multiplier(level)
            for row in rows:
                if row.min_thread_level > level or row.vital_bonus_amount is None:
                    continue
                total += row.vital_bonus_amount * multiplier

        # --- Non-GIFT: sum contributions ---
        for row in non_gift_effects:
            level = thread_level.get((row.target_kind, row.resonance_id), 0)
            if row.min_thread_level > level:
                continue
            multiplier = thread_level_multiplier(level)
            total += row.vital_bonus_amount * multiplier
        # round(), not int() truncation: thread_level_multiplier (#1718) returns a
        # fractional Decimal for levels 1-9, so `total` may now be a Decimal;
        # rounding to the nearest int is fairer to the player than flooring, and
        # this method's return type is `int`.
        return round(total)

    def passive_damage_type_resistance(self, damage_type: DamageType) -> int:
        """Sum flat tier-0 RESISTANCE for one damage type across owned threads (#1580).

        The species-gift thread's RESISTANCE effect offsets the species drawback's
        ``ConditionResistanceModifier`` vulnerability on the same incoming-damage
        subtraction in ``apply_damage_to_participant``. Unlike VITAL_BONUS, the
        passive contribution is FLAT (not scaled by ``level_multiplier``) — the
        ``min_thread_level`` gate is the level mechanism (the resistance switches on
        at a threshold). A null ``resistance_damage_type`` matches any damage type
        (parity with null ``ConditionResistanceModifier`` rows).

        Mirrors ``passive_vital_bonuses``: GIFT threads use gift-specific preference
        (a gift-specific row wins over a null-gift fallback) and are resolved
        per-thread; non-GIFT threads are batched in a single query.
        """
        threads = self._all
        if not threads:
            return 0
        gift_threads = [t for t in threads if t.target_kind == TargetKind.GIFT]
        non_gift_threads = [t for t in threads if t.target_kind != TargetKind.GIFT]
        return self._gift_resistance_total(gift_threads, damage_type) + (
            self._non_gift_resistance_total(non_gift_threads, damage_type)
        )

    @staticmethod
    def _resistance_matches(row: ThreadPullEffect, damage_type: DamageType) -> bool:
        """True iff a RESISTANCE row covers ``damage_type`` (null = all types)."""
        return row.resistance_damage_type_id in (damage_type.pk, None)

    def _gift_resistance_total(self, gift_threads: list[Thread], damage_type: DamageType) -> int:
        """Flat RESISTANCE total from GIFT threads (gift-specific preference, per-thread)."""
        total = 0
        for t in gift_threads:
            rows = get_pull_effects_for_thread(t, tier=0, effect_kind=EffectKind.RESISTANCE)
            for row in rows:
                if row.min_thread_level > t.level or row.resistance_amount is None:
                    continue
                if self._resistance_matches(row, damage_type):
                    total += row.resistance_amount
        return total

    def _non_gift_resistance_total(
        self, non_gift_threads: list[Thread], damage_type: DamageType
    ) -> int:
        """Flat RESISTANCE total from non-GIFT threads (single batched query)."""
        if not non_gift_threads:
            return 0

        from django.db.models import Q  # noqa: PLC0415

        thread_level: dict[tuple[str, int], int] = {}
        for t in non_gift_threads:
            key = (t.target_kind, t.resonance_id)
            thread_level[key] = max(thread_level.get(key, 0), t.level)

        q = Q()
        for target_kind, resonance_id in thread_level:
            q |= Q(target_kind=target_kind, resonance_id=resonance_id)
        rows = ThreadPullEffect.objects.filter(
            q,
            tier=0,
            effect_kind=EffectKind.RESISTANCE,
            target_gift__isnull=True,
        ).exclude(resistance_amount__isnull=True)

        total = 0
        for row in rows:
            level = thread_level.get((row.target_kind, row.resonance_id), 0)
            if row.min_thread_level > level or not self._resistance_matches(row, damage_type):
                continue
            total += row.resistance_amount
        return total

    def passive_capability_grants(self) -> set[int]:
        """Return CapabilityType PKs granted by tier-0 CAPABILITY_GRANT effects.

        Thin accessor over the per-handler cached grant set
        (``_passive_capability_grants_cache``). Cleared by ``invalidate()``
        alongside ``_all`` so a sweep over many techniques reuses one memoized
        result (one set of queries per character per request, not per
        requirement).
        """
        return self._passive_capability_grants_cache

    @cached_property
    def _passive_capability_grants_cache(self) -> set[int]:
        """Compute CapabilityType PKs granted by tier-0 CAPABILITY_GRANT effects.

        Derive-on-read mirror of ``passive_vital_bonuses``. For COVENANT_ROLE
        threads the grant only applies while the character holds an active,
        *engaged* CharacterCovenantRole for that role (Slice A §3.6 / #751).
        Other thread kinds always pass (anchor-in-scope via PROTECT — see
        ``passive_vital_bonuses``). Single batched query; no N+1.
        """
        threads = self._all
        if not threads:
            return set()

        from django.db.models import Q  # noqa: PLC0415

        # GIFT threads require gift-specific preference logic; separate them from
        # the non-GIFT batch to avoid cross-gift row leakage.
        gift_threads = [t for t in threads if t.target_kind == TargetKind.GIFT]
        non_gift_threads = [t for t in threads if t.target_kind != TargetKind.GIFT]

        threads_by_key: dict[tuple[str, int], list[Thread]] = {}
        for t in non_gift_threads:
            threads_by_key.setdefault((t.target_kind, t.resonance_id), []).append(t)

        non_gift_effects: list[ThreadPullEffect] = []
        if threads_by_key:
            q = Q()
            for target_kind, resonance_id in threads_by_key:
                q |= Q(target_kind=target_kind, resonance_id=resonance_id)
            non_gift_effects = list(
                ThreadPullEffect.objects.filter(
                    q,
                    tier=0,
                    effect_kind=EffectKind.CAPABILITY_GRANT,
                    target_gift__isnull=True,  # exclude gift-specific rows from batch
                )
                .exclude(capability_grant__isnull=True)
                .select_related("capability_grant")
            )

        from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

        engaged_role_ids = set(
            CharacterCovenantRole.objects.filter(
                character_sheet=self.character.sheet_data,
                engaged=True,
                left_at__isnull=True,
            ).values_list("covenant_role_id", flat=True)
        )

        granted: set[int] = set()

        # Non-GIFT batch processing (unchanged logic)
        for row in non_gift_effects:
            candidates = threads_by_key.get((row.target_kind, row.resonance_id), [])
            for t in candidates:
                if row.min_thread_level > t.level:
                    continue
                if (
                    row.target_kind == TargetKind.COVENANT_ROLE
                    and t.target_covenant_role_id not in engaged_role_ids
                ):
                    continue
                granted.add(row.capability_grant_id)
                break  # one qualifying thread suffices for this effect

        # GIFT threads: prefer gift-specific, fall back to null (per-thread)
        granted.update(self._gift_capability_grant_ids(gift_threads))

        # #2022: Role-granted capabilities from the CovenantRole.granted_capabilities
        # M2M — these are capabilities directly listed on the role (not via
        # ThreadPullEffect). They apply while the role is engaged.
        if engaged_role_ids:
            from world.covenants.models import CovenantRole  # noqa: PLC0415

            role_capability_ids = set(
                CovenantRole.objects.filter(
                    pk__in=engaged_role_ids,
                ).values_list("granted_capabilities", flat=True)
            )
            role_capability_ids.discard(None)
            granted.update(role_capability_ids)

        return granted

    @cached_property
    def context_free_power(self) -> int:
        """Power contributions that hold regardless of what the character is doing (#2708).

        Derived with ``channeled_intensity=0`` and ``technique=None``, so it carries the
        character-level term plus globally-scoped (null-scoped) character and condition
        modifiers, and nothing technique- or thread-contextual. Gift-scoped aura and
        touchstone terms return 0 without a technique by construction.

        ``applicable_threads=[]`` is passed explicitly but is not load-bearing:
        ``_derive_power`` normalizes ``None`` to ``[]`` internally
        (``applicable_threads or []``), so ``None``, ``[]``, and omitting the kwarg are
        byte-identical here. The thread term below is zero because nothing populates the
        list, not because ``[]`` suppresses any resolution — no layer anywhere resolves a
        character's real threads on its own. A later contextual thread term must actively
        resolve and pass a populated list; nothing here is primed to switch on.

        Memoized here rather than recomputed per grant: ``_derive_power`` costs roughly a
        dozen queries, and the agency oracle sweeps every known technique. One derivation
        per character per request keeps that sweep constant-query. Cleared by
        ``invalidate()`` alongside ``_all``.
        """
        from world.magic.services.techniques import _derive_power  # noqa: PLC0415

        return _derive_power(
            channeled_intensity=0,
            technique=None,
            character=self.character,
            applicable_threads=[],
        ).total

    @cached_property
    def _tier0_intensity_bumps(self) -> dict[int, int]:
        """Thread pk -> its tier-0 INTENSITY_BUMP total, batched once per character (#2708).

        One or two queries (non-GIFT threads batched by ``(target_kind, resonance_id)``;
        GIFT threads batched separately so gift-specific rows can be preferred over the
        null-``target_gift`` fallback, resolved in memory) covering every tier-0
        INTENSITY_BUMP row that could possibly apply to any of the character's threads,
        level-scaled the same way ``resolve_pull_effects`` scales an active pull
        (``round(intensity_bump_amount * thread_level_multiplier(thread.level))``, gated
        by ``min_thread_level <= thread.level``) — see
        ``world/magic/services/resonance.py`` around lines 716-734. Memoizing here is what
        keeps ``contextual_thread_power`` query-free per context, so the agency oracle's
        technique sweep stays constant-query. Cleared by ``invalidate()``.

        Does not replicate the FACET-kind worn-item quality-tier scaling
        ``resolve_pull_effects`` applies on top of the level multiplier (it would require
        a per-thread equipment query, defeating the point of this cache) — a tier-0
        INTENSITY_BUMP row authored against a FACET thread would under-scale here relative
        to an active pull of the same thread. No such content exists today.
        ``_non_gift_tier0_intensity_bumps`` guards against silently under-scaling one:
        a FACET-kind row is skipped (with a ``logger.warning``) rather than folded into
        the batch, so the day one is authored this surfaces loudly instead of quietly
        disagreeing with an active pull of the same thread.
        """
        threads = self._all
        if not threads:
            return {}

        gift_threads = [t for t in threads if t.target_kind == TargetKind.GIFT]
        non_gift_threads = [t for t in threads if t.target_kind != TargetKind.GIFT]

        bumps: dict[int, int] = self._non_gift_tier0_intensity_bumps(non_gift_threads)
        for pk, amount in self._gift_tier0_intensity_bumps(gift_threads).items():
            bumps[pk] = bumps.get(pk, 0) + amount
        return bumps

    @staticmethod
    def _non_gift_tier0_intensity_bumps(non_gift_threads: list[Thread]) -> dict[int, int]:
        """Tier-0 INTENSITY_BUMP totals for non-GIFT threads (single batched query).

        FACET-kind rows are skipped loudly (``logger.warning``) rather than folded into
        the generic batch: ``resolve_pull_effects`` scales a FACET pull by the worn-item
        quality-tier aggregate (``resonance.py`` ~lines 749-776) on top of the level
        multiplier this batch applies; replicating that here would need a per-thread
        equipment query, defeating the point of this cache (see the docstring on
        ``_tier0_intensity_bumps``). Silently computing an under-scaled value would let a
        passive contribution and a paid pull of the same thread disagree with no error —
        this makes that divergence impossible to miss instead.
        """
        if not non_gift_threads:
            return {}

        from django.db.models import Q  # noqa: PLC0415

        by_key: dict[tuple[str, int], list[Thread]] = {}
        for t in non_gift_threads:
            by_key.setdefault((t.target_kind, t.resonance_id), []).append(t)

        q = Q()
        for target_kind, resonance_id in by_key:
            q |= Q(target_kind=target_kind, resonance_id=resonance_id)
        rows = ThreadPullEffect.objects.filter(
            q,
            tier=0,
            effect_kind=EffectKind.INTENSITY_BUMP,
            target_gift__isnull=True,
        ).exclude(intensity_bump_amount__isnull=True)

        bumps: dict[int, int] = {}
        for row in rows:
            if row.target_kind == TargetKind.FACET:
                logger.warning(
                    "ThreadPullEffect %s is a FACET-kind tier-0 INTENSITY_BUMP row. "
                    "CharacterThreadHandler.contextual_thread_power does not replicate "
                    "resolve_pull_effects' worn-item quality-tier scaling for FACET "
                    "threads (world/magic/services/resonance.py, FACET branch of "
                    "resolve_pull_effects), so this row is skipped here rather than "
                    "silently under-scaled (#2708).",
                    row.pk,
                )
                continue
            for t in by_key.get((row.target_kind, row.resonance_id), []):
                if row.min_thread_level > t.level:
                    continue
                scaled = round(row.intensity_bump_amount * thread_level_multiplier(t.level))
                bumps[t.pk] = bumps.get(t.pk, 0) + scaled
        return bumps

    @staticmethod
    def _gift_tier0_intensity_bumps(gift_threads: list[Thread]) -> dict[int, int]:
        """Tier-0 INTENSITY_BUMP totals for GIFT threads.

        One batched query; gift-specific rows are preferred over the null-``target_gift``
        fallback per thread, resolved in memory (mirrors ``get_pull_effects_for_thread``'s
        per-thread preference without re-querying per thread).
        """
        if not gift_threads:
            return {}

        from django.db.models import Q  # noqa: PLC0415

        gift_ids = {t.target_gift_id for t in gift_threads}
        resonance_ids = {t.resonance_id for t in gift_threads}
        rows = list(
            ThreadPullEffect.objects.filter(
                Q(target_gift_id__in=gift_ids) | Q(target_gift__isnull=True),
                target_kind=TargetKind.GIFT,
                resonance_id__in=resonance_ids,
                tier=0,
                effect_kind=EffectKind.INTENSITY_BUMP,
            ).exclude(intensity_bump_amount__isnull=True)
        )

        by_resonance_gift: dict[tuple[int, int], list[ThreadPullEffect]] = {}
        by_resonance_null: dict[int, list[ThreadPullEffect]] = {}
        for row in rows:
            if row.target_gift_id is not None:
                by_resonance_gift.setdefault((row.resonance_id, row.target_gift_id), []).append(row)
            else:
                by_resonance_null.setdefault(row.resonance_id, []).append(row)

        bumps: dict[int, int] = {}
        for t in gift_threads:
            candidates = by_resonance_gift.get((t.resonance_id, t.target_gift_id))
            if candidates is None:
                candidates = by_resonance_null.get(t.resonance_id, [])
            total = 0
            for row in candidates:
                if row.min_thread_level > t.level:
                    continue
                total += round(row.intensity_bump_amount * thread_level_multiplier(t.level))
            if total:
                bumps[t.pk] = total
        return bumps

    @cached_property
    def _involved_gift_ids_cache(self) -> dict[tuple[int, ...], frozenset[int]]:
        """Memoizes ``resolve_involved_gift_ids`` per distinct ``involved_techniques`` (#2708).

        ``contextual_thread_power`` is swept once per technique by the capability oracle
        (Task 5), each call carrying a different ``ctx.involved_techniques`` singleton — so
        keying only on "have we resolved gift ids at all this request" (the pre-fix
        behaviour) still re-issued a ``Technique`` query on *every* call for any character
        who owns a GIFT thread. This dict caps that at one query per distinct
        ``involved_techniques`` value for the handler's lifetime (repeat calls with the
        same context: zero queries). It does NOT collapse an N-distinct-context sweep to
        one query on its own — see ``contextual_thread_power``'s ``involved_gift_ids=``
        parameter for the shape that does. Cleared by ``invalidate()``.
        """
        return {}

    def _resolve_involved_gift_ids_cached(
        self, involved_techniques: tuple[int, ...]
    ) -> frozenset[int]:
        """Return cached gift ids for ``involved_techniques``, resolving+caching on miss."""
        cache = self._involved_gift_ids_cache
        cached = cache.get(involved_techniques)
        if cached is None:
            cached = resolve_involved_gift_ids(involved_techniques)
            cache[involved_techniques] = cached
        return cached

    def contextual_thread_power(
        self, ctx: PullActionContext, *, involved_gift_ids: frozenset[int] | None = None
    ) -> int:
        """Tier-0 INTENSITY_BUMP from threads ambiently active for ``ctx`` (#2708).

        The contextual sibling of ``context_free_power``: sums the batched, level-scaled
        tier-0 INTENSITY_BUMP contribution (``_tier0_intensity_bumps``) of every owned
        thread that ``_anchor_ambiently_active`` (Task 3's demonstrable-activation gate,
        not the paid-pull ``_anchor_in_action`` predicate) confirms is genuinely engaged by
        ``ctx`` right now — a pyromancer's fire-gift thread must not raise their ability to
        climb a wall.

        Pure in-memory over the already-cached ``self._all`` and the batched bump map — no
        queries after the first call, EXCEPT for resolving ``ctx.involved_techniques``'s
        gift ids, which needs a real ``Technique`` query and is only skippable when the
        character owns no GIFT thread carrying tier-0 bump content (checked against
        ``bumps``, not merely "owns any GIFT thread" — a GIFT thread with no bump content
        can never change the answer, so the query is skipped even then).

        Two ways this stays cheap under repeated/swept calls, in order of preference:

        - **Batch callers that sweep many techniques** (Task 5's capability oracle: one
          call per technique, each with its own singleton ``involved_techniques``) should
          resolve gift ids for the WHOLE technique set ONCE via
          ``resolve_involved_gift_ids`` and pass the result as ``involved_gift_ids=`` on
          every call — this is what keeps an N-technique sweep at one query total instead
          of N. When supplied, no cache lookup or query happens here at all.
        - **Callers that don't precompute** fall back to ``_involved_gift_ids_cache``,
          which memoizes per distinct ``involved_techniques`` tuple — free for repeated
          calls with an unchanged context, but still one query per distinct tuple (a
          sweep with a genuinely distinct singleton per technique is NOT collapsed by this
          path alone; use ``involved_gift_ids=`` for that case).
        """
        bumps = self._tier0_intensity_bumps
        if not bumps:
            return 0
        if involved_gift_ids is None:
            has_active_gift_bump = any(
                t.target_kind == TargetKind.GIFT and t.pk in bumps for t in self._all
            )
            if has_active_gift_bump and ctx.involved_techniques:
                involved_gift_ids = self._resolve_involved_gift_ids_cached(ctx.involved_techniques)
            else:
                involved_gift_ids = frozenset()
        total = 0
        for thread in self._all:
            bump = bumps.get(thread.pk)
            if not bump:
                continue
            if _anchor_ambiently_active(
                thread, ctx, character=self.character, involved_gift_ids=involved_gift_ids
            ):
                total += bump
        return total

    def _gift_capability_grant_ids(self, gift_threads: list[Thread]) -> set[int]:
        """Return CapabilityType PKs from GIFT threads using gift-specific preference.

        Extracted from ``_passive_capability_grants_cache`` to keep that method
        below the complexity ceiling. Called only when the character has active
        GIFT threads.
        """
        granted: set[int] = set()
        for t in gift_threads:
            rows = get_pull_effects_for_thread(
                t,
                tier=0,
                effect_kind=EffectKind.CAPABILITY_GRANT,
            )
            for row in rows:
                if row.min_thread_level > t.level:
                    continue
                if row.capability_grant_id is not None:
                    granted.add(row.capability_grant_id)
        return granted

    @cached_property
    def _crossing_choices(self) -> list:
        """Batch-fetch all CrossingChoice rows for the character's threads.

        Returns CrossingChoice instances with select_related on ``option`` and
        ``option__condition_template`` so read paths don't fire follow-up queries.
        """
        from world.magic.models.crossing import CrossingChoice  # noqa: PLC0415

        thread_ids = [t.pk for t in self._all]
        if not thread_ids:
            return []
        return list(
            CrossingChoice.objects.filter(thread_id__in=thread_ids).select_related(
                "option", "option__condition_template", "thread__resonance"
            )
        )

    def passive_flat_bonus_for_resonance(self, resonance_id: int) -> int:
        """Sum flat bonuses from crossing choices for a specific resonance.

        Reads ConditionModifierEffect rows on each choice's
        option.condition_template. The modifier_target must not be
        ``power_multiplier`` (which is a percent-delta, not a flat addend).
        Read by the cast power pipeline alongside the existing distinction-power
        flat bonus.
        """
        from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415

        total = 0
        for choice in self._crossing_choices:
            thread = next((t for t in self._all if t.pk == choice.thread_id), None)
            if thread is None or thread.resonance_id != resonance_id:
                continue
            template = choice.option.condition_template
            effects = ConditionModifierEffect.objects.filter(
                condition=template,
            )
            for effect in effects:
                if effect.modifier_target.name == "power_multiplier":  # noqa: STRING_LITERAL
                    continue
                total += effect.value
        return total

    def invalidate(self) -> None:
        """Clear the cached thread list and any pull-side cache derived from threads.

        Called by mutation services after threads are created, retired, or levelled.
        Also clears ``combat_pulls._active`` if it has been loaded: thread mutations
        can shift the effective level multiplier on pull-resolved effects, so the
        active-pull snapshot must be refreshed alongside the thread list.
        """
        self.__dict__.pop("_all", None)
        self.__dict__.pop("_passive_capability_grants_cache", None)
        self.__dict__.pop("_crossing_choices", None)
        self.__dict__.pop("context_free_power", None)
        self.__dict__.pop("_tier0_intensity_bumps", None)
        self.__dict__.pop("_involved_gift_ids_cache", None)
        # Clear the pull-side cached_property only if the combat_pulls handler is
        # already instantiated (avoids triggering an import cycle on cold access).
        combat_pulls_handler = self.character.__dict__.get("combat_pulls")
        if combat_pulls_handler is not None:
            combat_pulls_handler.invalidate()


class CharacterResonanceHandler:
    """Handler for a character's CharacterResonance rows (Spec A §3.7).

    Cached ``{resonance_pk: CharacterResonance}`` dict for O(1) balance and
    lifetime lookups. Empty dict when the character has earned no resonances.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _by_resonance(self) -> dict[int, CharacterResonance]:
        sheet = self.character.sheet_data
        return {
            cr.resonance_id: cr
            for cr in CharacterResonance.objects.filter(character_sheet=sheet).select_related(
                "resonance__affinity"
            )
        }

    def all(self) -> list[CharacterResonance]:
        """Return all CharacterResonance rows for this character."""
        return list(self._by_resonance.values())

    def balance(self, resonance: Resonance) -> int:
        """Return the spendable balance for ``resonance``; 0 if no row exists."""
        cr = self._by_resonance.get(resonance.pk)
        return cr.balance if cr else 0

    def lifetime(self, resonance: Resonance) -> int:
        """Return the lifetime_earned value for ``resonance``; 0 if no row exists."""
        cr = self._by_resonance.get(resonance.pk)
        return cr.lifetime_earned if cr else 0

    def get_or_create(self, resonance: Resonance) -> CharacterResonance:
        """Return the CharacterResonance row, creating it lazily if absent."""
        cr = self._by_resonance.get(resonance.pk)
        if cr is None:
            cr, _ = CharacterResonance.objects.get_or_create(
                character_sheet=self.character.sheet_data,
                resonance=resonance,
                defaults={"balance": 0, "lifetime_earned": 0},
            )
            self._by_resonance[resonance.pk] = cr
        return cr

    def most_recently_earned(self) -> CharacterResonance | None:
        """Return the row with the highest lifetime_earned; ties broken by ``-pk``.

        Used by Mage Scars (`_apply_magical_scars`) to derive origin
        affinity / resonance from the character's magical history. Returns
        ``None`` when the character has earned no resonances yet.
        """
        rows = list(self._by_resonance.values())
        if not rows:
            return None
        return max(rows, key=lambda cr: (cr.lifetime_earned, cr.pk))

    def invalidate(self) -> None:
        """Clear the cached resonance dict. Called by mutation services."""
        self.__dict__.pop("_by_resonance", None)


class CharacterTechniqueHandler:
    """Per-character technique inventory with effect properties pre-resolved.

    Single underlying ``cached_property`` prefetches every Technique the
    character has been granted plus the Gift → Resonance → Property chain
    that drives clash-opposition matching. Subset methods do list-comps over
    the cache.

    Mutation contract: services that grant or revoke a CharacterTechnique
    call ``handler.invalidate()`` afterwards.

    Used by the combat-resolution-loop PR (Phase 2): clash participation
    services read eligibility from ``helper_eligible_for(clash_props)``;
    ``_detect_clash_flavor`` reads ``effect_property_ids_for(technique)`` to
    match PC and NPC opposition props.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _state(self) -> list[Technique]:
        """ONE prefetched list of every Technique the character has."""
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.mechanics.models import Property  # noqa: PLC0415

        return list(
            Technique.objects.filter(
                character_grants__character__character=self.character,
            )
            .select_related(
                "gift",
                "effect_type",
                "action_template",
                "action_template__check_type",
            )
            .prefetch_related(
                Prefetch(
                    "gift__resonances",
                    queryset=Resonance.objects.prefetch_related(
                        Prefetch(
                            "properties",
                            queryset=Property.objects.all(),
                            to_attr="cached_properties",
                        ),
                    ),
                    to_attr="cached_resonances",
                ),
            )
        )

    def all(self) -> list[Technique]:
        """Return every Technique the character has."""
        return list(self._state)

    def clash_capable(self) -> list[Technique]:
        """Return Techniques with clash_capable=True."""
        return [t for t in self._state if t.clash_capable]

    def effect_property_ids_for(self, technique: Technique) -> frozenset[int]:
        """Return the effect-Property pks carried by ``technique``.

        Resolved via the prefetched Gift → Resonance → Property chain. Returns
        an empty frozenset for techniques the character doesn't have or
        techniques without a Gift.
        """
        for t in self._state:
            if t.pk != technique.pk:
                continue
            if t.gift_id is None:
                return frozenset()
            ids: set[int] = set()
            for resonance in t.gift.cached_resonances:
                ids.update(p.pk for p in resonance.cached_properties)
            return frozenset(ids)
        return frozenset()

    def helper_eligible_for(
        self,
        clash_property_ids: frozenset[int] | set[int],
    ) -> list[Technique]:
        """Return clash-capable Techniques whose effect properties overlap.

        Used to surface helper-eligible techniques for an active clash —
        a Technique is eligible iff it is clash-capable AND its effect
        property set shares at least one Property with the clash's
        opposition props.
        """
        if not clash_property_ids:
            return []
        eligible: list[Technique] = []
        for t in self._state:
            if not t.clash_capable:
                continue
            t_props = self.effect_property_ids_for(t)
            if t_props & clash_property_ids:
                eligible.append(t)
        return eligible

    def invalidate(self) -> None:
        """Clear the cached technique list. Called by mutation services."""
        self.__dict__.pop("_state", None)


class CharacterWeavingUnlockHandler:
    """Cached handler for a character's weaving unlocks (ADR-0093).

    Loads all CharacterThreadWeavingUnlock rows once with select_related on
    the unlock. All lookups are list comprehensions against the cached list —
    never .filter()/.exists() in service functions.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _rows(self) -> list:
        from world.magic.models import CharacterThreadWeavingUnlock  # noqa: PLC0415

        return list(
            CharacterThreadWeavingUnlock.objects.filter(
                character_id=self.character.pk
            ).select_related("unlock")
        )

    def has_unlock_for_kind(self, kind: str) -> bool:
        """Return True if the character has any unlock with the given target_kind."""
        return any(r.unlock.target_kind == kind for r in self._rows)

    def has_unlock_for_trait(self, trait) -> bool:
        """Return True if the character has a TRAIT-kind unlock for the given trait."""
        return any(
            r.unlock.target_kind == TargetKind.TRAIT and r.unlock.unlock_trait_id == trait.pk
            for r in self._rows
        )

    def has_unlock_for_gift(self, gift) -> bool:
        """Return True if the character has a TECHNIQUE-kind unlock for the given gift."""
        return any(
            r.unlock.target_kind == TargetKind.TECHNIQUE and r.unlock.unlock_gift_id == gift.pk
            for r in self._rows
        )

    def has_unlock_for_track(self, track) -> bool:
        """Return True if the character has a RELATIONSHIP_TRACK-kind unlock for the given track."""
        return any(
            r.unlock.target_kind == TargetKind.RELATIONSHIP_TRACK
            and r.unlock.unlock_track_id == track.pk
            for r in self._rows
        )

    def invalidate(self) -> None:
        """Clear the cached unlock list. Called by mutator services."""
        self.__dict__.pop("_rows", None)
