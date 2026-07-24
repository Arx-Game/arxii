from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Prefetch, QuerySet

from world.forms.models import (
    ActiveAlternateSelf,
    AlternateSelf,
    AppearanceChangeLog,
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    ConcealmentLevel,
    DisguiseKind,
    FormCombatProfile,
    FormTrait,
    FormTraitOption,
    FormType,
    HeightBand,
    PersonaTraitDescriptor,
    SpeciesFormTrait,
    TemporaryFormChange,
)
from world.forms.services.transformation import SCALE
from world.forms.types import PresentedTrait
from world.magic.models import CharacterTechnique
from world.mechanics.models import CharacterModifier, ModifierSource
from world.species.models import Species

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona


class NonCosmeticTraitError(ValueError):
    """Raised when a player tries to cosmetically self-edit a fixed trait.

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so the edit
    endpoint can surface a safe string without leaking internals.
    """

    user_message = "That feature can't be changed cosmetically."


class TraitNotBlendableError(ValueError):
    """Raised when a blend is attempted on a trait with no composite option (#2632)."""

    user_message = "Those can't be blended together."


class StyleNotKnownError(ValueError):
    """Raised when the acting character doesn't know an exotic option (#2632)."""

    user_message = "You don't know how to produce that look."


class RevertBlockedError(ValueError):
    """Raised when a character tries to revert an alternate self while not in
    control (rage/possession/charm/mind-control — any ``alters_behavior``
    condition is active). Carries a fixed ``user_message`` so the action/view
    can surface a safe string without leaking internals.
    """

    user_message = "You can't revert while not in control of yourself."


class AlternateSelfActiveError(ValueError):
    """Raised when assuming an alternate self while a *different* one is already
    active. Assumption over an active alt-self would orphan the active one's
    stat-suite (ModifierSource/CharacterModifier) and ability-suite
    (source-tagged CharacterTechnique) grants with no revert path to clean them.
    Revert the active alt-self first. Carries a fixed ``user_message`` so the
    action/view can surface a safe string without leaking internals.
    """

    user_message = "You are already wearing another alternate self. Revert first."


class FormOwnershipError(ValueError):
    """Raised when switching a character to a ``CharacterForm`` that doesn't
    belong to them (a cross-sheet ``AlternateSelf.form`` FK — bad seed/admin
    edit; the ``form`` FK has no cross-sheet DB guard). Carries a fixed
    ``user_message`` so the action/view can surface a safe string without
    leaking internals, instead of propagating an uncaught ``ValueError`` to a
    500. Mirrors ``ActivePersonaError`` on the persona facet.
    """

    user_message = "That isn't one of this character's forms."


_NO_ACTIVE_ALT_SELF_MSG = "No active alternate self to revert"


def get_apparent_form(character) -> dict[FormTrait, FormTraitOption]:
    """
    Get the apparent form for a character, combining active form with temporaries.

    Returns a dict mapping FormTrait to FormTraitOption for display.
    """
    # Get active form values
    try:
        form_state = character.form_state
        active_form = form_state.active_form
    except CharacterFormState.DoesNotExist:
        return {}

    if not active_form:
        return {}

    # Build base values from active form
    base_values: dict[FormTrait, FormTraitOption] = {
        value.trait: value.option for value in active_form.values.select_related("trait", "option")
    }

    # Overlay active temporary changes (filter on active() first, then by character)
    temp_changes = TemporaryFormChange.objects.active().filter(character=character)
    for change in temp_changes.select_related("trait", "option"):
        base_values[change.trait] = change.option

    return base_values


def switch_form(character, target_form: CharacterForm) -> None:
    """
    Switch a character to a different form.

    Args:
        character: The character to switch
        target_form: The form to switch to

    Raises:
        FormOwnershipError: If the form doesn't belong to this character
            (a cross-sheet ``AlternateSelf.form`` FK — surfaced with a safe
            ``user_message`` rather than a bare ``ValueError``).
    """
    if target_form.character_id != character.id:
        raise FormOwnershipError

    form_state, _ = CharacterFormState.objects.get_or_create(character=character)
    form_state.active_form = target_form
    form_state.save()


