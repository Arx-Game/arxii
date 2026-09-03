"""Django system checks for evennia_extensions."""

import base64

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, register

from evennia_extensions.mfa_adapter import split_keys

# 32 zero bytes: the lowest-entropy string that still parses as a Fernet key, so it is
# what ends up pasted wherever a placeholder is wanted. Refused so it can never be deployed.
ALL_ZERO_KEY_BYTES = bytes(32)


@register()
def check_mfa_secrets_key(app_configs, **kwargs):  # noqa: ARG001
    """Every key in ``MFA_SECRETS_KEY`` must be a valid Fernet key (#3591, ADR-0267).

    Runs on ``migrate``/``check`` during the converge, before the release flips
    live, so a truncated or mis-pasted secret fails the deploy with a clear
    message instead of surfacing as a 500 on somebody's first 2FA sign-in.
    """
    keys = split_keys(settings.MFA_SECRETS_KEY)
    if not keys:
        return [
            Error(
                "MFA_SECRETS_KEY is empty. Generate a Fernet key and set it in the environment.",
                id="evennia_extensions.E001",
            )
        ]
    errors = []
    for position, key in enumerate(keys, start=1):
        try:
            Fernet(key.encode("ascii"))
        except (ValueError, TypeError):
            errors.append(
                Error(
                    f"MFA_SECRETS_KEY entry at position {position} is not a valid Fernet key "
                    "(expected 44 URL-safe base64 characters ending in '=').",
                    id="evennia_extensions.E001",
                )
            )
            continue
        if base64.urlsafe_b64decode(key.encode("ascii")) == ALL_ZERO_KEY_BYTES:
            errors.append(
                Error(
                    f"MFA_SECRETS_KEY entry at position {position} is the all-zero key. It is "
                    "a valid Fernet key shape but public, so anything encrypted under it is "
                    "plaintext in practice. Generate a real key.",
                    id="evennia_extensions.E001",
                )
            )
    return errors
