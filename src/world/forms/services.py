from __future__ import annotations

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
    FormTrait,
    FormTraitOption,
    FormType,
    HeightBand,
    PersonaTraitDescriptor,
    SpeciesFormTrait,
    TemporaryFormChange,
)
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


class RevertBlockedError(ValueError):
    """Raised when a character tries to revert an alternate self while not in
    control (rage/possession/charm/mind-control — any ``alters_behavior``
    condition is active). Carries a fixed ``user_message`` so the action/view
    can surface a safe string without leaking internals.
    """

    user_message = "You can't revert while not in control of yourself."


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
        ValueError: If the form doesn't belong to this character
    """
    if target_form.character_id != character.id:
        msg = "Cannot switch to a form belonging to another character"
        raise ValueError(msg)

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


def _create_assumption_grants(sheet: CharacterSheet, alt: AlternateSelf) -> None:
    """Create the stat-suite and ability-suite grants for an assumed alt-self.

    One ``ModifierSource`` owns both the ``CharacterModifier`` rows (CASCADE)
    and any granted ``CharacterTechnique`` rows. A persona-only/form-only
    alt-self has no granted rows, so no source is created (and revert deletes
    none). Permanently-known techniques (existing rows with ``source=None``)
    are left untouched by the stacking guard.
    """
    profile = alt.combat_profile
    has_techniques = alt.techniques.exists()
    if profile is None and not has_techniques:
        return

    source = ModifierSource.objects.create(form_combat_profile=profile)

    # Stat-suite.
    if profile is not None:
        for effect in profile.effects.all():
            CharacterModifier.objects.create(
                character=sheet,
                target=effect.target,
                value=effect.value,
                source=source,
            )

    # Ability-suite with stacking guard.
    if has_techniques:
        for technique in alt.techniques.all():
            CharacterTechnique.objects.get_or_create(
                character=sheet,
                technique=technique,
                defaults={"source": source},
            )


@transaction.atomic
def assume_alternate_self(sheet: CharacterSheet, alt: AlternateSelf) -> ActiveAlternateSelf:
    """Assume an alternate self — swap in form/persona facets, create the
    stat-suite (ModifierSource + CharacterModifier rows) and ability-suite
    (source-tagged CharacterTechnique rows), set return anchors.

    NOT gated by ``in_control`` — you can assume (or be forced into) an
    alternate self while not in control. Idempotent on re-assume of the same
    alt-self (no-op; preserves existing return anchors).

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

    Returns the ActiveAlternateSelf row.
    """
    from world.scenes.services import set_active_persona  # noqa: PLC0415

    active, _ = ActiveAlternateSelf.objects.get_or_create(character=sheet)

    # Idempotent: re-assuming the same alt-self is a no-op.
    if active.alternate_self_id == alt.pk:
        return active

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

    _create_assumption_grants(sheet, alt)

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

    # Force a fresh derivation of in_control — it's a cached_property on the
    # sheet instance and condition mutation services invalidate only the
    # conditions handler, not this sheet-level cache. Without this, a caller
    # holding the sheet across a condition change (rage clears → revert
    # unblocks, the decoupled flow) could read a stale in_control=False and
    # stay blocked forever. Re-deriving here makes revert's gate always
    # reflect current condition state.
    sheet.__dict__.pop("in_control", None)

    if not sheet.in_control:
        raise RevertBlockedError

    # Restore form facet.
    if active.return_form is not None:
        switch_form(sheet.character, active.return_form)
    else:
        revert_to_true_form(sheet.character)

    # Restore persona facet.
    if active.return_persona is not None:
        set_active_persona(sheet, active.return_persona)

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

    for source in sources:
        CharacterTechnique.objects.filter(source=source).delete()
        source.delete()

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


def change_appearance(  # noqa: PLR0913
    character,
    trait: FormTrait,
    new_option: FormTraitOption,
    *,
    persona: Persona,
    descriptor: str | None = None,
    note: str = "",
    actor_persona: Persona | None = None,
) -> CharacterFormValue:
    """Cosmetically edit one trait of the character's real form (hair dye, restyle).

    A real, in-place change — not a disguise. Only ``is_cosmetic`` traits are editable;
    the natural baseline is preserved, the active persona's descriptor is updated, and
    the change is logged for roster continuity. ``descriptor=None`` leaves the descriptor
    untouched; ``descriptor=""`` clears it (render falls back to the normalized value).
    """
    if not trait.is_cosmetic:
        raise NonCosmeticTraitError
    if new_option.trait_id != trait.id:
        msg = "Option does not belong to this trait"
        raise ValueError(msg)

    form = _true_form(character)
    value, created = CharacterFormValue.objects.get_or_create(
        form=form,
        trait=trait,
        defaults={"option": new_option, "natural_option": new_option},
    )
    if created:
        from_option = None
    else:
        from_option = value.option
        if value.option_id != new_option.id:
            value.option = new_option
            value.save(update_fields=["option"])

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


def get_presented_appearance(character) -> list[PresentedTrait]:
    """Compose what a viewer sees: real-form normalized traits overlaid with the active
    persona's descriptors. The single source for telnet and web (replacing the legacy
    Characteristic read and the TRUE-form-only web read).

    Slice 1: the real form is the true form; per-viewer gating and disguise overlays
    arrive in later slices.
    """
    # Lazy imports avoid a forms<->scenes import cycle at module load.
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        form = _true_form(character)
    except CharacterForm.DoesNotExist:
        return []

    descriptors: dict[int, str] = {}
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is not None:
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            persona = None
        if persona is not None:
            descriptors = {
                row.trait_id: row.text
                for row in PersonaTraitDescriptor.objects.filter(persona=persona)
            }

    presented: list[PresentedTrait] = []
    for value in form.values.select_related("trait", "option").order_by("trait__sort_order"):
        text = descriptors.get(value.trait_id, "")
        normalized = value.option.display_name
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
