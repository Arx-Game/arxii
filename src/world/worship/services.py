"""Worship service functions (#2355).

The single write paths for worship: ceremonies (#2289) and future worship acts
call ``grant_worship`` (being pool + ledger) and ``bump_devotion`` (PC↔god
standing + the God's Favorite achievement check). Explicit calls, no signals.
"""

import logging
from typing import TYPE_CHECKING

from django.db.models import Max
from django.utils import timezone

from world.worship.constants import (
    GODS_FAVORITE_CHOSEN,
    GODS_FAVORITE_PRINCE,
    GODS_FAVORITE_PRINCESS,
)
from world.worship.models import (
    ChosenFavorConfig,
    DevotionStanding,
    PatronageValence,
    WorshipDeclaration,
    WorshipGrant,
    WorshippedBeing,
)
from world.worship.types import ChosenDistinctionGrants, DevotionBump

if TYPE_CHECKING:
    from datetime import date

    from world.achievements.models import Achievement
    from world.character_sheets.models import CharacterSheet
    from world.traits.models import CheckOutcome
    from world.worship.models import DivineInterventionConfig, Miracle, MiraclePerformance
    from world.worship.types import FavorSource

logger = logging.getLogger(__name__)


def grant_worship(
    being: WorshippedBeing,
    amount: int,
    *,
    granted_by: "CharacterSheet | None" = None,
    reason: str = "",
) -> WorshipGrant:
    """Add worship to a being's pool and record the audit ledger row."""
    if amount <= 0:
        msg = "Worship grants must be a positive amount."
        raise ValueError(msg)
    being.resonance_pool += amount
    being.lifetime_worship += amount
    being.save(update_fields=["resonance_pool", "lifetime_worship"])
    return WorshipGrant.objects.create(
        being=being, amount=amount, granted_by=granted_by, reason=reason
    )


def convert_public_worship(
    character_sheet: "CharacterSheet",
    new_being: WorshippedBeing,
    *,
    is_sincere: bool = True,
) -> WorshipDeclaration:
    """Repoint a character's PUBLIC worship declaration (#2361).

    The single write path for a public conversion — called from
    ``world.ceremonies.services.finish_ceremony``'s CONVERSION branch for both
    routes (a PC-officiated rite the convert accepted, or a self-officiated solo
    rite). Get-or-creates the declaration so a character's first post-CG public
    declaration (no prior ``WorshipDeclaration`` row at all) is the same code path
    as a conversion — matches the draft spec's Decision 1.

    Decision 3 (issue #2361 draft, unamended): ``DevotionStanding`` rows for the
    old AND new being are untouched here — favor history with either god survives
    a conversion as-is; only the public *front* changes. ``secret_being``/
    ``secret`` are also untouched (out of scope for this pass per the ratified
    amendments — the old Secret stays exactly as minted, still discoverable).

    ``is_sincere`` is the private heart-vs-lip-service choice (Ratified
    amendment #2): True means the character converts inwardly too, False means
    the public act is performative only. Stored on the declaration itself;
    never exposed to a non-owner/non-staff viewer (see the ``current_mood``
    leak-table pattern in ``world.character_sheets.serializers._build_identity``).
    """
    declaration, _ = WorshipDeclaration.objects.get_or_create(character_sheet=character_sheet)
    declaration.public_being = new_being
    declaration.public_is_sincere = is_sincere
    declaration.save(update_fields=["public_being", "public_is_sincere"])
    return declaration


def gods_favorite_achievement_for(character_sheet: "CharacterSheet") -> "Achievement | None":
    """Resolve the gender-matched God's Favorite achievement row (Decision 6).

    ``female`` → Princess, ``male`` → Prince, anything else (nonbinary keys,
    unspecified, or no gender row) → Chosen. Returns None when the achievement
    rows aren't seeded (bare test DB) — callers skip gracefully.
    """
    from world.achievements.models import Achievement  # noqa: PLC0415

    gender_key = character_sheet.gender.key if character_sheet.gender_id else ""
    name = {
        "female": GODS_FAVORITE_PRINCESS,
        "male": GODS_FAVORITE_PRINCE,
    }.get(gender_key, GODS_FAVORITE_CHOSEN)
    return Achievement.objects.filter(name=name, is_active=True).first()