def revert_to_true_form(character) -> None:
    """
    Revert a character to their true form.

    Raises:
        CharacterForm.DoesNotExist: If no true form exists
    """
    true_form = CharacterForm.objects.get(character=character, form_type=FormType.TRUE)
    switch_form(character, true_form)


def _grant_stat_suite(
    sheet: CharacterSheet,
    profile: FormCombatProfile,
    source: ModifierSource,
    multiplier: float,
) -> None:
    """Write one ``CharacterModifier`` per profile effect, scaled by ``multiplier``.

    The neutral multiplier (``isclose(multiplier, 1.0)``) is the identity case:
    the granted value equals ``effect.value`` exactly, preserving prior grants.
    Float equality is avoided via ``math.isclose`` (SonarCloud S1244); any other
    multiplier scales ``effect.value`` and divides by ``SCALE``.
    """
    for effect in profile.effects.all():
        if math.isclose(multiplier, 1.0):
            granted_value = effect.value
        else:
            granted_value = round(effect.value * multiplier / SCALE)
        CharacterModifier.objects.create(
            character=sheet,
            target=effect.target,
            value=granted_value,
            source=source,
        )


def _create_assumption_grants(
    sheet: CharacterSheet, alt: AlternateSelf, instance_value: float = 1.0
) -> ModifierSource | None:
    """Create the stat-suite and ability-suite grants for an assumed alt-self.

    One ``ModifierSource`` owns both the ``CharacterModifier`` rows (CASCADE)
    and any granted ``CharacterTechnique`` rows. A persona-only/form-only
    alt-self has no granted rows, so no source is created (and revert deletes
    none). Permanently-known techniques (existing rows with ``source=None``)
    are left untouched by the stacking guard.

    Stat values are scaled by ``alt.tuning_value`` (the per-character template
    factor) and ``instance_value`` (the per-assumption multiplier), then
    divided by ``SCALE``. The neutral case is identity: when the combined
    multiplier is ``1.0`` (no scaling requested), the granted value equals
    ``effect.value`` exactly, preserving existing grants.

    Formula::

        multiplier = (alt.tuning_value or 1) * instance_value
        value = effect.value if isclose(multiplier, 1.0)
                else round(effect.value * multiplier / SCALE)

    Returns the created ``ModifierSource``, or ``None`` when nothing was
    granted (persona-only alt-self, or a techniques-only alt-self whose
    techniques were all permanently known) — so no empty source leaks for
    revert to miss.
    """
    profile = alt.combat_profile
    has_techniques = alt.techniques.exists()
    if profile is None and not has_techniques:
        return None

    source = ModifierSource.objects.create(form_combat_profile=profile)
    granted_any = profile is not None

    # Stat-suite. ``_grant_stat_suite`` writes one ``CharacterModifier`` per
    # profile effect, scaled by the combined multiplier (identity when neutral).
    if profile is not None:
        multiplier = (alt.tuning_value or 1) * instance_value
        _grant_stat_suite(sheet, profile, source, multiplier)

    # Ability-suite with stacking guard. ``get_or_create`` returns
    # ``created=False`` for a permanently-known technique (existing row with
    # ``source=None``); only a freshly-granted row points at this source. If
    # every technique was already known and there's no profile, the source is
    # empty and revert (which finds sources via ``granted_techniques``) would
    # never reclaim it — drop it now so no empty source leaks.
    if has_techniques:
        for technique in alt.techniques.all():
            _ct, created = CharacterTechnique.objects.get_or_create(
                character=sheet,
                technique=technique,
                defaults={"source": source},
            )
            if created:
                granted_any = True

    if not granted_any:
        source.delete()
        return None
    return source


