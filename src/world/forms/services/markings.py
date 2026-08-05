"""Body markings (#2985): grant, removal, visibility, and reveal/cover state.

Markings are features of a specific body (``FormMarking.form`` → ``CharacterForm``),
so the render composition holds: a shapeshifted or disguised body presents ITS
form's markings, never the real form's. Visibility rides the shared skin-coverage
predicate (``world.items.services.appearance.covered_regions``): a marking shows
iff its region is uncovered, or it was deliberately revealed.

``grant_marking`` is the single write seam — CG finalization, staff grants, and
the future combat/soulfray scar writers (TehomCD's domain) all land through it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from core_management.permissions import is_staff_observer
from world.forms.constants import MarkingKind, MarkingSource
from world.forms.models import CharacterForm, CharacterFormState, FormMarking, FormType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def ensure_true_form(sheet: CharacterSheet) -> CharacterForm:
    """Return the sheet's TRUE form, creating a bare one (and its form state) if absent.

    A finalized character legally has no form when their species declares no
    required ``SpeciesFormTrait`` rows (``_create_true_form`` early-returns), so
    marking writers must not assume one exists.
    """
    form, created = CharacterForm.objects.get_or_create(character=sheet, form_type=FormType.TRUE)
    if created:
        CharacterFormState.objects.get_or_create(character=sheet, defaults={"active_form": form})
    return form


def grant_marking(  # noqa: PLR0913 — the seam mirrors FormMarking's columns; a params object would just rename them
    sheet: CharacterSheet,
    *,
    body_region: str,
    kind: str,
    name: str,
    description: str = "",
    source: str = MarkingSource.GM_GRANT,
    revealed: bool = False,
) -> FormMarking:
    """Create a marking on ``sheet``'s TRUE form — the single write seam (#2985)."""
    form = ensure_true_form(sheet)
    return FormMarking.objects.create(
        form=form,
        body_region=body_region,
        kind=MarkingKind(kind),
        name=name,
        description=description,
        source=MarkingSource(source),
        revealed_at=timezone.now() if revealed else None,
    )


def remove_marking(marking: FormMarking) -> None:
    """Delete a marking (admin-only surface in MVP — magical removal later)."""
    marking.delete()


def visible_markings_for(
    character: ObjectDB,
    observer: object | None = None,
) -> list[FormMarking]:
    """Markings of ``character`` visible to ``observer`` (#2985).

    Resolves the *presented* form first (``_form_to_present``): an unpierced
    fake overlay presents the overlay form's markings — identifying marks are
    exactly what a disguise exists to hide. MVP "unpierced" is every observer
    except self/staff, mirroring ``visible_worn_items_for``'s bypass contract;
    per-viewer ``PersonaDiscovery`` piercing is out of scope.

    Missing form state or form ⇒ ``[]``, never a raise.
    """
    from world.forms.services import _form_to_present  # noqa: PLC0415
    from world.items.services.appearance import covered_regions  # noqa: PLC0415

    bypass = observer is character or is_staff_observer(observer)
    form = _form_to_present(character, pierced=bypass)
    if form is None:
        return []
    markings = list(form.markings.all())
    if not markings or bypass:
        return markings
    covered = covered_regions(character)
    return [m for m in markings if m.body_region not in covered or m.revealed_at is not None]


def marking_is_concealed(character: ObjectDB, marking: FormMarking) -> bool:
    """Whether ``marking`` is currently hidden by clothing (ignoring reveal state)."""
    from world.items.services.appearance import covered_regions  # noqa: PLC0415

    return marking.body_region in covered_regions(character)


def reveal_marking(marking: FormMarking) -> None:
    """Bare a concealed marking — it counts as visible until covered again."""
    marking.revealed_at = timezone.now()
    marking.save(update_fields=["revealed_at"])


def cover_marking(marking: FormMarking) -> None:
    """Tuck a revealed marking back under its clothing (the Cover verb)."""
    marking.revealed_at = None
    marking.save(update_fields=["revealed_at"])


def clear_revealed_markings(sheet: CharacterSheet, regions: set[str]) -> None:
    """Equip hook (#2985): covering skin re-conceals it.

    Called when a non-revealing garment lands on ``regions`` — any revealed
    TRUE-form marking there loses its reveal state (per-row saves so cached
    idmapper instances stay coherent; N is tiny).
    """
    rows = FormMarking.objects.filter(
        form__character=sheet,
        form__form_type=FormType.TRUE,
        body_region__in=regions,
        revealed_at__isnull=False,
    )
    for marking in rows:
        marking.revealed_at = None
        marking.save(update_fields=["revealed_at"])