def bump_devotion(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,
    amount: int,
    *,
    source: "FavorSource | None" = None,
) -> DevotionBump:
    """Upsert the (sheet, being) standing and run the God's Favorite check.

    Becoming — or tying — the top ``favor`` holder for the being grants the
    gender-matched achievement (leapfroggers earn it too; earlier holders keep
    theirs; ``grant_achievement`` is idempotent per sheet).

    A positive ``amount`` is scaled by the character's earning rate with the
    being (#4333, design 1a): 100%, plus favor earning modifiers (a Chosen's bonus is
    one, on the patron target, #4341). Every favor source writes through here, so all
    of them are scaled. A negative amount is applied as given. Returns the
    standing and the amount actually credited.

    While the character holds an open pledge to ``being`` (#4333 slice 2), the
    credited amount also advances the pledge's ``Project.current_progress`` and
    is recorded as a ``PledgeCredit`` of ``source``'s kind with its calculation.
    While she holds an active pact with ``being`` (#4341), it also counts toward each
    open period of the pact (``record_pact_credit``).
    """
    from world.pacts.services import record_pact_credit  # noqa: PLC0415
    from world.worship.favor_services import earning_rate  # noqa: PLC0415
    from world.worship.pledge_services import record_pledge_credit  # noqa: PLC0415

    earned = amount > 0
    base = amount
    rate = 100
    owed_paid = 0
    standing, _ = DevotionStanding.objects.get_or_create(
        character_sheet=character_sheet, being=being
    )
    if earned:
        # Owed favor (#4349) is paid first, from the base amount, before the earning rate:
        # only the rest is scaled, added to favor and counted toward an open pledge.
        owed_paid = min(standing.owed_favor, base)
        standing.owed_favor -= owed_paid
        base -= owed_paid
        rate = earning_rate(character_sheet, being)
        amount = base * rate // 100
    standing.favor += amount
    standing.lifetime_favor += max(amount, 0)
    standing.save(update_fields=["favor", "lifetime_favor", "owed_favor"])

    top_other = (
        (
            DevotionStanding.objects.filter(being=being)
            .exclude(pk=standing.pk)
            .aggregate(top=Max("favor"))["top"]
        )
        or 0
    )
    if standing.favor >= top_other:
        achievement = gods_favorite_achievement_for(character_sheet)
        if achievement is not None:
            from world.achievements.services import grant_achievement  # noqa: PLC0415

            grant_achievement(achievement, [character_sheet])

    # Divine intervention trigger installation/removal (#2360)
    cfg = get_divine_intervention_config()
    if standing.favor >= cfg.favor_threshold:
        install_divine_intervention_trigger(character_sheet, being)
    else:
        remove_divine_intervention_trigger(character_sheet, being)

    pledge_credit = None
    if earned:
        pledge_credit = record_pledge_credit(
            character_sheet,
            being,
            base=base,
            rate=rate,
            credited=amount,
            source=source,
            owed_paid=owed_paid,
        )
        # A write the pledge credit already counts takes nothing more from the deed cap.
        record_pact_credit(
            character_sheet,
            being,
            amount,
            source,
            base=0 if pledge_credit is not None else base,
        )
    return DevotionBump(
        standing=standing,
        credited=amount,
        pledge_credit=pledge_credit,
        earning_rate_percent=rate,
        owed_paid=owed_paid,
    )


def get_divine_intervention_config() -> "DivineInterventionConfig":
    """Lazy-create the singleton (pk=1) divine intervention config (#2360)."""
    from world.worship.models import DivineInterventionConfig  # noqa: PLC0415

    cfg = DivineInterventionConfig.objects.cached_singleton()
    if cfg is None:
        cfg = DivineInterventionConfig.objects.create(pk=1)
    return cfg