@transaction.atomic
def assume_alternate_self(
    sheet: CharacterSheet, alt: AlternateSelf, instance_value: float = 1.0
) -> ActiveAlternateSelf:
    """Assume an alternate self — swap in form/persona facets, create the
    stat-suite (ModifierSource + CharacterModifier rows) and ability-suite
    (source-tagged CharacterTechnique rows), set return anchors.

    NOT gated by ``in_control`` — you can assume (or be forced into) an
    alternate self while not in control. Idempotent on re-assume of the same
    alt-self (no-op; preserves existing return anchors). Raises
    ``AlternateSelfActiveError`` if a *different* alt-self is already active
    — revert it first (strictly-one-active, so grants never orphan).

    Source granularity: exactly one ``ModifierSource`` is created per
    assumption (using ``form_combat_profile=alt.combat_profile``). It owns both
    the stat ``CharacterModifier`` rows (CASCADE on source deletion) and any
    granted ``CharacterTechnique`` rows (tagged with the same source). A
    technique the character already permanently knows (existing
    ``CharacterTechnique`` row with ``source=None``) is left untouched by the
    stacking guard.

    Args:
        sheet: the character (CharacterSheet — the service convention).
        alt: the AlternateSelf grant to assume (caller already validated the
            repertoire gate).
        instance_value: per-assumption multiplier for the granted stat-suite
            (default 1.0 = no scaling).

    Returns the ActiveAlternateSelf row.
    """
    from world.scenes.services import set_active_persona  # noqa: PLC0415

    active, _ = ActiveAlternateSelf.objects.get_or_create(character=sheet)

    # Idempotent: re-assuming the same alt-self is a no-op.
    if active.alternate_self_id == alt.pk:
        return active

    # A *different* alt-self is already active. Assumption here would overwrite
    # ``active.alternate_self`` and the return anchors and create the new
    # alt-self's grants — but never clean the active one's ModifierSource /
    # CharacterModifier / source-tagged CharacterTechnique rows, orphaning them
    # with no revert path (reverting the new one later finds no active alt-self
    # to clean the prior one). Enforce strictly-one-active: revert first.
    if active.alternate_self_id is not None:
        raise AlternateSelfActiveError

    # Capture current return anchors (active form / active persona) before
    # overwriting them. If there's no active form state, default to true form.
    try:
        form_state = sheet.character.form_state
        current_form = form_state.active_form
    except CharacterFormState.DoesNotExist:
        current_form = None

    if current_form is not None:
        active.return_form = current_form
    else:
        # Try to set return anchor to true form if an active form state is absent.
        true_form = CharacterForm.objects.filter(
            character=sheet.character, form_type=FormType.TRUE
        ).first()
        active.return_form = true_form

    active.return_persona = sheet.active_persona

    # Form facet.
    if alt.form is not None:
        switch_form(sheet.character, alt.form)

    # Persona facet.
    if alt.persona is not None:
        set_active_persona(sheet, alt.persona)

    source = _create_assumption_grants(sheet, alt, instance_value=instance_value)
    # ``_create_assumption_grants`` may have written/updated ``CharacterTechnique``
    # rows (the ability-suite). Invalidate the character's technique-handler cache
    # per its mutation contract (``world/magic/handlers.py``: services that grant or
    # revoke a ``CharacterTechnique`` call ``handler.invalidate()`` afterwards) so
    # the weave picker / clash-opposition matcher see the granted techniques this
    # session. The cast gate itself reads the DB fresh, so cast availability is
    # unaffected; this is for the handler-cached read paths.
    sheet.character.techniques.invalidate()

    # Collect techniques newly granted by this assumption (tagged to this source).
    # Permanently-known techniques were left untouched by the stacking guard, so
    # they do not appear in CharacterTechnique rows under this source.
    if source is not None:
        granted_techniques = [
            ct.technique
            for ct in CharacterTechnique.objects.filter(source=source).select_related("technique")
        ]
    else:
        granted_techniques = []
    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.achievements.discovery import announce_access_change  # noqa: PLC0415

    announce_access_change(
        sheet,
        gained=granted_techniques,
        lost=[],
        source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
    )

    active.alternate_self = alt
    active.save(update_fields=["alternate_self", "return_form", "return_persona"])
    return active


