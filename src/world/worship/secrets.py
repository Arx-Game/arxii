"""Worship Secret minting (#2355) — mirrors ``mint_distinction_secret``."""

from typing import TYPE_CHECKING

from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret
from world.worship.constants import WORSHIP_SECRET_DEFAULT_LEVEL

if TYPE_CHECKING:
    from world.worship.models import WorshipDeclaration, WorshippedBeing


def worship_secret_content(being: "WorshippedBeing") -> str:
    """The words of the Secret a secret worship declaration mints (#2355, #5206: the
    character-creation waiting sheet lists it before it exists)."""
    return f"Secretly worships {being.name}"


def mint_worship_secret(declaration: "WorshipDeclaration") -> Secret:
    """Mint the Secret backing a secret worship declaration.

    Idempotent: an existing ``declaration.secret`` is returned untouched.
    GM_AUTHORED provenance matches the CG-curated mint path the
    secret-by-default distinctions use.
    """
    if declaration.secret_id is not None:
        return declaration.secret
    secret = Secret.objects.create(
        subject_sheet=declaration.character_sheet,
        level=WORSHIP_SECRET_DEFAULT_LEVEL,
        provenance=SecretProvenance.GM_AUTHORED,
        content=worship_secret_content(declaration.secret_being),
    )
    declaration.secret = secret
    declaration.save(update_fields=["secret"])
    return secret