def spend_worship_pool(being: WorshippedBeing, amount: int, *, reason: str = "") -> bool:  # noqa: ARG001
    """Deduct ``amount`` from ``being.resonance_pool`` (the spend counterpart to ``grant_worship``).

    Returns ``True`` if the deduction succeeded, ``False`` if the pool was
    insufficient (no partial spend). Raises ``ValueError`` for non-positive amounts.
    Does NOT create an audit row — the caller creates ``MiraclePerformance``.
    """
    if amount <= 0:
        msg = "Worship pool spends must be a positive amount."
        raise ValueError(msg)
    # Re-fetch with lock to avoid race on concurrent miracles.
    locked = WorshippedBeing.objects.select_for_update().filter(pk=being.pk).first()
    if locked is None or locked.resonance_pool < amount:
        return False
    locked.resonance_pool -= amount
    locked.save(update_fields=["resonance_pool"])
    # Propagate to the in-memory instance the caller holds.
    being.resonance_pool = locked.resonance_pool
    return True


# =============================================================================
# Divine intervention (#2360)
# =============================================================================

_DIVINE_INTERVENTION_TRIGGER_NAME = "divine_intervention_on_incapacitated"
COOLDOWN_CONDITION_NAME = "Divine Intervention Cooldown"


def _tell_room_without_a_scene(character, text: str, *, notify_character: bool) -> None:
    """The fallback when there is no scene to EMIT into (#4349): the room's other occupants
    hear ``text`` at once, and with ``notify_character`` the one it concerns is sent it as a
    stored notice, so an effect that applied is never silent for them."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415

    location = character.location
    if location is not None:
        location.msg_contents(text, exclude=[character])
    if not notify_character:
        return
    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return
    send_stored_notice(sheet, text, ooc_note="Divine intervention")


def _broadcast_miracle_narrative(
    character, text: str, scene=None, *, notify_character: bool = True
) -> None:
    """Broadcast miracle narrative as an EMIT to the active scene.

    With no scene (or no primary persona) the room hears it directly and, when
    ``notify_character``, the character it concerns is sent it too (#4349). Mirrors
    ``_broadcast_manifestation`` in ``world/magic/audere_majora.py``.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_interaction,
        push_interaction,
    )
    from world.scenes.models import Persona, Scene  # noqa: PLC0415

    if scene is None:
        scene = Scene.objects.active_for_room(character.location).first()
    if scene is None:
        _tell_room_without_a_scene(character, text, notify_character=notify_character)
        return

    try:
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        _tell_room_without_a_scene(character, text, notify_character=notify_character)
        return

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.EMIT,
        scene=scene,
    )
    push_interaction(
        interaction,
        receiver_persona_ids=[],
        target_persona_ids=[],
        receiver_characters=[],
    )


def broadcast_prayer_line(character, text: str, scene=None) -> None:
    """Post a prayer's room line as an EMIT to the scene (#4349): an ally praying for a fallen
    character, which onlookers see before the result's own lines."""
    _broadcast_miracle_narrative(character, text, scene, notify_character=False)