@transaction.atomic
def revert_alternate_self(sheet: CharacterSheet) -> None:
    """Revert the active alternate self — restore return anchors, delete the
    granted stat-suite and ability-suite rows.

    Blocked while ``not sheet.in_control`` (rage/possession/charm) — raises
    ``RevertBlockedError``. Only revert is blocked; assumption stays allowed.
    Removing an alters_behavior condition does NOT call this — it re-derives
    ``in_control=True`` and unblocks a later self-revert.

    Raises:
        ValueError: if no active alternate self exists for this sheet.
        RevertBlockedError: if the character is not in control.
    """
    from world.scenes.services import set_active_persona  # noqa: PLC0415

    try:
        active = ActiveAlternateSelf.objects.select_related("return_form").get(character=sheet)
    except ActiveAlternateSelf.DoesNotExist as exc:
        raise ValueError(_NO_ACTIVE_ALT_SELF_MSG) from exc

    if active.alternate_self_id is None:
        raise ValueError(_NO_ACTIVE_ALT_SELF_MSG)

    # ``in_control`` is a plain property reading the character's
    # ``CharacterConditionHandler`` cache (invalidated by every condition
    # mutation service), so it always reflects current condition state — no
    # manual cache-pop needed here. A caller holding the sheet across a
    # condition change (rage clears → revert unblocks, the decoupled flow) reads
    # the fresh value on the next access.
    if not sheet.in_control:
        raise RevertBlockedError

    # Restore form facet.
    if active.return_form is not None:
        switch_form(sheet.character, active.return_form)
    else:
        revert_to_true_form(sheet.character)

    # Restore persona facet. Symmetric with the form facet's ``else`` above:
    # ``return_persona`` is NULL when the character was on their implicit PRIMARY
    # (NULL ⇒ primary via ``active_persona_for_sheet``) at assume time — restore
    # explicitly to the PRIMARY persona row rather than leaving the assumed alt
    # persona stuck on. ``set_active_persona`` validates ownership, so this stays
    # within the character's own faces. (Previously this branch was skipped when
    # ``return_persona`` was NULL, so reverting an alt-self assumed from the
    # implicit-primary state left ``active_persona`` stuck on the alt persona.)
    if active.return_persona is not None:
        set_active_persona(sheet, active.return_persona)
    else:
        set_active_persona(sheet, sheet.primary_persona)

    # Delete the assumption source(s). Because CharacterTechnique.source is
    # SET_NULL, deleting the source alone would NULL out granted techniques and
    # turn temporary grants permanent; delete granted rows first. Symmetric with
    # assume: a source exists only when profile or techniques were granted.
    alt = active.alternate_self
    if alt.combat_profile is not None:
        sources = ModifierSource.objects.filter(form_combat_profile=alt.combat_profile)
    elif alt.techniques.exists():
        sources = ModifierSource.objects.filter(
            granted_techniques__character=sheet,
            granted_techniques__technique__in=alt.techniques.all(),
        ).distinct()
    else:
        sources = ModifierSource.objects.none()

    # Collect the techniques about to be reclaimed BEFORE deletion so we can
    # announce them afterwards. Only technique rows (CharacterTechnique) are
    # collected; stat rows (CharacterModifier) are dropped via CASCADE on source.
    reclaimed_techniques = [
        ct.technique
        for ct in CharacterTechnique.objects.filter(source__in=sources).select_related("technique")
    ]

    for source in sources:
        CharacterTechnique.objects.filter(source=source).delete()
        source.delete()

    # ``CharacterTechnique`` rows for the assumption's ability-suite were just
    # deleted above. Invalidate the technique-handler cache so the weave picker /
    # clash-opposition matcher drop the reclaimed techniques this session — same
    # mutation contract as the assume path. Idempotent when no rows changed.
    sheet.character.techniques.invalidate()

    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.achievements.discovery import announce_access_change  # noqa: PLC0415

    announce_access_change(
        sheet,
        gained=[],
        lost=reclaimed_techniques,
        source=AccessChangeSource.REVERTED_ALTERNATE_SELF,
    )

    # Clear the active alt-self placeholder.
    active.alternate_self = None
    active.return_form = None
    active.return_persona = None
    active.save(update_fields=["alternate_self", "return_form", "return_persona"])


