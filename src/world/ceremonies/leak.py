"""Twisted-rite secret leak (#2289, spec Decision 2 + 10).

When a ceremony secretly serves the officiant's hidden god, perceptive
witnesses may sense the rite's forms are subtly wrong. Eligibility routes
through the existing consent register (the ``secret-investigation`` category,
antagonism tree) — mirroring ``accusation_permitted`` — then a hidden
Perception/Investigation ("Search") roll decides; success mints a clue against
the officiant's worship Secret. Failures are silent.
"""

import logging
from typing import TYPE_CHECKING

from world.ceremonies.models import Ceremony, get_ceremony_config
from world.clues.constants import ClueTargetKind
from world.clues.models import Clue

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterTenure

logger = logging.getLogger(__name__)

SECRET_INVESTIGATION_CATEGORY_KEY = "secret-investigation"  # noqa: S105 — consent slug


def _active_tenure(sheet: "CharacterSheet") -> "RosterTenure | None":
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet=sheet, end_date__isnull=True
    ).first()


def _may_investigate(observer_sheet: "CharacterSheet", officiant_sheet: "CharacterSheet") -> bool:
    """Consent gate: may this observer investigate the officiant's secrets."""
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415

    owner_tenure = _active_tenure(officiant_sheet)
    if owner_tenure is None:
        return True  # tenure-less officiant (NPC) — no consent register to consult
    try:
        category = SocialConsentCategory.objects.get_by_natural_key(
            SECRET_INVESTIGATION_CATEGORY_KEY
        )
    except SocialConsentCategory.DoesNotExist:
        return True  # category not seeded (bare test DB) — no gate to apply
    return not consent_blocks_targeting(
        owner_tenure=owner_tenure,
        category=category,
        actor_tenure=_active_tenure(observer_sheet),
    )


def run_twisted_rite_leak(*, ceremony: Ceremony, officiant_sheet: "CharacterSheet") -> int:
    """Roll each eligible witness's Search check; mint clues on success.

    Returns the number of clues minted. No-ops when the officiant has no
    worship Secret (nothing to point at) or the rite is not twisted.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.checks.models import CheckType  # noqa: PLC0415
    from world.clues.constants import SEARCH_CHECK_TYPE_NAME  # noqa: PLC0415

    if not ceremony.is_twisted:
        return 0
    try:
        declaration = officiant_sheet.worship_declaration
    except ObjectDoesNotExist:
        return 0
    worship_secret = declaration.secret if declaration else None
    if worship_secret is None:
        return 0
    check_type = CheckType.objects.filter(name=SEARCH_CHECK_TYPE_NAME).first()
    if check_type is None:
        return 0

    config = get_ceremony_config()
    room = ceremony.location.objectdb
    minted = 0
    for obj in room.contents:
        try:
            observer_sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        if observer_sheet is None or observer_sheet.pk == officiant_sheet.pk:
            continue
        if _observer_senses_twist(
            observer=obj,
            observer_sheet=observer_sheet,
            officiant_sheet=officiant_sheet,
            check_type=check_type,
            difficulty=config.leak_detect_difficulty,
            worship_secret=worship_secret,
        ):
            minted += 1
    return minted


def _observer_senses_twist(  # noqa: PLR0913
    *, observer, observer_sheet, officiant_sheet, check_type, difficulty, worship_secret
) -> bool:
    """One witness: consent gate → hidden Search roll → clue mint on success."""
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.clues.services import acquire_clue  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    if not _may_investigate(observer_sheet, officiant_sheet):
        return False
    result = perform_check(observer, check_type, target_difficulty=difficulty)
    if result.outcome is None or result.outcome.success_level <= 0:
        return False
    entry = RosterEntry.objects.filter(character_sheet=observer_sheet).first()
    if entry is None:
        return False
    clue, _ = Clue.objects.get_or_create(
        target_kind=ClueTargetKind.SECRET,
        target_secret=worship_secret,
        defaults={
            "name": "Something off about the rite",
            "description": (
                "PLACEHOLDER — the liturgy's forms bent subtly away from the "
                "god they were spoken for."
            ),
        },
    )
    acquire_clue(entry, clue)
    return True