def perform_divine_intervention(  # noqa: PLR0913 - the roll's result and the GM's line ride along
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,
    miracle: "Miracle",
    *,
    scene=None,
    trigger_event: str = "character_incapacitated",
    outcome_tier: "CheckOutcome | None" = None,
    context_text: str = "",
) -> "MiraclePerformance":
    """Commit seam for a divine intervention: spend pool, apply conditions, audit.

    Called by ``fire_divine_intervention`` (the intervention roll) and by the steward's live
    answer. Assumes eligibility is already verified (favor threshold, pool sufficient,
    cooldown clear). ``character_sheet`` is the one the miracle lands on. ``trigger_event``
    names what fired it on the audit row (the combat event, or a prayer's straits).
    ``outcome_tier`` is the intervention roll's result, recorded on the audit row (a live
    answer passes none); ``context_text`` is the GM's line for the ``MIRACLE`` prompt.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.worship.models import MiraclePerformance  # noqa: PLC0415

    character = character_sheet.character

    with transaction.atomic():
        spend_worship_pool(being, miracle.resonance_pool_cost, reason="divine_intervention")

        # Apply each MiracleAppliedCondition row directly via apply_condition.
        # Miracles have no technique context, so apply_technique_conditions is
        # not used — only base_severity and base_duration_rounds contribute.
        for row in miracle.condition_applications.select_related("condition"):
            apply_condition(
                target=character,
                condition=row.condition,
                severity=row.base_severity,
                duration_rounds=row.base_duration_rounds,
            )

        performance = MiraclePerformance.objects.create(
            miracle=miracle,
            being=being,
            target_character=character_sheet,
            scene=scene,
            resonance_spent=miracle.resonance_pool_cost,
            trigger_event=trigger_event,
            outcome_tier=outcome_tier,
        )

    _route_miracle(character_sheet, miracle.narrative_text, scene, context_text=context_text)

    return performance


def route_intervention_text(
    character_sheet: "CharacterSheet", text: str, scene=None, *, context_text: str = ""
) -> None:
    """Route a lesser answer's or backfire's authored text the way a miracle's is: to the scene
    GM as a ``MIRACLE`` prompt when one is present, else as a room line (#4349)."""
    _route_miracle(character_sheet, text, scene, context_text=context_text)


def _route_miracle(
    character_sheet: "CharacterSheet", text: str, scene=None, *, context_text: str = ""
) -> None:
    """Prompt the scene GM with the miracle, or broadcast its authored text as today (#4101).

    ``context_text`` is the GM-only line (result tier, what was drawn, who prayed, #4349).
    Follows the shape of ``_announce_surge``/``_route_ultimate_chosen``/``_route_crossing``
    (``world/magic/audere.py`` et al.): the scene lookup and ``route_narratable_event``
    call run inside the same ``transaction.atomic()``, so a ``DatabaseError`` raised
    from either is contained to this savepoint rather than aborting whatever
    enclosing transaction the caller is in (#4101 fix round 1, ruling R8-1 shape).
    ``_deliver()`` -- the unprompted broadcast -- runs exactly once, outside the
    try/except, keyed on whether ``route_narratable_event`` actually produced any
    prompts; it passes the caller's own ``scene`` argument (possibly None) rather
    than a variable resolved inside the try, since that resolution may never have
    run if the try raised before reaching it -- ``_broadcast_miracle_narrative``
    re-resolves a None scene by the character's current location itself.
    """
    from django.db import DatabaseError, transaction  # noqa: PLC0415

    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    character = character_sheet.character

    def _deliver() -> None:
        if text.strip():
            _broadcast_miracle_narrative(character, text, scene)

    try:
        with transaction.atomic():
            routed_scene = (
                scene
                if scene is not None
                else Scene.objects.active_for_room(character.location).first()
            )
            prompts = route_narratable_event(
                NarratableEvent(
                    kind=GMPromptKind.MIRACLE,
                    scene=routed_scene,
                    character_sheet=character_sheet,
                    room_text=text,
                    context_text=context_text,
                ),
            )
    except DatabaseError:
        logger.exception(
            "Miracle routing failed to create GM prompts for sheet %s; "
            "delivering unprompted instead (#4101).",
            character_sheet.pk,
        )
        prompts = []
    if not prompts:
        _deliver()


def maybe_fire_divine_intervention(character=None, payload=None) -> None:
    """Trigger handler: divine intercession, a being stepping in for a fallen character (#4349).

    Called by the ``divine_intervention_on_incapacitated`` TriggerDefinition's
    ``CALL_SERVICE_FUNCTION`` flow step. The ``payload`` is a
    ``CharacterIncapacitatedPayload`` (unused — the character is the trigger's ``obj``).
    The trigger is installed once favor reaches ``DivineInterventionConfig.favor_threshold``
    (the intercession threshold); the fallen character makes the roll at her own odds and
    cost, exactly as if she had prayed. She is told privately what came of it.
    """
    from django.core.exceptions import ObjectDoesNotExist, ValidationError  # noqa: PLC0415
    from django.db import DatabaseError  # noqa: PLC0415

    from flows.object_states.base_state import BaseState  # noqa: PLC0415
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415
    from world.worship.constants import MiracleTrigger  # noqa: PLC0415
    from world.worship.intervention_services import (  # noqa: PLC0415
        fire_divine_intervention,
        intercession_lines,
    )

    if isinstance(character, BaseState):
        # A flow step hands a game object over as its state (CALL_SERVICE_FUNCTION resolves an
        # "@owner" reference that way): the character is the state's object.
        character = character.obj
    if character is None and payload is not None:
        character = payload.character
    if character is None:
        return
    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return
    scene = Scene.objects.active_for_room(character.location).first()
    try:
        result = fire_divine_intervention(
            sheet,
            trigger=MiracleTrigger.INCAPACITATED,
            trigger_event="character_incapacitated",
            scene=scene,
        )
    except (DatabaseError, ObjectDoesNotExist, ValidationError, LookupError, ValueError, TypeError):
        # Authored-data and write failures in the roll or its draw never break incapacitation.
        # The roll runs in its own transaction, so a failure leaves no half-paid cost behind.
        logger.exception(
            "Divine intercession failed for sheet %s; incapacitation goes on (#4349).", sheet.pk
        )
        return
    if result.rolled:
        from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415

        for line in intercession_lines(result):
            send_stored_notice(sheet, line, ooc_note="Divine intercession")


def intervention_cooldown_active(character) -> bool:
    """Whether the divine intervention cooldown condition is on ``character``."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        condition__name=COOLDOWN_CONDITION_NAME,
    ).exists()


def miracle_ineligibility(
    character_sheet: "CharacterSheet",
    miracle: "Miracle",
    *,
    favor: int | None = None,
    on_cooldown: bool | None = None,
    cfg: "DivineInterventionConfig | None" = None,
) -> str:
    """Why ``miracle`` cannot be performed for ``character_sheet`` now, or "" when it can.

    The eligibility half of a divine intervention (#2360, #4333 design 6), shared
    by the intervention roll (``intervention_services.fire_divine_intervention``) and the
    live answer panel: the intervention cooldown condition is clear, the character's favor
    with the miracle's being meets the higher of the prayer favor gate and the miracle's own
    threshold (the floor a live answer keeps, since new miracles default to 0), and the being's
    pool covers the larger of the miracle's cost and the config minimum. The config's favor
    threshold is not asked here: since #4349 it is the divine intercession threshold. Owed
    favor and the wait belong to the roll, which a steward's live answer does not obey. The
    miracle's trigger is not asked either: a caller that fires on a trigger filters by it.
    ``favor``, ``on_cooldown`` and ``cfg`` let a caller that already holds them skip the
    lookups.
    """
    if cfg is None:
        cfg = get_divine_intervention_config()
    if on_cooldown is None:
        on_cooldown = intervention_cooldown_active(character_sheet.character)
    if on_cooldown:
        return "Divine intervention is on cooldown for this character."
    being = miracle.being
    if favor is None:
        standing = DevotionStanding.objects.filter(
            character_sheet=character_sheet, being=being
        ).first()
        favor = standing.favor if standing is not None else 0
    threshold = max(cfg.prayer_favor_gate, miracle.favor_threshold)
    if favor < threshold:
        return f"Favor with {being.name} ({favor}) is below this miracle's threshold ({threshold})."
    needed = max(miracle.resonance_pool_cost, cfg.min_pool_for_intervention)
    if being.resonance_pool < needed:
        return f"{being.name}'s worship pool ({being.resonance_pool}) cannot pay {needed}."
    return ""


def install_divine_intervention_trigger(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,  # noqa: ARG001
) -> None:
    """Install the divine intervention Trigger on the character's ObjectDB.

    Idempotent — ``get_or_create`` on (obj, trigger_definition). Called from
    ``bump_devotion`` when favor crosses the config threshold. Mirrors the
    Soul Tether trigger installation pattern (soul_tether.py:316).
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    trigger_def = TriggerDefinition.objects.filter(
        name=_DIVINE_INTERVENTION_TRIGGER_NAME,
    ).first()
    if trigger_def is None:
        return  # Content not seeded; no-op.

    character = character_sheet.character
    trigger, created = Trigger.objects.get_or_create(
        obj=character,
        trigger_definition=trigger_def,
    )
    if created:
        handler = character.trigger_handler
        if handler is not None:
            handler.on_trigger_added(trigger)


def remove_divine_intervention_trigger(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,  # noqa: ARG001
) -> None:
    """Remove the divine intervention trigger when favor drops below threshold."""
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    trigger_def = TriggerDefinition.objects.filter(
        name=_DIVINE_INTERVENTION_TRIGGER_NAME,
    ).first()
    if trigger_def is None:
        return

    character = character_sheet.character
    Trigger.objects.filter(
        obj=character,
        trigger_definition=trigger_def,
    ).delete()


def get_chosen_favor_config() -> ChosenFavorConfig:
    """Lazy-create the ChosenFavorConfig singleton (pk=1)."""

    config, _ = ChosenFavorConfig.objects.get_or_create(pk=1)
    return config


def active_patronage_for(sheet: "CharacterSheet") -> list[DevotionStanding]:
    """Return all active patronages for a character, ordered by favor descending.

    An active patronage is a DevotionStanding with ``valence`` set (non-null)
    and ``released_at`` null. Ordinary worship rows (valence=null) and released
    patronages are excluded.

    ``select_related("being")``: the Audere ultimate reveal (#4098,
    ``world.magic.services.ultimates._patron_pools``) reads ``s.being`` for
    every row this returns — without it, that access costs one query per
    patronage.
    """
    return list(
        DevotionStanding.objects.filter(
            character_sheet=sheet,
            valence__isnull=False,
            released_at__isnull=True,
        )
        .select_related("being")
        .order_by("-favor")
    )


def grant_chosen_distinction_to_chosen(config: ChosenFavorConfig) -> ChosenDistinctionGrants:
    """Grant the designated Chosen distinction to every Chosen who lacks it (#4341).

    Called by the Chosen favor admin when staff set or change
    ``config.chosen_distinction``; character creation grants it with the patronage
    (``establish_chosen_patronage``). A Chosen whose distinctions exclude it is skipped
    and returned, so the admin can name her. Does nothing when no distinction is
    designated.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415
    from world.worship.favor_services import chosen_standing_q  # noqa: PLC0415

    distinction = config.chosen_distinction
    if distinction is None:
        return ChosenDistinctionGrants(granted=0, skipped=())
    holders = CharacterDistinction.objects.filter(distinction=distinction).values("character_id")
    sheet_ids = (
        DevotionStanding.objects.filter(chosen_standing_q())
        .exclude(character_sheet_id__in=holders)
        .values_list("character_sheet_id", flat=True)
        .distinct()
    )
    granted = 0
    skipped: list[CharacterSheet] = []
    for sheet in CharacterSheet.objects.filter(pk__in=list(sheet_ids)).order_by("pk"):
        try:
            grant_distinction(
                sheet,
                distinction,
                origin=DistinctionOrigin.GAMEPLAY,
                rank=1,
                source_description="Chosen of a being",
            )
        except DistinctionExclusionError:
            logger.warning(
                "Chosen distinction %s skipped for sheet %s (exclusion conflict)",
                distinction.pk,
                sheet.pk,
            )
            skipped.append(sheet)
            continue
        granted += 1
    return ChosenDistinctionGrants(granted=granted, skipped=tuple(skipped))


def grant_chosen_distinction(sheet: "CharacterSheet") -> None:
    """Grant ``sheet`` the designated Chosen distinction at character creation (#4341),
    unless none is designated or she already holds it. A distinction she holds that
    excludes it is logged and skipped; creation goes on."""
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    distinction = get_chosen_favor_config().chosen_distinction
    if distinction is None:
        return
    if CharacterDistinction.objects.filter(character=sheet, distinction=distinction).exists():
        return
    try:
        grant_distinction(
            sheet,
            distinction,
            origin=DistinctionOrigin.CHARACTER_CREATION,
            rank=1,
            source_description="Path of the Chosen",
        )
    except DistinctionExclusionError:
        # Creation still succeeds: she is Chosen, without the bonus her distinctions
        # exclude (the achievements reward grant handles the conflict the same way).
        logger.warning(
            "Chosen distinction %s skipped at creation for sheet %s (exclusion conflict)",
            distinction.pk,
            sheet.pk,
        )


def establish_patronage(
    sheet: "CharacterSheet",
    being: WorshippedBeing,
    *,
    valence: PatronageValence,
) -> DevotionStanding:
    """Get-or-create a DevotionStanding and mark it as a patronage.

    If the standing already exists (ordinary worship), the valence and
    established_at are set on it — favor is preserved. Idempotent: re-calling
    with the same being does not reset established_at.
    """
    standing, _ = DevotionStanding.objects.get_or_create(
        character_sheet=sheet,
        being=being,
    )
    if standing.valence is None:
        standing.valence = valence
        standing.established_at = timezone.now()
        standing.save(update_fields=["valence", "established_at"])
    return standing


def release_patronage(standing: DevotionStanding) -> None:
    """Mark a patronage as released (dormant).

    Sets ``released_at`` — the Chosen keeps the Path but this patron's favor
    no longer counts toward benefit thresholds. The standing row is preserved
    for audit.
    """
    standing.released_at = timezone.now()
    standing.save(update_fields=["released_at"])


def is_birth_favored_by(
    character_sheet: "CharacterSheet", being: WorshippedBeing, *, today: "date | None" = None
) -> bool:
    """Whether character_sheet is birth-favored by being today (#3776).

    True only when BOTH hold: the character's own tarot card matches one of the
    being's tarot cards, AND today is the character's birthday. Being-scoped, pure
    query — issue #3777's worship-rite reward calc doubles the payout when this is
    True; it does not itself grant anything.

    ``character_sheet.tarot_card`` is a forwarding property onto
    ``true_profile.tarot_card`` (#1270 slice 3) — there is no separate
    ``character_sheet.profile`` accessor to go through; it already returns None
    when the sheet has no ``true_profile`` attached.

    ``birthday_month``/``birthday_day`` are IC calendar values (#2756) — the Town
    Crier birthday feed (``world.tidings.services._birthday_items``) already compares
    them against ``get_ic_now()``, never the real wall clock, so a caller-omitted
    ``today`` resolves the same way here instead of defaulting to
    ``datetime.date.today()``. Returns False (never raises) when no ``GameClock`` is
    active — the same "content not seeded" graceful-skip other worship service
    functions use for a bare test DB.
    """
    if today is None:
        from world.game_clock.services import get_ic_now  # noqa: PLC0415

        ic_now = get_ic_now()
        if ic_now is None:
            return False
        today = ic_now.date()
    tarot_card = character_sheet.tarot_card
    if tarot_card is None:
        return False
    if not being.tarot_cards.filter(pk=tarot_card.pk).exists():
        return False
    return (
        character_sheet.birthday_month == today.month and character_sheet.birthday_day == today.day
    )