def get_cg_form_options(species: Species) -> dict[FormTrait, list[FormTraitOption]]:
    """
    Get available form trait options for character creation.

    Returns traits this species has in CG with their available options.
    Options are filtered by the SpeciesFormTrait.allowed_options field -
    if empty, all options are available; if set, only those options show.
    """
    result: dict[FormTrait, list[FormTraitOption]] = {}

    # Get traits available for this species in CG
    species_traits = (
        SpeciesFormTrait.objects.filter(species=species, is_available_in_cg=True)
        .select_related("trait")
        .prefetch_related(
            Prefetch(
                "allowed_options",
                queryset=FormTraitOption.objects.order_by("sort_order", "display_name"),
                to_attr="cached_allowed_options",
            ),
            Prefetch(
                "trait__options",
                queryset=FormTraitOption.objects.order_by("sort_order", "display_name"),
                to_attr="cached_options",
            ),
        )
    )

    for species_trait in species_traits:
        trait = species_trait.trait
        # Use the model method to get species-specific options
        options = list(species_trait.get_available_options())
        result[trait] = options

    return result


def create_true_form(character, selections: dict[FormTrait, FormTraitOption]) -> CharacterForm:
    """
    Create the true form for a character during character creation.

    Args:
        character: The character to create the form for
        selections: Dict mapping traits to selected options

    Returns:
        The created CharacterForm

    Raises:
        ValueError: If a true form already exists for this character
    """
    if CharacterForm.objects.filter(character=character, form_type=FormType.TRUE).exists():
        msg = "Character already has a true form"
        raise ValueError(msg)

    # Create the form
    form = CharacterForm.objects.create(
        character=character,
        form_type=FormType.TRUE,
        is_player_created=False,
    )

    # Create form values; the initial value is also the natural baseline.
    for trait, option in selections.items():
        CharacterFormValue.objects.create(
            form=form, trait=trait, option=option, natural_option=option
        )

    # Create/update form state
    CharacterFormState.objects.update_or_create(character=character, defaults={"active_form": form})

    return form


# --- Appearance editing & presentation (slice 1) ---


def _true_form(character) -> CharacterForm:
    """The character's real/true form. Raises if character creation never ran."""
    return CharacterForm.objects.get(character=character, form_type=FormType.TRUE)


def _blend_component(
    value: CharacterFormValue, trait: FormTrait, new_option: FormTraitOption
) -> None:
    """Fold ``new_option`` into ``value`` as a blend component (#2632).

    First blend seeds the current option as the base component, then appends
    the new color; the value itself moves to the trait's composite option.
    Blending a color already in the mix is a no-op on components.
    """
    from world.forms.models import FormValueComponent  # noqa: PLC0415

    if value.option_id == new_option.id and not value.components.exists():
        return  # blending a color onto itself: nothing to mix
    if not value.components.exists():
        # Seed the base: what the hair/eyes were before this blend.
        FormValueComponent.objects.create(value=value, option=value.option, sort_order=0)
    if not value.components.filter(option=new_option).exists():
        next_order = value.components.count()
        FormValueComponent.objects.create(value=value, option=new_option, sort_order=next_order)
    if value.option_id != trait.composite_option_id:
        value.option = trait.composite_option
        value.save(update_fields=["option"])


