from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    FormType,
    SpeciesFormTrait,
    SpeciesOriginTraitOption,
    TemporaryFormChange,
)
from world.species.models import Species, SpeciesOrigin


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


def get_cg_form_options(
    species: Species, origin: SpeciesOrigin
) -> dict[FormTrait, list[FormTraitOption]]:
    """
    Get available form trait options for character creation.

    Returns traits this species has in CG, with options filtered by origin overrides.
    """
    result: dict[FormTrait, list[FormTraitOption]] = {}

    # Get traits available for this species in CG
    species_traits = SpeciesFormTrait.objects.filter(
        species=species, is_available_in_cg=True
    ).select_related("trait")

    for species_trait in species_traits:
        trait = species_trait.trait

        # Start with all options for this trait
        all_options = set(trait.options.all())

        # Apply origin overrides
        overrides = SpeciesOriginTraitOption.objects.filter(
            species_origin=origin, trait=trait
        ).select_related("option")

        for override in overrides:
            if override.is_available:
                all_options.add(override.option)
            else:
                all_options.discard(override.option)

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
