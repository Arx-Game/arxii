"""Per-character handlers for the resonance/thread surface (Spec A §3.7).

These handlers wire onto the ``Character`` typeclass alongside the established
``character.traits`` etc. handlers. They cache per-character data via
``django.utils.functional.cached_property`` and rely on service functions to
call ``.invalidate()`` after mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django.utils.functional import cached_property

from world.magic.constants import EffectKind, TargetKind
from world.magic.models import CharacterResonance, Thread, ThreadPullEffect
from world.magic.models.techniques import Technique
from world.magic.services.pull_effects import get_pull_effects_for_thread

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.conditions.models import DamageType
    from world.magic.models import Facet, Resonance


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
        sheet = self.character.sheet_data
        return list(
            Thread.objects.filter(owner=sheet, retired_at__isnull=True).select_related(
                "resonance__affinity",
                "target_trait",
                "target_technique",
                "target_relationship_track",
                "target_capstone",
                "target_facet",
                "target_covenant_role",
                "target_gift",
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
        formula as active pulls: ``level_multiplier = max(1, thread.level // 10)``
        times the authored ``vital_bonus_amount``. ``min_thread_level``
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
            multiplier = max(1, level // 10)
            for row in rows:
                if row.min_thread_level > level or row.vital_bonus_amount is None:
                    continue
                total += row.vital_bonus_amount * multiplier

        # --- Non-GIFT: sum contributions ---
        for row in non_gift_effects:
            level = thread_level.get((row.target_kind, row.resonance_id), 0)
            if row.min_thread_level > level:
                continue
            multiplier = max(1, level // 10)
            total += row.vital_bonus_amount * multiplier
        return total

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
        return granted

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

    def invalidate(self) -> None:
        """Clear the cached thread list and any pull-side cache derived from threads.

        Called by mutation services after threads are created, retired, or levelled.
        Also clears ``combat_pulls._active`` if it has been loaded: thread mutations
        can shift the effective level multiplier on pull-resolved effects, so the
        active-pull snapshot must be refreshed alongside the thread list.
        """
        self.__dict__.pop("_all", None)
        self.__dict__.pop("_passive_capability_grants_cache", None)
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