def change_appearance(  # noqa: PLR0913
    character,
    trait: FormTrait,
    new_option: FormTraitOption,
    *,
    persona: Persona,
    descriptor: str | None = None,
    note: str = "",
    actor_persona: Persona | None = None,
    blend: bool = False,
) -> CharacterFormValue:
    """Cosmetically edit one trait of the character's real form (hair dye, restyle).

    A real, in-place change — not a disguise. Only ``is_cosmetic`` traits are editable;
    the natural baseline is preserved, the active persona's descriptor is updated, and
    the change is logged for roster continuity. ``descriptor=None`` leaves the descriptor
    untouched; ``descriptor=""`` clears it (render falls back to the normalized value).

    ``blend=True`` (#2632) ADDS ``new_option`` to the current look instead of
    replacing it: the value moves to the trait's ``composite_option`` (multihued
    hair, mismatched eyes) and the ACTUAL components are kept as ordered
    ``FormValueComponent`` rows — so the normalized layer renders "red-green"
    (honest under descriptor concealment) rather than the umbrella word alone.
    A non-blend change clears any components (you dyed over the whole look).
    Raises ``TraitNotBlendableError`` when the trait has no composite option.
    """
    if not trait.is_cosmetic:
        raise NonCosmeticTraitError
    if new_option.trait_id != trait.id:
        msg = "Option does not belong to this trait"
        raise ValueError(msg)
    if blend and trait.composite_option_id is None:
        raise TraitNotBlendableError

    form = _true_form(character)
    value, created = CharacterFormValue.objects.get_or_create(
        form=form,
        trait=trait,
        defaults={"option": new_option, "natural_option": new_option},
    )
    if blend and not created:
        from_option = value.option
        _blend_component(value, trait, new_option)
    elif created:
        from_option = None
        if blend:
            # Blending onto a bare value: nothing to mix with — the "blend" is
            # just the color itself; components stay empty.
            pass
    else:
        from_option = value.option
        if value.option_id != new_option.id:
            value.option = new_option
            value.save(update_fields=["option"])
        # Full application replaces the whole look — stale components go.
        value.components.all().delete()

    existing = PersonaTraitDescriptor.objects.filter(persona=persona, trait=trait).first()
    from_text = existing.text if existing else ""
    to_text = from_text
    if descriptor is not None:
        cleaned = descriptor.strip()
        if cleaned:
            PersonaTraitDescriptor.objects.update_or_create(
                persona=persona, trait=trait, defaults={"text": cleaned}
            )
            to_text = cleaned
        else:
            PersonaTraitDescriptor.objects.filter(persona=persona, trait=trait).delete()
            to_text = ""

    AppearanceChangeLog.objects.create(
        form=form,
        persona=persona,
        trait=trait,
        from_option=from_option,
        to_option=new_option,
        from_text=from_text,
        to_text=to_text,
        actor_persona=actor_persona or persona,
        note=note,
    )
    return value


def reset_trait_to_natural(
    character,
    trait: FormTrait,
    *,
    persona: Persona,
    actor_persona: Persona | None = None,
    note: str = "",
) -> CharacterFormValue:
    """Restore one trait to its natural (origin) value — "wash out the dye."""
    form = _true_form(character)
    value = CharacterFormValue.objects.get(form=form, trait=trait)
    if value.natural_option_id is None or value.option_id == value.natural_option_id:
        return value
    from_option = value.option
    value.option = value.natural_option
    value.save(update_fields=["option"])
    AppearanceChangeLog.objects.create(
        form=form,
        persona=persona,
        trait=trait,
        from_option=from_option,
        to_option=value.natural_option,
        from_text="",
        to_text="",
        actor_persona=actor_persona or persona,
        note=note or "reset to natural",
    )
    return value


class NotADisguiseError(ValueError):
    """Raised when a form offered as a disguise overlay isn't a DISGUISE form (#1110).

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``).
    """

    user_message = "That isn't a disguise you can put on."


def apply_disguise(
    character,
    disguise_form: CharacterForm,
    *,
    kind: DisguiseKind = DisguiseKind.MUNDANE,
    concealment_level: ConcealmentLevel = ConcealmentLevel.NONE,
    kit_instance=None,
) -> CharacterFormState:
    """Paint a fake overlay over the character's real form (#1110).

    The real form is preserved beneath; presentation swaps in the overlay's traits for viewers
    who haven't pierced it (the pierce *contest* is the senior dev's domain). ``kind`` records how
    it's pierced (mundane → perception, magical → dispel). ``concealment_level`` controls what an
    unpierced viewer sees (#1272): NONE = full trait + descriptor, DESCRIPTOR = value only,
    FULL = nothing. Single-slot: applying a new overlay replaces any current one. The disguise
    form must belong to ``character`` and be a DISGUISE.

    ``kit_instance`` (optional, #2249) stamps the ``ItemInstance`` whose use applied this overlay
    onto ``CharacterFormState.applied_kit_instance``, so ``identification_difficulty`` can read its
    ``QualityTier.stat_multiplier`` for the kit-quality bonus term. None when the overlay is
    narratively applied (no kit involved).
    """
    if disguise_form.character_id != character.id:
        msg = "Cannot wear a disguise belonging to another character"
        raise ValueError(msg)
    if disguise_form.form_type != FormType.DISGUISE:
        raise NotADisguiseError

    disguise_form.concealment_level = concealment_level
    disguise_form.save(update_fields=["concealment_level"])
    form_state, _ = CharacterFormState.objects.get_or_create(character=character)
    form_state.active_fake_overlay = disguise_form
    form_state.overlay_kind = kind
    form_state.applied_kit_instance = kit_instance
    form_state.save(update_fields=["active_fake_overlay", "overlay_kind", "applied_kit_instance"])
    return form_state


