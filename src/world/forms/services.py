from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet

from world.forms.models import (
    AppearanceChangeLog,
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    DisguiseKind,
    FormTrait,
    FormTraitOption,
    FormType,
    HeightBand,
    PersonaTraitDescriptor,
    SpeciesFormTrait,
    TemporaryFormChange,
)
from world.forms.types import PresentedTrait
from world.species.models import Species

if TYPE_CHECKING:
    from world.scenes.models import Persona


class NonCosmeticTraitError(ValueError):
    """Raised when a player tries to cosmetically self-edit a fixed trait.

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so the edit
    endpoint can surface a safe string without leaking internals.
    """

    user_message = "That feature can't be changed cosmetically."


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
) -> CharacterFormState:
    """Paint a fake overlay over the character's real form (#1110).

    The real form is preserved beneath; presentation swaps in the overlay's traits for viewers
    who haven't pierced it (the pierce *contest* is the senior dev's domain). ``kind`` records how
    it's pierced (mundane → perception, magical → dispel). Single-slot: applying a new overlay
    replaces any current one. The disguise form must belong to ``character`` and be a DISGUISE.
    """
    if disguise_form.character_id != character.id:
        msg = "Cannot wear a disguise belonging to another character"
        raise ValueError(msg)
    if disguise_form.form_type != FormType.DISGUISE:
        raise NotADisguiseError

    form_state, _ = CharacterFormState.objects.get_or_create(character=character)
    form_state.active_fake_overlay = disguise_form
    form_state.overlay_kind = kind
    form_state.save(update_fields=["active_fake_overlay", "overlay_kind"])
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
    form_state.save(update_fields=["active_fake_overlay", "overlay_kind"])


def _form_to_present(character, *, pierced: bool) -> CharacterForm | None:
    """The form a viewer actually sees (#1110).

    An active fake overlay is shown until the viewer pierces it (or it's the owner/staff
    ground-truth read, ``pierced=True``); otherwise the real form. Falls back to the true form
    when no explicit real-form slot is set.
    """
    form_state = getattr(character, "form_state", None)  # noqa: GETATTR_LITERAL
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
    """
    # Lazy imports avoid a forms<->scenes import cycle at module load.
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    form = _form_to_present(character, pierced=pierced)
    if form is None:
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
