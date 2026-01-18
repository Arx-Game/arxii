from django.db.models import QuerySet

from world.forms.models import (
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    FormType,
    HeightBand,
    SpeciesFormTrait,
    TemporaryFormChange,
)
from world.species.models import Species


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

    Returns traits this species has in CG with all available options.
    """
    result: dict[FormTrait, list[FormTraitOption]] = {}

    # Get traits available for this species in CG
    species_traits = SpeciesFormTrait.objects.filter(
        species=species, is_available_in_cg=True
    ).select_related("trait")

    for species_trait in species_traits:
        trait = species_trait.trait

        # Get all options for this trait
        all_options = list(trait.options.all())

        result[trait] = sorted(all_options, key=lambda o: (o.sort_order, o.display_name))

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

    # Create form values
    for trait, option in selections.items():
        CharacterFormValue.objects.create(form=form, trait=trait, option=option)

    # Create/update form state
    CharacterFormState.objects.update_or_create(character=character, defaults={"active_form": form})

    return form


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