def remove_disguise(character) -> None:
    """Drop the active fake overlay — the real form presents again (#1110). Idempotent."""
    try:
        form_state = character.form_state
    except CharacterFormState.DoesNotExist:
        return
    if form_state.active_fake_overlay_id is None and not form_state.overlay_kind:
        return
    form_state.active_fake_overlay = None
    form_state.overlay_kind = ""
    form_state.applied_kit_instance = None
    form_state.save(update_fields=["active_fake_overlay", "overlay_kind", "applied_kit_instance"])


def _form_to_present(character, *, pierced: bool) -> CharacterForm | None:
    """The form a viewer actually sees (#1110).

    An active fake overlay is shown until the viewer pierces it (or it's the owner/staff
    ground-truth read, ``pierced=True``); otherwise the real form. Falls back to the true form
    when no explicit real-form slot is set.
    """
    form_state = character.form_state_or_none
    if form_state is not None and not pierced and form_state.active_fake_overlay_id is not None:
        return form_state.active_fake_overlay
    try:
        return _true_form(character)
    except CharacterForm.DoesNotExist:
        return None


def get_presented_appearance(character, *, pierced: bool = False) -> list[PresentedTrait]:
    """Compose what a viewer sees: the presented form's normalized traits overlaid with the
    active persona's descriptors. The single source for telnet and web (replacing the legacy
    Characteristic read and the TRUE-form-only web read).

    When the character wears a **fake overlay** (#1110) and the viewer hasn't ``pierced`` it, the
    overlay's traits are presented over the preserved real form. The owner/staff ground-truth read
    passes ``pierced=True`` to ignore overlays. The pierce *contest* (perception/dispel) lives in
    the senior dev's domain; this read just takes its outcome.

    The overlay's ``concealment_level`` (#1272) controls what an unpierced viewer sees:
    - ``NONE``: full trait + descriptor (the existing behavior).
    - ``DESCRIPTOR``: normalized value visible, player-authored descriptor hidden.
    - ``FULL``: traits hidden entirely — an empty list is returned.
    """
    # Lazy imports avoid a forms<->scenes import cycle at module load.
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    form = _form_to_present(character, pierced=pierced)
    if form is None:
        return []

    # Full concealment: an unpierced viewer sees nothing (#1272).
    form_state = character.form_state_or_none
    if (
        not pierced
        and form_state is not None
        and form_state.active_fake_overlay_id is not None
        and form_state.active_fake_overlay.concealment_level == ConcealmentLevel.FULL
    ):
        return []

    # Descriptor concealment: blank the descriptor so only the normalized value shows (#1272).
    hide_descriptors = (
        not pierced
        and form_state is not None
        and form_state.active_fake_overlay_id is not None
        and form_state.active_fake_overlay.concealment_level == ConcealmentLevel.DESCRIPTOR
    )

    descriptors: dict[int, str] = {}
    sheet = character.character_sheet
    if sheet is not None and not hide_descriptors:
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            persona = None
        if persona is not None:
            descriptors = {
                row.trait_id: row.text
                for row in PersonaTraitDescriptor.objects.filter(persona=persona)
            }

    # Blend components (#2632): one query, keyed by value pk — deliberately NOT
    # a prefetch onto the identity-mapped CharacterFormValue instances. A
    # blended value renders its ACTUAL components ("Red-Green") as the
    # normalized form, so descriptor concealment still tells the honest,
    # witness-visible truth without the distinctive prose.
    from world.forms.models import FormValueComponent  # noqa: PLC0415

    components_by_value: dict[int, list[str]] = {}
    for comp in (
        FormValueComponent.objects.filter(value__form=form)
        .select_related("option")
        .order_by("value_id", "sort_order")
    ):
        components_by_value.setdefault(comp.value_id, []).append(comp.option.display_name)

    presented: list[PresentedTrait] = []
    for value in form.values.select_related("trait", "option").order_by("trait__sort_order"):
        text = descriptors.get(value.trait_id, "")
        component_names = components_by_value.get(value.pk)
        normalized = "-".join(component_names) if component_names else value.option.display_name
        presented.append(
            PresentedTrait(
                trait_name=value.trait.name,
                trait_display=value.trait.display_name,
                normalized=normalized,
                descriptor=text,
                display=text or normalized,
            )
        )
    return presented


# --- Height/Build Service Functions ---


def get_height_band(height_inches: int) -> HeightBand | None:
    """
    Get the HeightBand for a given height in inches.

    Returns None if no band matches the height.
    """
    return HeightBand.objects.filter(
        min_inches__lte=height_inches,
        max_inches__gte=height_inches,
    ).first()


def calculate_weight(height_inches: int, build: Build) -> int:
    """
    Calculate weight in pounds from height and build.

    Weight = height_inches × build.weight_factor, clamped by band bounds.
    """
    raw_weight = int(height_inches * build.weight_factor)

    # Get the height band to check for weight bounds
    band = get_height_band(height_inches)
    if band:
        if band.weight_max is not None:
            raw_weight = min(raw_weight, band.weight_max)
        if band.weight_min is not None:
            raw_weight = max(raw_weight, band.weight_min)

    return raw_weight


def get_apparent_height(character) -> tuple[int, HeightBand | None]:
    """
    Get the apparent height for a character including trait modifiers.

    Returns (apparent_height_inches, height_band).
    """
    # Get base height from character sheet
    try:
        base_height = character.sheet_data.true_height_inches
    except AttributeError:
        return (0, None)

    if base_height is None:
        return (0, None)

    # Sum height modifiers from active form traits
    modifier_total = 0
    apparent_form = get_apparent_form(character)
    for option in apparent_form.values():
        if option.height_modifier_inches:
            modifier_total += option.height_modifier_inches

    apparent_height = base_height + modifier_total
    band = get_height_band(apparent_height)

    return (apparent_height, band)


def get_apparent_build(character) -> Build | None:
    """
    Get the apparent build for a character.

    Returns None if no build set or if height band hides build.
    """
    try:
        build = character.sheet_data.build
    except AttributeError:
        return None

    if build is None:
        return None

    # Check if height band hides build
    _apparent_height, band = get_apparent_height(character)
    if band and band.hide_build:
        return None

    return build


def get_cg_height_bands() -> QuerySet[HeightBand]:
    """Get height bands available in character creation."""
    return HeightBand.objects.filter(is_cg_selectable=True)


def get_cg_builds() -> QuerySet[Build]:
    """Get builds available in character creation."""
    return Build.objects.filter(is_cg_selectable=True)


# --- Exotic style knowledge (#2632) ---


def knows_style(character_sheet, option: FormTraitOption) -> bool:
    """True when the sheet may produce ``option`` (ungated options always may)."""
    from world.forms.models import CharacterKnownStyle  # noqa: PLC0415

    if not option.requires_teaching:
        return True
    return CharacterKnownStyle.objects.filter(
        character_sheet=character_sheet, option=option
    ).exists()


def learn_style(character_sheet, option: FormTraitOption, *, taught_by_label: str = "") -> None:
    """Grant knowledge of an exotic option — 'learned by having it done' (#2632).

    Idempotent. Ungated options are a no-op (nothing to learn).
    """
    from world.forms.models import CharacterKnownStyle  # noqa: PLC0415

    if not option.requires_teaching:
        return
    CharacterKnownStyle.objects.get_or_create(
        character_sheet=character_sheet,
        option=option,
        defaults={"taught_by_label": taught_by_label},
    )
